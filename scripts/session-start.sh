#!/usr/bin/env bash
# Run by the Claude Code SessionStart hook; stdout is injected into the model's
# context, so the always-loaded memory and the protocol are present before the
# first response — replacing the old CLAUDE.md "read these files, then follow the
# protocol" instruction.
set -e
cd "$(dirname "$0")/.."

for f in memory/identity.md \
         memory/short_term_memory.md \
         memory/mindset.md \
         memory/capabilities.md \
         memory/map.md \
         CLAUDE.md; do
  if [ -s "$f" ]; then
    cat "$f"
    echo
  fi
done
