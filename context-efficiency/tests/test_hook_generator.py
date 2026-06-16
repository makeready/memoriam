"""Tests for the hook generator."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hook_generator import generate_hook_script, generate_settings_fragment
from models import FilterRule


def _make_rule(**kwargs) -> FilterRule:
    defaults = dict(
        id="test-rule",
        tool="Bash",
        pattern="compile:js",
        match_field="command",
        avg_output_tokens=2000,
        avg_utilization=0.02,
        sample_count=50,
        confidence=0.9,
        action="add_tail",
        action_params={"lines": 5},
        description="test rule",
    )
    defaults.update(kwargs)
    return FilterRule(**defaults)


class TestGenerateHookScript(unittest.TestCase):
    def test_produces_valid_python(self):
        script = generate_hook_script(Path("/tmp/rules.json"), Path("/tmp/config.json"))
        # Should be parseable Python
        compile(script, "<hook>", "exec")

    def test_reads_stdin_and_exits_cleanly(self):
        """The hook script should read JSON from stdin and exit 0."""
        rules = [_make_rule()]
        with tempfile.TemporaryDirectory() as tmpdir:
            rules_path = Path(tmpdir) / "rules.json"
            rules_path.write_text(json.dumps([r.to_dict() for r in rules]))

            config_path = Path(tmpdir) / "config.json"
            config_path.write_text(json.dumps({
                "context_efficiency": {"enabled": True, "hooks_enabled": True}
            }))

            script = generate_hook_script(rules_path, config_path)
            script_path = Path(tmpdir) / "hook.py"
            script_path.write_text(script)

            stdin_data = json.dumps({
                "tool_name": "Bash",
                "tool_input": {"command": "pnpm --filter {./}... compile:js"},
            })

            result = subprocess.run(
                [sys.executable, str(script_path)],
                input=stdin_data,
                capture_output=True,
                text=True,
                timeout=5,
            )
            self.assertEqual(result.returncode, 0)

    def test_modifies_bash_command(self):
        rules = [_make_rule(action="add_tail", action_params={"lines": 5})]
        with tempfile.TemporaryDirectory() as tmpdir:
            rules_path = Path(tmpdir) / "rules.json"
            rules_path.write_text(json.dumps([r.to_dict() for r in rules]))

            config_path = Path(tmpdir) / "config.json"
            config_path.write_text(json.dumps({
                "context_efficiency": {"enabled": True, "hooks_enabled": True}
            }))

            script = generate_hook_script(rules_path, config_path)
            script_path = Path(tmpdir) / "hook.py"
            script_path.write_text(script)

            stdin_data = json.dumps({
                "tool_name": "Bash",
                "tool_input": {"command": "pnpm --filter {./}... compile:js"},
            })

            result = subprocess.run(
                [sys.executable, str(script_path)],
                input=stdin_data,
                capture_output=True,
                text=True,
                timeout=5,
            )
            output = json.loads(result.stdout)
            updated = output["hookSpecificOutput"]["updatedInput"]["command"]
            self.assertIn("tail", updated)

    def test_adds_limit_to_read(self):
        rules = [_make_rule(
            id="read-large",
            tool="Read",
            pattern="Read .ts",
            match_field="file_path",
            action="add_limit",
            action_params={"limit": 50},
        )]
        with tempfile.TemporaryDirectory() as tmpdir:
            rules_path = Path(tmpdir) / "rules.json"
            rules_path.write_text(json.dumps([r.to_dict() for r in rules]))

            config_path = Path(tmpdir) / "config.json"
            config_path.write_text(json.dumps({
                "context_efficiency": {"enabled": True, "hooks_enabled": True}
            }))

            script = generate_hook_script(rules_path, config_path)
            script_path = Path(tmpdir) / "hook.py"
            script_path.write_text(script)

            stdin_data = json.dumps({
                "tool_name": "Read",
                "tool_input": {"file_path": "/tmp/project/src/foo.ts"},
            })

            result = subprocess.run(
                [sys.executable, str(script_path)],
                input=stdin_data,
                capture_output=True,
                text=True,
                timeout=5,
            )
            output = json.loads(result.stdout)
            updated = output["hookSpecificOutput"]["updatedInput"]
            self.assertEqual(updated["limit"], 50)

    def test_passthrough_for_non_matching(self):
        rules = [_make_rule()]
        with tempfile.TemporaryDirectory() as tmpdir:
            rules_path = Path(tmpdir) / "rules.json"
            rules_path.write_text(json.dumps([r.to_dict() for r in rules]))

            config_path = Path(tmpdir) / "config.json"
            config_path.write_text(json.dumps({
                "context_efficiency": {"enabled": True, "hooks_enabled": True}
            }))

            script = generate_hook_script(rules_path, config_path)
            script_path = Path(tmpdir) / "hook.py"
            script_path.write_text(script)

            stdin_data = json.dumps({
                "tool_name": "Bash",
                "tool_input": {"command": "git status"},
            })

            result = subprocess.run(
                [sys.executable, str(script_path)],
                input=stdin_data,
                capture_output=True,
                text=True,
                timeout=5,
            )
            self.assertEqual(result.returncode, 0)
            # No output means passthrough
            self.assertEqual(result.stdout.strip(), "")

    def test_noop_when_hooks_disabled(self):
        rules = [_make_rule()]
        with tempfile.TemporaryDirectory() as tmpdir:
            rules_path = Path(tmpdir) / "rules.json"
            rules_path.write_text(json.dumps([r.to_dict() for r in rules]))

            config_path = Path(tmpdir) / "config.json"
            config_path.write_text(json.dumps({
                "context_efficiency": {"enabled": True, "hooks_enabled": False}
            }))

            script = generate_hook_script(rules_path, config_path)
            script_path = Path(tmpdir) / "hook.py"
            script_path.write_text(script)

            stdin_data = json.dumps({
                "tool_name": "Bash",
                "tool_input": {"command": "pnpm --filter {./}... compile:js"},
            })

            result = subprocess.run(
                [sys.executable, str(script_path)],
                input=stdin_data,
                capture_output=True,
                text=True,
                timeout=5,
            )
            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout.strip(), "")


class TestGenerateSettingsFragment(unittest.TestCase):
    def test_produces_valid_hook_config(self):
        fragment = generate_settings_fragment(Path("/tmp/hook.py"))
        self.assertIn("PreToolUse", fragment)
        hook_list = fragment["PreToolUse"]
        self.assertEqual(len(hook_list), 1)
        self.assertIn("matcher", hook_list[0])
        self.assertIn("hooks", hook_list[0])
        self.assertEqual(hook_list[0]["hooks"][0]["type"], "command")


if __name__ == "__main__":
    unittest.main()
