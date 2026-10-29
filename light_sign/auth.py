"""组织者管理端的登录口令：本机回环地址免登录，局域网访问需要口令。"""

import hmac
from ipaddress import ip_address
import os
from pathlib import Path
import re
import secrets

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
PASSWORD_FILE = "PASSWORD.conf"
SESSION_KEY = "organizer_authenticated"
MIN_PASSWORD_LENGTH = 8
_PASSWORD_LINE = re.compile(r"^\s*(?:password|口令)\s*[=＝:：]\s*(.*)$", re.IGNORECASE)


def password_path(root=ROOT):
    return Path(root) / PASSWORD_FILE


def read_password(path):
    """读取口令文件；支持 `password = 值`、`口令: 值` 或直接写一行的纯文本。"""
    try:
        text = Path(path).read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError):
        return None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith(("#", ";")):
            continue
        match = _PASSWORD_LINE.match(line)
        value = match.group(1) if match else line
        return value.strip().strip("\"'").strip() or None
    return None


def _write_password(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        "# LightSign 组织者登录口令（局域网访问时使用；修改后重启服务生效）\n"
        f"password = {value}\n",
        encoding="utf-8",
    )
    try:
        temporary.chmod(0o600)
    except OSError:
        pass
    os.replace(temporary, path)


def ensure_password(path):
    """返回 (口令, 是否新建)。文件缺失时生成随机口令；文件存在但读不出时拒绝启动。"""
    password = read_password(path)
    if password is not None:
        if len(password) < MIN_PASSWORD_LENGTH:
            raise ValueError(f"{Path(path).name} 中的口令至少需要 {MIN_PASSWORD_LENGTH} 个字符")
        return password, False
    if Path(path).exists():
        raise ValueError(f"{Path(path).name} 中没有可用口令，请写入 password = 你的口令")
    password = secrets.token_urlsafe(9)
    _write_password(Path(path), password)
    return password, True


def client_is_loopback():
    """Streamlit 对本机连接返回 None，其余情况返回 TCP 对端地址；地址未知时要求登录。"""
    try:
        value = st.context.ip_address
    except Exception:
        return False
    if value is None:
        return True
    if not isinstance(value, str):
        return False
    try:
        return ip_address(value).is_loopback
    except ValueError:
        return False


def require_login(session_key=SESSION_KEY):
    """登录通过或本机访问时返回，否则渲染登录页并停止当前脚本。"""
    if st.session_state.get(session_key):
        return
    if client_is_loopback():
        st.session_state[session_key] = True
        return
    path = password_path()
    password = read_password(path)
    st.title("轻签 · 组织者登录")
    if not password:
        st.error(f"未找到组织者登录口令。请先运行 run.py，或在项目根目录 {path.name} 中写入 password = 你的口令。")
        st.stop()
    st.caption("组织者管理端已在局域网开放，请输入项目根目录 PASSWORD.conf 中的登录口令。")
    with st.form("organizer_login"):
        value = st.text_input("登录口令", type="password")
        submitted = st.form_submit_button("进入管理端", type="primary")
    if submitted:
        if hmac.compare_digest(value.encode("utf-8"), password.encode("utf-8")):
            st.session_state[session_key] = True
            st.rerun()
        st.error("口令不正确，请重新输入。")
    st.stop()
