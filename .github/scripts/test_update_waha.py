import contextlib
import datetime
import io
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

import update_waha


class UpdateTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.directory = self.root / "waha"
        self.directory.mkdir()
        self.files = {
            "Dockerfile": "# image\nFROM devlikeapro/waha:noweb-arm-2026.9.9\nUSER root\n",
            "config.yaml": 'name: WAHA\nversion: "0.2.4"\n',
            "CHANGELOG.md": "# Changelog\n\nChanges.\n\n## 0.2.4 - 2026-10-01\n\n- Previous.\n",
        }
        for name, content in self.files.items():
            (self.directory / name).write_text(content, encoding="utf-8")
        self.release = {"draft": False, "prerelease": False, "tag_name": "2026.10.1"}
        self.tag = {"name": "noweb-arm-2026.10.1", "digest": "sha256:" + "a" * 64,
                    "images": [{"os": "linux", "architecture": "arm64", "status": "active"}]}
        self.calls = []

    def fetch(self, url):
        self.calls.append(url)
        return self.release if url == update_waha.RELEASE_URL else self.tag

    def run_update(self):
        return update_waha.update(self.root, self.fetch, datetime.date(2026, 11, 27))

    def assert_unchanged(self):
        for name, content in self.files.items():
            self.assertEqual((self.directory / name).read_text(encoding="utf-8"), content)

    def test_update_numeric_comparison_and_files(self):
        self.assertEqual(self.run_update(), "2026.10.1")
        docker = (self.directory / "Dockerfile").read_text()
        self.assertIn("FROM devlikeapro/waha:noweb-arm-2026.10.1@sha256:" + "a" * 64, docker)
        self.assertIn('version: "0.2.5"', (self.directory / "config.yaml").read_text())
        changelog = (self.directory / "CHANGELOG.md").read_text()
        self.assertIn("## 0.2.5 - 2026-11-27", changelog)
        self.assertLess(changelog.index("## 0.2.5"), changelog.index("## 0.2.4"))
        self.assertIn("`noweb-arm-2026.9.9` to `noweb-arm-2026.10.1`", changelog)
        self.assertIn("https://github.com/devlikeapro/waha/releases/tag/2026.10.1", changelog)
        self.assertEqual(self.calls, [update_waha.RELEASE_URL, update_waha.TAG_URL + "noweb-arm-2026.10.1"])

    def test_no_update_for_draft_prerelease_or_older(self):
        for change in ({"draft": True}, {"prerelease": True}, {"tag_name": "2026.9.9"}, {"tag_name": "2026.9.8"}):
            with self.subTest(change=change):
                self.release = {"draft": False, "prerelease": False, "tag_name": "2026.10.1", **change}
                self.calls.clear()
                self.assertIsNone(self.run_update())
                self.assertEqual(self.calls, [update_waha.RELEASE_URL])
                self.assert_unchanged()

    def test_existing_digest_is_replaced(self):
        path = self.directory / "Dockerfile"
        path.write_text(self.files["Dockerfile"].replace("noweb-arm-2026.9.9", "noweb-arm-2026.9.9@sha256:" + "b" * 64))
        self.run_update()
        self.assertIn("noweb-arm-2026.10.1@sha256:" + "a" * 64, path.read_text())

    def test_image_not_published(self):
        def fetch(url):
            if url == update_waha.RELEASE_URL:
                return self.release
            raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)
        self.assertIsNone(update_waha.update(self.root, fetch))
        self.assert_unchanged()

    def test_invalid_remote_inputs_leave_files_unchanged(self):
        for field, value in (
            ("tag_name", "2026.10.1-rc1"),
            ("tag_name", "20260.10.1"),
            ("tag_name", "２０２６.10.1"),
            ("draft", None),
        ):
            with self.subTest(field=field, value=value):
                original = self.release[field]
                self.release[field] = value
                with self.assertRaises(ValueError):
                    self.run_update()
                self.release[field] = original
                self.assert_unchanged()
        for field, value in (("name", "wrong"), ("digest", "sha256:bad"),
                             ("images", [{"os": "linux", "architecture": "amd64", "status": "active"}]),
                             ("images", [{"os": "linux", "architecture": "arm64", "status": "inactive"}])):
            with self.subTest(field=field):
                original = self.tag[field]
                self.tag[field] = value
                with self.assertRaises(ValueError):
                    self.run_update()
                self.tag[field] = original
                self.assert_unchanged()

    def test_surprising_files_fail_before_any_write(self):
        for name, bad in (("Dockerfile", "FROM another/image:latest\n"),
                          ("config.yaml", 'version: "0.2.4"\nversion: "0.2.4"\n'),
                          ("CHANGELOG.md", "# Changelog\n\n## 0.2.3 - 2026-10-01\n")):
            with self.subTest(name=name):
                path = self.directory / name
                path.write_text(bad)
                expected = {**self.files, name: bad}
                with self.assertRaises(ValueError):
                    self.run_update()
                for filename, content in expected.items():
                    self.assertEqual((self.directory / filename).read_text(), content)
                path.write_text(self.files[name])

    def test_cli_output_and_remote_failure(self):
        args = ["update_waha.py", "--root", str(self.root)]
        out, err = io.StringIO(), io.StringIO()
        with (
            patch("sys.argv", args),
            patch.object(update_waha, "get_json", side_effect=self.fetch),
            contextlib.redirect_stdout(out),
            contextlib.redirect_stderr(err),
        ):
            self.assertEqual(update_waha.main(), 0)
        self.assertEqual(out.getvalue(), "2026.10.1\n")
        self.assertEqual(err.getvalue(), "")
        out = io.StringIO()
        with (
            patch("sys.argv", args),
            patch.object(update_waha, "get_json", side_effect=self.fetch),
            contextlib.redirect_stdout(out),
        ):
            self.assertEqual(update_waha.main(), 0)
        self.assertEqual(out.getvalue(), "")
        out, err = io.StringIO(), io.StringIO()
        with (
            patch("sys.argv", args),
            patch.object(update_waha, "get_json", side_effect=urllib.error.URLError("service unavailable")),
            contextlib.redirect_stdout(out),
            contextlib.redirect_stderr(err),
        ):
            self.assertEqual(update_waha.main(), 1)
        self.assertEqual(out.getvalue(), "")
        self.assertIn("service unavailable", err.getvalue())


if __name__ == "__main__":
    unittest.main()
