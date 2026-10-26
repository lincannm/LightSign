"""签到取时：等待写锁期间跨过有效期的请求应按取得锁之后的时间判定。"""

import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from light_sign import store


class CheckinClockTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "db.sqlite3"
        self.key = b"clock-test-key"
        c = store.connect(self.db)
        self.event = store.event(c, "取时测试")
        c.close()

    def tearDown(self):
        self.tmp.cleanup()

    def test_clock_read_after_write_lock(self):
        base = int(time.time())
        writer = store.connect(self.db)
        token = store.issue(writer, self.key, self.event, ttl=10, now=base)
        writer.execute("BEGIN IMMEDIATE")
        clock = {"now": base + 5}
        result = {}

        def submit():
            c = store.connect(self.db)
            try:
                with patch.object(store.time, "time", side_effect=lambda: clock["now"]):
                    result.update(store.checkin(c, self.key, token, "DEMO01", True))
            finally:
                c.close()

        worker = threading.Thread(target=submit)
        worker.start()
        time.sleep(0.3)
        # 排队期间时钟越过有效期，释放写锁后签到应被拒绝。
        clock["now"] = base + 11
        writer.rollback()
        worker.join(5)
        writer.close()
        self.assertFalse(worker.is_alive())
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "二维码已过期")

    def test_explicit_now_still_supported(self):
        c = store.connect(self.db)
        token = store.issue(c, self.key, self.event, ttl=60, now=1000)
        self.assertTrue(store.checkin(c, self.key, token, "DEMO01", True, now=1001)["ok"])
        self.assertFalse(store.checkin(c, self.key, token, "DEMO01", True, now=1002)["ok"])
        self.assertEqual(store.checkin(c, self.key, token, "DEMO02", True, now=1060)["reason"], "二维码已过期")
        c.close()


class ScanTicketTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "db.sqlite3"
        self.key = b"scan-test-key"
        self.connection = store.connect(self.db)
        self.event = store.event(self.connection, "扫码填写测试")
        self.token = store.issue(self.connection, self.key, self.event, ttl=10, now=1000)
        self.ticket, error = store.prepare_checkin(self.connection, self.key, self.token, now=1009)
        self.assertIsNone(error)

    def tearDown(self):
        self.connection.close()
        self.tmp.cleanup()

    def submit(self, now, **kwargs):
        return store.checkin(self.connection, self.key, self.token, "DEMO01", True,
                             now=now, scan_ticket=self.ticket, **kwargs)

    def test_scan_before_expiry_can_submit_after_qr_expires(self):
        self.assertEqual(store.verify(self.connection, self.key, self.token, now=1015)[1], "二维码已过期")
        self.assertTrue(self.submit(now=1015)["ok"])
        self.assertEqual(store.rows(self.connection)[0]["created"], 1015)
        self.assertEqual(self.submit(now=1016)["reason"], "本活动已签到")

    def test_expired_qr_cannot_start_a_new_filling_session(self):
        ticket, error = store.prepare_checkin(self.connection, self.key, self.token, now=1010)
        self.assertIsNone(ticket)
        self.assertEqual(error, "二维码已过期")
        result = store.checkin(self.connection, self.key, self.token, "OTHER01", True, now=1015)
        self.assertEqual(result["reason"], "二维码已过期")

    def test_filling_deadline_is_fixed_and_expires_at_boundary(self):
        self.assertIsNone(store.verify_scan(self.connection, self.key, self.token, self.ticket, now=1308)[1])
        self.assertEqual(self.submit(now=1309)["reason"], "填写时间已结束，请重新扫描二维码")
        self.assertEqual(store.rows(self.connection), [])

    def test_scan_ticket_is_bound_to_qr_and_cannot_be_forged(self):
        other = store.issue(self.connection, self.key, self.event, ttl=10, now=1000)
        tampered = self.ticket[:-1] + ("0" if self.ticket[-1] != "0" else "1")
        for token, ticket in ((other, self.ticket), (self.token, tampered),
                              (self.token, self.token), (self.token, "invalid")):
            with self.subTest(token=token, ticket=ticket):
                payload, error = store.verify_scan(self.connection, self.key, token, ticket, now=1015)
                self.assertIsNone(payload)
                self.assertEqual(error, "无效扫码凭证，请重新扫描二维码")

    def test_revoke_invalidates_an_existing_filling_session(self):
        store.revoke(self.connection, self.event)
        self.assertEqual(self.submit(now=1015)["reason"], "二维码已撤销或不存在")
        self.assertEqual(store.rows(self.connection), [])

    def test_close_invalidates_an_existing_filling_session(self):
        store.close(self.connection, self.event)
        self.assertEqual(self.submit(now=1015)["reason"], "活动已关闭")
        self.assertEqual(store.rows(self.connection), [])

    def test_filling_deadline_is_checked_after_waiting_for_write_lock(self):
        self.connection.execute("BEGIN IMMEDIATE")
        clock = {"now": 1308}
        result = {}
        started = threading.Event()

        def submit():
            c = store.connect(self.db)
            try:
                with patch.object(store.time, "time", side_effect=lambda: clock["now"]):
                    started.set()
                    result.update(store.checkin(c, self.key, self.token, "DEMO01", True,
                                                scan_ticket=self.ticket))
            finally:
                c.close()

        worker = threading.Thread(target=submit)
        worker.start()
        self.assertTrue(started.wait(5))
        clock["now"] = 1309
        self.connection.rollback()
        worker.join(5)
        self.assertFalse(worker.is_alive())
        self.assertEqual(result["reason"], "填写时间已结束，请重新扫描二维码")
        self.assertEqual(store.rows(self.connection), [])


if __name__ == "__main__":
    unittest.main()
