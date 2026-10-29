"""组织者登录口令的读取、生成与登录门禁检查。"""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from light_sign import auth

ROOT = Path(__file__).resolve().parents[2]
APP_TIMEOUT = 30
TABS = ["活动与二维码", "人数清点", "记录与数据"]


def organizer_app():
    return AppTest.from_file(str(ROOT / "app.py"), default_timeout=APP_TIMEOUT)


class PasswordFileTests(unittest.TestCase):
    def test_reads_key_value_plain_and_quoted_passwords(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "PASSWORD.conf"
            for content, expected in [
                ("password = demo-pass\n", "demo-pass"),
                ("口令: 中文口令\n", "中文口令"),
                ("# 注释\n; 另一条注释\n  纯文本口令  \n", "纯文本口令"),
                ('password = "引号口令"\n', "引号口令"),
            ]:
                with self.subTest(content=content):
                    path.write_text(content, encoding="utf-8")
                    self.assertEqual(auth.read_password(path), expected)

    def test_missing_or_comment_only_file_has_no_password(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "PASSWORD.conf"
            self.assertIsNone(auth.read_password(path))
            path.write_text("# 只有注释\n\n", encoding="utf-8")
            self.assertIsNone(auth.read_password(path))

    def test_generates_password_once_and_reuses_it(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "PASSWORD.conf"
            generated, created = auth.ensure_password(path)
            self.assertTrue(created)
            self.assertGreaterEqual(len(generated), auth.MIN_PASSWORD_LENGTH)
            self.assertEqual(auth.read_password(path), generated)
            again, created = auth.ensure_password(path)
            self.assertFalse(created)
            self.assertEqual(again, generated)
            self.assertIn("password = ", path.read_text(encoding="utf-8"))

    def test_rejects_short_or_empty_setting(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "PASSWORD.conf"
            path.write_text("password = ab\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                auth.ensure_password(path)
            path.write_text("# 没有口令\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                auth.ensure_password(path)


class LoginGateTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.password_file = Path(self.directory.name) / "PASSWORD.conf"
        self.password_file.write_text("password = demo-pass\n", encoding="utf-8")

    def tearDown(self):
        self.directory.cleanup()

    def test_loopback_client_enters_without_password(self):
        with patch.object(auth, "client_is_loopback", return_value=True):
            app = organizer_app().run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual([tab.label for tab in app.tabs], TABS)
        self.assertEqual([field.label for field in app.text_input], ["新活动名称"])

    def test_lan_client_must_log_in(self):
        with patch.object(auth, "password_path", return_value=self.password_file):
            app = organizer_app().run()
            self.assertEqual(len(app.exception), 0)
            self.assertEqual(len(app.tabs), 0)
            self.assertEqual([field.label for field in app.text_input], ["登录口令"])
            app.text_input[0].set_value("wrong")
            app.button[0].click().run()
            self.assertEqual(len(app.tabs), 0)
            self.assertTrue(any("口令不正确" in item.value for item in app.error))
            app.text_input[0].set_value("demo-pass")
            app.button[0].click().run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual([tab.label for tab in app.tabs], TABS)

    def test_lan_login_blocks_when_password_file_is_missing(self):
        missing = Path(self.directory.name) / "absent.conf"
        with patch.object(auth, "password_path", return_value=missing):
            app = organizer_app().run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(len(app.tabs), 0)
        self.assertTrue(any("未找到组织者登录口令" in item.value for item in app.error))


if __name__ == "__main__":
    unittest.main()
