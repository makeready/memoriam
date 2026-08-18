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
  printf 'Weave them into mindset.md and move them to absorbed/ once integrated.\n'
  for f in "${fragments[@]}"; do
    printf '\n### fragment: %s\n\n' "$(basename "$f")"
    cat "$f"
  done
fi
