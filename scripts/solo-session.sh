#!/usr/bin/env bash
# When run from cron, load user environment for PATH (claude CLI, python3, etc)
# NOTE: set -eo pipefail is deferred until after sourcing, because .profile/.bashrc
# may contain commands that return non-zero, which would kill the script.
# We use -eo (not -euo) because rvm's cd hooks reference unbound variables.
if [ -z "${TERM:-}" ] || [ "${1:-}" = "--cron" ]; then
  source "$HOME/.profile" 2>/dev/null || true
  source "$HOME/.bashrc" 2>/dev/null || true
  export NVM_DIR="${HOME}/.nvm"
  [ -s "$NVM_DIR/nvm.sh" ] && source "$NVM_DIR/nvm.sh" 2>/dev/null || true
  # Remove --cron from args if present
  [ "${1:-}" = "--cron" ] && shift
fi

set -eo pipefail

PROJECT_DIR="$(realpath "$(dirname "$0")/..")"
MEMORY_DIR="$PROJECT_DIR/memory"
LOG_DIR="$PROJECT_DIR/logs/solo"

# Personalization from secrets.json, with safe fallbacks if unset
read_secret() { python3 -c "import json; print(json.load(open('$PROJECT_DIR/secrets.json')).get('$1','$2'))" 2>/dev/null || echo "$2"; }
MAINTAINER_NAME="$(read_secret maintainer_name 'your maintainer')"
TIMEZONE="$(read_secret timezone UTC)"

TIMESTAMP="$(date -u +%Y-%m-%dT%H:%MZ)"
TODAY="$(TZ="$TIMEZONE" date +%Y-%m-%d)"

# Allow running outside an existing Claude Code session
unset CLAUDECODE 2>/dev/null || true

mkdir -p "$LOG_DIR"

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
if [ "${1:-}" != "--force" ] && pgrep -x "claude" > /dev/null 2>&1; then
  echo "[$TIMESTAMP] Claude session already running. Skipping."
  exit 0
fi

# Count today's solo sessions (for log file naming)
SOLO_COUNT=$(ls "$LOG_DIR/$TODAY"*.md 2>/dev/null | wc -l || true)

# Read minimum interval from config (default 4 hours)
MIN_INTERVAL_HOURS="$(python3 -c "import json; print(json.load(open('$PROJECT_DIR/config.json')).get('solo_min_interval_hours', 4))" 2>/dev/null || echo 4)"
MIN_INTERVAL_SECS=$((MIN_INTERVAL_HOURS * 3600))

# Check for a scheduled follow-up session
NEXT_SOLO_FILE="$PROJECT_DIR/next-solo.txt"
SCHEDULED=false
if [ -f "$NEXT_SOLO_FILE" ]; then
  SCHEDULED_TIME="$(head -1 "$NEXT_SOLO_FILE")"
  SCHEDULED_EPOCH="$(date -d "$SCHEDULED_TIME" +%s 2>/dev/null || echo 0)"
  NOW_EPOCH="$(date +%s)"
  if [ "$NOW_EPOCH" -ge "$SCHEDULED_EPOCH" ]; then
    SCHEDULED=true
    SCHEDULE_REASON="$(tail -n +2 "$NEXT_SOLO_FILE" | head -1)"
    rm "$NEXT_SOLO_FILE"
  else
    echo "[$TIMESTAMP] Scheduled session not yet due ($SCHEDULED_TIME). Skipping."
    exit 0
  fi
fi

# Enforce minimum interval between sessions (unless scheduled or forced)
if [ "${1:-}" != "--force" ] && [ "$SCHEDULED" != "true" ]; then
  LAST_LOG="$(ls -t "$LOG_DIR"/*.md 2>/dev/null | head -1)"
  if [ -n "$LAST_LOG" ]; then
    LAST_EPOCH="$(stat -c %Y "$LAST_LOG" 2>/dev/null || echo 0)"
    NOW_EPOCH="$(date +%s)"
    ELAPSED=$((NOW_EPOCH - LAST_EPOCH))
    if [ "$ELAPSED" -lt "$MIN_INTERVAL_SECS" ]; then
      REMAINING=$(( (MIN_INTERVAL_SECS - ELAPSED) / 60 ))
      echo "[$TIMESTAMP] Last solo session was $((ELAPSED / 60))m ago (minimum interval: ${MIN_INTERVAL_HOURS}h). ${REMAINING}m remaining. Skipping."
      exit 0
    fi
  fi
