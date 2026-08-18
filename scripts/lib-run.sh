#!/usr/bin/env bash
# Shared helper for the automation scripts.
#
# macOS ships no `timeout` binary (coreutils installs it as `gtimeout`), so
# invoking it directly makes every cron script fail at the point of use even
# when the script itself parses. Prefer a real timeout when one exists, and
# degrade to running without one rather than not running at all.
#
# Install the real thing with `brew install coreutils` — without it a hung
# `claude -p` has no upper bound.

run_with_timeout() {
  local limit="$1"
  shift
  if command -v timeout >/dev/null 2>&1; then
    timeout --kill-after=30s "$limit" "$@"
  elif command -v gtimeout >/dev/null 2>&1; then
    gtimeout --kill-after=30s "$limit" "$@"
  else
    echo "warning: no timeout/gtimeout on PATH, running without a time limit (brew install coreutils)" >&2
    "$@"
  fi
}
