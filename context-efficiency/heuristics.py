"""Utilization detection heuristics for tool call output."""

import re
from models import UtilizationScore

# Common JS/TS/Python keywords to exclude from distinctive token extraction
COMMON_KEYWORDS = {
    "function", "return", "import", "export", "const", "class",
    "extends", "implements", "interface", "undefined", "require",
    "module", "default", "async", "await", "Promise", "boolean",
    "string", "number", "object", "typeof", "instanceof", "continue",
    "break", "switch", "throw", "catch", "finally", "static",
    "private", "protected", "public", "abstract", "readonly",
    "override", "declare", "namespace", "keyof",
}

# Minimum characters for a token to be considered distinctive
MIN_TOKEN_LENGTH = 9

# Threshold for "tiny output" that shouldn't be flagged as waste
TINY_OUTPUT_CHARS = 50

# Threshold for "null response" detection (roughly ~50 tokens)
NULL_RESPONSE_CHARS = 200

# Tools whose output value can't be measured by content overlap.
# These are interactive/meta tools — their output is "used" by being acted on,
# not by being quoted. Scoring them by substring overlap produces false positives.
META_TOOLS = {
    "AskUserQuestion", "ExitPlanMode", "EnterPlanMode",
    "TaskCreate", "TaskUpdate", "TaskGet", "TaskList",
    "WebSearch", "WebFetch",
}

# Weights for composite score (default, used for non-Read tools).
# Action signal is the strongest indicator — if a Read is followed by an Edit
# on the same file, the output was useful regardless of whether it was quoted.
WEIGHT_SUBSTRING = 0.3
WEIGHT_ACTION = 0.5
WEIGHT_NULL_RESPONSE = 0.2

# Weights for Read tool specifically.
# Read value comes from comprehension, not quotation — substring overlap is a
# poor signal because you read a file to understand it, not to echo it back.
# Action signal (did a related edit follow?) is much more meaningful.
WEIGHT_READ_SUBSTRING = 0.1
WEIGHT_READ_ACTION = 0.7
WEIGHT_READ_NULL_RESPONSE = 0.2


def extract_distinctive_tokens(text: str) -> set[str]:
    """Extract identifier-like strings that are distinctive enough to track."""
    if not text:
        return set()

    # Extract word-like sequences (including dots and slashes for paths)
    candidates = re.findall(r'[a-zA-Z_][a-zA-Z0-9_./]*[a-zA-Z0-9]', text)

    return {
        token for token in candidates
        if len(token) >= MIN_TOKEN_LENGTH and token not in COMMON_KEYWORDS
    }


def compute_substring_overlap(
    tool_result: str, assistant_texts: list[str]
) -> float:
    """Compute what fraction of distinctive tokens from tool_result appear in assistant text."""
    tokens = extract_distinctive_tokens(tool_result)
    if not tokens:
        return 0.0

    combined = " ".join(assistant_texts)
    matched = sum(1 for t in tokens if t in combined)
    return matched / len(tokens)


def _stems_match(path_a: str, path_b: str) -> bool:
    """Check if two file paths refer to a test/source pair or same logical unit.

    Matches cases like:
    - Foo.test.tsx ↔ Foo.tsx
    - Foo.test.ts ↔ Foo.ts
    - buildOrder.test.ts ↔ buildOrder.ts
    """
    from pathlib import PurePosixPath

    stem_a = PurePosixPath(path_a).name
    stem_b = PurePosixPath(path_b).name

    # Strip test suffixes to get base names
    def base_name(name: str) -> str:
        # Remove extension first, then .test/.spec/.medium-test
        for ext in (".tsx", ".ts", ".js", ".jsx", ".mjs"):
            if name.endswith(ext):
                name = name[: -len(ext)]
                break
        for suffix in (".test", ".spec", ".medium-test"):
            if name.endswith(suffix):
                name = name[: -len(suffix)]
                break
        return name

    return base_name(stem_a) == base_name(stem_b) and stem_a != stem_b


def _paths_share_module(path_a: str, path_b: str, max_depth: int = 2) -> bool:
    """Check if two paths share a parent directory within max_depth levels."""
    from pathlib import PurePosixPath

    parents_a = list(PurePosixPath(path_a).parents)[:max_depth]
    parents_b = list(PurePosixPath(path_b).parents)[:max_depth]
    return bool(set(parents_a) & set(parents_b))


