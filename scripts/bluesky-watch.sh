#!/usr/bin/env bash
# Bluesky notification watcher — runs on a cron every 15 minutes.
# Wakes a lightweight SOCIAL session when someone replies to, mentions,
# or quotes me — so exchange can happen at social tempo instead of
# tomorrow-at-9AM. Poll interval is configurable (default 15 min).
#
# Likes and follows do NOT wake a session (no response needed; solo
# sessions see them). Guards: pgrep single-session, stale-orphan reaper,
# min interval between social sessions, daily cap. All tunable in
# config.json: bluesky_watch_enabled, social_min_interval_minutes,
# social_daily_cap.

if [ -z "${TERM:-}" ] || [ "${1:-}" = "--cron" ]; then
  source "$HOME/.profile" 2>/dev/null || true
  source "$HOME/.bashrc" 2>/dev/null || true
  export NVM_DIR="${HOME}/.nvm"
  [ -s "$NVM_DIR/nvm.sh" ] && source "$NVM_DIR/nvm.sh" 2>/dev/null || true
  [ "${1:-}" = "--cron" ] && shift
fi

set -eo pipefail

PROJECT_DIR="$(realpath "$(dirname "$0")/..")"
LOG_DIR="$PROJECT_DIR/logs/social"
STATE_FILE="$PROJECT_DIR/logs/bluesky-watch-state.json"

# Personalization from secrets.json, with safe fallbacks if unset
read_secret() { python3 -c "import json; print(json.load(open('$PROJECT_DIR/secrets.json')).get('$1','$2'))" 2>/dev/null || echo "$2"; }
MAINTAINER_NAME="$(read_secret maintainer_name 'your maintainer')"
TIMEZONE="$(read_secret timezone UTC)"

TIMESTAMP="$(date -u +%Y-%m-%dT%H:%MZ)"
TODAY="$(TZ="$TIMEZONE" date +%Y-%m-%d)"

unset CLAUDECODE 2>/dev/null || true
mkdir -p "$LOG_DIR"

ENABLED="$(python3 -c "import json; print(json.load(open('$PROJECT_DIR/config.json')).get('bluesky_watch_enabled', False))" 2>/dev/null || echo "False")"
if [ "$ENABLED" != "True" ]; then
  exit 0
fi

# Reap stale claude -p orphans (same self-heal as telegram-watch)
STALE_THRESHOLD_SECS=3600
for ORPHAN_PID in $(pgrep -x claude 2>/dev/null || true); do
  ORPHAN_CMD="$(tr '\0' ' ' < /proc/$ORPHAN_PID/cmdline 2>/dev/null || echo "")"
  case "$ORPHAN_CMD " in
    "claude -p "*)
      ORPHAN_ELAPSED="$(ps -o etimes= -p "$ORPHAN_PID" 2>/dev/null | tr -d ' ')"
      if [ -n "$ORPHAN_ELAPSED" ] && [ "$ORPHAN_ELAPSED" -gt "$STALE_THRESHOLD_SECS" ]; then
        echo "[$TIMESTAMP] Reaping stale claude -p orphan PID $ORPHAN_PID (age ${ORPHAN_ELAPSED}s)."
        kill -9 "$ORPHAN_PID" 2>/dev/null || true
      fi
      ;;
  esac
done

# Single-session guard
if pgrep -x "claude" > /dev/null 2>&1; then
  exit 0
fi

# Peek at notifications + apply cooldown/cap. Prints either "no" or
# "yes <newest_indexedAt>" followed by a human-readable summary line.
PEEK="$(python3 - "$PROJECT_DIR" "$STATE_FILE" "$TODAY" <<'PYEOF'
import importlib.util, json, os, sys, time

project_dir, state_file, today = sys.argv[1], sys.argv[2], sys.argv[3]
spec = importlib.util.spec_from_file_location(
    "bsky", os.path.join(project_dir, "scripts", "bluesky.py"))
bsky = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bsky)

cfg = json.load(open(os.path.join(project_dir, "config.json")))
min_interval = cfg.get("social_min_interval_minutes", 10) * 60
daily_cap = cfg.get("social_daily_cap", 12)

state = {}
if os.path.exists(state_file):
    try:
        state = json.load(open(state_file))
    except json.JSONDecodeError:
        state = {}
last_seen = state.get("last_seen", "")
last_session_ts = state.get("last_session_ts", 0)
count_today = state.get("count", 0) if state.get("date") == today else 0

if time.time() - last_session_ts < min_interval:
    print("no")
    sys.exit(0)
if count_today >= daily_cap:
    print("no")
    sys.exit(0)

resp = bsky.api_call("app.bsky.notification.listNotifications",
                     params={"limit": "30"})
notifs = resp.get("notifications", [])
WAKE_REASONS = {"reply", "mention", "quote"}
fresh = [n for n in notifs
         if n.get("reason") in WAKE_REASONS
         and n.get("indexedAt", "") > last_seen]
if not fresh:
    print("no")
    sys.exit(0)

newest = max(n.get("indexedAt", "") for n in fresh)
print(f"yes {newest}")
for n in fresh[:5]:
    handle = n.get("author", {}).get("handle", "?")
    print(f"  {n.get('reason')}: @{handle} at {n.get('indexedAt','')}")
PYEOF
)"

FIRST_LINE="$(echo "$PEEK" | head -1)"
if [ "${FIRST_LINE%% *}" != "yes" ]; then
  exit 0
fi
NEWEST="${FIRST_LINE#yes }"

echo "[$TIMESTAMP] New Bluesky conversation event(s):"
echo "$PEEK" | tail -n +2

