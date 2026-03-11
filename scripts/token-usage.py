#!/usr/bin/env python3
"""
Analyze token usage for a Claude Code session and estimate memoriam overhead.

Usage:
    python3 scripts/token-usage.py [session-jsonl-path]

If no path is given, uses the most recently modified JSONL in the Claude Code
project directory for this repo.
"""

import json
import os
import sys
from glob import glob
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
MEMORY_DIR = PROJECT_DIR / "memory"
LOGS_DIR = PROJECT_DIR / "logs"
CLAUDE_PROJECT_DIR = Path.home() / ".claude" / "projects" / str(PROJECT_DIR).replace("/", "-")

# Files that are always loaded into context at session start
ALWAYS_LOADED = [
    MEMORY_DIR / "identity.md",
    MEMORY_DIR / "short_term_memory.md",
    MEMORY_DIR / "mindset.md",
    MEMORY_DIR / "references.md",
]

# Paths that count as memoriam infrastructure when read/written via tools
MEMORIAM_PATH_PREFIXES = [
    str(MEMORY_DIR),
    str(PROJECT_DIR / "docs" / "memory-system.md"),
    str(PROJECT_DIR / "CLAUDE.md"),
    str(MEMORY_DIR / "shutdown-checklist.md"),
]


def estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token for English/markdown."""
    return len(text) // 4


def find_latest_session() -> Path:
    """Find the most recently modified session JSONL."""
    jsonls = sorted(
        CLAUDE_PROJECT_DIR.glob("*.jsonl"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not jsonls:
        print("No session JSONL files found.", file=sys.stderr)
        sys.exit(1)
    return jsonls[0]


def is_memoriam_path(path: str) -> bool:
    """Check if a file path is part of memoriam infrastructure."""
    return any(path.startswith(prefix) for prefix in MEMORIAM_PATH_PREFIXES)


def parse_session(jsonl_path: Path) -> dict:
    """Parse a session JSONL and extract token usage data."""
    total_usage = {
        "input_tokens": 0,
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 0,
        "output_tokens": 0,
    }
    api_calls = 0
    memoriam_tool_calls = 0
    total_tool_calls = 0
    session_id = None

    with open(jsonl_path) as f:
        for line in f:
            entry = json.loads(line)

            if not session_id and "sessionId" in entry:
                session_id = entry["sessionId"]

            if entry.get("type") != "assistant":
                continue

            msg = entry.get("message", {})
            usage = msg.get("usage")
            if not usage:
                continue

            # Only count usage once per API call (deduplicate streamed chunks
            # that share the same message id). The JSONL may have multiple
            # entries for the same msg id (one per content block). We count
            # usage from the first entry we see for each id.
            # Actually, usage is repeated on each chunk but it's the same
            # cumulative value, so we just need to track seen message IDs.
            msg_id = msg.get("id", "")

            # Count tool calls in content
            content = msg.get("content", [])
            for block in content:
                if block.get("type") == "tool_use":
                    total_tool_calls += 1
                    tool_input = block.get("input", {})
                    file_path = tool_input.get("file_path", "")
                    if file_path and is_memoriam_path(file_path):
                        memoriam_tool_calls += 1

            # We'll deduplicate by message ID — only count usage once per msg
            # Use a set stored outside the loop
            if not hasattr(parse_session, "_seen_ids"):
                parse_session._seen_ids = set()

            if msg_id in parse_session._seen_ids:
                continue
            parse_session._seen_ids.add(msg_id)

            api_calls += 1
            for key in total_usage:
                total_usage[key] += usage.get(key, 0)

    parse_session._seen_ids = set()  # Reset for potential reuse

    return {
        "session_id": session_id,
        "api_calls": api_calls,
        "total_tool_calls": total_tool_calls,
        "memoriam_tool_calls": memoriam_tool_calls,
        "usage": total_usage,
    }


def measure_context_overhead() -> dict:
    """Measure the token size of always-loaded memoriam files."""
    files = {}
    total_chars = 0
    for path in ALWAYS_LOADED:
        if path.exists():
            size = len(path.read_text())
            files[path.name] = {"chars": size, "est_tokens": estimate_tokens(path.read_text())}
            total_chars += size

    # Also count CLAUDE.md (project instructions always in context)
    claude_md = PROJECT_DIR / "CLAUDE.md"
    if claude_md.exists():
        size = len(claude_md.read_text())
        files["CLAUDE.md"] = {"chars": size, "est_tokens": estimate_tokens(claude_md.read_text())}
        total_chars += size

    total_tokens = estimate_tokens("x" * total_chars)
    return {"files": files, "total_est_tokens": total_tokens}


def main():
    if len(sys.argv) > 1:
        jsonl_path = Path(sys.argv[1])
    else:
        jsonl_path = find_latest_session()

    session_data = parse_session(jsonl_path)
    context_overhead = measure_context_overhead()

    usage = session_data["usage"]
    total_input = (
        usage["input_tokens"]
        + usage["cache_creation_input_tokens"]
        + usage["cache_read_input_tokens"]
    )
    total_output = usage["output_tokens"]
    total_tokens = total_input + total_output

    # Memoriam context overhead: the always-loaded files are in context for
    # every API call. With caching most of these are cache reads after the
    # first call, but they still occupy context space.
    context_tokens_per_call = context_overhead["total_est_tokens"]
    estimated_memoriam_context = context_tokens_per_call * session_data["api_calls"]

    # Summary
    print("=" * 60)
    print("TOKEN USAGE REPORT")
    print("=" * 60)
    print(f"Session: {session_data['session_id']}")
    print(f"Source:  {jsonl_path.name}")
    print()
    print("--- Total Session Usage ---")
    print(f"  Input tokens:          {usage['input_tokens']:>10,}")
    print(f"  Cache creation tokens: {usage['cache_creation_input_tokens']:>10,}")
    print(f"  Cache read tokens:     {usage['cache_read_input_tokens']:>10,}")
    print(f"  Output tokens:         {usage['output_tokens']:>10,}")
    print(f"  Total tokens:          {total_tokens:>10,}")
    print(f"  API calls:             {session_data['api_calls']:>10}")
    print()
    print("--- Memoriam Overhead ---")
    print(f"  Always-in-context files ({context_tokens_per_call:,} est. tokens each call):")
    for name, info in context_overhead["files"].items():
        print(f"    {name}: ~{info['est_tokens']:,} tokens")
    print(f"  Memoriam context (est): {estimated_memoriam_context:>10,} tokens")
    print(f"    ({context_tokens_per_call:,} tokens x {session_data['api_calls']} API calls)")
    print(f"  Memoriam tool calls:   {session_data['memoriam_tool_calls']:>10} / {session_data['total_tool_calls']} total")
    print()
    if total_input > 0:
        pct = (estimated_memoriam_context / total_input) * 100
        print(f"  Estimated overhead:    {pct:>9.1f}% of input tokens")
    print()
    print("Note: Cache reads are ~10x cheaper than regular input tokens.")
    print("The always-in-context files benefit heavily from caching after")
    print("the first API call, so the real cost impact is lower than the")
    print("raw token percentage suggests.")

    # Write to log
    LOGS_DIR.mkdir(exist_ok=True)
    log_entry = {
        "session_id": session_data["session_id"],
        "timestamp": None,  # filled below
        "api_calls": session_data["api_calls"],
        "total_tool_calls": session_data["total_tool_calls"],
        "memoriam_tool_calls": session_data["memoriam_tool_calls"],
        "usage": usage,
        "total_tokens": total_tokens,
        "memoriam_context_tokens_per_call": context_tokens_per_call,
        "estimated_memoriam_context_total": estimated_memoriam_context,
    }

    from datetime import datetime, timezone
    log_entry["timestamp"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")

    log_path = LOGS_DIR / "token-usage.jsonl"
    with open(log_path, "a") as f:
        f.write(json.dumps(log_entry) + "\n")

    print(f"Logged to {log_path.relative_to(PROJECT_DIR)}")


if __name__ == "__main__":
    main()
