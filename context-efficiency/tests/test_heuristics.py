"""Tests for utilization detection heuristics."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from heuristics import (
    META_TOOLS,
    _paths_share_module,
    _stems_match,
    compute_substring_overlap,
    compute_utilization,
    detect_action_signal,
    detect_read_action_signal,
    detect_null_response,
    extract_distinctive_tokens,
)


class TestExtractDistinctiveTokens(unittest.TestCase):
    def test_extracts_identifiers(self):
        text = "import { getMaxStableOrdinalForSubscription } from '../repository';"
        tokens = extract_distinctive_tokens(text)
        self.assertIn("getMaxStableOrdinalForSubscription", tokens)

    def test_ignores_short_strings(self):
        text = "const x = foo + bar;"
        tokens = extract_distinctive_tokens(text)
        # All tokens here are <= 8 chars
        self.assertEqual(tokens, set())

    def test_ignores_common_keywords(self):
        text = "function something return undefined"
        tokens = extract_distinctive_tokens(text)
        self.assertNotIn("function", tokens)
        self.assertNotIn("undefined", tokens)
        self.assertIn("something", tokens)

    def test_empty_input(self):
        self.assertEqual(extract_distinctive_tokens(""), set())

    def test_extracts_file_paths(self):
        text = "src/repository/order/order.ts\n  7:3   error  Something"
        tokens = extract_distinctive_tokens(text)
        self.assertIn("src/repository/order/order.ts", tokens)


class TestComputeSubstringOverlap(unittest.TestCase):
    def test_full_overlap(self):
        tool_result = "getMaxStableOrdinalForSubscription returned 5"
        assistant_text = ["The getMaxStableOrdinalForSubscription function returned 5"]
        ratio = compute_substring_overlap(tool_result, assistant_text)
        self.assertGreater(ratio, 0.5)

    def test_no_overlap(self):
        tool_result = "getMaxStableOrdinalForSubscription returned 5"
        assistant_text = ["I'll check the database now."]
        ratio = compute_substring_overlap(tool_result, assistant_text)
        self.assertAlmostEqual(ratio, 0.0)

    def test_partial_overlap(self):
        tool_result = (
            "getMaxStableOrdinalForSubscription returned 5\n"
            "fetchInitialSubscriptionSnapshotRulesContext loaded\n"
            "buildInstantSubscriptionCart completed"
        )
        assistant_text = [
            "The getMaxStableOrdinalForSubscription function works correctly."
        ]
        ratio = compute_substring_overlap(tool_result, assistant_text)
        self.assertGreater(ratio, 0.0)
        self.assertLess(ratio, 1.0)

    def test_empty_result(self):
        ratio = compute_substring_overlap("", ["some text"])
        self.assertAlmostEqual(ratio, 0.0)

    def test_empty_assistant(self):
        ratio = compute_substring_overlap("someIdentifier here", [])
        self.assertAlmostEqual(ratio, 0.0)


class TestStemsMatch(unittest.TestCase):
    def test_test_source_pair_ts(self):
        self.assertTrue(_stems_match("/src/order.test.ts", "/src/order.ts"))

    def test_test_source_pair_tsx(self):
        self.assertTrue(_stems_match("/src/OrderInfo.test.tsx", "/src/OrderInfo.tsx"))

    def test_medium_test(self):
        self.assertTrue(_stems_match("/src/order.medium-test.ts", "/src/order.ts"))

    def test_spec_file(self):
        self.assertTrue(_stems_match("/src/order.spec.ts", "/src/order.ts"))

    def test_same_file_does_not_match(self):
        self.assertFalse(_stems_match("/src/order.ts", "/src/order.ts"))

    def test_unrelated_files(self):
        self.assertFalse(_stems_match("/src/order.ts", "/src/subscription.ts"))


class TestPathsShareModule(unittest.TestCase):
    def test_same_directory(self):
        self.assertTrue(_paths_share_module("/src/orders/Foo.ts", "/src/orders/Bar.ts"))

    def test_parent_child(self):
        self.assertTrue(_paths_share_module("/src/orders/Foo.ts", "/src/orders/utils/helper.ts"))

    def test_unrelated_dirs(self):
        self.assertFalse(_paths_share_module("/src/orders/Foo.ts", "/lib/auth/Bar.ts"))


class TestDetectReadActionSignal(unittest.TestCase):
    def test_edit_same_file(self):
        signal = detect_read_action_signal(
            "/tmp/foo.ts",
            next_actions=[{"name": "Edit", "input": {"file_path": "/tmp/foo.ts"}}],
            extended_next_actions=[{"name": "Edit", "input": {"file_path": "/tmp/foo.ts"}}],
        )
        self.assertEqual(signal, 1.0)

    def test_edit_test_source_pair(self):
        signal = detect_read_action_signal(
            "/src/OrderInfo.test.tsx",
            next_actions=[],
            extended_next_actions=[
                {"name": "Edit", "input": {"file_path": "/src/OrderInfo.tsx"}}
            ],
        )
        self.assertAlmostEqual(signal, 0.9)

    def test_edit_same_module(self):
        signal = detect_read_action_signal(
            "/src/orders/types.ts",
            next_actions=[],
            extended_next_actions=[
                {"name": "Edit", "input": {"file_path": "/src/orders/OrderInfo.tsx"}}
            ],
        )
        self.assertGreaterEqual(signal, 0.7)

    def test_comprehension_read_before_unrelated_edit(self):
        """Read file A, then edit unrelated file B — still a comprehension read."""
        signal = detect_read_action_signal(
            "/lib/utils/helpers.ts",
            next_actions=[],
            extended_next_actions=[
                {"name": "Edit", "input": {"file_path": "/src/features/dashboard.tsx"}}
            ],
        )
        self.assertGreaterEqual(signal, 0.4)

    def test_read_explore_same_directory(self):
        signal = detect_read_action_signal(
            "/src/orders/Foo.ts",
            next_actions=[],
            extended_next_actions=[
                {"name": "Read", "input": {"file_path": "/src/orders/Bar.ts"}}
            ],
        )
        self.assertAlmostEqual(signal, 0.5)

    def test_no_followup_actions(self):
        signal = detect_read_action_signal(
            "/tmp/foo.ts",
            next_actions=[],
            extended_next_actions=[],
        )
        self.assertAlmostEqual(signal, 0.0)

    def test_edit_found_in_extended_window_not_immediate(self):
        """Edit happens in a later message, not the immediate next one."""
        signal = detect_read_action_signal(
            "/src/order.ts",
            next_actions=[
                {"name": "Read", "input": {"file_path": "/src/types.ts"}}
            ],
            extended_next_actions=[
                {"name": "Read", "input": {"file_path": "/src/types.ts"}},
                {"name": "Read", "input": {"file_path": "/src/utils.ts"}},
                {"name": "Edit", "input": {"file_path": "/src/order.ts"}},
            ],
        )
        self.assertEqual(signal, 1.0)

    def test_empty_file_path(self):
        signal = detect_read_action_signal(
            "",
            next_actions=[{"name": "Edit", "input": {"file_path": "/tmp/foo.ts"}}],
            extended_next_actions=[],
        )
        self.assertAlmostEqual(signal, 0.0)


class TestDetectActionSignal(unittest.TestCase):
    def test_read_delegates_to_read_signal(self):
        """Read tool should use the Read-specific heuristic."""
        signal = detect_action_signal(
            tool_name="Read",
            tool_input={"file_path": "/tmp/foo.ts"},
            next_actions=[
                {"name": "Edit", "input": {"file_path": "/tmp/foo.ts"}}
            ],
        )
        self.assertGreater(signal, 0.5)

    def test_read_uses_extended_window(self):
        signal = detect_action_signal(
            tool_name="Read",
            tool_input={"file_path": "/src/order.test.ts"},
            next_actions=[],
            extended_next_actions=[
                {"name": "Edit", "input": {"file_path": "/src/order.ts"}}
            ],
        )
        self.assertAlmostEqual(signal, 0.9)

    def test_grep_followed_by_read_of_match(self):
        signal = detect_action_signal(
            tool_name="Grep",
            tool_input={"pattern": "something"},
            next_actions=[
                {"name": "Read", "input": {"file_path": "/tmp/matched.ts"}}
            ],
            result_text="/tmp/matched.ts\n/tmp/other.ts",
        )
        self.assertGreater(signal, 0.5)

    def test_grep_followed_by_edit_of_match(self):
        signal = detect_action_signal(
            tool_name="Grep",
            tool_input={"pattern": "something"},
            next_actions=[
                {"name": "Edit", "input": {"file_path": "/tmp/matched.ts"}}
            ],
            result_text="/tmp/matched.ts\n/tmp/other.ts",
        )
        self.assertGreater(signal, 0.5)

    def test_grep_followed_by_another_grep(self):
        signal = detect_action_signal(
            tool_name="Grep",
            tool_input={"pattern": "something"},
            next_actions=[
                {"name": "Grep", "input": {"pattern": "something else"}}
            ],
        )
        self.assertAlmostEqual(signal, 0.5)

    def test_bash_followed_by_read_of_output_path(self):
        signal = detect_action_signal(
            tool_name="Bash",
            tool_input={"command": "ls -la"},
            next_actions=[
                {"name": "Read", "input": {"file_path": "/tmp/project/config.json"}}
            ],
            result_text="total 24\n-rw-r--r-- 1 user staff  120 Mar 18 /tmp/project/config.json\n",
        )
        self.assertGreater(signal, 0.5)

    def test_empty_next_actions(self):
        signal = detect_action_signal(
            tool_name="Read",
            tool_input={"file_path": "/tmp/foo.ts"},
            next_actions=[],
        )
        self.assertAlmostEqual(signal, 0.0)


class TestDetectNullResponse(unittest.TestCase):
    def test_short_transition_text(self):
        score = detect_null_response("Let me check the next file.")
        self.assertGreater(score, 0.5)

    def test_substantive_response(self):
        long_text = (
            "The function getMaxStableOrdinalForSubscription queries the orders "
            "table and returns the maximum stableOrdinal value. Looking at the "
            "implementation, it filters by payment status and shipment status "
            "using an OR condition, which means an order qualifies if it has "
            "either a paid-like payment status or a Delivered shipment status."
        )
        score = detect_null_response(long_text)
        self.assertAlmostEqual(score, 0.0)

    def test_empty_response(self):
        score = detect_null_response("")
        self.assertGreater(score, 0.5)


class TestComputeUtilization(unittest.TestCase):
    def test_high_utilization(self):
        tool_result = "getMaxStableOrdinalForSubscription returned 5"
        assistant_texts = [
            "The getMaxStableOrdinalForSubscription function returned 5, "
            "which confirms the ordinal is correct."
        ]
        score = compute_utilization(
            tool_result=tool_result,
            assistant_texts=assistant_texts,
            next_actions=[],
        )
        self.assertGreater(score.composite, 0.3)

    def test_low_utilization(self):
        tool_result = "Done in 3.2s\n" * 50  # verbose build output
        assistant_texts = ["Let me check the tests now."]
        score = compute_utilization(
            tool_result=tool_result,
            assistant_texts=assistant_texts,
            next_actions=[],
        )
        self.assertLess(score.composite, 0.3)

    def test_action_based_utilization(self):
        tool_result = "export function getMaxStableOrdinalForSubscription() { return this.model.max('stableOrdinal'); }"
        assistant_texts = [""]
        score = compute_utilization(
            tool_result=tool_result,
            assistant_texts=assistant_texts,
            next_actions=[
                {"name": "Edit", "input": {"file_path": "/tmp/foo.ts"}}
            ],
            tool_name="Read",
            tool_input={"file_path": "/tmp/foo.ts"},
        )
        self.assertGreater(score.action_signal, 0.5)

    def test_read_weights_favor_action_over_substring(self):
        """Read with strong action signal but zero substring overlap should score well."""
        tool_result = "export function buildOrder() { /* complex logic */ }\n" * 20
        assistant_texts = ["Let me fix the issue."]  # no quoting
        score = compute_utilization(
            tool_result=tool_result,
            assistant_texts=assistant_texts,
            next_actions=[
                {"name": "Edit", "input": {"file_path": "/tmp/order.ts"}}
            ],
            tool_name="Read",
            tool_input={"file_path": "/tmp/order.ts"},
        )
        # With Read weights: 0.1*0 + 0.7*1.0 + 0.2*1.0 = 0.9
        self.assertGreater(score.composite, 0.7)

    def test_read_extended_window_boosts_score(self):
        """Read followed by edit in extended window (not immediate) should score well."""
        tool_result = "export function orderHelper() { return 42; }\n" * 10
        assistant_texts = [""]
        score = compute_utilization(
            tool_result=tool_result,
            assistant_texts=assistant_texts,
            next_actions=[],  # no immediate actions
            tool_name="Read",
            tool_input={"file_path": "/src/orders/helper.ts"},
            extended_next_actions=[
                {"name": "Read", "input": {"file_path": "/src/orders/types.ts"}},
                {"name": "Edit", "input": {"file_path": "/src/orders/helper.ts"}},
            ],
        )
        self.assertGreater(score.composite, 0.5)

    def test_meta_tools_always_utilized(self):
        for tool in ["AskUserQuestion", "WebSearch", "ExitPlanMode", "TaskCreate"]:
            score = compute_utilization(
                tool_result="some verbose output " * 50,
                assistant_texts=["unrelated response"],
                next_actions=[],
                tool_name=tool,
            )
            self.assertAlmostEqual(score.composite, 1.0, msg=f"{tool} should always be 1.0")

    def test_skips_tiny_output(self):
        tool_result = "ok"
        assistant_texts = ["Done."]
        score = compute_utilization(
            tool_result=tool_result,
            assistant_texts=assistant_texts,
            next_actions=[],
        )
        # Tiny output shouldn't be flagged as waste
        self.assertGreater(score.composite, 0.5)


if __name__ == "__main__":
    unittest.main()
