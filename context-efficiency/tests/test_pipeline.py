"""Tests for the pipeline orchestrator."""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import discover_project_dirs, run_analysis, run_rule_generation

FIXTURES = Path(__file__).resolve().parent / "fixtures"


class TestDiscoverProjectDirs(unittest.TestCase):
    def test_returns_empty_for_nonexistent(self):
        dirs = discover_project_dirs(Path("/nonexistent"))
        self.assertEqual(dirs, [])

    def test_finds_subdirectories(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "project-a").mkdir()
            (Path(tmpdir) / "project-b").mkdir()
            dirs = discover_project_dirs(Path(tmpdir))
            self.assertEqual(len(dirs), 2)


class TestRunAnalysis(unittest.TestCase):
    def test_analyzes_fixture_sessions(self):
        all_pairs, patterns = run_analysis([FIXTURES])
        self.assertGreater(len(all_pairs), 0)
        self.assertGreater(len(patterns), 0)

    def test_handles_empty_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            all_pairs, patterns = run_analysis([Path(tmpdir)])
            self.assertEqual(len(all_pairs), 0)
            self.assertEqual(len(patterns), 0)


class TestRunRuleGeneration(unittest.TestCase):
    def test_generates_report(self):
        import pipeline
        original_reports = pipeline.REPORTS_DIR

        with tempfile.TemporaryDirectory() as tmpdir:
            pipeline.REPORTS_DIR = Path(tmpdir)
            pipeline.RULES_DIR = Path(tmpdir)

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
            rules = run_rule_generation(patterns, min_confidence=0.7)
            self.assertGreater(len(rules), 0)

            report_path = Path(tmpdir) / "latest-report.md"
            self.assertTrue(report_path.exists())

            pipeline.REPORTS_DIR = original_reports


class TestFullPipeline(unittest.TestCase):
    def test_end_to_end_with_fixtures(self):
        """Run the full pipeline on fixture data."""
        all_pairs, patterns = run_analysis([FIXTURES])
        self.assertGreater(len(all_pairs), 0)

        # With a very low confidence threshold, should produce some rules
        import pipeline
        with tempfile.TemporaryDirectory() as tmpdir:
            pipeline.REPORTS_DIR = Path(tmpdir)
            pipeline.RULES_DIR = Path(tmpdir)
            rules = run_rule_generation(patterns, min_confidence=0.0)
            # Should have at least generated a report
            self.assertTrue((Path(tmpdir) / "latest-report.md").exists())

    def test_config_toggle_respected(self):
        """Pipeline should exit early when disabled."""
        from models import load_config

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"context_efficiency": {"enabled": False}}, f)
            f.flush()
            config = load_config(Path(f.name))
            self.assertFalse(config["enabled"])
        import os
        os.unlink(f.name)


if __name__ == "__main__":
    unittest.main()
