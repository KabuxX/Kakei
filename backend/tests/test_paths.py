import importlib
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import paths


class PathsTests(unittest.TestCase):
    def test_paths_are_absolute_and_independent_of_working_directory(self):
        root = Path(__file__).resolve().parents[2]
        expected = {
            "BACKEND_DIR": root / "backend",
            "FRONT_DIST_DIR": root / "front" / "dist",
            "SAMPLE_DATA_DIR": root / "front" / "src" / "data",
            "DEFAULT_DB_PATH": root / "backend" / "data" / "kakei.sqlite3",
            "TIMELINE_PATH": root / "front" / "src" / "data" / "september-timeline.json",
        }
        original_directory = Path.cwd()
        try:
            with tempfile.TemporaryDirectory() as directory:
                os.chdir(directory)
                importlib.reload(paths)
                for name, expected_path in expected.items():
                    with self.subTest(name=name):
                        actual = getattr(paths, name)
                        self.assertIsInstance(actual, Path)
                        self.assertTrue(actual.is_absolute())
                        self.assertEqual(actual, expected_path)
        finally:
            os.chdir(original_directory)


if __name__ == "__main__":
    unittest.main()
