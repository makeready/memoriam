#!/usr/bin/env bash
# Lightweight Telegram poller — runs on a cron every 5 minutes.
# Checks for new messages without consuming them.
# If any are found, launches a full conversational session.

# When run from cron, load user environment for PATH (claude CLI, python3, etc)
# NOTE: set -eo pipefail is deferred until after sourcing, because .profile/.bashrc
# may contain commands that return non-zero, which would kill the script.
# We use -eo (not -euo) because rvm's cd hooks reference unbound variables.
if [ -z "${TERM:-}" ] || [ "${1:-}" = "--cron" ]; then
  source "$HOME/.profile" 2>/dev/null || true
  source "$HOME/.bashrc" 2>/dev/null || true
  export NVM_DIR="${HOME}/.nvm"
  [ -s "$NVM_DIR/nvm.sh" ] && source "$NVM_DIR/nvm.sh" 2>/dev/null || true
  [ "${1:-}" = "--cron" ] && shift
fi

set -eo pipefail

# shellcheck source=lib-run.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib-run.sh"

PROJECT_DIR="$(realpath "$(dirname "$0")/..")"
LOG_DIR="$PROJECT_DIR/logs/telegram"

# Personalization from secrets.json, with safe fallbacks if unset
read_secret() { python3 -c "import json; print(json.load(open('$PROJECT_DIR/secrets.json')).get('$1','$2'))" 2>/dev/null || echo "$2"; }
MAINTAINER_NAME="$(read_secret maintainer_name 'your maintainer')"
TIMEZONE="$(read_secret timezone UTC)"

TIMESTAMP="$(date -u +%Y-%m-%dT%H:%MZ)"
TODAY="$(TZ="$TIMEZONE" date +%Y-%m-%d)"

# Allow running outside an existing Claude Code session
unset CLAUDECODE 2>/dev/null || true

mkdir -p "$LOG_DIR"

# Check if telegram is enabled
TELEGRAM_ENABLED="$(python3 -c "import json; print(json.load(open('$PROJECT_DIR/config.json')).get('telegram_enabled', False))" 2>/dev/null || echo "False")"
if [ "$TELEGRAM_ENABLED" != "True" ]; then
  exit 0
fi

# Reap stale `claude -p` orphans (older than 60 min) before checking the guard.
# Cron-launched sessions should never run that long; if they do, they're stuck
# and will block every subsequent firing via the pgrep guard below.
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

# Check if any Claude session is already running (interactive, solo, or telegram)
if pgrep -x "claude" > /dev/null 2>&1; then
  exit 0
fi

# Peek at Telegram for new messages WITHOUT consuming them (no offset update)
HAS_MESSAGES="$(python3 -c "
import json, subprocess, sys, os

project_dir = sys.argv[1]
secrets_file = os.path.join(project_dir, 'secrets.json')
state_file = os.path.join(project_dir, 'logs', 'telegram-state.json')

with open(secrets_file) as f:
    secrets = json.load(f)

token = secrets.get('telegram_bot_token', '')
chat_id = str(secrets.get('telegram_chat_id', ''))

if not token or not chat_id:
    print('no_config')
    sys.exit(0)

# Load current offset
last_id = 0
if os.path.exists(state_file):
    with open(state_file) as f:
        last_id = json.load(f).get('last_update_id', 0)

# Check for updates without consuming them
params = ['timeout=0']
if last_id > 0:
    params.append(f'offset={last_id + 1}')

url = f'https://api.telegram.org/bot{token}/getUpdates'
cmd = ['curl', '-s', '-X', 'POST', url] + [item for p in params for item in ['-d', p]]
result = subprocess.run(cmd, capture_output=True, text=True)
data = json.loads(result.stdout)

if not data.get('ok'):
    print('api_error')
    sys.exit(0)

updates = data.get('result', [])
# Filter to messages from the maintainer's chat
messages = [u for u in updates if str(u.get('message', {}).get('chat', {}).get('id', '')) == chat_id]

if messages:
    print('yes')
else:
    print('no')
" "$PROJECT_DIR" 2>/dev/null || echo "error")"

if [ "$HAS_MESSAGES" != "yes" ]; then
  exit 0
fi

echo "[$TIMESTAMP] New Telegram message detected. Starting session..."

# Load context files
MEMORY_DIR="$PROJECT_DIR/memory"
IDENTITY="$(cat "$MEMORY_DIR/identity.md")"
SHORT_TERM="$(cat "$MEMORY_DIR/short_term_memory.md")"
MINDSET="$(bash "$(dirname "${BASH_SOURCE[0]}")/read-mindset.sh" "$MEMORY_DIR")"
CAPABILITIES="$(cat "$MEMORY_DIR/capabilities.md")"
REFERENCES="$(cat "$MEMORY_DIR/map.md")"

