import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from runtime import require_supported_python


class RuntimeTests(unittest.TestCase):
    def test_rejects_python_older_than_314(self):
        with self.assertRaisesRegex(SystemExit, "Python 3.14"):
            require_supported_python((3, 13, 9))

    def test_accepts_python_314(self):
        require_supported_python((3, 14, 0))


if __name__ == "__main__":
    unittest.main()
