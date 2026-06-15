#!/usr/bin/env bash
set -e

cd "$(dirname "$0")"

# Always-loaded memory files — created blank, populated through use.
touch memory/identity.md \
      memory/short_term_memory.md \
      memory/mindset.md \
      memory/capabilities.md \
      memory/map.md \
      memory/substrate-log.md

# Personalization & secrets — copy the template, then fill it in.
if [ ! -f secrets.json ]; then
  cp secrets.json.example secrets.json
  echo "Created secrets.json from template."
  echo "  -> Edit it to set maintainer_name, timezone, assistant_name,"
  echo "     and any Telegram / Bluesky credentials you want to use."
fi

echo "Behavioral settings (session intervals, caps, feature toggles) live in config.json."
echo "Ready. Open a Claude Code session in this directory to start the identity conversation."
