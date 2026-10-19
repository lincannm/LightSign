"""参与者链接与二维码内容解析。"""

from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit


def participant_link(base_url, token):
    parts = urlsplit(base_url.strip())
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        raise ValueError("参与者地址须为完整的 HTTP 或 HTTPS 地址")
    if parts.username or parts.password or parts.query or parts.fragment:
        raise ValueError("参与者地址不能包含账号、查询参数或片段")
    return urlunsplit((parts.scheme, parts.netloc, parts.path or "/", urlencode({"token": token}), ""))


def extract_token(value):
    value = value.strip()
    if value.startswith(("https://", "http://")):
        tokens = parse_qs(urlsplit(value).query).get("token", [])
        return tokens[0] if len(tokens) == 1 else ""
    return value
