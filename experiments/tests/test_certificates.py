"""检查实际证书内容、TLS加载、复用及更新条件。"""

from datetime import datetime, timedelta, timezone
from ipaddress import ip_address
from pathlib import Path
import contextlib
import io
import ssl
import tempfile
import unittest
from unittest.mock import patch

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from light_sign.certificates import ensure_certificate
import generate_cert


class CertificateTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.cert = Path(self.directory.name) / "nested/cert.pem"
        self.key = self.cert.with_name("key.pem")
        self.now = datetime.now(timezone.utc)

    def load_cert(self):
        return x509.load_pem_x509_certificate(self.cert.read_bytes())

    def test_certificate_contains_access_names_and_loads_in_tls(self):
        ensure_certificate(self.cert, self.key, ["192.168.1.42", "0.0.0.0", "::", "demo.local"], now=self.now)
        cert = self.load_cert()
        sans = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        self.assertIn("localhost", sans.get_values_for_type(x509.DNSName))
        self.assertIn("demo.local", sans.get_values_for_type(x509.DNSName))
        addresses = sans.get_values_for_type(x509.IPAddress)
        for host in ["127.0.0.1", "::1", "192.168.1.42"]:
            self.assertIn(ip_address(host), addresses)
        self.assertNotIn(ip_address("0.0.0.0"), addresses)
        self.assertNotIn(ip_address("::"), addresses)
        self.assertFalse(cert.extensions.get_extension_for_class(x509.BasicConstraints).value.ca)
        self.assertEqual(cert.subject, cert.issuer)
        cert.verify_directly_issued_by(cert)
        self.assertEqual(cert.public_key().key_size, 3072)
        ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER).load_cert_chain(self.cert, self.key)

    def test_reuse_then_renew_for_new_address(self):
        self.assertTrue(ensure_certificate(self.cert, self.key, ["192.168.1.42"], now=self.now))
        original = self.cert.read_bytes(), self.key.read_bytes()
        self.assertFalse(ensure_certificate(self.cert, self.key, ["192.168.1.42"], now=self.now))
        self.assertEqual((self.cert.read_bytes(), self.key.read_bytes()), original)
        self.assertTrue(ensure_certificate(self.cert, self.key, ["192.168.1.43"], now=self.now))
        self.assertIn(ip_address("192.168.1.43"), self.load_cert().extensions.get_extension_for_class(
            x509.SubjectAlternativeName).value.get_values_for_type(x509.IPAddress))

    def test_renew_before_expiry_and_after_expiry_or_clock_change(self):
        ensure_certificate(self.cert, self.key, now=self.now)
        self.assertTrue(ensure_certificate(self.cert, self.key, now=self.now + timedelta(days=340)))
        self.assertTrue(ensure_certificate(self.cert, self.key, now=self.now + timedelta(days=710)))
        self.assertTrue(ensure_certificate(self.cert, self.key, now=self.now))

    def test_repair_mismatched_corrupt_and_missing_key(self):
        ensure_certificate(self.cert, self.key)
        other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.key.write_bytes(other_key.private_bytes(serialization.Encoding.PEM,
                            serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        self.assertTrue(ensure_certificate(self.cert, self.key))
        self.key.write_bytes(b"invalid key")
        self.assertTrue(ensure_certificate(self.cert, self.key))
        self.key.unlink()
        self.assertTrue(ensure_certificate(self.cert, self.key))
        self.cert.write_bytes(b"invalid certificate")
        self.assertTrue(ensure_certificate(self.cert, self.key))

    def test_force_and_reject_identical_paths(self):
        ensure_certificate(self.cert, self.key)
        original = self.cert.read_bytes()
        self.assertTrue(ensure_certificate(self.cert, self.key, force=True))
        self.assertNotEqual(self.cert.read_bytes(), original)
        with self.assertRaises(ValueError):
            ensure_certificate(self.cert, self.cert)

    def test_manual_command_handles_offline_host_and_force(self):
        with patch.object(generate_cert, "ROOT", Path(self.directory.name)), \
             patch.object(generate_cert, "participant_base_url", side_effect=ValueError("未连接局域网")), \
             contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(generate_cert.main(["--host", "192.168.1.42"]), 0)
            cert = Path(self.directory.name) / "certs/cert.pem"
            original = cert.read_bytes()
            self.assertEqual(generate_cert.main(["--host", "192.168.1.42"]), 0)
            self.assertEqual(cert.read_bytes(), original)
            self.assertEqual(generate_cert.main(["--host", "192.168.1.42", "--force"]), 0)
            self.assertNotEqual(cert.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
