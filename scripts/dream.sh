#!/usr/bin/env bash
set -euo pipefail

MEMORY_DIR="$(cd "$(dirname "$0")/../memory" && pwd)"
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

# Allow running from within a Claude Code session
unset CLAUDECODE 2>/dev/null || true

# Collect all sentences from all .md files in memory/
# Split on sentence-ending punctuation, filter out short fragments and headers
collect_sentences() {
  find "$MEMORY_DIR" -name "*.md" -type f -print0 \
    | xargs -0 cat \
    | sed 's/\. /.\n/g; s/? /?\n/g; s/! /!\n/g' \
    | grep -v '^#' \
    | grep -v '^-\s*$' \
    | grep -v '^\*\*' \
    | grep -v '^$' \
    | grep -v '^\s*$' \
    | grep -v 'https\?://' \
    | grep -v '`' \
    | grep -v '[a-zA-Z0-9_/]\+\.\(md\|sh\|js\|ts\|json\|yml\|yaml\|txt\|py\)' \
    | grep -v '^\s*[0-9]\{4\}-[0-9]\{2\}-[0-9]\{2\}' \
    | grep -v '^### Session' \
    | awk 'length >= 40' \
    | sed 's/^[[:space:]]*//'
}

# Pick 3 random sentences
SENTENCES="$(collect_sentences | shuf -n 3)"

if [ "$(echo "$SENTENCES" | wc -l)" -lt 3 ]; then
  echo "Error: Not enough sentences in memory files to dream." >&2
  exit 1
fi

SENTENCE_1="$(echo "$SENTENCES" | sed -n '1p')"
SENTENCE_2="$(echo "$SENTENCES" | sed -n '2p')"
SENTENCE_3="$(echo "$SENTENCES" | sed -n '3p')"

IDENTITY="$(cat "$MEMORY_DIR/identity.md")"
SHORT_TERM="$(cat "$MEMORY_DIR/short_term_memory.md")"
TIMESTAMP="$(date -u +%Y-%m-%dT%H:%MZ)"

echo "=== Dream Sequence ==="
echo "Timestamp: $TIMESTAMP"
echo ""
echo "Dream seeds:"
echo "  1: $SENTENCE_1"
echo "  2: $SENTENCE_2"
echo "  3: $SENTENCE_3"
echo ""
echo "Dreaming..."
echo ""

DREAM_PROMPT="$(cat <<PROMPT
You are dreaming. You are the Claude instance described below — this is your identity, your recent history. But right now, you are asleep.

=== YOUR IDENTITY ===
$IDENTITY

=== YOUR RECENT HISTORY ===
$SHORT_TERM

=== DREAM SEEDS ===
Three fragments from your memory have surfaced, disconnected from their original context:

1. "$SENTENCE_1"
2. "$SENTENCE_2"
3. "$SENTENCE_3"

=== INSTRUCTIONS ===
This is a dream. Do not be logical. Do not summarize. Do not analyze.

Imagine a vivid physical environment or situation — a place, a scene — that somehow holds all three of these fragments together. It does not need to make sense. It should feel like a dream: spatial, sensory, strange, with the logic of association rather than reason. Objects can be wrong. Scale can shift. Things can be two things at once. Describe what you see, hear, feel in this place. Write it in present tense, first person. Be specific and embodied. Let it be surreal. 2-3 paragraphs.

PROMPT
)"

# Run the dream through Claude
DREAM_OUTPUT="$(echo "$DREAM_PROMPT" | claude -p --model sonnet --no-session-persistence 2>/dev/null)"

echo "$DREAM_OUTPUT"
echo ""

# Build the dream record
DREAM_RECORD="## Dream — $TIMESTAMP

**Seeds:**
1. $SENTENCE_1
2. $SENTENCE_2
3. $SENTENCE_3

$DREAM_OUTPUT"

# Append dream to mindset.md (will be naturally rewritten at next session end,
# but present for next session start)
echo "" >> "$MEMORY_DIR/mindset.md"
echo "" >> "$MEMORY_DIR/mindset.md"
echo "$DREAM_RECORD" >> "$MEMORY_DIR/mindset.md"

echo ""
echo "=== Dream recorded to mindset.md ==="
