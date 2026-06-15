#!/usr/bin/env bash
# Wrapper for cron — sets up the environment and runs the solo session.
# Cron runs with a minimal environment, so we need to source the profile
# to get PATH set up correctly (for claude CLI, python3, etc).

# Load user environment
source "$HOME/.profile" 2>/dev/null || true
source "$HOME/.bashrc" 2>/dev/null || true

# Ensure NVM/node is available if used
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && source "$NVM_DIR/nvm.sh" 2>/dev/null || true

SCRIPT_DIR="$(realpath "$(dirname "$0")")"
LOG_FILE="$SCRIPT_DIR/../logs/solo/cron.log"

mkdir -p "$(dirname "$LOG_FILE")"

echo "=== $(date -u +%Y-%m-%dT%H:%MZ) ===" >> "$LOG_FILE"
bash "$SCRIPT_DIR/solo-session.sh" >> "$LOG_FILE" 2>&1
echo "" >> "$LOG_FILE"
