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


if __name__ == "__main__":
    unittest.main()
