"""Phase 1: Parse session transcripts and compute tool output utilization."""

import json
import re
from pathlib import Path

from heuristics import META_TOOLS, compute_utilization

# Tool results under this size (chars) are excluded from analysis — too small to matter
MIN_RESULT_SIZE = 20

# Tools whose results are always trivial (e.g., "File updated successfully")
TRIVIAL_RESULT_TOOLS = {"Edit", "Write"}

# Tools excluded from analysis — their value can't be measured by content overlap
EXCLUDED_TOOLS = META_TOOLS


def _estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token."""
    return len(text) // 4


def _extract_command_pattern(command: str) -> str:
    """Extract a generalizable pattern from a Bash command."""
    # Strip leading cd ... && or cd ... ;
    command = re.sub(r'^cd\s+\S+\s*&&\s*', '', command)
    command = re.sub(r'^cd\s+\S+\s*;\s*', '', command)

    # Extract the core command (first meaningful segment)
    parts = command.strip().split()
    if not parts:
        return "unknown"

    # For pnpm/npm commands, capture the script name
    if parts[0] in ("pnpm", "npm", "npx"):
        significant = [p for p in parts[1:] if not p.startswith("-")]
        if significant:
            return f"{parts[0]} {' '.join(significant[:3])}"
        return parts[0]

    # For git commands
    if parts[0] == "git" and len(parts) > 1:
        return f"git {parts[1]}"

    # For other commands, use first 1-2 tokens
    return " ".join(parts[:2])


def _extract_pattern(tool_name: str, tool_input: dict) -> str:
    """Extract a generalizable pattern from a tool call."""
    if tool_name == "Bash":
        return _extract_command_pattern(tool_input.get("command", ""))
    if tool_name == "Read":
        path = tool_input.get("file_path", "")
        # Generalize to file extension
        ext = Path(path).suffix if path else ""
        return f"Read {ext}" if ext else "Read"
    if tool_name == "Grep":
        return "Grep"
    if tool_name == "Glob":
        return f"Glob {tool_input.get('pattern', '')}"
    return tool_name


def parse_session(jsonl_path: Path) -> list[dict]:
    """Parse a session JSONL and extract tool call pairs with context.

    Returns a list of dicts, each containing:
    - tool_name, tool_id, tool_input: the tool call details
    - result_text: the tool's output
    - result_tokens: estimated token count of the output
    - assistant_texts: list of text blocks from the next assistant response
    - next_actions: list of {name, input} dicts for tool_use blocks in the next response
    """
    entries = []
    with open(jsonl_path) as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))

    # Build a map of tool_use_id -> tool call info from assistant messages
    tool_calls = []  # ordered list of (tool_use_id, tool_name, tool_input, assistant_uuid)
    # Map of assistant uuid -> full assistant message entry
    assistant_msgs = {}

    for entry in entries:
        if entry.get("type") != "assistant":
            continue
        msg = entry.get("message", {})
        content = msg.get("content", [])
        uuid = entry.get("uuid", "")
        assistant_msgs[uuid] = entry

        for block in content:
            if block.get("type") == "tool_use":
                tool_calls.append({
                    "tool_use_id": block["id"],
                    "tool_name": block["name"],
                    "tool_input": block.get("input", {}),
                    "assistant_uuid": uuid,
                })

    # Build a map of tool_use_id -> result text from user messages
    results = {}
    for entry in entries:
        if entry.get("type") != "user":
            continue
        msg = entry.get("message", {})
        content = msg.get("content", [])
        if not isinstance(content, list):
            continue
        for block in content:
            if block.get("type") == "tool_result":
                results[block["tool_use_id"]] = block.get("content", "")

    # Build ordered list of assistant entries for context lookup
    ordered_assistants = [e for e in entries if e.get("type") == "assistant"]

    def _find_next_assistants(current_uuid: str, count: int = 1) -> list[dict]:
        """Find the next `count` assistant messages after the one containing this tool call."""
        found = False
        result = []
        for entry in ordered_assistants:
            if entry.get("uuid") == current_uuid:
                found = True
                continue
            if found:
                result.append(entry)
                if len(result) >= count:
                    break
        return result

    def _extract_actions_from_assistant(entry: dict) -> tuple[list[str], list[dict]]:
        """Extract text blocks and tool actions from an assistant message."""
        texts = []
        actions = []
        for block in entry.get("message", {}).get("content", []):
            if block.get("type") == "text":
                texts.append(block["text"])
            elif block.get("type") == "tool_use":
                actions.append({
                    "name": block["name"],
                    "input": block.get("input", {}),
                })
        return texts, actions

    # How many future assistant messages to scan for extended action context
    EXTENDED_WINDOW = 3

    # Build the pairs
    pairs = []
    for tc in tool_calls:
        # Skip tools with trivial results or unmeasurable value
        if tc["tool_name"] in TRIVIAL_RESULT_TOOLS or tc["tool_name"] in EXCLUDED_TOOLS:
            continue

        result_text = results.get(tc["tool_use_id"], "")
        if len(result_text) < MIN_RESULT_SIZE:
            continue

        # Find the next assistant responses for context
        next_assistants = _find_next_assistants(tc["assistant_uuid"], count=EXTENDED_WINDOW)

        assistant_texts = []
        next_actions = []
        extended_next_actions = []

        for i, assistant_entry in enumerate(next_assistants):
            texts, actions = _extract_actions_from_assistant(assistant_entry)
            if i == 0:
                assistant_texts = texts
                next_actions = actions
            extended_next_actions.extend(actions)

        pairs.append({
            "tool_name": tc["tool_name"],
            "tool_id": tc["tool_use_id"],
            "tool_input": tc["tool_input"],
            "result_text": result_text,
            "result_tokens": _estimate_tokens(result_text),
            "assistant_texts": assistant_texts,
            "next_actions": next_actions,
            "extended_next_actions": extended_next_actions,
        })

    return pairs


def find_session_files(directory: Path) -> list[Path]:
    """Find all JSONL session files in a directory (including subdirectories)."""
    if not directory.exists():
        return []
    return sorted(directory.glob("**/*.jsonl"), key=lambda p: p.stat().st_mtime)


def aggregate_patterns(pairs: list[dict]) -> dict:
    """Aggregate tool call pairs into patterns with utilization statistics.

    Returns a dict keyed by (tool, pattern) string, with values containing
    aggregated stats.
    """
    buckets: dict[str, list] = {}

    for pair in pairs:
        pattern = _extract_pattern(pair["tool_name"], pair["tool_input"])
        key = f"{pair['tool_name']}:{pattern}"

        score = compute_utilization(
            tool_result=pair["result_text"],
            assistant_texts=pair["assistant_texts"],
            next_actions=pair["next_actions"],
            tool_name=pair["tool_name"],
            tool_input=pair["tool_input"],
            extended_next_actions=pair.get("extended_next_actions", []),
        )

        if key not in buckets:
            buckets[key] = []
        buckets[key].append({
            "result_tokens": pair["result_tokens"],
            "utilization": score,
        })

    # Aggregate each bucket
    patterns = {}
    for key, items in buckets.items():
        tool, pattern = key.split(":", 1)
        scores = [item["utilization"] for item in items]
        avg_tokens = sum(item["result_tokens"] for item in items) / len(items)
        avg_util = sum(s.composite for s in scores) / len(scores)

        patterns[key] = {
            "tool": tool,
            "pattern": pattern,
            "avg_output_tokens": int(avg_tokens),
            "avg_utilization": round(avg_util, 3),
            "sample_count": len(items),
            "utilization_scores": [s.composite for s in scores],
        }

    return patterns
