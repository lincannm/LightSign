"""Windows 批处理入口的编码、文件名和命令解析回归检查。"""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ("START.bat",)


class BatchFileTests(unittest.TestCase):
    def test_filenames_and_ascii_crlf_are_preserved(self):
        names = {path.name for path in ROOT.glob("*") if path.suffix.lower() == ".bat"}
        self.assertTrue(set(SCRIPTS).issubset(names))
        for name in SCRIPTS:
            with self.subTest(script=name):
                data = (ROOT / name).read_bytes()
                self.assertFalse(data.startswith(b"\xef\xbb\xbf"))
                self.assertIn("powershell.exe", data.decode("ascii"))
                self.assertNotIn(b"chcp", data)
                self.assertIn(b"\r\n", data)
                self.assertNotIn(b"\n", data.replace(b"\r\n", b""))
                self.assertNotIn(b"\r", data.replace(b"\r\n", b""))

    def test_chinese_powershell_scripts_have_utf8_bom(self):
        for name in ("start.ps1",):
            with self.subTest(script=name):
                data = (ROOT / "scripts" / name).read_bytes()
                self.assertTrue(data.startswith(b"\xef\xbb\xbf"))
                self.assertIn("LightSign 轻签", data.decode("utf-8-sig"))


@unittest.skipUnless(os.name == "nt", "需要 Windows CMD")
class BatchCommandTests(unittest.TestCase):
    def run_batch(self, command, codepage=936, call=False, cwd=ROOT, env=None):
        return subprocess.run(
            [os.environ.get("COMSPEC", "cmd.exe"), "/d", "/c",
             f"chcp {codepage} >nul & {'call ' if call else ''}{command} <nul"],
            cwd=cwd, env=env, capture_output=True, encoding="utf-8", timeout=30,
        )

    def test_help_is_chinese_and_has_no_command_errors(self):
        for name in SCRIPTS:
            for codepage in (437, 936, 65001):
                for call in (False, True):
                    with self.subTest(script=name, codepage=codepage, call=call):
                        result = self.run_batch(f"{name} --help", codepage, call=call)
                        self.assertEqual(result.returncode, 0, result.stderr)
                        self.assertEqual(result.stderr, "")
                        self.assertIn("LightSign 轻签", result.stdout)
                        self.assertIn("使用方法：", result.stdout)
                        self.assertIn(name, result.stdout)
                        self.assertNotIn("\ufffd", result.stdout)

    def test_lf_wrappers_work_from_chinese_directory_with_spaces(self):
        with tempfile.TemporaryDirectory(prefix="lightsign-batch-") as directory:
            project = Path(directory) / "轻签 项目"
            (project / "scripts").mkdir(parents=True)
            for name in ("start.ps1",):
                (project / "scripts" / name).write_bytes((ROOT / "scripts" / name).read_bytes())
            for name in SCRIPTS:
                (project / name).write_bytes((ROOT / name).read_bytes().replace(b"\r\n", b"\n"))
                with self.subTest(script=name):
                    # Keep the driver ASCII even when the target path is Chinese.
                    driver = Path(directory) / "invoke.cmd"
                    driver.write_text(
                        f'@echo off\n"%LIGHTSIGN_TEST_PROJECT%\\{name}" --help <nul\n',
                        encoding="ascii", newline="\r\n",
                    )
                    env = dict(os.environ, LIGHTSIGN_TEST_PROJECT=str(project))
                    for codepage in (437, 936, 65001):
                        result = self.run_batch("invoke.cmd", codepage=codepage, cwd=directory, env=env)
                        self.assertEqual(result.returncode, 0, result.stderr)
                        self.assertEqual(result.stderr, "")
                        self.assertIn("LightSign 轻签", result.stdout)

    def test_start_missing_project_file_is_reported_without_command_errors(self):
        with tempfile.TemporaryDirectory(prefix="lightsign-missing-") as directory:
            project = Path(directory)
            (project / "scripts").mkdir()
            (project / "START.bat").write_bytes((ROOT / "START.bat").read_bytes())
            (project / "scripts" / "start.ps1").write_bytes((ROOT / "scripts" / "start.ps1").read_bytes())
            result = self.run_batch("START.bat", cwd=project)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stderr, "")
            self.assertIn("缺少文件：run.py", result.stdout)


if __name__ == "__main__":
    unittest.main()
