#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""就地修复被整体复制/移动过的 .venv（Windows）。

为什么需要
----------
venv 不是可移植目录：把它复制或移动到新位置后，有三处路径会失效。

1. ``Scripts/*.exe`` 是 pip 生成入口点时写出的启动器，启动器把创建时的
   解释器绝对路径以 ``#!<路径>`` + 换行的形式嵌进了二进制里。旧路径一旦
   不存在，运行 streamlit / pip / uvicorn 等任何入口点都会报::

       Fatal error in launcher: Unable to create process using
       '"C:\\Users\\...\\Desktop\\LightSign\\.venv\\Scripts\\python.exe" ...'

2. ``Scripts/activate``、``activate.bat``、``activate.fish`` 里写死了
   ``VIRTUAL_ENV=<旧路径>``。

3. ``pyvenv.cfg`` 的 ``command`` 行留的是旧路径（仅作记录，不影响运行）。

本脚本离线就地修复这三处，不触碰 site-packages 里任何已安装的包。
启动器的重建直接复用 pip 自己的生成代码（``PipScriptMaker``），因此产物与
在同一位置重新 ``pip install`` 出来的完全一致。

用法
----
在项目根目录执行::

    .venv\\Scripts\\python.exe scripts\\fix_venv.py            # 修复
    .venv\\Scripts\\python.exe scripts\\fix_venv.py --dry-run   # 只报告会改什么

``Scripts\\python.exe`` 在目录被复制后仍然可用（它按相对位置读取
``pyvenv.cfg``），所以可以直接用它来运行本脚本。
"""

from __future__ import annotations

import argparse
import configparser
import re
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_VENV = HERE.parent / ".venv"

# 启动器尾部形如 b'#!C:\\...\\python.exe\\n'，后面紧跟 zip 载荷。
# 启动器桩自身含 UTF-16LE 的 "#!  PATHEXT"，不会被这个 ASCII 模式命中。
SHEBANG_RE = re.compile(rb"#!([A-Za-z]:[^\r\n\x00]*)\r?\n")

# 覆盖激活脚本里所有给 VIRTUAL_ENV 赋绝对路径的写法：
#   bash/zsh : VIRTUAL_ENV=$(cygpath 'C:\...\.venv')  /  export VIRTUAL_ENV='C:\...'
#   fish     : set -gx VIRTUAL_ENV 'C:\...\.venv'
#   cmd      : set "VIRTUAL_ENV=C:\...\.venv"
#   PS       : $VIRTUAL_ENV = 'C:\...\.venv'
VIRTUAL_ENV_RE = re.compile(
    r"(?P<prefix>VIRTUAL_ENV(?:\s*=\s*|\s+)(?:\$\(cygpath\s+)?)"
    r"(?P<quote>['\"]?)(?P<path>[A-Za-z]:\\[^'\"\r\n]*)(?P=quote)"
)

ACTIVATION_SCRIPTS = (
    "activate",
    "activate.bat",
    "activate.fish",
    "Activate.ps1",
    "deactivate.bat",
)

# 这两个是解释器本身，不是 pip 生成的入口点启动器，必须原样保留。
KEEP_EXES = {"python.exe", "pythonw.exe"}


def read_shebang(exe: Path) -> str | None:
    """从启动器二进制里取出嵌入的解释器路径；取不到返回 None。"""
    match = SHEBANG_RE.search(exe.read_bytes())
    if not match:
        return None
    return match.group(1).decode("utf-8", "replace").strip('"')


def collect_entry_points(site_packages: Path):
    """收集所有已安装发行版声明的控制台/GUI 入口点。

    这正是 pip 安装 wheel 时读取的同一份元数据（``entry_points.txt``）。
    """
    console: dict[str, str] = {}
    gui: dict[str, str] = {}
    origin: dict[str, str] = {}
    conflicts: list[str] = []

    for ep_file in sorted(site_packages.glob("*.dist-info/entry_points.txt")):
        parser = configparser.ConfigParser(delimiters=("=",))
        parser.optionxform = str  # 入口点名字大小写敏感，不要小写化
        try:
            parser.read(ep_file, encoding="utf-8")
        except (configparser.Error, OSError, UnicodeDecodeError) as exc:
            print(f"  ! 跳过无法解析的 {ep_file.parent.name}: {exc}")
            continue

        dist = ep_file.parent.name
        for section, bucket in (("console_scripts", console), ("gui_scripts", gui)):
            if not parser.has_section(section):
                continue
            for name, value in parser.items(section):
                name = name.strip()
                value = " ".join(value.split())
                if not name or not value:
                    continue
                if name in bucket:
                    conflicts.append(f"{name}（{origin[name]} 与 {dist}）")
                    continue
                bucket[name] = value
                origin[name] = dist

    return console, gui, conflicts


def build_script_specs(console: dict[str, str], gui: dict[str, str]):
    """把入口点字典转成 distlib 的 spec 字符串。

    ``get_console_script_specs`` 会补出 pip 自己的 ``pipX`` / ``pipX.Y``
    版本化入口点（本机即 ``pip3.14``），所以生成的 .exe 名字要以它为准。
    """
    from pip._internal.operations.install.wheel import get_console_script_specs

    console_specs = get_console_script_specs(dict(console))
    gui_specs = [f"{name} = {value}" for name, value in gui.items()]
    return console_specs, gui_specs


def spec_name(spec: str) -> str:
    """从 'name = module:attrs' 里取出入口点名字。"""
    return spec.split("=", 1)[0].strip()


def regenerate_launchers(
    scripts_dir: Path,
    py_exe: Path,
    console_specs: list[str],
    gui_specs: list[str],
    dry_run: bool,
) -> list[str]:
    """用 pip 自己的生成器重建 ``Scripts/*.exe``，返回生成的文件名。"""
    from pip._internal.operations.install.wheel import PipScriptMaker
    from pip._vendor.distlib.scripts import enquote_executable

    # PipScriptMaker 是 distlib.ScriptMaker 的子类，只把脚本模板换成了 pip 版本。
    maker = PipScriptMaker(None, str(scripts_dir))
    maker.clobber = True          # 覆盖旧启动器（pip 装 wheel 时也是这么设的）
    maker.variants = {""}         # 不生成 streamlit3 / streamlit-1.65 之类变体
    maker.set_mode = True
    # 显式指定 shebang，并按 pip 的方式处理含空格的路径（加引号）。
    maker.executable = enquote_executable(str(py_exe))
    maker.dry_run = dry_run

    filenames = maker.make_multiple(console_specs)
    filenames += maker.make_multiple(gui_specs, {"gui": True})
    return filenames


def repair_activation_scripts(scripts_dir: Path, venv_dir: Path, dry_run: bool) -> list[str]:
    """把激活脚本里写死的 VIRTUAL_ENV 旧路径改成当前 venv 路径。"""
    changes: list[str] = []
    new_dir = str(venv_dir)

    for filename in ACTIVATION_SCRIPTS:
        path = scripts_dir / filename
        if not path.is_file():
            continue
        try:
            # newline="" 保留原有行尾，避免把 activate.bat 的 CRLF 变成 LF
            with path.open("r", encoding="utf-8", newline="") as handle:
                text = handle.read()
        except (OSError, UnicodeDecodeError):
            continue

        hits: list[str] = []

        def _sub(match: re.Match[str]) -> str:
            old = match.group("path")
            # 只替换指向某个 .venv 目录、且确实不等于当前路径的赋值，
            # 避免误伤无关的绝对路径。
            if old == new_dir or not old.replace("/", "\\").rstrip("\\").lower().endswith(".venv"):
                return match.group(0)
            hits.append(old)
            return f"{match.group('prefix')}{match.group('quote')}{new_dir}{match.group('quote')}"

        new_text = VIRTUAL_ENV_RE.sub(_sub, text)
        if not hits:
            continue

        changes.append(f"{filename}: {len(hits)} 处 VIRTUAL_ENV  {hits[0]} -> {new_dir}")
        if not dry_run:
            with path.open("w", encoding="utf-8", newline="") as handle:
                handle.write(new_text)

    return changes


def repair_pyvenv_cfg(cfg: Path, old_dir: str | None, venv_dir: Path, base_python: str) -> str | None:
    """更新 pyvenv.cfg 的 command 行，让它记录当前位置。"""
    if not cfg.is_file():
        return None
    with cfg.open("r", encoding="utf-8", newline="") as handle:
        text = handle.read()
    new_dir = str(venv_dir)

    def _sub(match: re.Match[str]) -> str:
        return f"{match.group(1)}{new_dir}"

    if old_dir and old_dir != new_dir and old_dir in text:
        new_text = text.replace(old_dir, new_dir)
    else:
        new_text, count = re.subn(
            r"(?m)^(command\s*=\s*.*?-m\s+venv\s+).*$", _sub, text, count=1
        )
        if count == 0:
            new_text = text.rstrip("\n") + f"\ncommand = {base_python} -m venv {new_dir}\n"

    if new_text == text:
        return None
    with cfg.open("w", encoding="utf-8", newline="") as handle:
        handle.write(new_text)
    return f"command 行已更新为: {new_dir}"


def main() -> int:
    # 输出走管道时 Windows 会退回 GBK，中文会乱码；统一成 UTF-8。
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            pass

    parser = argparse.ArgumentParser(
        description="修复被复制/移动过的 Windows venv 里失效的启动器路径。"
    )
    parser.add_argument(
        "--venv", type=Path, default=DEFAULT_VENV, help=f"venv 目录（默认 {DEFAULT_VENV}）"
    )
    parser.add_argument("--dry-run", action="store_true", help="只显示将要做的改动，不写盘")
    args = parser.parse_args()

    venv_dir = args.venv.resolve()
    scripts_dir = venv_dir / "Scripts"
    site_packages = venv_dir / "Lib" / "site-packages"
    py_exe = scripts_dir / "python.exe"
    cfg = venv_dir / "pyvenv.cfg"

    missing = [p for p in (venv_dir, scripts_dir, site_packages, py_exe) if not p.exists()]
    if missing:
        print("找不到 venv 的必要组成:")
        for path in missing:
            print(f"  - {path}")
        return 2

    # 启动器的位数取自运行它的解释器，因此必须用 venv 自己的解释器来跑。
    if Path(sys.prefix).resolve() != venv_dir:
        print("请用该 venv 自己的解释器运行本脚本：")
        print(f'    "{py_exe}" "{Path(__file__).resolve()}"')
        print(f"（当前解释器 sys.executable={sys.executable}，sys.prefix={sys.prefix}）")
        return 2

    base_home = ""
    if cfg.is_file():
        match = re.search(r"(?m)^home\s*=\s*(.+?)\s*$", cfg.read_text(encoding="utf-8"))
        if match:
            base_home = match.group(1)

    old_dir = None
    if cfg.is_file():
        match = re.search(
            r"(?m)^command\s*=\s*(.+?)\s*$", cfg.read_text(encoding="utf-8")
        )
        if match:
            tokens = match.group(1).split()
            if tokens and ":" in tokens[-1]:
                old_dir = tokens[-1]

    print("== 环境 ==")
    print(f"venv       : {venv_dir}")
    print(f"解释器      : {py_exe}  ({struct.calcsize('P') * 8} 位, Python {sys.version.split()[0]})")
    print(f"基础 Python : {base_home or '(pyvenv.cfg 未记录)'}")
    print(f"记录中的旧位置: {old_dir or '(无)'}")
    if args.dry_run:
        print("模式       : 预演（不会写盘）")
    print()

    # ---- 1/3 控制台脚本启动器 ----------------------------------------------
    console, gui, conflicts = collect_entry_points(site_packages)
    console_specs, gui_specs = build_script_specs(console, gui)
    print(
        f"== 1/3 入口点启动器（{len(console_specs)} 个控制台 + {len(gui_specs)} 个 GUI）=="
    )
    for name in conflicts:
        print(f"  ! 入口点重名，已取先出现的定义: {name}")

    expected_exes = {spec_name(spec) for spec in console_specs + gui_specs}
    for exe_name in sorted(expected_exes):
        exe = scripts_dir / f"{exe_name}.exe"
        current = read_shebang(exe) if exe.is_file() else None
        if current is None:
            state = "缺失，将新建"
        elif Path(current) == py_exe:
            state = "已正确"
        else:
            state = f"失效 -> {current}"
        print(f"  {exe_name + '.exe':<20} {state}")

    generated = regenerate_launchers(
        scripts_dir, py_exe, console_specs, gui_specs, args.dry_run
    )
    verb = "将重建" if args.dry_run else "已重建"
    print(f"  {verb} {len(generated)} 个启动器")

    orphans = sorted(
        p.name
        for p in scripts_dir.glob("*.exe")
        if p.name not in KEEP_EXES and p.stem not in expected_exes
    )
    for name in orphans:
        print(f"  ! {name} 不对应任何已安装的入口点，保留原样（如需清理请手动删除）")
    print()

    # ---- 2/3 激活脚本 ------------------------------------------------------
    print("== 2/3 激活脚本 ==")
    activation_changes = repair_activation_scripts(scripts_dir, venv_dir, args.dry_run)
    if activation_changes:
        for line in activation_changes:
            print(f"  {line}")
    else:
        print("  无需改动")
    print()

    # ---- 3/3 pyvenv.cfg ----------------------------------------------------
    print("== 3/3 pyvenv.cfg ==")
    if args.dry_run:
        print("  预演模式，跳过")
    else:
        cfg_change = repair_pyvenv_cfg(cfg, old_dir, venv_dir, base_home or sys.base_prefix)
        print(f"  {cfg_change}" if cfg_change else "  无需改动")
    print()

    # ---- 校验 --------------------------------------------------------------
    if args.dry_run:
        print("预演结束。去掉 --dry-run 即可实际修复。")
        return 0

    print("== 校验 ==")
    bad = []
    for exe_name in sorted(expected_exes):
        exe = scripts_dir / f"{exe_name}.exe"
        current = read_shebang(exe) if exe.is_file() else None
        if current is None or Path(current) != py_exe:
            bad.append(f"{exe_name}.exe -> {current}")

    for filename in ACTIVATION_SCRIPTS:
        path = scripts_dir / filename
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for match in VIRTUAL_ENV_RE.finditer(text):
            found = match.group("path")
            if found != str(venv_dir) and found.rstrip("\\").lower().endswith(".venv"):
                bad.append(f"{filename} -> {found}")

    if bad:
        print("  以下项目仍未指向当前 venv:")
        for line in bad:
            print(f"    - {line}")
        print("  修复未完成。")
        return 1

    print(f"  全部 {len(expected_exes)} 个启动器与激活脚本均指向 {venv_dir}")
    print()
    print("完成。现在可以运行：")
    print(f'  "{py_exe}" -m streamlit run app.py --server.port 8503 --server.address 127.0.0.1')
    print("或先激活：")
    print(f'  {venv_dir}\\Scripts\\Activate.ps1')
    print("  streamlit run app.py --server.port 8503 --server.address 127.0.0.1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
