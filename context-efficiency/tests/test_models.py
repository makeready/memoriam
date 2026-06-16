"""Tests for data models and config loading."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from models import (
    FilterRule,
    ToolCall,
    UtilizationScore,
    load_config,
)


class TestToolCall(unittest.TestCase):
    def test_to_dict_round_trip(self):
        tc = ToolCall(
            tool_name="Bash",
            tool_id="toolu_abc123",
            tool_input={"command": "pnpm compile:js"},
            result_text="Done in 3.2s",
            result_tokens=50,
        )
        d = tc.to_dict()
        restored = ToolCall.from_dict(d)
        self.assertEqual(tc, restored)

    def test_to_json_round_trip(self):
        tc = ToolCall(
            tool_name="Read",
            tool_id="toolu_xyz",
            tool_input={"file_path": "/tmp/foo.ts", "limit": 100},
            result_text="file contents here",
            result_tokens=120,
        )
        j = tc.to_json()
        restored = ToolCall.from_json(j)
        self.assertEqual(tc, restored)

    def test_defaults(self):
        tc = ToolCall(
            tool_name="Grep",
            tool_id="toolu_1",
            tool_input={},
            result_text="",
            result_tokens=0,
        )
        self.assertEqual(tc.tool_name, "Grep")
        self.assertEqual(tc.result_tokens, 0)


class TestUtilizationScore(unittest.TestCase):
    def test_to_dict_round_trip(self):
        score = UtilizationScore(
            substring_ratio=0.15,
            action_signal=0.8,
            null_response=0.0,
            composite=0.45,
        )
        d = score.to_dict()
        restored = UtilizationScore.from_dict(d)
        self.assertEqual(score, restored)

    def test_to_json_round_trip(self):
        score = UtilizationScore(
            substring_ratio=0.0,
            action_signal=0.0,
            null_response=1.0,
            composite=0.1,
        )
        j = score.to_json()
        restored = UtilizationScore.from_json(j)
        self.assertEqual(score, restored)


class TestFilterRule(unittest.TestCase):
    def test_to_dict_round_trip(self):
        rule = FilterRule(
            id="bash-compile-js",
            tool="Bash",
            pattern="compile:js",
            match_field="command",
            avg_output_tokens=2100,
            avg_utilization=0.02,
            sample_count=47,
            confidence=0.91,
            action="add_tail",
            action_params={"lines": 5},
            description="pnpm compile:js output averages 2100 tokens with 2% utilization",
        )
        d = rule.to_dict()
        restored = FilterRule.from_dict(d)
        self.assertEqual(rule, restored)

    def test_to_json_round_trip(self):
        rule = FilterRule(
            id="read-large-file",
            tool="Read",
            pattern=".*\\.generated\\.ts$",
            match_field="file_path",
            avg_output_tokens=5000,
            avg_utilization=0.05,
            sample_count=12,
            confidence=0.75,
            action="add_limit",
            action_params={"limit": 50},
            description="Generated TS files rarely referenced in full",
        )
        j = rule.to_json()
        restored = FilterRule.from_json(j)
        self.assertEqual(rule, restored)


class TestLoadConfig(unittest.TestCase):
    def test_returns_defaults_when_no_file(self):
        config = load_config(Path("/nonexistent/config.json"))
        self.assertFalse(config["enabled"])
        self.assertFalse(config["analyze_on_shutdown"])
        self.assertAlmostEqual(config["min_confidence"], 0.7)
        self.assertEqual(config["project_dirs"], [])
        self.assertFalse(config["hooks_enabled"])

    def test_returns_defaults_when_key_missing(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump({"track_token_usage": True}, f)
            f.flush()
            config = load_config(Path(f.name))
        os.unlink(f.name)
        self.assertFalse(config["enabled"])
        self.assertFalse(config["hooks_enabled"])

    def test_respects_all_toggles(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(
                {
                    "context_efficiency": {
                        "enabled": True,
                        "analyze_on_shutdown": True,
                        "min_confidence": 0.9,
                        "project_dirs": ["/tmp/project-a"],
                        "hooks_enabled": True,
                    }
                },
                f,
            )
            f.flush()
            config = load_config(Path(f.name))
        os.unlink(f.name)
        self.assertTrue(config["enabled"])
        self.assertTrue(config["analyze_on_shutdown"])
        self.assertAlmostEqual(config["min_confidence"], 0.9)
        self.assertEqual(config["project_dirs"], ["/tmp/project-a"])
        self.assertTrue(config["hooks_enabled"])

    def test_partial_overrides_keep_defaults(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(
                {"context_efficiency": {"enabled": True}},
                f,
            )
            f.flush()
            config = load_config(Path(f.name))
        os.unlink(f.name)
        self.assertTrue(config["enabled"])
        self.assertFalse(config["analyze_on_shutdown"])
        self.assertAlmostEqual(config["min_confidence"], 0.7)
        self.assertFalse(config["hooks_enabled"])


if __name__ == "__main__":
    unittest.main()
