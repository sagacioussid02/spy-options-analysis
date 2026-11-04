import subprocess
import sys
import unittest
from pathlib import Path


RUN_STEP = Path(__file__).with_name("run_step.py")
PYTHON = sys.executable


class RunStepTests(unittest.TestCase):
    def test_returns_child_exit_code(self):
        result = subprocess.run(
            [PYTHON, str(RUN_STEP), "5", PYTHON, "-c", "raise SystemExit(7)"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 7)

    def test_timeout_terminates_child(self):
        result = subprocess.run(
            [PYTHON, str(RUN_STEP), "0.2", PYTHON, "-c", "import time; time.sleep(5)"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 124)
        self.assertIn("terminated", result.stderr)


if __name__ == "__main__":
    unittest.main()