def detect_read_action_signal(
    file_path: str,
    next_actions: list[dict],
    extended_next_actions: list[dict],
) -> float:
    """Detect if subsequent actions imply a Read's output was used.

    Uses the extended action window (multiple future messages) because Read
    value often manifests several actions later — e.g., read 3 files, then edit
    one of them two turns later.

    Returns 1.0 for strong signals, 0.5-0.8 for moderate, 0.0 for none.
    """
    if not file_path:
        return 0.0

    # Use extended window for all checks
    all_actions = extended_next_actions if extended_next_actions else next_actions
    if not all_actions:
        return 0.0

    best_signal = 0.0

    for action in all_actions:
        action_name = action.get("name", "")
        action_input = action.get("input", {})
        action_file = action_input.get("file_path", "")

        # Read → Edit/Write same file (strongest)
        if action_name in ("Edit", "Write") and file_path == action_file:
            return 1.0

        # Read → Edit/Write matching test/source pair
        if action_name in ("Edit", "Write") and action_file:
            if _stems_match(file_path, action_file):
                best_signal = max(best_signal, 0.9)
            # Read → Edit in the same module/directory tree
            elif _paths_share_module(file_path, action_file):
                best_signal = max(best_signal, 0.7)

        # Read → Read in the same directory (exploration)
        if action_name == "Read" and action_file:
            from pathlib import PurePosixPath
            if PurePosixPath(file_path).parent == PurePosixPath(action_file).parent:
                best_signal = max(best_signal, 0.5)

    # If any Edit/Write happens in the extended window, it's at least a
    # comprehension read — you read file A to understand before editing file B
    if best_signal == 0.0:
        has_edit = any(
            a.get("name") in ("Edit", "Write") for a in all_actions
        )
        if has_edit:
            best_signal = 0.4

    return best_signal


def detect_action_signal(
    tool_name: str,
    tool_input: dict,
    next_actions: list[dict],
    result_text: str = "",
    extended_next_actions: list[dict] | None = None,
) -> float:
    """Detect if subsequent actions imply the tool output was used.

    Returns 1.0 for strong signals (direct file relationship), 0.5 for
    moderate signals (plausible indirect use), 0.0 for no signal.
    """
    if extended_next_actions is None:
        extended_next_actions = []

    # Read gets its own dedicated heuristic with wider action window
    if tool_name == "Read":
        file_path = tool_input.get("file_path", "")
        return detect_read_action_signal(file_path, next_actions, extended_next_actions)

    if not next_actions:
        return 0.0

    best_signal = 0.0

    for action in next_actions:
        action_name = action.get("name", "")
        action_input = action.get("input", {})
        action_file = action_input.get("file_path", "")

        # Grep/Glob results followed by Read of a file mentioned in results
        if tool_name in ("Grep", "Glob") and action_name == "Read":
            if result_text and action_file and action_file in result_text:
                return 1.0

        # Grep/Glob followed by Edit of a file in results — search-then-fix
        if tool_name in ("Grep", "Glob") and action_name in ("Edit", "Write"):
            if result_text and action_file and action_file in result_text:
                return 1.0

        # Grep/Glob followed by another search — narrowing down
        if tool_name in ("Grep", "Glob") and action_name in ("Grep", "Glob"):
            best_signal = max(best_signal, 0.5)

        # Bash followed by Read/Edit of a path appearing in the output
        if tool_name == "Bash" and action_name in ("Read", "Edit"):
            if result_text and action_file and action_file in result_text:
                return 1.0

        # Bash followed by another Bash — chained commands (moderate signal)
        if tool_name == "Bash" and action_name == "Bash":
            best_signal = max(best_signal, 0.3)

    return best_signal


def detect_null_response(next_text: str) -> float:
    """Detect if the assistant's response is a short transition (low-visibility utilization)."""
    if len(next_text) < NULL_RESPONSE_CHARS:
        return 1.0
    return 0.0


def compute_utilization(
    tool_result: str,
    assistant_texts: list[str],
    next_actions: list[dict],
    tool_name: str = "",
    tool_input: dict | None = None,
    extended_next_actions: list[dict] | None = None,
) -> UtilizationScore:
    """Compute a composite utilization score for a tool call."""
    if tool_input is None:
        tool_input = {}
    if extended_next_actions is None:
        extended_next_actions = []

    # Meta-tools are always considered utilized — their value isn't in content
    if tool_name in META_TOOLS:
        return UtilizationScore(
            substring_ratio=1.0,
            action_signal=1.0,
            null_response=0.0,
            composite=1.0,
        )

    # Tiny output is always "utilized" — not worth filtering
    if len(tool_result) < TINY_OUTPUT_CHARS:
        return UtilizationScore(
            substring_ratio=1.0,
            action_signal=0.0,
            null_response=0.0,
            composite=1.0,
        )

    substring = compute_substring_overlap(tool_result, assistant_texts)
    action = detect_action_signal(
        tool_name, tool_input, next_actions, result_text=tool_result,
        extended_next_actions=extended_next_actions,
    )
    null_resp = detect_null_response(" ".join(assistant_texts))

    # If there's a null response, reduce its negative impact when action signal is high
    # (the output was used via action, just not quoted)
    if action > 0.5 and null_resp > 0.5:
        null_resp = 0.0

    # Use Read-specific weights when tool is Read
    if tool_name == "Read":
        w_sub, w_act, w_null = WEIGHT_READ_SUBSTRING, WEIGHT_READ_ACTION, WEIGHT_READ_NULL_RESPONSE
    else:
        w_sub, w_act, w_null = WEIGHT_SUBSTRING, WEIGHT_ACTION, WEIGHT_NULL_RESPONSE

    composite = (
        w_sub * substring
        + w_act * action
        + w_null * (1.0 - null_resp)
    )

    return UtilizationScore(
        substring_ratio=substring,
        action_signal=action,
        null_response=null_resp,
        composite=composite,
    )
