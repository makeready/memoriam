"""Phase 3: Generate Claude Code hook script and settings fragment."""

import json
import textwrap
from pathlib import Path

from models import FilterRule


def generate_hook_script(rules_path: Path, config_path: Path) -> str:
    """Generate the Python hook script that runs as a PreToolUse hook.

    The generated script:
    1. Checks config.json for hooks_enabled
    2. Reads rules.json
    3. Matches the current tool call against rules
    4. Emits updatedInput JSON for matches
    5. Always exits 0
    """
    return textwrap.dedent(f'''\
        #!/usr/bin/env python3
        """Context-efficiency PreToolUse hook. Auto-generated — do not edit manually."""

        import json
        import re
        import sys

        RULES_PATH = {json.dumps(str(rules_path))}
        CONFIG_PATH = {json.dumps(str(config_path))}


        def load_config():
            try:
                with open(CONFIG_PATH) as f:
                    raw = json.load(f)
                return raw.get("context_efficiency", {{}})
            except Exception:
                return {{}}


        def load_rules():
            try:
                with open(RULES_PATH) as f:
                    return json.load(f)
            except Exception:
                return []


        def match_rule(rule, tool_name, tool_input):
            if rule["tool"] != tool_name:
                return False
            match_field = rule.get("match_field", "command")
            value = str(tool_input.get(match_field, ""))
            pattern = rule["pattern"]
            # Strip tool name prefix from pattern (e.g., "Read .ts" -> ".ts")
            if pattern.startswith(tool_name + " "):
                pattern = pattern[len(tool_name) + 1:]
            return pattern in value


        def apply_rule(rule, tool_input):
            action = rule["action"]
            params = rule.get("action_params", {{}})

            if action == "add_tail":
                lines = params.get("lines", 5)
                cmd = tool_input.get("command", "")
                tool_input["command"] = f"{{cmd}} | tail -n {{lines}}"
                return {{"updatedInput": tool_input}}

            if action == "add_limit":
                limit = params.get("limit", 50)
                tool_input["limit"] = limit
                return {{"updatedInput": tool_input}}

            if action == "add_head_limit":
                head_limit = params.get("head_limit", 10)
                tool_input["head_limit"] = head_limit
                return {{"updatedInput": tool_input}}

            if action == "add_context":
                return {{"additionalContext": f"Note: {{rule.get('description', 'This output is typically not referenced.')}}"}}

            return None


        def main():
            try:
                config = load_config()
                if not config.get("hooks_enabled", False):
                    sys.exit(0)

                stdin_data = json.loads(sys.stdin.read())
                tool_name = stdin_data.get("tool_name", "")
                tool_input = stdin_data.get("tool_input", {{}})

                rules = load_rules()
                for rule in rules:
                    if match_rule(rule, tool_name, tool_input):
                        result = apply_rule(rule, tool_input)
                        if result:
                            output = {{
                                "hookSpecificOutput": {{
                                    "hookEventName": "PreToolUse",
                                    **result,
                                }}
                            }}
                            print(json.dumps(output))
                            sys.exit(0)

            except Exception:
                pass

            sys.exit(0)


        if __name__ == "__main__":
            main()
    ''')


def generate_settings_fragment(hook_script_path: Path) -> dict:
    """Generate the hooks section for Claude Code settings.json."""
    return {
        "PreToolUse": [
            {
                "matcher": "Bash|Read|Grep",
                "hooks": [
                    {
                        "type": "command",
                        "command": f"python3 {hook_script_path}",
                        "timeout": 5,
                    }
                ],
            }
        ],
    }


def write_hooks(
    rules: list[FilterRule],
    rules_path: Path,
    config_path: Path,
    output_dir: Path,
) -> tuple[Path, dict]:
    """Write the hook script and return (script_path, settings_fragment)."""
    output_dir.mkdir(parents=True, exist_ok=True)
    script_path = output_dir / "filter-tool-input.py"
    script_content = generate_hook_script(rules_path, config_path)
    script_path.write_text(script_content)
    script_path.chmod(0o755)

    fragment = generate_settings_fragment(script_path)
    fragment_path = output_dir / "settings-fragment.json"
    fragment_path.write_text(json.dumps(fragment, indent=2))

    return script_path, fragment
