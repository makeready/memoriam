"""Tests for the rule generator."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rule_generator import (
    determine_action,
    generate_report,
    generate_rules,
    score_confidence,
    write_staging_rules,
)


class TestScoreConfidence(unittest.TestCase):
    def test_high_sample_low_variance(self):
        confidence = score_confidence(sample_count=50, utilization_scores=[0.01] * 50)
        self.assertGreater(confidence, 0.8)

    def test_low_sample_count(self):
        confidence = score_confidence(sample_count=2, utilization_scores=[0.01, 0.02])
        self.assertLess(confidence, 0.5)

    def test_high_variance_reduces_confidence(self):
        # Mix of high and low utilization — inconsistent pattern
        scores = [0.01, 0.9, 0.02, 0.85, 0.05]
        confidence = score_confidence(sample_count=5, utilization_scores=scores)
        low_var = score_confidence(sample_count=5, utilization_scores=[0.01] * 5)
        self.assertLess(confidence, low_var)

    def test_single_sample(self):
        confidence = score_confidence(sample_count=1, utilization_scores=[0.01])
        self.assertLess(confidence, 0.3)


class TestDetermineAction(unittest.TestCase):
    def test_bash_gets_add_tail(self):
        action, params = determine_action("Bash", "pnpm compile:js", 2000)
        self.assertEqual(action, "add_tail")
        self.assertIn("lines", params)

    def test_read_gets_add_context(self):
        action, params = determine_action("Read", "Read .ts", 5000)
        self.assertEqual(action, "add_context")
        self.assertIn("note", params)

    def test_grep_gets_head_limit(self):
        action, params = determine_action("Grep", "Grep", 3000)
        self.assertEqual(action, "add_head_limit")
        self.assertIn("head_limit", params)

    def test_unknown_tool_gets_context(self):
        action, params = determine_action("Agent", "some pattern", 1000)
        self.assertEqual(action, "add_context")


class TestGenerateRules(unittest.TestCase):
    def test_generates_rules_above_threshold(self):
        patterns = {
            "Bash:pnpm compile:js": {
                "tool": "Bash",
                "pattern": "pnpm compile:js",
                "avg_output_tokens": 2000,
                "avg_utilization": 0.02,
                "sample_count": 50,
                "utilization_scores": [0.02] * 50,
            },
        }
        rules = generate_rules(patterns, min_confidence=0.7)
        self.assertEqual(len(rules), 1)
        self.assertEqual(rules[0].tool, "Bash")

    def test_excludes_rules_below_threshold(self):
        patterns = {
            "Bash:pnpm test": {
                "tool": "Bash",
                "pattern": "pnpm test",
                "avg_output_tokens": 500,
                "avg_utilization": 0.5,
                "sample_count": 2,
                "utilization_scores": [0.5, 0.5],
            },
        }
        rules = generate_rules(patterns, min_confidence=0.7)
        self.assertEqual(len(rules), 0)

    def test_excludes_high_utilization_patterns(self):
        patterns = {
            "Read:Read .ts": {
                "tool": "Read",
                "pattern": "Read .ts",
                "avg_output_tokens": 3000,
                "avg_utilization": 0.8,
                "sample_count": 50,
                "utilization_scores": [0.8] * 50,
            },
        }
        rules = generate_rules(patterns, min_confidence=0.7)
        self.assertEqual(len(rules), 0)


class TestWriteStagingRules(unittest.TestCase):
    def test_writes_json_file(self):
        from models import FilterRule

        rules = [
            FilterRule(
                id="bash-compile",
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
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            write_staging_rules(rules, output_dir)
            staging_path = output_dir / "rules.staging.json"
            self.assertTrue(staging_path.exists())

            data = json.loads(staging_path.read_text())
            self.assertEqual(len(data), 1)
            self.assertEqual(data[0]["id"], "bash-compile")


class TestGenerateReport(unittest.TestCase):
    def test_produces_markdown(self):
        from models import FilterRule

        rules = [
            FilterRule(
                id="bash-compile",
                tool="Bash",
                pattern="compile:js",
                match_field="command",
                avg_output_tokens=2000,
                avg_utilization=0.02,
                sample_count=50,
                confidence=0.9,
                action="add_tail",
                action_params={"lines": 5},
                description="compile output rarely referenced",
            )
        ]
        patterns = {
            "Bash:pnpm compile:js": {
                "tool": "Bash",
                "pattern": "pnpm compile:js",
                "avg_output_tokens": 2000,
                "avg_utilization": 0.02,
                "sample_count": 50,
                "utilization_scores": [0.02] * 50,
            }
        }
        report = generate_report(rules, patterns)
        self.assertIn("compile:js", report)
        self.assertIn("#", report)  # has markdown headers


if __name__ == "__main__":
    unittest.main()
