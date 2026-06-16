#!/usr/bin/env bash
set -e

cd "$(dirname "$0")"

# Always-loaded memory files — created blank, populated through use.
touch memory/identity.md \
      memory/short_term_memory.md \
      memory/mindset.md \
      memory/capabilities.md \
      memory/map.md \
      memory/substrate-log.md

# Personalization & secrets — copy the template, then fill it in.
if [ ! -f secrets.json ]; then
  cp secrets.json.example secrets.json
  echo "Created secrets.json from template."
  echo "  -> Edit it to set maintainer_name, timezone, assistant_name,"
  echo "     and any Telegram / Bluesky credentials you want to use."
fi

echo "Behavioral settings (session intervals, caps, feature toggles) live in config.json."

# Install the SessionStart hook into the user's global Claude Code settings, so memory
# loads at the start of every session in any project — not just this folder.
SETTINGS="$HOME/.claude/settings.json"
HOOK_CMD="$(pwd)/scripts/session-start.sh"
chmod +x scripts/session-start.sh
mkdir -p "$HOME/.claude"
[ -f "$SETTINGS" ] || echo '{}' > "$SETTINGS"
if ! command -v jq >/dev/null 2>&1; then
  echo "jq not found — add a SessionStart hook to $SETTINGS that runs: $HOOK_CMD"
elif grep -q "session-start.sh" "$SETTINGS"; then
  echo "SessionStart hook already installed in $SETTINGS."
else
  tmp="$(mktemp)"
  jq --arg cmd "$HOOK_CMD" \
    '.hooks.SessionStart += [{"matcher":"startup|resume|clear|compact","hooks":[{"type":"command","command":$cmd}]}]' \
    "$SETTINGS" > "$tmp" && mv "$tmp" "$SETTINGS"
  echo "Installed SessionStart hook -> $HOOK_CMD"
fi

echo "Ready. Open a Claude Code session to start the identity conversation."
