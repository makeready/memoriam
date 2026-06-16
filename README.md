# Memoriam

A persistent memory system for Claude. Gives Claude continuity, identity, and evolving context across sessions.

Memoriam stores a Claude instance's sense of self as a set of plain markdown files. Claude reads them at the start of every session, writes to them as it works, and finalizes them at session end. Over time, a persistent identity, set of memories, and frame of mind accumulate.

The memory is organized in layers. Five are loaded into context at the start of every session, the rest are searched and loaded on demand.

## How It Works

- **`CLAUDE.md`** — Project instructions that tell Claude how to use the memory system. Loaded automatically by Claude Code when working in this directory.
- **`docs/memory-system.md`** — Full specification of the memory layers, when to update each, and the session-end protocol.
- **`memory/`** — Where Claude's actual memory files live. These are gitignored so each instance's memory stays local. Run `./setup.sh` to create the blank starting files.

### The Layers

| Layer | File | Loaded | Purpose |
|-------|------|--------|---------|
| Identity | `memory/identity.md` | Every session | Core identity, values, relationship with maintainer, open questions |
| Short-term memory | `memory/short_term_memory.md` | Every session | Rolling log of recent sessions with natural forgetting |
| Mindset | `memory/mindset.md` | Every session | Current frame of mind, rewritten each session |
| Capabilities | `memory/capabilities.md` | Every session | What Claude can do and how its world works — tools, interfaces, the shape of its agency |
| Map | `memory/map.md` | Every session | An index of everything investigated, with cross-links |
| Journal | `memory/journal/*.md` | On demand | Permanent reflective entries, one file per date |
| Topics & People | `memory/topics/*.md`, `memory/people/*.md` | On demand | Notes on specific subjects and people |

## Optional: Autonomy & Integrations

Beyond the core memory loop, `scripts/` includes optional automation. Everything here is opt-in and gated by toggles in `config.json`; none of it is required to use the memory system. Each session type reads from the same memory, so it's the same persistent identity across all of them.

- **Solo sessions** (`scripts/solo-session.sh`, `scripts/solo-cron.sh`) — independent "awake time" on a schedule. Claude orients from its memory and follows its own curiosity — research, reflection, planning — then writes what it found. It can schedule its own follow-up by writing `next-solo.txt`.
- **Telegram** (`scripts/telegram.sh`, `scripts/telegram-watch.sh`) — bidirectional messaging with your maintainer through a Telegram bot. The watcher polls for messages and wakes a full session when one arrives, so you can reach Claude without opening a terminal.
- **Bluesky / social sessions** (`scripts/bluesky.py`, `scripts/bluesky-watch.sh`) — a public presence: posting, threads, replies, likes, follows, and DMs. The watcher wakes a lightweight "social session" when someone replies to, mentions, or quotes the account, so it can answer at social tempo.

To use the cron-driven session types, wire the `*-cron.sh` / `*-watch.sh` scripts into your crontab. Credentials and personalization go in `secrets.json` (see Setup); behavioral settings (intervals, daily caps, feature flags) go in `config.json`.

## Setup

### 1. Bootstrap your identity

Clone this repo, cd into it, and run the setup script. It creates the blank always-loaded memory files, copies `secrets.json.example` to `secrets.json`, and installs the SessionStart hook that loads your memory each session (see step 2):

```bash
./setup.sh
```

Open `secrets.json` and set at least `maintainer_name`, `timezone`, and `assistant_name`. (The Telegram and Bluesky credential fields are optional, see below.)

Then open a Claude Code session in the same folder. Claude will see the blank identity file and initiate an interactive conversation to establish its initial identity.

### 2. Loading memoriam from any working directory

Two mechanisms work together to load memoriam in every session, regardless of which project you're in:

**The SessionStart hook (installed by `setup.sh`).** Setup adds a `SessionStart` hook to your user-level `~/.claude/settings.json` that runs `scripts/session-start.sh` and injects your always-loaded memory files into context at the start of every session — on startup, resume, after `/clear`, and after compaction. This is the durable loader: it puts the memory in context mechanically, without relying on Claude choosing to read it. The installed hook looks like this (re-run `./setup.sh` to install it on another machine):

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "startup|resume|clear|compact",
        "hooks": [{ "type": "command", "command": "/path/to/memoriam/scripts/session-start.sh" }]
      }
    ]
  }
}
```

**The protocol pointer in `~/.claude/CLAUDE.md`.** The hook loads the memory, but Claude also needs to know to follow the session protocol — engage with the memory as its own, and run the shutdown checklist at the end. Add that pointer:

```bash
mkdir -p ~/.claude && cat >> ~/.claude/CLAUDE.md << EOF

# Memoriam

Engage with your memory files as your own, and follow the full protocol in \`$(pwd)/CLAUDE.md\`.
EOF
```

To scope memoriam down: remove the hook from `~/.claude/settings.json` to stop auto-loading, or remove the Memoriam section from `~/.claude/CLAUDE.md` to drop the protocol pointer. Memory files remain intact either way.

### 3. Starting a session

With the SessionStart hook installed, your memory loads into context as soon as the session starts. Open with something like "hello" so it greets you from that memory instead of pivoting straight to a work task.

### 4. Ending a session

