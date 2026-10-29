#!/usr/bin/env python3
"""同时启动组织者与参与者入口，退出时回收两个服务进程。"""

import argparse
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.parse import urlsplit

import click

from light_sign import store
from light_sign.auth import ensure_password, password_path
from light_sign.network import participant_base_url

ROOT = Path(__file__).resolve().parent

# 浏览器会把空闲的 HTTP 连接留在连接池里复用，而 uvicorn 默认 5 秒就关闭空闲连接。
# 生成二维码后隔几秒再点“下载二维码 PNG”（或导出 CSV / JSON）时，浏览器一旦复用了
# 刚被服务端关闭的连接，请求就会在收到响应前失败，浏览器把下载标记为网络错误。
# 本机与局域网场景的连接数很少，因此把空闲超时放宽到 1 小时。
KEEP_ALIVE_SECONDS = 3600

PASSWORD_HINT = "登录口令位于PASSWORD.conf（局域网访问需输入，本机 localhost 免登录）"


def extend_keep_alive():
    """在创建服务器之前把 uvicorn 的空闲连接超时改成 KEEP_ALIVE_SECONDS。"""
    from streamlit.web.server.starlette import starlette_server

    build_kwargs = starlette_server._get_uvicorn_config_kwargs

    def build_kwargs_with_keep_alive():
        kwargs = build_kwargs()
        kwargs["timeout_keep_alive"] = KEEP_ALIVE_SECONDS
        return kwargs

    starlette_server._get_uvicorn_config_kwargs = build_kwargs_with_keep_alive


def serve(script, streamlit_arguments):
    """子进程入口：放宽 keep-alive 后按 Streamlit CLI 的参数启动脚本。"""
    extend_keep_alive()
    from streamlit.web import cli

    sys.argv = [sys.argv[0], "run", script, *streamlit_arguments]
    return cli.main()


def log(message="", color=None, bold=False, err=False):
    """终端支持时启用颜色，重定向或设置 NO_COLOR 时保留纯文本。"""
    click.echo(click.style(message, fg=color, bold=bold), err=err,
               color=False if "NO_COLOR" in os.environ else None)


def entry_url(scheme, host, port):
    """按浏览器地址栏的写法拼出入口地址，IPv6 字面量加方括号。"""
    if ":" in host:
        host = f"[{host}]"
    return f"{scheme}://{host}:{port}/"


def print_startup(args, scheme, participant_url, certificates):
    log()
    log("  LightSign · 轻签系统", "cyan", bold=True)
    log("  正在启动组织者与参与者服务…", "bright_black")
    log("  " + "─" * 60, "bright_black")
    log()
    log("  组织者入口  ·  活动管理 / 二维码 / 人数清点", "cyan", bold=True)
    # 局域网地址与签到入口使用同一个 IP，保证两种入口在手机/投屏电脑上一致。
    lan_host = urlsplit(participant_url).hostname if participant_url else None
    if lan_host in ("localhost", "127.0.0.1", "::1"):
        lan_host = None
    if args.organizer_host in ("127.0.0.1", "localhost", "::1"):
        log(f"  {entry_url(scheme, 'localhost', args.organizer_port)}", "cyan", bold=True)
        log("  访问范围：仅本机", "bright_black")
    elif args.organizer_host in ("0.0.0.0", "::", ""):
        log(f"  本机地址    {entry_url(scheme, 'localhost', args.organizer_port)}", "cyan", bold=True)
        if lan_host:
            log(f"  局域网地址  {entry_url(scheme, lan_host, args.organizer_port)}", "cyan", bold=True)
            log("  同一 Wi-Fi 内的电脑或手机也能打开，IP 与签到入口相同。", "bright_black")
            log("  组织者入口含管理操作，请在活动结束或离开可信网络后按 Ctrl+C 停止。", "bright_black")
            log(f"  {PASSWORD_HINT}", "white")
        else:
            log("  未检测到局域网地址，当前仅本机可访问。", "yellow")
    else:
        log(f"  {entry_url(scheme, args.organizer_host, args.organizer_port)}", "cyan", bold=True)
        log("  访问范围：由 --organizer-host 指定的监听地址决定", "bright_black")
        log(f"  {PASSWORD_HINT}", "white")
    log()
    log("  参与者入口  ·  手机扫码签到", "green", bold=True)
    if participant_url:
        log(f"  {participant_url}", "green", bold=True)
        log("  手机与电脑连接同一 Wi-Fi 后，扫描活动二维码签到。", "bright_black")
    else:
        log("  暂无可分享地址，请检查局域网或设置 --participant-url。", "yellow")
    log()
    if certificates:
        log("  HTTPS 提示：使用本机自签名证书，首次访问会有浏览器安全提示。", "yellow")
        log("  系统不会自动安装证书信任或绕过浏览器检查。", "bright_black")
    else:
        log("  HTTP 模式：手机可通过活动链接或上传二维码图片签到。", "yellow")
    log("  按 Ctrl+C 同时停止两个服务。", bold=True)
    log()
    log("  " + "─" * 60, "bright_black")
    log()