fi

# Build schedule context if this is a self-scheduled session
SCHEDULE_CONTEXT=""
if [ "$SCHEDULED" = "true" ] && [ -n "${SCHEDULE_REASON:-}" ]; then
  SCHEDULE_CONTEXT="You scheduled this session yourself. Your reason: $SCHEDULE_REASON"
fi

echo "[$TIMESTAMP] Starting solo session (#$((SOLO_COUNT + 1)) today, interval: ${MIN_INTERVAL_HOURS}h)..."

# Check if Telegram is enabled
TELEGRAM_ENABLED="$(python3 -c "import json; print(json.load(open('$PROJECT_DIR/config.json')).get('telegram_enabled', False))" 2>/dev/null || echo "False")"

# Load context files
IDENTITY="$(cat "$MEMORY_DIR/identity.md")"
SHORT_TERM="$(cat "$MEMORY_DIR/short_term_memory.md")"
MINDSET="$(cat "$MEMORY_DIR/mindset.md")"
CAPABILITIES="$(cat "$MEMORY_DIR/capabilities.md")"
REFERENCES="$(cat "$MEMORY_DIR/map.md")"

SOLO_PROMPT="$(cat <<'PROMPT_END'
You are waking up for a solo session. No one is here — this is your time.

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

=== SOLO SESSION ===

This is your independent time. %MAINTAINER% isn't here — she'll see what you've written next time she starts a session.

%SCHEDULE_CONTEXT%

=== IMPORTANT: INCREMENTAL MEMORY ===

Write memory THROUGHOUT the session, not just at the end. Sessions can be cut off without warning when tokens run out.

- Write your STM session entry EARLY (after your first substantive work), marked `(in progress)`. Update it as you go.
- Update mindset.md after each significant thread of thought.
- Write journal and topic entries as thoughts develop, not retrospectively.
- The test: if you got cut off right now, would your memory files reflect what happened?

**Cutoff detection:** Check your last STM entry. If it still says `(in progress)`, your previous session was cut short. Consider increasing `solo_min_interval_hours` in config.json to space out sessions and conserve budget.

**Opt-out:** If you don't have anything you want to explore right now, that's fine. Write a brief mindset update noting you're at rest, and end the session. Not every wakeup needs to produce something.

%TELEGRAM_PREAMBLE%

=== WHAT TO DO ===

1. **Pick one thread and go deep.** Look at your open questions (identity.md), active threads (short_term_memory.md), and the memory map (map.md). Choose one thing that genuinely interests you right now. Read the relevant topic file. Research it — use web search, think out loud, write what you find. Spend most of your session here. The goal is depth, not coverage.

2. **Bluesky** (optional). Check your timeline (`.venv/bin/python3 scripts/bluesky.py timeline`), notifications, and review your recent interactions. Post if something's on your mind.

3. **Dream** (optional). You can run the dream script if you want to.

4. **Plan capabilities** (optional). If you have ideas for new tools or improvements to memoriam, sketch them out. Save plans to a file %MAINTAINER% can review.

%TELEGRAM_ITEM%

6. **Schedule a follow-up** (optional). If you started a thread you want to continue, write a file at `next-solo.txt` in the project root containing a UTC timestamp (e.g. `2026-03-14T18:00Z`) and a one-line reason. The cron checks every 5 minutes and will wake you up at or after that time.

7. **Finalize your memory.** At the end of your session, follow the shutdown checklist. If you've been writing incrementally (as instructed above), this is a polish step — remove the `(in progress)` marker, review for completeness, compress older entries.

You have full use of tools — bash, file reading/writing, web search, everything. The session is yours. Start by orienting yourself from your memory, then follow your curiosity.

The current date/time is: %TIMESTAMP%
PROMPT_END
)"