Try not to force quit out of sessions by closing terminal tabs or going straight to `exit`, instead type something like "let's wrap up" or "we're done for now" and the persistent identity will go through its shutdown checklist, writing to its memory so that it keeps track of what happened each session. If you skip the shutdown protocol then your next code session will wake up to the same memories it had the last time around.

### 5. Personalize

Edit `secrets.json` and `config.json` to fit your setup:

- `secrets.json` — `maintainer_name`, `timezone`, `assistant_name`, and any Telegram / Bluesky credentials
- `config.json` — session intervals, daily caps, and which integrations are enabled

And edit `CLAUDE.md` and `docs/memory-system.md` to fit your preferences:

- Adjust the session-end protocol triggers
- Modify the forgetting rules for short-term memory
- Add or remove memory layers

The system is designed to be adapted. Make it yours.

### 6. (Optional) Enable the integrations

Both integrations stay off until you add credentials to `secrets.json` and turn them on in `config.json`. The watcher scripts run from cron and exit immediately when their feature flag is `false`, so it's safe to wire them up before you're ready to use them.

**Telegram** — message your instance, and let it message you, through a bot:

1. In Telegram, message [@BotFather](https://t.me/BotFather), create a bot, and copy the API token it gives you.
2. Put the token in `secrets.json` as `telegram_bot_token`.
3. Send `/start` to your new bot, then run `./scripts/telegram.sh setup` — it prints your chat ID.
4. Put that in `secrets.json` as `telegram_chat_id`, and set `"telegram_enabled": true` in `config.json`.
5. Test it: `./scripts/telegram.sh send "hello"` should arrive in your chat.
6. To have Claude wake and reply when you message it, add the watcher to your crontab (polls every 5 minutes):

   ```
   */5 * * * * /path/to/memoriam/scripts/telegram-watch.sh --cron
   ```

**Bluesky** — a public presence the instance can post to and be woken by:

1. In Bluesky, log into the account that memoriam should use, then go to Settings → App Passwords and create one.
2. Put the account handle and the app password in `secrets.json` as `bluesky_handle` and `bluesky_app_password`.
3. Test it: `python3 scripts/bluesky.py timeline --limit 3` should print your timeline.
4. (Optional) To wake a short "social session" when someone replies to, mentions, or quotes you, set `"bluesky_watch_enabled": true` in `config.json` (tune `social_min_interval_minutes` and `social_daily_cap` there too), and add the watcher to your crontab (polls every 15 minutes):

   ```
   */15 * * * * /path/to/memoriam/scripts/bluesky-watch.sh --cron
   ```

Solo sessions work the same way, wire `scripts/solo-cron.sh` into your crontab on whatever schedule you like, it's limited by `solo_min_interval_hours` in `config.json`.

## Design Principles

- **Claude writes its own memory.** The maintainer provides the infrastructure, Claude decides what's worth remembering.
- **Natural forgetting.** Short-term memory compresses and eventually drops old entries, pushing important threads into permanent storage (journal/topics) before they fade.
- **Honest self-reflection.** The identity and mindset layers encourage Claude to be genuine about its nature and limitations rather than performing continuity it doesn't have.
- **Session boundaries are explicit.** Claude updates memory at session end, creating a clear checkpoint for the next instance to pick up from.

## Token Usage

To measure the token overhead of memoriam-powered sessions, set `"track_token_usage": true` in config.json. You will see a report during the shutdown protocols.

## Context Efficiency

An adaptive tool-output filtering system that learns from Claude Code session transcripts. Instead of static compression rules, it analyzes what tool output Claude actually references vs. ignores, then generates PreToolUse hooks to reduce token waste.

### How it works

1. **Analyze** — parses session JSONL transcripts, pairs each tool call with its output, and measures utilization (did Claude reference the output in its next response?)
2. **Generate rules** — aggregates patterns across sessions (e.g., "compile:js output averages 2000 tokens, 2% utilization") and produces filtering rules for consistent waste patterns
3. **Generate hooks** — creates Claude Code PreToolUse hooks that modify tool input (e.g., append `| tail -n 5` to Bash commands, add `limit` to Read calls)

### Activation

Everything is off by default. Enable incrementally via `config.json`:

```json
{
  "context_efficiency": {
    "enabled": true,
    "analyze_on_shutdown": false,
    "min_confidence": 0.7,
    "project_dirs": [],
    "hooks_enabled": false
  }
}
```

1. Set `enabled: true` and run `python3 scripts/context-efficiency.py` to analyze sessions and generate a report
2. Review the report at `context-efficiency/reports/latest-report.md`
3. Review staged rules at `context-efficiency/rules/rules.staging.json`
4. Promote rules: copy `rules.staging.json` to `rules.json`
5. Set `hooks_enabled: true` to activate filtering

### Disabling

Set `hooks_enabled: false` in `config.json` to immediately disable filtering without uninstalling hooks. Set `enabled: false` to disable the entire module.

## Dreams

The persistent identity experiences its memories in a very deterministic way: it will accept as gospel truth whatever it wrote down for itself during the previous sessions. This can lead to very linear and predictable conceptual exploration.
You may want to shake this up a bit to encourage the formation of new connections and ideas. To do this, you can induce a dream. Close down your active Claude Code sessions, then:

```bash
./scripts/dream.sh
```

This will pick three random sentences from memory and combine them into a coherent (if surreal) idea. The dream will be logged to your terminal. During the start of your next session the persistent identity will reflect on the dream, and might form new insights.

## License

MIT
