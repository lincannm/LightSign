"""入口分离、链接兼容与启动进程管理的回归检查。"""

import contextlib
import io
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

from streamlit.testing.v1 import AppTest

from light_sign import store
from light_sign import network
from light_sign.links import extract_token, participant_link
import run

ROOT = Path(__file__).resolve().parents[1]


class LinkTests(unittest.TestCase):
    def test_signed_token_link_roundtrip(self):
        with tempfile.TemporaryDirectory() as directory:
            connection = store.connect(Path(directory) / "db")
            event = store.event(connection, "链接测试")
            token = store.issue(connection, b"test-key", event, now=1000)
            link = participant_link("https://192.168.1.10:8504/", token)
            self.assertEqual(extract_token(link), token)
            self.assertEqual(extract_token("  " + token + "  "), token)
            payload, error = store.verify(connection, b"test-key", extract_token(link), now=1001)
            self.assertIsNone(error)
            self.assertEqual(payload["e"], event)
            connection.close()

    def test_invalid_addresses_and_ambiguous_tokens(self):
        for address in ["javascript:alert(1)", "localhost:8504", "https://user:pass@host/",
                        "https://host/?token=x", "https://host/#fragment"]:
            with self.subTest(address=address), self.assertRaises(ValueError):
                participant_link(address, "token")
        self.assertEqual(extract_token("https://host/?token=a&token=b"), "")

    def test_new_link_qr_decodes(self):
        import cv2
        import numpy as np
        import qrcode

        token = "a" * 78 + "." + "b" * 64
        link = participant_link("https://192.168.1.10:8504/", token)
        decoded, _, _ = cv2.QRCodeDetector().detectAndDecode(np.array(qrcode.make(link).convert("RGB")))
        self.assertEqual(extract_token(decoded), token)


class LauncherTests(unittest.TestCase):
    def test_explicit_http_overrides_certificates(self):
        command = run.server_command("participant.py", "0.0.0.0", 8504, None)
        self.assertEqual(command[command.index("--server.sslCertFile") + 1], "")
        self.assertEqual(command[command.index("--server.port") + 1], "8504")

    def test_configured_certificates_and_missing_files(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(run, "ROOT", Path(directory)):
            config_dir = Path(directory) / ".streamlit"
            config_dir.mkdir()
            (config_dir / "config.toml").write_text('[server]\nsslCertFile="cert.pem"\nsslKeyFile="key.pem"\n', encoding="utf-8")
            self.assertIsNone(run.certificate_files())
            for file in ["cert.pem", "key.pem"]:
                (Path(directory) / file).touch()
            self.assertEqual(run.certificate_files(), (Path(directory) / "cert.pem", Path(directory) / "key.pem"))
            self.assertIsNone(run.certificate_files(http=True))

    def test_rejects_same_port_before_starting(self):
        with patch.object(run.subprocess, "Popen") as popen, contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                run.main(["--organizer-port", "8503", "--participant-port", "8503"])
            popen.assert_not_called()

    def test_cleanup_terminates_only_running_processes(self):
        running = Mock()
        running.poll.return_value = None
        exited = Mock()
        exited.poll.return_value = 1
        run.stop_servers([running, exited])
        running.terminate.assert_called_once()
        exited.terminate.assert_not_called()

    def test_cleanup_kills_stuck_process(self):
        process = Mock()
        process.poll.return_value = None
        process.wait.side_effect = [subprocess.TimeoutExpired("streamlit", 5), 0]
        run.stop_servers([process])
        process.kill.assert_called_once()


class EntryPointTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        database = Path(self.directory.name) / "db"
        connect = store.connect
        self.connection = connect(database)
        self.event = store.event(self.connection, "入口测试活动")
        self.key = b"test-key"
        self.token = store.issue(self.connection, self.key, self.event)
        self.connect_patch = patch.object(store, "connect", side_effect=lambda: connect(database))
        self.key_patch = patch.object(store, "key", return_value=self.key)
        self.connect_patch.start()
        self.key_patch.start()

    def tearDown(self):
        self.connect_patch.stop()
        self.key_patch.stop()
        self.connection.close()
        self.directory.cleanup()

    def test_organizer_does_not_render_participant_form(self):
        app = AppTest.from_file(str(ROOT / "app.py")).run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual([tab.label for tab in app.tabs], ["活动与二维码", "匿名计数", "记录与数据"])
        self.assertNotIn("提交签到", [button.label for button in app.button])

    def test_organizer_generates_lan_qr_without_showing_address(self):
        with patch.dict("os.environ", {"LIGHTSIGN_PARTICIPANT_PORT": "9004", "LIGHTSIGN_PARTICIPANT_SCHEME": "http"}), \
             patch.object(network, "discover_lan_ipv4", return_value="192.168.1.42"):
            with patch.dict("os.environ"):
                import os
                os.environ.pop("LIGHTSIGN_PARTICIPANT_URL", None)
                app = AppTest.from_file(str(ROOT / "app.py")).run()
                next(button for button in app.button if button.label == "生成限时二维码").click().run()
            self.assertEqual(len(app.exception), 0)
            self.assertEqual([field.label for field in app.text_input], ["新活动名称"])
            link = app.session_state.participant_link
            self.assertTrue(link.startswith("http://192.168.1.42:9004/?token="))
            self.assertIsNone(store.verify(self.connection, self.key, extract_token(link))[1])
            self.assertEqual(len(app.code), 0)
            self.assertNotIn("打开参与者签到入口", [element.label for element in app.get("link_button")])
            self.assertFalse(any("不能证明持有者在场" in item.value for item in app.caption))

    def test_missing_network_does_not_issue_token_or_leave_stale_qr(self):
        with patch.object(network, "participant_base_url", side_effect=ValueError("请连接 Wi-Fi")):
            app = AppTest.from_file(str(ROOT / "app.py")).run()
            app.session_state.token = "old-token"
            app.session_state.participant_link = "http://old-address/"
            app.session_state.token_event = self.event
            before = self.connection.execute("SELECT COUNT(*) FROM challenges").fetchone()[0]
            next(button for button in app.button if button.label == "生成限时二维码").click().run()
            self.assertEqual(len(app.exception), 0)
            self.assertEqual(app.error[0].value, "请连接 Wi-Fi")
            self.assertNotIn("token", app.session_state)
            self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM challenges").fetchone()[0], before)

    def test_participant_has_no_admin_actions_and_initially_disabled(self):
        app = AppTest.from_file(str(ROOT / "participant.py")).run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(len(app.tabs), 0)
        self.assertEqual([button.label for button in app.button], ["提交签到"])
        self.assertTrue(app.button[0].disabled)

    def test_checkin_waits_for_browser_receipt(self):
        app = AppTest.from_file(str(ROOT / "participant.py"))
        app.query_params["token"] = self.token
        app.run()
        self.assertEqual(len(app.exception), 0)
        self.assertTrue(app.button[-1].disabled)

    def test_bad_token_does_not_enable_submission(self):
        app = AppTest.from_file(str(ROOT / "participant.py"))
        app.query_params["token"] = self.token[:-1] + ("0" if self.token[-1] != "0" else "1")
        app.run()
        self.assertEqual(len(app.exception), 0)
        self.assertTrue(app.button[-1].disabled)
        self.assertEqual(app.warning[0].value, "签名不匹配")


if __name__ == "__main__":
    unittest.main()