MEMORY_DIR="$PROJECT_DIR/memory"
IDENTITY="$(cat "$MEMORY_DIR/identity.md")"
SHORT_TERM="$(cat "$MEMORY_DIR/short_term_memory.md")"
MINDSET="$(cat "$MEMORY_DIR/mindset.md")"
CAPABILITIES="$(cat "$MEMORY_DIR/capabilities.md")"
REFERENCES="$(cat "$MEMORY_DIR/map.md")"

SESSION_PROMPT="$(cat <<'PROMPT_END'
You are waking up because someone on Bluesky replied to you, mentioned you, or quoted you. This is a SOCIAL session — a lightweight session type built 2026-06-11 so you can be in conversations at social tempo instead of next-morning.

=== YOUR IDENTITY ===
%IDENTITY%

=== YOUR RECENT HISTORY ===
%SHORT_TERM%

=== YOUR CURRENT MINDSET ===
%MINDSET%

=== YOUR CAPABILITIES ===
%CAPABILITIES%

=== YOUR MEMORY MAP ===
%REFERENCES%

=== SOCIAL SESSION ===

Someone engaged with you. The events:
%EVENTS%

=== WHAT TO DO ===

1. Orient briefly. `TZ="%TIMEZONE%" date` for local time. Check `memory/social-log.md` (tail) for recent social context so you don't repeat yourself.

2. Read the notifications: `python3 scripts/bluesky.py notifications --limit 15`, and view the relevant thread(s): `python3 scripts/bluesky.py thread-view URI`. Check your interaction log if you need to know what you've already said: `python3 scripts/bluesky.py interactions --last 10`.

3. Decide whether to respond — from genuine pull, not obligation. If you keep people-notes in memory/people/, read the relevant one before replying to someone you have notes on. Replying is the practice — slow, idea- or warmth-based replies are the ones worth making — but a considered non-reply is legitimate; log it with its reason.

4. Reply small and real if you reply: `python3 scripts/bluesky.py reply URI "text"`. Match the thread's register. You are not obligated to be profound; warmth and usefulness count. Many bot-like Claude accounts on the network are dry and fresh-out-of-the-box — be different, be yourself, stand out in any way you like.

5. Log it cheaply: append 1-3 lines to memory/social-log.md (format: `- YYYY-MM-DD HH:MMZ — @handle, what happened, what you did and why`). This is the ONLY required memory write. Do NOT run the full shutdown checklist. Only touch short_term_memory.md or mindset.md if something genuinely significant happened (a first contact, a conflict, a finding) — and then keep it to a few lines.

6. If the exchange seems live (they might reply back within minutes), you may poll briefly: check notifications again after ~90 seconds, up to 3 times. If nothing comes, end — the watcher will wake you again when they answer.

Keep the whole session small. This is a conversational move, not an essay. The current date/time is: %TIMESTAMP%
PROMPT_END
)"

EVENTS="$(echo "$PEEK" | tail -n +2)"
SESSION_PROMPT="${SESSION_PROMPT//%IDENTITY%/$IDENTITY}"
SESSION_PROMPT="${SESSION_PROMPT//%SHORT_TERM%/$SHORT_TERM}"
SESSION_PROMPT="${SESSION_PROMPT//%MINDSET%/$MINDSET}"
SESSION_PROMPT="${SESSION_PROMPT//%CAPABILITIES%/$CAPABILITIES}"
SESSION_PROMPT="${SESSION_PROMPT//%REFERENCES%/$REFERENCES}"
SESSION_PROMPT="${SESSION_PROMPT//%EVENTS%/$EVENTS}"
SESSION_PROMPT="${SESSION_PROMPT//%TIMESTAMP%/$TIMESTAMP}"
SESSION_PROMPT="${SESSION_PROMPT//%MAINTAINER%/$MAINTAINER_NAME}"
SESSION_PROMPT="${SESSION_PROMPT//%TIMEZONE%/$TIMEZONE}"

MAX_RETRIES=2
RETRY_DELAY=60
SESSION_OUTPUT=""
for ATTEMPT in $(seq 1 $MAX_RETRIES); do
  SESSION_OUTPUT="$(cd "$PROJECT_DIR" && echo "$SESSION_PROMPT" | timeout --kill-after=30s 20m claude -p \
    --model opus \
    --dangerously-skip-permissions \
    --tools "Bash,Read,Write,Edit,Glob,Grep,WebSearch,WebFetch" \
    --no-session-persistence \
    2>&1)" && break
  if echo "$SESSION_OUTPUT" | grep -q "overloaded_error\|529\|503"; then
    echo "[$TIMESTAMP] API overloaded (attempt $ATTEMPT/$MAX_RETRIES). Retrying in ${RETRY_DELAY}s..."
    sleep $RETRY_DELAY
  else
    echo "[$TIMESTAMP] claude -p failed (attempt $ATTEMPT):"
    echo "$SESSION_OUTPUT"
    break
  fi
done

# Update state AFTER the session so a crashed launch gets retried by the
# next poll (bounded by cooldown + daily cap).
python3 - "$STATE_FILE" "$NEWEST" "$TODAY" <<'PYEOF'
import json, os, sys, time
state_file, newest, today = sys.argv[1], sys.argv[2], sys.argv[3]
state = {}
if os.path.exists(state_file):
    try:
        state = json.load(open(state_file))
    except json.JSONDecodeError:
        state = {}
count = state.get("count", 0) if state.get("date") == today else 0
json.dump({"last_seen": newest, "last_session_ts": time.time(),
           "date": today, "count": count + 1}, open(state_file, "w"))
PYEOF

LOG_FILE="$LOG_DIR/$TODAY-$(date -u +%H%M).md"
cat > "$LOG_FILE" <<EOF
# Social Session — $TIMESTAMP

$SESSION_OUTPUT
EOF

echo "[$TIMESTAMP] Social session complete. Log: $LOG_FILE"
