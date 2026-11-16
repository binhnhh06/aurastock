"""Kiểm thử bộ giới hạn tần suất và logger (không gọi mạng)."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.aura_log import RateLimiter, get_logger  # noqa: E402


class FakeClock:
    def __init__(self):
        self.t = 100.0
        self.slept = []

    def now(self):
        return self.t

    def sleep(self, s):
        self.slept.append(s)
        self.t += s


class TestRateLimiter(unittest.TestCase):
    def test_lan_dau_khong_cho(self):
        c = FakeClock()
        self.assertEqual(RateLimiter(1.0, c.now, c.sleep).wait(), 0.0)

    def test_goi_lien_tiep_phai_cho_du_khoang_cach(self):
        c = FakeClock()
        lim = RateLimiter(1.0, c.now, c.sleep)
        lim.wait()
        c.t += 0.3
        self.assertAlmostEqual(lim.wait(), 0.7)
        # 5 lần gọi liên tiếp không thể vượt 1 lần/giây
        for _ in range(5):
            lim.wait()
        self.assertGreaterEqual(c.t - 100.0, 6.0)

    def test_da_qua_khoang_cach_thi_khong_cho(self):
        c = FakeClock()
        lim = RateLimiter(1.0, c.now, c.sleep)
        lim.wait()
        c.t += 2.0
        self.assertEqual(lim.wait(), 0.0)


class TestLogger(unittest.TestCase):
    def test_logger_dung_chung_khong_nhan_doi_handler(self):
        a = get_logger("aura.ssi")
        n = len(get_logger().handlers)
        get_logger("aura.ssi")
        self.assertEqual(len(get_logger().handlers), n)
        self.assertEqual(a.name, "aura.ssi")


if __name__ == "__main__":
    unittest.main()
