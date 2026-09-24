import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_ROOT / "cases" / "快马-顺英" / "案例配置.json"

sys.path.insert(0, str(PROJECT_ROOT))
from scripts.validate_case import default_output_path


class CommandLineTest(unittest.TestCase):
    def test_default_output_path_is_scoped_by_dealer(self):
        self.assertEqual(
            default_output_path(CONFIG_PATH, "顺英"),
            PROJECT_ROOT / "outputs" / "顺英" / "run.json",
        )

    def test_validate_case_runs_as_documented(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "run.json"
            completed = subprocess.run(
                [
                    sys.executable,
                    "scripts/validate_case.py",
                    "--config",
                    "cases/快马-顺英/案例配置.json",
                    "--output",
                    str(output),
                ],
                cwd=PROJECT_ROOT,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertTrue(output.exists())


if __name__ == "__main__":
    unittest.main()
