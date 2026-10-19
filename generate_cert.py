#!/usr/bin/env python3
"""手动检查或更新 HTTPS 自签名证书，无需安装 OpenSSL 命令行工具。"""

import argparse
from pathlib import Path
import sys
from urllib.parse import urlsplit

from light_sign.certificates import certificate_paths, ensure_certificate
from light_sign.network import participant_base_url

ROOT = Path(__file__).resolve().parent


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", action="append", default=[], help="额外的访问 IP 或域名，可重复指定")
    parser.add_argument("--force", action="store_true", help="强制重新生成证书和私钥")
    args = parser.parse_args(argv)
    hosts = list(args.host)
    try:
        hosts.append(urlsplit(participant_base_url()).hostname)
    except ValueError as error:
        print(f"{error} 仍可生成本机访问证书。", file=sys.stderr)
    try:
        cert, key = certificate_paths(ROOT)
        changed = ensure_certificate(cert, key, hosts, force=args.force)
        print("已生成或更新证书。" if changed else "现有证书有效，无需更新。")
        print(f"证书文件：{cert}\n私钥文件：{key}")
        print("服务启动后使用 HTTPS；已运行的服务需要重启。浏览器保留默认的自签名证书警告。")
        return 0
    except (OSError, ValueError) as error:
        print(f"证书生成失败：{error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