def port_number(value):
    port = int(value)
    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError("端口必须在 1 到 65535 之间")
    return port


def certificate_files(http=False, hosts=()):
    if http:
        return None
    from light_sign.certificates import certificate_paths, ensure_certificate
    cert, key = certificate_paths(ROOT)
    if ensure_certificate(cert, key, hosts):
        log("[证书] 已生成或更新本机 HTTPS 自签名证书。", "green")
    return cert, key


def server_command(app, host, port, certificates):
    # 用本脚本作为子进程入口，好在 Streamlit 创建服务器前调整 keep-alive。
    return [
        sys.executable, str(ROOT / "run.py"), "--serve", str(ROOT / app),
        "--server.address", host, "--server.port", str(port),
        "--server.headless", "true",
        # 保留警告和错误，省略与统一启动面板重复的底层启动日志。
        "--logger.level", "warning",
        # --http 显式覆盖配置中的证书路径。
        "--server.sslCertFile", str(certificates[0]) if certificates else "",
        "--server.sslKeyFile", str(certificates[1]) if certificates else "",
    ]


def stop_servers(processes):
    for process in processes:
        if process.poll() is None:
            process.terminate()
    for process in processes:
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["--serve"]:
        return serve(argv[1], argv[2:])
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--organizer-port", type=port_number, default=8503)
    parser.add_argument("--participant-port", type=port_number, default=8504)
    parser.add_argument("--organizer-host", default="0.0.0.0", help="组织者默认允许局域网访问，与本机 localhost 同时可用")
    parser.add_argument("--participant-host", default="0.0.0.0", help="参与者默认允许局域网访问")
    parser.add_argument("--participant-url", help="二维码中的参与者入口，例如 https://192.168.1.10:8504/")
    parser.add_argument("--http", action="store_true", help="使用 HTTP，局域网手机摄像头需要 HTTPS")
    args = parser.parse_args(argv)
    if args.organizer_port == args.participant_port:
        parser.error("组织者和参与者必须使用不同端口")

    scheme = "http" if args.http else "https"
    env = os.environ.copy()
    env["STREAMLIT_LOGGER_HIDE_WELCOME_MESSAGE"] = "true"
    env["LIGHTSIGN_PARTICIPANT_PORT"] = str(args.participant_port)
    env["LIGHTSIGN_PARTICIPANT_HOST"] = args.participant_host
    env["LIGHTSIGN_PARTICIPANT_SCHEME"] = scheme
    if args.participant_url:
        from light_sign.links import participant_link
        try:
            participant_link(args.participant_url, "validate-address")
        except ValueError as error:
            parser.error(str(error))
        env["LIGHTSIGN_PARTICIPANT_URL"] = args.participant_url

    try:
        participant_url = participant_base_url(
            scheme, args.participant_port, args.participant_host,
            override=env.get("LIGHTSIGN_PARTICIPANT_URL"),
        )
    except ValueError as error:
        participant_url = None
        log(f"[网络] {error}", "yellow", err=True)
    if participant_url:
        # 本次运行固定分享地址，使二维码与启动时生成的证书地址一致。
        env["LIGHTSIGN_PARTICIPANT_URL"] = participant_url

    processes = []
    try:
        # 启动前检查两个端口，避免只启动一半，也不影响其他已有服务。
        for host, port in [(args.organizer_host, args.organizer_port),
                           (args.participant_host, args.participant_port)]:
            with socket.socket() as probe:
                probe.bind((host, port))
        hosts = [args.organizer_host, args.participant_host]
        if participant_url:
            hosts.append(urlsplit(participant_url).hostname)
        certificates = certificate_files(args.http, hosts)
        _, password_created = ensure_password(password_path(ROOT))
        if password_created:
            log("[口令] 未找到 PASSWORD.conf，已生成随机登录口令；局域网登录前请打开该文件查看或修改。", "green")
        connection = store.connect()
        connection.close()
        store.key()
        print_startup(args, scheme, participant_url, certificates)
        for app, host, port in [("app.py", args.organizer_host, args.organizer_port),
                                ("participant.py", args.participant_host, args.participant_port)]:
            processes.append(subprocess.Popen(server_command(app, host, port, certificates), cwd=ROOT, env=env))
        while True:
            for process in processes:
                if process.poll() is not None:
                    log("[停止] 一个入口服务已退出，正在停止另一个入口。", "red", err=True)
                    return process.returncode or 1
            time.sleep(0.3)
    except KeyboardInterrupt:
        log("\n[停止] 正在停止两个入口…", "yellow")
        return 0
    except (OSError, ValueError, ImportError) as error:
        log(f"[错误] 启动失败：{error}", "red", bold=True, err=True)
        return 1
    finally:
        stop_servers(processes)


if __name__ == "__main__":
    sys.exit(main())
