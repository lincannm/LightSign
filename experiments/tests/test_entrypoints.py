"""入口分离、链接兼容与启动进程管理的回归检查。"""

import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from streamlit.testing.v1 import AppTest

from light_sign import store
from light_sign import network
from light_sign import organizer_qr
from light_sign.links import extract_token, participant_link
import run

ROOT = Path(__file__).resolve().parents[2]
# 首次冷启动（新解压目录、无字节码缓存）可能超过 AppTest 默认的 3 秒。
APP_TIMEOUT = 30


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
        self.assertEqual(command[command.index("--logger.level") + 1], "warning")

    def test_servers_start_through_keepalive_launcher(self):
        command = run.server_command("app.py", "127.0.0.1", 8503, None)
        self.assertEqual(command[:4], [
            sys.executable, str(run.ROOT / "run.py"), "--serve", str(run.ROOT / "app.py")])
        self.assertEqual(command[command.index("--server.port") + 1], "8503")

    def test_launcher_extends_idle_keepalive(self):
        from streamlit.web.server.starlette import starlette_server

        original = starlette_server._get_uvicorn_config_kwargs
        try:
            starlette_server._get_uvicorn_config_kwargs = lambda: {"ws": "auto"}
            run.extend_keep_alive()
            kwargs = starlette_server._get_uvicorn_config_kwargs()
            self.assertEqual(kwargs["timeout_keep_alive"], run.KEEP_ALIVE_SECONDS)
            self.assertEqual(kwargs["ws"], "auto")
        finally:
            starlette_server._get_uvicorn_config_kwargs = original

    def test_startup_panel_highlights_both_entries_and_redirects_without_ansi(self):
        args = Mock(organizer_host="127.0.0.1", organizer_port=8503)
        with contextlib.redirect_stdout(io.StringIO()) as output:
            run.print_startup(args, "https", "https://192.168.1.42:8504/", ("cert", "key"))
        panel = output.getvalue()
        self.assertIn("\n  组织者入口", panel)
        self.assertIn("\n  https://localhost:8503/\n", panel)
        self.assertIn("\n  参与者入口", panel)
        self.assertIn("\n  https://192.168.1.42:8504/\n", panel)
        self.assertIn("HTTPS 提示", panel)
        self.assertNotIn("\x1b[", panel)

    def test_terminal_colors_and_no_color_opt_out(self):
        with patch.dict(os.environ):
            os.environ.pop("NO_COLOR", None)
            terminal = io.StringIO()
            terminal.isatty = lambda: True
            with contextlib.redirect_stdout(terminal):
                run.log("组织者入口", "cyan", bold=True)
            self.assertIn("\x1b[", terminal.getvalue())
            os.environ["NO_COLOR"] = "1"
            with contextlib.redirect_stdout(io.StringIO()) as output:
                run.log("组织者入口", "cyan", bold=True)
            self.assertNotIn("\x1b[", output.getvalue())

    def test_startup_panel_handles_missing_lan_and_custom_binding(self):
        args = Mock(organizer_host="192.168.1.10", organizer_port=9003)
        with contextlib.redirect_stdout(io.StringIO()) as output:
            run.print_startup(args, "http", None, None)
        panel = output.getvalue()
        self.assertIn("http://192.168.1.10:9003/", panel)
        self.assertIn("暂无可分享地址", panel)
        self.assertIn("HTTP 模式", panel)
        self.assertNotIn("访问范围：本机", panel)

    def test_configured_certificates_and_missing_files(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(run, "ROOT", Path(directory)):
            config_dir = Path(directory) / ".streamlit"
            config_dir.mkdir()
            (config_dir / "config.toml").write_text('[server]\nsslCertFile="cert.pem"\nsslKeyFile="key.pem"\n', encoding="utf-8")
            paths = run.certificate_files(hosts=["192.168.1.42"])
            self.assertEqual(paths, (Path(directory) / "cert.pem", Path(directory) / "key.pem"))
            original = [path.read_bytes() for path in paths]
            self.assertEqual(run.certificate_files(hosts=["192.168.1.42"]), paths)
            self.assertEqual([path.read_bytes() for path in paths], original)
            self.assertIsNone(run.certificate_files(http=True))

    def test_http_does_not_create_certificate_files(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(run, "ROOT", Path(directory)):
            self.assertIsNone(run.certificate_files(http=True))
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_certificate_failure_does_not_start_or_fall_back_to_http(self):
        with patch.object(run, "participant_base_url", return_value="https://192.168.1.42:8504/"), \
             patch.object(run.socket, "socket"), \
             patch.object(run, "certificate_files", side_effect=OSError("证书写入失败")), \
             patch.object(run.subprocess, "Popen") as popen, \
             contextlib.redirect_stderr(io.StringIO()) as errors:
            self.assertEqual(run.main([]), 1)
            popen.assert_not_called()
            self.assertIn("证书写入失败", errors.getvalue())

    def test_launcher_covers_and_pins_the_shared_address(self):
        first, second = Mock(), Mock()
        first.poll.return_value = 1
        second.poll.return_value = 1
        first.returncode = second.returncode = 1
        with patch.object(run, "participant_base_url", return_value="https://192.168.1.42:8504/"), \
             patch.object(run.socket, "socket"), \
             patch.object(run, "certificate_files", return_value=(Path("cert"), Path("key"))) as certificates, \
             patch.object(run.store, "connect"), patch.object(run.store, "key"), \
             patch.object(run.subprocess, "Popen", side_effect=[first, second]) as popen, \
             contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(run.main([]), 1)
            self.assertIn("192.168.1.42", certificates.call_args.args[1])
            for call in popen.call_args_list:
                self.assertEqual(call.kwargs["env"]["LIGHTSIGN_PARTICIPANT_URL"], "https://192.168.1.42:8504/")
                self.assertEqual(call.kwargs["env"]["LIGHTSIGN_PARTICIPANT_SCHEME"], "https")
                self.assertEqual(call.kwargs["env"]["STREAMLIT_LOGGER_HIDE_WELCOME_MESSAGE"], "true")

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
        app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=APP_TIMEOUT).run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual([tab.label for tab in app.tabs], ["活动与二维码", "人数清点", "记录与数据"])
        self.assertNotIn("提交签到", [button.label for button in app.button])
        self.assertEqual([checkbox.label for checkbox in app.checkbox], ["二维码自动刷新"])
        self.assertTrue(app.checkbox[0].value)

    def test_organizer_runs_when_experiment_records_are_unavailable(self):
        read_text = Path.read_text
        for error in (FileNotFoundError("experiment records omitted"),
                      json.JSONDecodeError("invalid experiment record", "", 0)):
            with self.subTest(error=type(error).__name__):
                def unavailable(path, *args, **kwargs):
                    if path.parent == ROOT / "experiments" / "results":
                        raise error
                    return read_text(path, *args, **kwargs)

                with patch.object(Path, "read_text", unavailable):
                    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=APP_TIMEOUT).run()
                self.assertEqual(len(app.exception), 0)
                self.assertTrue(any("当前未附带可读取的实验记录" in item.value for item in app.info))
                self.assertIn("导出 JSON", [item.label for item in app.get("download_button")])

    def test_expired_qr_turns_black_and_cannot_be_downloaded_when_refresh_disabled(self):
        with patch.object(organizer_qr, "time", return_value=1000) as clock, \
             patch.object(network, "participant_base_url", return_value="https://192.168.1.42:8504/"):
            app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=APP_TIMEOUT).run()
            app.checkbox[0].uncheck().run()
            next(button for button in app.button if button.label == "生成限时二维码").click().run()
            token = app.session_state.token
            self.assertTrue(any(item.label == "下载二维码 PNG" for item in app.get("download_button")))
            clock.return_value = 1120
            app.run()
            self.assertEqual(len(app.exception), 0)
            self.assertEqual(app.session_state.token, token)
            self.assertEqual(app.warning[0].value, "二维码已过期")
            self.assertTrue(any("background:#000" in item.proto.body for item in app.get("html")))
            self.assertFalse(any(item.label == "下载二维码 PNG" for item in app.get("download_button")))
            self.assertEqual(len(app.get("imgs")), 0)

    def test_auto_refresh_renews_only_at_expiry_and_uses_current_lifetime(self):
        with patch.object(organizer_qr, "time", return_value=1000) as clock, \
             patch.object(network, "participant_base_url", return_value="https://192.168.1.42:8504/"):
            app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=APP_TIMEOUT).run()
            next(button for button in app.button if button.label == "生成限时二维码").click().run()
            original_token = app.session_state.token
            original_png = app.session_state.qr_png
            clock.return_value = 1119
            app.run()
            self.assertEqual(app.session_state.token, original_token)
            clock.return_value = 1120
            app.slider[0].set_value(60).run()
            self.assertEqual(len(app.exception), 0)
            self.assertNotEqual(app.session_state.token, original_token)
            self.assertNotEqual(app.session_state.qr_png, original_png)
            payload, error = store.verify(self.connection, self.key, app.session_state.token, now=1120)
            self.assertIsNone(error)
            self.assertEqual(payload["x"], 1180)
            self.assertEqual(app.session_state.token_expires, 1180)
            self.assertEqual(store.verify(self.connection, self.key, original_token, now=1120)[1], "二维码已过期")
            self.assertTrue(any("剩余 60 秒" in item.value for item in app.caption))

    def test_enabling_auto_refresh_replaces_an_expired_qr(self):
        with patch.object(organizer_qr, "time", return_value=1000) as clock, \
             patch.object(network, "participant_base_url", return_value="https://192.168.1.42:8504/"):
            app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=APP_TIMEOUT).run()
            app.checkbox[0].uncheck().run()
            next(button for button in app.button if button.label == "生成限时二维码").click().run()
            original_token = app.session_state.token
            clock.return_value = 1120
            app.run()
            app.checkbox[0].check().run()
            self.assertEqual(len(app.exception), 0)
            self.assertNotEqual(app.session_state.token, original_token)
            self.assertEqual(len(app.warning), 0)

    def test_timer_rerun_updates_only_qr_after_main_connection_closes(self):
        from streamlit.runtime.scriptrunner_utils.script_requests import RerunData
        from streamlit.testing.v1 import local_script_runner

        with patch.object(organizer_qr, "time", return_value=1000) as clock, \
             patch.object(network, "participant_base_url", return_value="https://192.168.1.42:8504/"):
            app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=APP_TIMEOUT).run()
            next(button for button in app.button if button.label == "生成限时二维码").click().run()
            token = app.session_state.token
            fragment_id, = app._fragment_storage._fragments
            clock.return_value = 1120
            def timer_request(**kwargs):
                return RerunData(**kwargs, fragment_id_queue=[fragment_id], is_auto_rerun=True)
            with patch.object(local_script_runner, "RerunData", side_effect=timer_request), \
                 patch.object(organizer_qr, "issue_qr", wraps=organizer_qr.issue_qr) as issue:
                app.run()
            self.assertEqual(len(app.exception), 0)
            issue.assert_called_once()
            self.assertNotEqual(app.session_state.token, token)
            self.assertIsNone(store.verify(self.connection, self.key, app.session_state.token, now=1120)[1])

    def test_existing_qr_session_builds_missing_png_without_reissuing(self):
        with patch.object(organizer_qr, "time", return_value=1000), \
             patch.object(network, "participant_base_url", return_value="https://192.168.1.42:8504/"):
            app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=APP_TIMEOUT).run()
            next(button for button in app.button if button.label == "生成限时二维码").click().run()
            token = app.session_state.token
            del app.session_state["qr_png"]
            app.run()
            self.assertEqual(len(app.exception), 0)
            self.assertEqual(app.session_state.token, token)
            self.assertTrue(app.session_state.qr_png.startswith(b"\x89PNG"))

    def test_expired_qr_does_not_auto_refresh_after_external_revoke_or_close(self):
        for action, message in [(store.revoke, "二维码已撤销或不存在"), (store.close, "活动已关闭")]:
            with self.subTest(action=action.__name__), \
                 patch.object(organizer_qr, "time", return_value=1000) as clock, \
                 patch.object(network, "participant_base_url", return_value="https://192.168.1.42:8504/"):
                app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=APP_TIMEOUT).run()
                next(button for button in app.button if button.label == "生成限时二维码").click().run()
                original_token = app.session_state.token
                action(self.connection, self.event)
                clock.return_value = 1120
                app.run()
                self.assertEqual(len(app.exception), 0)
                self.assertEqual(app.session_state.token, original_token)
                self.assertEqual(app.warning[0].value, message)

    def test_auto_refresh_failure_keeps_expired_qr_black(self):
        with patch.object(organizer_qr, "time", return_value=1000) as clock, \
             patch.object(network, "participant_base_url", return_value="https://192.168.1.42:8504/") as address:
            app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=APP_TIMEOUT).run()
            next(button for button in app.button if button.label == "生成限时二维码").click().run()
            original_token = app.session_state.token
            address.side_effect = ValueError("请连接 Wi-Fi")
            clock.return_value = 1120
            app.run()
            self.assertEqual(len(app.exception), 0)
            self.assertEqual(app.session_state.token, original_token)
            self.assertIn("自动刷新失败", app.error[0].value)
            self.assertEqual(app.warning[0].value, "二维码已过期")

    def test_revoke_and_close_clear_qr_without_automatic_reissue(self):
        for label in ("撤销该活动二维码", "关闭活动"):
            with self.subTest(label=label), patch.object(organizer_qr, "time", return_value=1000), \
                 patch.object(network, "participant_base_url", return_value="https://192.168.1.42:8504/"):
                app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=APP_TIMEOUT).run()
                next(button for button in app.button if button.label == "生成限时二维码").click().run()
                next(button for button in app.button if button.label == label).click().run()
                app.run()
                self.assertEqual(len(app.exception), 0)
                self.assertNotIn("token", app.session_state)
                self.assertNotIn("participant_link", app.session_state)
                self.assertNotIn("qr_png", app.session_state)

    def test_organizer_generates_lan_qr_without_showing_address(self):
        with patch.dict("os.environ", {"LIGHTSIGN_PARTICIPANT_PORT": "9004", "LIGHTSIGN_PARTICIPANT_SCHEME": "http"}), \
             patch.object(network, "discover_lan_ipv4", return_value="192.168.1.42"):
            with patch.dict("os.environ"):
                import os
                os.environ.pop("LIGHTSIGN_PARTICIPANT_URL", None)
                app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=APP_TIMEOUT).run()
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
            app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=APP_TIMEOUT).run()
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
        app = AppTest.from_file(str(ROOT / "participant.py"), default_timeout=APP_TIMEOUT).run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(len(app.tabs), 0)
        self.assertEqual([button.label for button in app.button], ["提交签到"])
        self.assertTrue(app.button[0].disabled)
        self.assertEqual(app.radio[0].label, "二维码扫描方式")
        self.assertEqual(app.radio[0].options, ["上传图片", "摄像头扫码"])
        self.assertEqual(len(app.text_area), 0)
        self.assertEqual(app.text_input[0].label, "参与代号（不需要姓名等个人信息）")

    def test_checkin_waits_for_browser_receipt(self):
        app = AppTest.from_file(str(ROOT / "participant.py"), default_timeout=APP_TIMEOUT)
        app.query_params["token"] = self.token
        app.run()
        self.assertEqual(len(app.exception), 0)
        self.assertTrue(app.button[-1].disabled)

    def test_bad_token_does_not_enable_submission(self):
        app = AppTest.from_file(str(ROOT / "participant.py"), default_timeout=APP_TIMEOUT)
        app.query_params["token"] = self.token[:-1] + ("0" if self.token[-1] != "0" else "1")
        app.run()
        self.assertEqual(len(app.exception), 0)
        self.assertTrue(app.button[-1].disabled)
        self.assertEqual(app.warning[0].value, "签名不匹配")


    def test_records_display_chinese_headers_and_readable_beijing_time(self):
        token = store.issue(self.connection, self.key, self.event, now=1000)
        store.checkin(self.connection, self.key, token, "DEMO01", True, now=1001)
        app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=APP_TIMEOUT).run()
        self.assertEqual(len(app.exception), 0)
        records = app.dataframe[0].value
        self.assertEqual(list(records.columns), ["活动名称", "活动编号", "参与者匿名编号", "签到时间（北京时间）"])
        self.assertEqual(records.iloc[0]["签到时间（北京时间）"], "1970-01-01 08:16:41")

    def test_participant_can_finish_after_ten_second_qr_expires(self):
        token = store.issue(self.connection, self.key, self.event, ttl=10, now=1000)
        with patch.object(store.time, "time", return_value=1009) as clock, \
             patch("light_sign.browser_receipt.browser_receipt", return_value={"available": True, "checkedIn": False}):
            app = AppTest.from_file(str(ROOT / "participant.py"), default_timeout=APP_TIMEOUT)
            app.query_params["token"] = token
            app.run()
            ticket = app.session_state.scan_ticket
            app.text_input[0].set_value("DEM").run()
            clock.return_value = 1015
            app.text_input[0].set_value("DEMO01").run()
            app.checkbox[0].check().run()
            self.assertEqual(app.session_state.scan_ticket, ticket)
            self.assertFalse(app.button[-1].disabled)
            self.assertEqual(len(app.warning), 0)
            app.button[-1].click().run()
            self.assertEqual(len(app.exception), 0)
            self.assertEqual(app.success[0].value, "本活动已签到，无需重复提交。")
            self.assertEqual(len(store.rows(self.connection)), 1)
            self.assertEqual(store.rows(self.connection)[0]["created"], 1015)

    def test_taken_code_is_reported_and_another_code_can_be_submitted(self):
        token = store.issue(self.connection, self.key, self.event, ttl=60, now=1000)
        store.checkin(self.connection, self.key, token, "DEMO01", True, now=1001)
        with patch.object(store.time, "time", return_value=1050), \
             patch("light_sign.browser_receipt.browser_receipt", return_value={"available": True, "checkedIn": False}):
            app = AppTest.from_file(str(ROOT / "participant.py"), default_timeout=APP_TIMEOUT)
            app.query_params["token"] = token
            app.run()
            app.text_input[0].set_value("DEMO01").run()
            app.checkbox[0].check().run()
            app.button[-1].click().run()
            self.assertEqual(len(app.exception), 0)
            self.assertTrue(any("已被使用" in item.value for item in app.warning))
            # 代号被占用不等于本人已签到：不写本地签到标记，表单保持可编辑。
            self.assertEqual(app.session_state.get("confirmed_events", set()), set())
            self.assertEqual(app.text_input[0].value, "DEMO01")
            self.assertFalse(app.text_input[0].disabled)
            self.assertFalse(app.button[-1].disabled)
            self.assertEqual(len(store.rows(self.connection)), 1)
            app.text_input[0].set_value("DEMO02").run()
            self.assertFalse(any("已被使用" in item.value for item in app.warning))
            self.assertEqual(len(app.warning), 0)
            app.checkbox[0].check().run()
            app.button[-1].click().run()
            self.assertEqual(len(app.exception), 0)
            self.assertEqual(app.success[0].value, "本活动已签到，无需重复提交。")
        rows = store.rows(self.connection)
        self.assertEqual(len(rows), 2)
        self.assertNotEqual(rows[0]["participant"], rows[1]["participant"])

    def test_uploaded_scan_survives_reruns_without_query_parameter(self):
        token = store.issue(self.connection, self.key, self.event, ttl=10, now=1000)
        with patch.object(store.time, "time", return_value=1009) as clock, \
             patch("streamlit.file_uploader", return_value=object()), \
             patch("cv2.QRCodeDetector") as detector, \
             patch("PIL.Image.open") as image:
            import numpy as np
            image.return_value.convert.return_value = np.zeros((10, 10, 3), dtype=np.uint8)
            detector.return_value.detectAndDecode.return_value = (token, None, None)
            app = AppTest.from_file(str(ROOT / "participant.py"), default_timeout=APP_TIMEOUT).run()
            ticket = app.session_state.scan_ticket
            self.assertEqual(app.session_state.scan_token, token)
            self.assertEqual(dict(app.query_params), {})
            clock.return_value = 1015
            app.text_input[0].set_value("DEMO01").run()
            self.assertEqual(len(app.exception), 0)
            self.assertEqual(len(app.warning), 0)
            self.assertEqual(app.session_state.scan_ticket, ticket)
            self.assertEqual(app.subheader[0].value, "入口测试活动")

    def test_filling_deadline_does_not_renew_on_rerun(self):
        token = store.issue(self.connection, self.key, self.event, ttl=10, now=1000)
        with patch.object(store.time, "time", return_value=1009) as clock:
            app = AppTest.from_file(str(ROOT / "participant.py"), default_timeout=APP_TIMEOUT)
            app.query_params["token"] = token
            app.run()
            ticket = app.session_state.scan_ticket
            clock.return_value = 1309
            app.text_input[0].set_value("DEMO01").run()
            self.assertEqual(len(app.exception), 0)
            self.assertEqual(app.warning[0].value, "填写时间已结束，请重新扫描二维码")
            self.assertEqual(app.session_state.scan_ticket, ticket)
            self.assertEqual(app.text_input[0].value, "DEMO01")
            self.assertTrue(app.button[-1].disabled)

    def test_switching_qr_clears_scan_ticket_and_form(self):
        app = AppTest.from_file(str(ROOT / "participant.py"), default_timeout=APP_TIMEOUT)
        app.query_params["token"] = self.token
        app.run()
        app.text_input[0].set_value("DEMO01").run()
        app.checkbox[0].check().run()
        app.button[0].click().run()
        self.assertEqual(len(app.exception), 0)
        self.assertNotIn("scan_token", app.session_state)
        self.assertNotIn("scan_ticket", app.session_state)
        self.assertEqual(app.text_input[0].value, "")
        self.assertFalse(app.checkbox[0].value)
        self.assertEqual(app.radio[0].options, ["上传图片", "摄像头扫码"])


if __name__ == "__main__":
    unittest.main()
