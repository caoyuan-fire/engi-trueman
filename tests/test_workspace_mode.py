"""Exercise real files and fresh CLI processes; leave the user's workspace untouched."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "workspace_mode.py"
BEGIN = b"<!-- engi-trueman:workspace -->"
END = b"<!-- /engi-trueman:workspace -->"


class WorkspaceModeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="engi-trueman-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.agents = self.root / "AGENTS.md"

    def run_mode(self, action, check=True):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), action, "--workspace", str(self.root)],
            capture_output=True, text=True, check=check,
        )
        return json.loads(result.stdout) if check else result

    def test_status_does_not_create_files(self):
        state = self.run_mode("status")
        self.assertEqual(state["mode"], "off")
        self.assertFalse(state["configured"])
        self.assertEqual(list(self.root.iterdir()), [])

    def test_on_persists_full_contract_and_preserves_original_bytes(self):
        original = "# 团队约定\r\n使用项目命令。\r\n末行不补换行".encode()
        self.agents.write_bytes(original)
        self.agents.chmod(0o640)
        state = self.run_mode("on")
        content = self.agents.read_bytes()
        self.assertTrue(state["changed"])
        self.assertTrue(content.endswith(original))
        self.assertTrue(content.startswith(BEGIN))
        self.assertIn("## 判断有依据".encode(), content)
        self.assertIn("## 工程有分寸".encode(), content)
        self.assertIn("## 表达具体自然".encode(), content)
        self.assertNotIn(b"references/examples.md", content)
        self.assertEqual(self.agents.stat().st_mode & 0o777, 0o640)
        self.assertEqual(self.run_mode("status")["mode"], "on")
        self.assertFalse(self.run_mode("on")["changed"])
        self.assertEqual(self.agents.read_bytes(), content)

    def test_off_removes_contract_and_keeps_persistent_off_state(self):
        original = b"# Existing rules\nKeep these."
        self.agents.write_bytes(original)
        self.run_mode("on")
        self.run_mode("off")
        content = self.agents.read_bytes()
        self.assertTrue(content.endswith(original))
        self.assertIn(b"mode: off", content)
        self.assertNotIn("## 判断有依据".encode(), content)
        self.assertEqual(self.run_mode("status")["mode"], "off")
        self.assertTrue(self.run_mode("status")["configured"])
        self.assertFalse(self.run_mode("off")["changed"])
        self.run_mode("on")
        self.assertEqual(self.run_mode("status")["mode"], "on")

    def test_off_without_prior_on_is_persistent(self):
        self.run_mode("off")
        self.assertEqual(self.run_mode("status")["mode"], "off")
        self.assertTrue(self.run_mode("status")["configured"])

    def test_active_override_wins_and_regular_agents_stays_unchanged(self):
        self.agents.write_bytes(b"Regular rules\n")
        override = self.root / "AGENTS.override.md"
        override.write_bytes(b"Override rules\n")
        state = self.run_mode("on")
        self.assertEqual(state["instruction_file"], str(override))
        self.assertEqual(self.agents.read_bytes(), b"Regular rules\n")
        self.assertTrue(override.read_bytes().endswith(b"Override rules\n"))
        self.run_mode("off")
        self.assertEqual(self.run_mode("status")["mode"], "off")
        self.assertEqual(self.agents.read_bytes(), b"Regular rules\n")

    def test_empty_override_does_not_hide_regular_instructions(self):
        override = self.root / "AGENTS.override.md"
        override.write_bytes(b"")
        self.assertEqual(self.run_mode("on")["instruction_file"], str(self.agents))
        self.assertEqual(override.read_bytes(), b"")

    def test_existing_block_replacement_preserves_both_sides(self):
        self.run_mode("on")
        body = self.agents.read_bytes()
        managed = body[:body.index(END) + len(END)]
        prefix, suffix = b"# Before\r\n\r\n", b"\n# After\nExact suffix"
        self.agents.write_bytes(prefix + managed + suffix)
        self.run_mode("off")
        updated = self.agents.read_bytes()
        self.assertEqual(updated[:updated.index(BEGIN)], prefix)
        self.assertEqual(updated[updated.index(END) + len(END):], suffix)

    def test_malformed_markers_fail_without_overwriting_user_content(self):
        for content in (BEGIN + b"\nUser rules", END + b"\n" + BEGIN, BEGIN + b"\n" + BEGIN + END):
            with self.subTest(content=content):
                self.agents.write_bytes(content)
                result = self.run_mode("on", check=False)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(self.agents.read_bytes(), content)

    def test_symlink_does_not_modify_shared_instructions(self):
        shared = self.root / "shared.md"
        shared.write_bytes(b"Shared instructions\n")
        self.agents.symlink_to(shared)
        result = self.run_mode("on", check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(self.agents.is_symlink())
        self.assertEqual(shared.read_bytes(), b"Shared instructions\n")


if __name__ == "__main__":
    unittest.main()