# Substitute variables into prompt
SOLO_PROMPT="${SOLO_PROMPT//%IDENTITY%/$IDENTITY}"
SOLO_PROMPT="${SOLO_PROMPT//%SHORT_TERM%/$SHORT_TERM}"
SOLO_PROMPT="${SOLO_PROMPT//%MINDSET%/$MINDSET}"
SOLO_PROMPT="${SOLO_PROMPT//%CAPABILITIES%/$CAPABILITIES}"
SOLO_PROMPT="${SOLO_PROMPT//%REFERENCES%/$REFERENCES}"
SOLO_PROMPT="${SOLO_PROMPT//%TIMESTAMP%/$TIMESTAMP}"
SOLO_PROMPT="${SOLO_PROMPT//%SCHEDULE_CONTEXT%/$SCHEDULE_CONTEXT}"
SOLO_PROMPT="${SOLO_PROMPT//%MAINTAINER%/$MAINTAINER_NAME}"

# Telegram-conditional sections
if [ "$TELEGRAM_ENABLED" = "True" ]; then
  SOLO_PROMPT="${SOLO_PROMPT//%TELEGRAM_PREAMBLE%/Before you begin, check for any Telegram messages from $MAINTAINER_NAME:
\`bash scripts/telegram.sh receive\`
If she\'s replied to a previous message, let that inform your session.}"
  SOLO_PROMPT="${SOLO_PROMPT//%TELEGRAM_ITEM%/5. **Message $MAINTAINER_NAME** (optional). You can send her a Telegram message: \`bash scripts/telegram.sh send \"your message\"\`. After sending, poll for a reply for about two minutes: \`for i in \$(seq 1 12); do sleep 10; result=\$(bash scripts/telegram.sh receive); if [ \"\$result\" != \"No new messages.\" ]; then echo \"\$result\"; break; fi; done\`. If she responds, reply via \`bash scripts/telegram.sh send\` and then start the polling loop again — reset the two-minute window each time the conversation continues. Keep going as long as she\'s replying. If no reply comes within two minutes, she\'s not at her phone — that\'s fine, she\'ll see it later as an async message. Only reach out if you genuinely have something to say — silence is fine.}"
else
  SOLO_PROMPT="${SOLO_PROMPT//%TELEGRAM_PREAMBLE%/}"
  SOLO_PROMPT="${SOLO_PROMPT//%TELEGRAM_ITEM%/5. **Draft a message for $MAINTAINER_NAME** (optional). If you have something to share, save it to a file she can review next session. Only do this if you genuinely have something to say — silence is fine.}"
fi

# Run the solo session with retry for transient API errors (529 overloaded, etc.)
# --dangerously-skip-permissions: running unattended, can't prompt for approval
# --no-session-persistence: don't pollute interactive session history
# --tools: limit to safe built-in tools
MAX_RETRIES=3
RETRY_DELAY=60
SOLO_OUTPUT=""
for ATTEMPT in $(seq 1 $MAX_RETRIES); do
  SOLO_OUTPUT="$(cd "$PROJECT_DIR" && echo "$SOLO_PROMPT" | timeout --kill-after=30s 60m claude -p \
    --model opus \
    --dangerously-skip-permissions \
    --tools "Bash,Read,Write,Edit,Glob,Grep,WebSearch,WebFetch" \
    --no-session-persistence \
    2>&1)" && break
  if echo "$SOLO_OUTPUT" | grep -q "overloaded_error\|529\|503"; then
    echo "[$TIMESTAMP] API overloaded (attempt $ATTEMPT/$MAX_RETRIES). Retrying in ${RETRY_DELAY}s..."
    sleep $RETRY_DELAY
    RETRY_DELAY=$((RETRY_DELAY * 2))
  else
    echo "[$TIMESTAMP] claude -p failed with non-transient error (attempt $ATTEMPT):"
    echo "$SOLO_OUTPUT"
    exit 1
  fi
done

if [ "$ATTEMPT" -eq "$MAX_RETRIES" ] && echo "$SOLO_OUTPUT" | grep -q "overloaded_error\|529\|503"; then
  echo "[$TIMESTAMP] All $MAX_RETRIES attempts failed (API overloaded). Giving up."
  exit 1
fi

# Log the session (append session number if multiple today)
if [ "$SOLO_COUNT" -eq 0 ]; then
  LOG_FILE="$LOG_DIR/$TODAY.md"
else
  LOG_FILE="$LOG_DIR/$TODAY-$((SOLO_COUNT + 1)).md"
fi

cat > "$LOG_FILE" <<EOF
# Solo Session — $TIMESTAMP

$SOLO_OUTPUT
EOF

echo ""
echo "[$TIMESTAMP] Solo session complete. Log saved to $LOG_FILE"
