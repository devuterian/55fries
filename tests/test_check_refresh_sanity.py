import json
import tempfile
import unittest
from pathlib import Path

from scripts.check_refresh_sanity import check


def write(directory: Path, name: str, active: int, sold: int, models: int = 5) -> None:
    listings = [{"state": "active", "model": f"m{i % models}"} for i in range(active)]
    listings += [{"state": "sold", "model": f"m{i % models}"} for i in range(sold)]
    (directory / name).write_text(json.dumps({"listings": listings}))


class SanityTest(unittest.TestCase):
    def test_normal_change_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(Path(tmp), "auto-2026-11-04.json", 1000, 100)
            write(Path(tmp), "auto-2026-11-05.json", 980, 105)
            self.assertEqual(check(Path(tmp)), [])

    def test_big_drop_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(Path(tmp), "auto-2026-11-04.json", 1000, 100)
            write(Path(tmp), "auto-2026-11-05.json", 300, 100)
            problems = check(Path(tmp))
            self.assertTrue(any("판매중" in problem for problem in problems))

    def test_first_run_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(Path(tmp), "auto-2026-11-05.json", 10, 1)
            self.assertEqual(check(Path(tmp)), [])


if __name__ == "__main__":
    unittest.main()
