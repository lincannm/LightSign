"""Windows 批处理入口的编码、文件名和命令解析回归检查。"""

import os
from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ("package.bat", "START.bat")


class BatchFileTests(unittest.TestCase):
    def test_filenames_and_utf8_crlf_are_preserved(self):
        names = {path.name for path in ROOT.glob("*") if path.suffix.lower() == ".bat"}
        self.assertEqual(names, set(SCRIPTS))
        for name in SCRIPTS:
            with self.subTest(script=name):
                data = (ROOT / name).read_bytes()
                self.assertFalse(data.startswith(b"\xef\xbb\xbf"))
                self.assertIn("轻签", data.decode("utf-8"))
                self.assertIn(b"\r\n", data)
                self.assertNotIn(b"\n", data.replace(b"\r\n", b""))
                self.assertNotIn(b"\r", data.replace(b"\r\n", b""))


@unittest.skipUnless(os.name == "nt", "需要 Windows CMD")
class BatchCommandTests(unittest.TestCase):
    def run_batch(self, command, codepage=936):
        return subprocess.run(
            [os.environ.get("COMSPEC", "cmd.exe"), "/d", "/c",
             f"chcp {codepage} >nul & call {command} <nul"],
            cwd=ROOT, capture_output=True, encoding="utf-8", timeout=30,
        )

    def test_help_is_chinese_and_has_no_command_errors(self):
        for name in SCRIPTS:
            for codepage in (936, 65001):
                with self.subTest(script=name, codepage=codepage):
                    result = self.run_batch(f"{name} --help", codepage)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(result.stderr, "")
                    self.assertIn("LightSign 轻签", result.stdout)
                    self.assertIn("使用方法：", result.stdout)
                    self.assertIn(name, result.stdout)
                    self.assertNotIn("\ufffd", result.stdout)

    def test_package_rejects_extra_arguments(self):
        result = self.run_batch("package.bat one two")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stderr, "")
        self.assertIn("最多接受一个参数", result.stdout)


if __name__ == "__main__":
    unittest.main()
