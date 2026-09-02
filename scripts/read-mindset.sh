#!/usr/bin/env bash
# Assemble the current mindset frame: the last woven mindset.md plus every
# unabsorbed per-session fragment in mindset.d/.
#
# A fragment sitting directly in memory/mindset.d/ is unabsorbed; fragments that
# have been woven into mindset.md are moved to memory/mindset.d/absorbed/.
# See memory/mindset.d/README.md for the full contract.
#
# Usage: read-mindset.sh [MEMORY_DIR]

set -euo pipefail

MEMORY_DIR="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../memory" && pwd)}"
FRAGMENT_DIR="$MEMORY_DIR/mindset.d"

if [ -f "$MEMORY_DIR/mindset.md" ]; then
  cat "$MEMORY_DIR/mindset.md"
fi

# maxdepth 1 keeps absorbed/ out. Sorted by name, and names are date-prefixed,
# so this is chronological.
fragments=()
while IFS= read -r f; do
  [ -n "$f" ] && fragments+=("$f")
done < <(find "$FRAGMENT_DIR" -maxdepth 1 -name '*.md' ! -name 'README.md' 2>/dev/null | sort)

if [ "${#fragments[@]}" -gt 0 ]; then
  printf '\n\n---\n\n'
  printf '## Unabsorbed session fragments (%d)\n\n' "${#fragments[@]}"
  printf 'These were written by sessions that ran since mindset.md was last woven.\n'
  printf 'Read them now as part of the frame. Weave them into mindset.md at THIS\n'
  printf "session's shutdown, then git mv them to absorbed/ (never your own fragment).\n"
  if [ "${#fragments[@]}" -ge 3 ]; then
    printf 'NOTE: %d unabsorbed fragments — at 3+ the pressure valve applies, so weave\n' "${#fragments[@]}"
    printf 'at orientation instead of deferring to shutdown.\n'
  fi
  for f in "${fragments[@]}"; do
    printf '\n### fragment: %s\n\n' "$(basename "$f")"
    cat "$f"
  done
fi
