import importlib.util
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "scripts" / "mirror_instagram_covers.py"
SPEC = importlib.util.spec_from_file_location("mirror_instagram_covers", MODULE_PATH)
mirror = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(mirror)


class MirrorInstagramCoversTests(unittest.TestCase):
    def test_accepts_only_meta_image_cdn_hosts(self):
        self.assertTrue(mirror.is_meta_cdn_url("https://scontent-fra5-2.cdninstagram.com/image.jpg"))
        self.assertTrue(mirror.is_meta_cdn_url("https://lookaside.fbsbx.com/image.jpg".replace("fbsbx.com", "fbcdn.net")))
        self.assertFalse(mirror.is_meta_cdn_url("http://scontent-fra5-2.cdninstagram.com/image.jpg"))
        self.assertFalse(mirror.is_meta_cdn_url("https://cdninstagram.com.evil.example/image.jpg"))

    def test_manifest_write_is_parseable(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"
            mirror.atomic_json_write(path, {"schema_version": 1, "covers": {"42": {"url": "https://example.test/a.jpg"}}})
            self.assertEqual(mirror.load_manifest(path)["covers"]["42"]["url"], "https://example.test/a.jpg")

    def test_workflow_commits_new_untracked_covers(self):
        workflow = (Path(__file__).parents[1] / ".github" / "workflows" / "mirror-instagram-covers.yml").read_text(encoding="utf-8")
        self.assertIn("git status --porcelain -- instagram-covers", workflow)
        self.assertNotIn("git diff --quiet -- instagram-covers", workflow)


if __name__ == "__main__":
    unittest.main()
