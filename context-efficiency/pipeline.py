"""Orchestrator: run the full context-efficiency pipeline."""

import json
import sys
from pathlib import Path

from analyzer import aggregate_patterns, find_session_files, parse_session
from hook_generator import write_hooks
from models import load_config
from rule_generator import generate_report, generate_rules, write_staging_rules

MODULE_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = MODULE_DIR.parent / "config.json"
DEFAULT_CLAUDE_DIR = Path.home() / ".claude" / "projects"
RULES_DIR = MODULE_DIR / "rules"
REPORTS_DIR = MODULE_DIR / "reports"
HOOKS_DIR = MODULE_DIR / "hooks"


def discover_project_dirs(claude_dir: Path) -> list[Path]:
    """Auto-discover Claude project directories."""
    if not claude_dir.exists():
        return []
    return [p for p in claude_dir.iterdir() if p.is_dir()]


def run_analysis(
    project_dirs: list[Path],
) -> tuple[list[dict], dict]:
    """Run analysis across all sessions in the given project directories.

    Returns (all_pairs, aggregated_patterns).
    """
    all_pairs = []

    for project_dir in project_dirs:
        session_files = find_session_files(project_dir)
        for session_file in session_files:
            try:
                pairs = parse_session(session_file)
                all_pairs.extend(pairs)
            except Exception:
                continue

    patterns = aggregate_patterns(all_pairs) if all_pairs else {}
    return all_pairs, patterns


def run_rule_generation(
    patterns: dict, min_confidence: float
) -> list:
    """Generate rules from patterns and write to staging."""
    rules = generate_rules(patterns, min_confidence=min_confidence)

    if rules:
        write_staging_rules(rules, RULES_DIR)

    report = generate_report(rules, patterns)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS_DIR / "latest-report.md"
    report_path.write_text(report)

    return rules


def run_hook_generation(rules: list, config_path: Path) -> None:
    """Generate hook script from active rules."""
    rules_path = RULES_DIR / "rules.json"
    if not rules_path.exists():
        print("No active rules.json found. Promote rules from staging first.")
        return

    write_hooks(
        rules=rules,
        rules_path=rules_path,
        config_path=config_path,
        output_dir=HOOKS_DIR,
    )
    print(f"Hook script written to {HOOKS_DIR / 'filter-tool-input.py'}")
    print(f"Settings fragment written to {HOOKS_DIR / 'settings-fragment.json'}")


def main():
    config_path = DEFAULT_CONFIG_PATH
    config = load_config(config_path)

    if not config["enabled"]:
        print("Context efficiency is disabled. Set enabled=true in config.json.")
        sys.exit(0)

    # Determine project directories
    project_dirs = [Path(p) for p in config["project_dirs"]]
    if not project_dirs:
        project_dirs = discover_project_dirs(DEFAULT_CLAUDE_DIR)

    if not project_dirs:
        print("No project directories found.")
        sys.exit(1)

    print(f"Analyzing {len(project_dirs)} project directories...")

    # Phase 1: Analyze
    all_pairs, patterns = run_analysis(project_dirs)
    print(f"Found {len(all_pairs)} tool calls across {len(patterns)} patterns.")

    # Phase 2: Generate rules
    min_confidence = config["min_confidence"]
    rules = run_rule_generation(patterns, min_confidence)
    print(f"Generated {len(rules)} rules (min confidence: {min_confidence}).")

    if rules:
        print(f"Staging rules written to {RULES_DIR / 'rules.staging.json'}")
        print(f"Report written to {REPORTS_DIR / 'latest-report.md'}")

    # Phase 3: Generate hooks (only if active rules exist)
    if config["hooks_enabled"]:
        run_hook_generation(rules, config_path)
    else:
        print("Hook generation skipped (hooks_enabled=false).")

    print("Done.")


if __name__ == "__main__":
    main()
