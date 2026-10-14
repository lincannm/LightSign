#!/usr/bin/env python3
"""生成自签名 SSL 证书用于 HTTPS 访问

使用方法:
    python generate_cert.py
"""
import subprocess
import sys
from pathlib import Path


def main():
    """生成自签名证书"""
    certs_dir = Path(__file__).parent / "certs"
    certs_dir.mkdir(exist_ok=True)

    cert_file = certs_dir / "cert.pem"
    key_file = certs_dir / "key.pem"
    config_file = certs_dir / "openssl.cnf"

    # 检查是否已存在证书
    if cert_file.exists() and key_file.exists():
        response = input("证书已存在,是否重新生成? (y/N): ").strip().lower()
        if response != 'y':
            print("已取消")
            return

    print("正在生成自签名 SSL 证书...")

    # 检查 OpenSSL 是否可用
    try:
        result = subprocess.run(
            ["openssl", "version"],
            capture_output=True,
            text=True,
            check=True
        )
        print(f"✓ 检测到 {result.stdout.strip()}")
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("错误: 未找到 OpenSSL,请先安装", file=sys.stderr)
        sys.exit(1)

    # 如果配置文件不存在,创建它
    if not config_file.exists():
        config_content = """[req]
default_bits = 4096
prompt = no
default_md = sha256
distinguished_name = dn
x509_extensions = v3_ca

[dn]
C=CN
ST=Local
L=Local
O=LightSign
OU=Development
CN=localhost

[v3_ca]
subjectAltName = @alt_names
basicConstraints = CA:FALSE
keyUsage = digitalSignature, keyEncipherment
extendedKeyUsage = serverAuth

[alt_names]
DNS.1 = localhost
DNS.2 = 127.0.0.1
IP.1 = 127.0.0.1
IP.2 = 0.0.0.0
"""
        config_file.write_text(config_content, encoding='utf-8')
        print(f"✓ 已创建配置文件: {config_file}")

    # 生成证书
    cmd = [
        "openssl", "req", "-x509",
        "-newkey", "rsa:4096",
        "-keyout", str(key_file),
        "-out", str(cert_file),
        "-days", "365",
        "-nodes",
        "-config", str(config_file)
    ]

    try:
        subprocess.run(cmd, check=True, capture_output=True)
        print(f"✓ 证书生成成功")
        print(f"  证书文件: {cert_file}")
        print(f"  私钥文件: {key_file}")
        print()
        print("证书有效期: 365 天")
        print()
        print("下次启动应用时将自动使用 HTTPS")
        print("访问地址: https://localhost:8503")
    except subprocess.CalledProcessError as e:
        print(f"错误: 证书生成失败", file=sys.stderr)
        if e.stderr:
            print(e.stderr.decode('utf-8', errors='ignore'), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
