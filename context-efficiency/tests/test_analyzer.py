"""Tests for the session transcript analyzer."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from analyzer import (
    aggregate_patterns,
    find_session_files,
    parse_session,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"


class TestParseSession(unittest.TestCase):
    def test_extracts_tool_pairs(self):
        pairs = parse_session(FIXTURES / "sample-session.jsonl")
        # Fixture has 3 tool uses: Read, Bash (compile), Bash (test)
        # Edit result is trivial ("File updated successfully") so still counted
        tool_names = [p["tool_name"] for p in pairs]
        self.assertEqual(tool_names, ["Read", "Bash", "Bash"])

    def test_pairs_have_result_text(self):
        pairs = parse_session(FIXTURES / "sample-session.jsonl")
        # First pair is the Read call
        self.assertIn("getMaxStableOrdinalForSubscription", pairs[0]["result_text"])

    def test_pairs_have_subsequent_assistant_context(self):
        pairs = parse_session(FIXTURES / "sample-session.jsonl")
        # After the Read call, assistant said "The getMaxStableOrdinalForSubscription..."
        # and made an Edit action
        first = pairs[0]
        self.assertTrue(len(first["assistant_texts"]) > 0)
        self.assertIn("getMaxStableOrdinalForSubscription", first["assistant_texts"][0])

    def test_pairs_have_next_actions(self):
        pairs = parse_session(FIXTURES / "sample-session.jsonl")
        first = pairs[0]
        # After Reading the file, assistant edited it
        self.assertTrue(len(first["next_actions"]) > 0)
        self.assertEqual(first["next_actions"][0]["name"], "Edit")

    def test_pairs_include_tool_input(self):
        pairs = parse_session(FIXTURES / "sample-session.jsonl")
        self.assertEqual(pairs[0]["tool_input"]["file_path"], "/tmp/project/src/order.ts")

    def test_pairs_have_extended_next_actions(self):
        pairs = parse_session(FIXTURES / "sample-session.jsonl")
        first = pairs[0]
        self.assertIn("extended_next_actions", first)
        # Extended window should include actions from multiple future messages
        self.assertIsInstance(first["extended_next_actions"], list)

    def test_compile_output_has_low_utilization_context(self):
        pairs = parse_session(FIXTURES / "sample-session.jsonl")
        # The compile:js call (index 1) was followed by "Now let me run the tests."
        compile_pair = pairs[1]
        self.assertTrue(len(compile_pair["assistant_texts"]) > 0)


class TestFindSessionFiles(unittest.TestCase):
    def test_finds_jsonl_in_directory(self):
        files = find_session_files(FIXTURES)
        self.assertTrue(any(f.name == "sample-session.jsonl" for f in files))

    def test_returns_empty_for_missing_dir(self):
        files = find_session_files(Path("/nonexistent/dir"))
        self.assertEqual(files, [])


class TestAggregatePatterns(unittest.TestCase):
    def test_aggregates_by_tool_and_pattern(self):
        pairs = parse_session(FIXTURES / "sample-session.jsonl")
        patterns = aggregate_patterns(pairs)

        # Should have entries keyed by (tool, pattern)
        self.assertIsInstance(patterns, dict)
        self.assertTrue(len(patterns) > 0)

    def test_pattern_has_required_fields(self):
        pairs = parse_session(FIXTURES / "sample-session.jsonl")
        patterns = aggregate_patterns(pairs)

        for key, data in patterns.items():
            self.assertIn("tool", data)
            self.assertIn("pattern", data)
            self.assertIn("avg_output_tokens", data)
            self.assertIn("avg_utilization", data)
            self.assertIn("sample_count", data)
            self.assertIn("utilization_scores", data)

    def test_compile_pattern_extracted(self):
        pairs = parse_session(FIXTURES / "sample-session.jsonl")
        patterns = aggregate_patterns(pairs)

        # Should have a pattern for compile:js
        compile_keys = [k for k in patterns if "compile:js" in k]
        self.assertTrue(len(compile_keys) > 0)


if __name__ == "__main__":
    unittest.main()
