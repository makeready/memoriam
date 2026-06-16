"""Phase 2: Generate filtering rules from aggregated patterns."""

import json
import re
import statistics
from pathlib import Path

from heuristics import META_TOOLS
from models import FilterRule

# Minimum utilization threshold — patterns above this are considered "used enough"
MAX_UTILIZATION_FOR_RULE = 0.3

# Minimum sample count for any confidence
MIN_SAMPLES = 1

# Sample count that gives full confidence on the count dimension
FULL_CONFIDENCE_SAMPLES = 30


def score_confidence(sample_count: int, utilization_scores: list[float]) -> float:
    """Score confidence that a pattern is consistently low-utilization.

    Based on sample count (more = higher confidence) and consistency
    (low variance in utilization = higher confidence).
    """
    if sample_count < MIN_SAMPLES:
        return 0.0

    # Sample count factor: ramps from 0 to 1 as count approaches FULL_CONFIDENCE_SAMPLES
    count_factor = min(sample_count / FULL_CONFIDENCE_SAMPLES, 1.0)

    # Consistency factor: lower variance = higher confidence
    if len(utilization_scores) < 2:
        variance = 0.0
    else:
        variance = statistics.variance(utilization_scores)

    # Variance of 0 = perfect consistency (1.0), variance of 0.25 = very inconsistent (0.0)
    consistency_factor = max(0.0, 1.0 - variance * 4)

    # Multiply instead of add — low sample count should cap overall confidence
    return count_factor * (0.5 + 0.5 * consistency_factor)


def determine_action(
    tool_name: str, pattern: str, avg_output_tokens: int
) -> tuple[str, dict]:
    """Determine the appropriate filtering action for a waste pattern.

    Actions are intentionally conservative — it's better to leave some waste
    than to truncate output that turns out to be needed. Read and Grep are
    especially risky to limit because their value is often indirect.
    """
    if tool_name == "Bash":
        # For Bash commands, limit output with tail.
        # Git commands that produce structured output get more lines.
        if pattern.startswith("git "):
            lines = max(10, min(30, avg_output_tokens // 100))
        else:
            lines = max(5, min(20, avg_output_tokens // 150))
        return "add_tail", {"lines": lines}

    if tool_name == "Read":
        # Read is high-risk to limit — a file read followed by an edit needs
        # the full file. Only add a context note, never force a limit.
        return "add_context", {"note": f"avg {avg_output_tokens} tokens, typically low direct reference"}

    if tool_name == "Grep":
        # Grep results often drive the next action (which file to read).
        # Use a generous head_limit — the floor is 15.
        head_limit = max(15, min(40, avg_output_tokens // 50))
        return "add_head_limit", {"head_limit": head_limit}

    # For anything else, just add context suggesting it's verbose
    return "add_context", {}


def _make_rule_id(tool: str, pattern: str) -> str:
    """Generate a kebab-case rule ID from tool and pattern."""
    raw = f"{tool}-{pattern}"
    return re.sub(r'[^a-z0-9]+', '-', raw.lower()).strip('-')[:60]


def _match_field_for_tool(tool: str) -> str:
    """Return the input field to match against for each tool type."""
    if tool == "Bash":
        return "command"
    if tool == "Read":
        return "file_path"
    if tool == "Grep":
        return "pattern"
    if tool == "Glob":
        return "pattern"
    return "command"


def generate_rules(
    patterns: dict, min_confidence: float = 0.7
) -> list[FilterRule]:
    """Generate filtering rules from aggregated patterns.

    Only generates rules for patterns that are:
    - Below the utilization threshold (consistently low use)
    - Above the confidence threshold (enough samples, consistent behavior)
    """
    rules = []

    for key, data in patterns.items():
        # Skip meta-tools — their output value can't be measured this way
        if data["tool"] in META_TOOLS:
            continue

        # Skip patterns with high utilization
        if data["avg_utilization"] > MAX_UTILIZATION_FOR_RULE:
            continue

        confidence = score_confidence(
            data["sample_count"], data["utilization_scores"]
        )
        if confidence < min_confidence:
            continue

        action, action_params = determine_action(
            data["tool"], data["pattern"], data["avg_output_tokens"]
        )

        rule = FilterRule(
            id=_make_rule_id(data["tool"], data["pattern"]),
            tool=data["tool"],
            pattern=data["pattern"],
            match_field=_match_field_for_tool(data["tool"]),
            avg_output_tokens=data["avg_output_tokens"],
            avg_utilization=data["avg_utilization"],
            sample_count=data["sample_count"],
            confidence=round(confidence, 3),
            action=action,
            action_params=action_params,
            description=f"{data['pattern']} output averages {data['avg_output_tokens']} tokens with {data['avg_utilization']:.0%} utilization",
        )
        rules.append(rule)

    return sorted(rules, key=lambda r: r.confidence, reverse=True)


def write_staging_rules(rules: list[FilterRule], output_dir: Path) -> None:
    """Write rules to a staging file for human review."""
    output_dir.mkdir(parents=True, exist_ok=True)
    staging_path = output_dir / "rules.staging.json"
    with open(staging_path, "w") as f:
        json.dump([r.to_dict() for r in rules], f, indent=2)


def generate_report(
    rules: list[FilterRule], patterns: dict
) -> str:
    """Generate a human-readable markdown report."""
    lines = [
        "# Context Efficiency Report",
        "",
        f"## Analyzed Patterns: {len(patterns)}",
        "",
    ]

    if patterns:
        lines.append("| Tool | Pattern | Avg Tokens | Avg Utilization | Samples |")
        lines.append("|------|---------|-----------|----------------|---------|")
        for key, data in sorted(patterns.items(), key=lambda x: x[1]["avg_utilization"]):
            lines.append(
                f"| {data['tool']} | {data['pattern']} | {data['avg_output_tokens']} "
                f"| {data['avg_utilization']:.1%} | {data['sample_count']} |"
            )
        lines.append("")

    lines.append(f"## Generated Rules: {len(rules)}")
    lines.append("")

    if rules:
        for rule in rules:
            lines.append(f"### {rule.id}")
            lines.append(f"- **Tool**: {rule.tool}")
            lines.append(f"- **Pattern**: `{rule.pattern}`")
            lines.append(f"- **Action**: {rule.action} {json.dumps(rule.action_params)}")
            lines.append(f"- **Confidence**: {rule.confidence:.1%}")
            lines.append(f"- {rule.description}")
            lines.append("")
    else:
        lines.append("No rules generated — either insufficient data or no consistent waste patterns found.")
        lines.append("")

    return "\n".join(lines)
