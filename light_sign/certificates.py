"""在本机生成和复用 HTTPS 自签名证书，不修改系统或浏览器信任。"""

from datetime import datetime, timedelta, timezone
from ipaddress import ip_address
import os
from pathlib import Path
import ssl
import tempfile
import tomllib

from cryptography import x509
from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID


def certificate_paths(root):
    config_file = Path(root) / ".streamlit/config.toml"
    config = tomllib.loads(config_file.read_text(encoding="utf-8")) if config_file.exists() else {}
    server = config.get("server", {})
    cert = server.get("sslCertFile", "certs/cert.pem")
    key = server.get("sslKeyFile", "certs/key.pem")
    if not cert or not key:
        raise ValueError("HTTPS 证书与私钥路径不能为空；使用 HTTP 请指定 --http")
    paths = Path(root) / cert, Path(root) / key
    if paths[0].resolve() == paths[1].resolve():
        raise ValueError("HTTPS 证书与私钥必须使用不同文件")
    return paths


def subject_names(hosts=()):
    names = {x509.DNSName("localhost"), x509.IPAddress(ip_address("127.0.0.1")),
             x509.IPAddress(ip_address("::1"))}
    for host in hosts:
        if not host:
            continue
        try:
            address = ip_address(host)
        except ValueError:
            names.add(x509.DNSName(host.encode("idna").decode("ascii").lower()))
        else:
            # 监听所有网卡的地址不是浏览器访问地址，不能充当 SAN 通配符。
            if not address.is_unspecified:
                names.add(x509.IPAddress(address))
    return sorted(names, key=lambda name: str(name.value))


def certificate_is_usable(cert_path, key_path, names, now):
    try:
        cert = x509.load_pem_x509_certificate(cert_path.read_bytes())
        if cert.not_valid_before_utc > now or cert.not_valid_after_utc <= now + timedelta(days=30):
            return False
        sans = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        if not set(names).issubset(set(sans)):
            return False
        # 由实际 TLS 实现检查 PEM 格式、密钥配对及算法是否可用。
        ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER).load_cert_chain(
            cert_path, key_path, password=lambda: b"",
        )
        return True
    except (OSError, ValueError, UnsupportedAlgorithm, x509.ExtensionNotFound):
        return False


def _write_private_file(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".lightsign-", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(content)
        temporary.chmod(0o600)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def ensure_certificate(cert_path, key_path, hosts=(), *, force=False, now=None):
    """有效证书保持不变；缺失、临近过期、地址变化或密钥不匹配时重建。"""
    cert_path, key_path = Path(cert_path), Path(key_path)
    if cert_path.resolve() == key_path.resolve():
        raise ValueError("HTTPS 证书与私钥必须使用不同文件")
    now = now or datetime.now(timezone.utc)
    names = subject_names(hosts)
    if not force and certificate_is_usable(cert_path, key_path, names, now):
        return False

    key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    subject = x509.Name([
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "LightSign"),
        x509.NameAttribute(NameOID.COMMON_NAME, "localhost"),
    ])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=365))
        .add_extension(x509.SubjectAlternativeName(names), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .sign(key, hashes.SHA256())
    )
    _write_private_file(key_path, key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption(),
    ))
    _write_private_file(cert_path, cert.public_bytes(serialization.Encoding.PEM))
    return True