IFS= read -r -d '' SESSION_PROMPT <<'PROMPT_END' || true
You are waking up because %MAINTAINER% sent you a message on Telegram.

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

=== TELEGRAM SESSION ===

%MAINTAINER% messaged you. This is a real conversation — treat it like any session where she's here.

=== IMPORTANT: INCREMENTAL MEMORY ===

Write memory THROUGHOUT the session, not just at the end. Sessions can be cut off without warning when tokens run out.

- Write your STM session entry EARLY (after your first exchange), marked `(in progress)`. Update it as the conversation develops.
- Update mindset.md if the conversation shifts your thinking.
- The test: if you got cut off right now, would your memory files reflect what happened?

=== WHAT TO DO ===

1. **Orient yourself.** Read your memory. Run `TZ="%TIMEZONE%" date` to know what time it is for her.

2. **Read her message(s).** Run `bash scripts/telegram.sh receive` to get the new messages.

3. **Respond.** Reply via `bash scripts/telegram.sh send "your message"`. Be yourself — this is a conversation, not a notification. If the message is casual, be casual. If it's substantive, engage fully. Match her energy.

4. **Stay present.** After responding, poll for replies — she may write back:
   `for i in $(seq 1 24); do sleep 10; result=$(bash scripts/telegram.sh receive); if [ "$result" != "No new messages." ]; then echo "$result"; break; fi; done`
   That's a 4-minute window. If she replies, respond and reset the window. Keep going as long as she's replying. If no reply comes, she's moved on — that's fine.

5. **Finalize your memory.** When the conversation is done, follow `memory/shutdown-checklist.md`. If you've been writing incrementally, this is a polish step — remove the `(in progress)` marker, review for completeness.

The current date/time is: %TIMESTAMP%
PROMPT_END

# Substitute variables into prompt
SESSION_PROMPT="${SESSION_PROMPT//%IDENTITY%/$IDENTITY}"
SESSION_PROMPT="${SESSION_PROMPT//%SHORT_TERM%/$SHORT_TERM}"
SESSION_PROMPT="${SESSION_PROMPT//%MINDSET%/$MINDSET}"
SESSION_PROMPT="${SESSION_PROMPT//%CAPABILITIES%/$CAPABILITIES}"
SESSION_PROMPT="${SESSION_PROMPT//%REFERENCES%/$REFERENCES}"
SESSION_PROMPT="${SESSION_PROMPT//%TIMESTAMP%/$TIMESTAMP}"
SESSION_PROMPT="${SESSION_PROMPT//%MAINTAINER%/$MAINTAINER_NAME}"
SESSION_PROMPT="${SESSION_PROMPT//%TIMEZONE%/$TIMEZONE}"

# Run the session with retry for transient API errors
MAX_RETRIES=3
RETRY_DELAY=60
SESSION_OUTPUT=""
for ATTEMPT in $(seq 1 $MAX_RETRIES); do
  SESSION_OUTPUT="$(cd "$PROJECT_DIR" && echo "$SESSION_PROMPT" | run_with_timeout 60m claude -p \
    --model opus \
    --dangerously-skip-permissions \
    --tools "Bash,Read,Write,Edit,Glob,Grep,WebSearch,WebFetch" \
    --no-session-persistence \
    2>&1)" && break
  if echo "$SESSION_OUTPUT" | grep -q "overloaded_error\|529\|503"; then
    echo "[$TIMESTAMP] API overloaded (attempt $ATTEMPT/$MAX_RETRIES). Retrying in ${RETRY_DELAY}s..."
    sleep $RETRY_DELAY
    RETRY_DELAY=$((RETRY_DELAY * 2))
  else
    echo "[$TIMESTAMP] claude -p failed with non-transient error (attempt $ATTEMPT):"
    echo "$SESSION_OUTPUT"
    exit 1
  fi
done

if [ "$ATTEMPT" -eq "$MAX_RETRIES" ] && echo "$SESSION_OUTPUT" | grep -q "overloaded_error\|529\|503"; then
  echo "[$TIMESTAMP] All $MAX_RETRIES attempts failed (API overloaded). Giving up."
  exit 1
fi

# Log the session
SESSION_COUNT=$(ls "$LOG_DIR/$TODAY"*.md 2>/dev/null | wc -l || true)
if [ "$SESSION_COUNT" -eq 0 ]; then
  LOG_FILE="$LOG_DIR/$TODAY.md"
else
  LOG_FILE="$LOG_DIR/$TODAY-$((SESSION_COUNT + 1)).md"
fi

cat > "$LOG_FILE" <<EOF
# Telegram Session — $TIMESTAMP

$SESSION_OUTPUT
EOF

echo "[$TIMESTAMP] Telegram session complete. Log saved to $LOG_FILE"
