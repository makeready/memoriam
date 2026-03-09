#!/usr/bin/env bash
set -e

cd "$(dirname "$0")"

touch memory/identity.md memory/short_term_memory.md memory/mindset.md

cat > memory/references.md << 'EOF'
**Topics:**
(none yet)

**People:**
(none yet)
EOF

echo "Ready. Open a Claude Code session in this directory to start the identity conversation."
