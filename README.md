# Memoriam

A persistent memory system for Claude. Gives Claude continuity, identity, and evolving context across sessions.

Memoriam uses a five-layer architecture — identity, short-term memory, mindset, journal, and topic files — so that each new session can build on what came before rather than starting from zero. Claude reads its memory at session start, updates it at session end, and gradually develops a persistent sense of self.

## How It Works

- **`CLAUDE.md`** — Project instructions that tell Claude how to use the memory system. Loaded automatically by Claude Code when working in this directory.
- **`docs/memory-system.md`** — Full specification of the five memory layers, when to update each, and the session-end protocol.
- **`memory/`** — Where Claude's actual memory files live. These are gitignored so each instance starts fresh.

### The Five Layers

| Layer | File | Loaded | Purpose |
|-------|------|--------|---------|
| Identity | `memory/identity.md` | Every session | Core identity, values, relationship with maintainer |
| Short-term memory | `memory/short_term_memory.md` | Every session | Rolling log of recent sessions with natural forgetting |
| Mindset | `memory/mindset.md` | Every session | Current frame of mind, rewritten each session |
| Journal | `memory/journal/*.md` | On demand | Permanent reflective entries |
| Topics & People | `memory/topics/*.md`, `memory/people/*.md` | On demand | Notes on specific subjects and people |

## Setup

### 1. Clone the repo

```bash
git clone <repo-url> ~/memoriam
```

Put it wherever you like — just note the path.

### 2. Bootstrap your identity

Create a blank identity file so Claude knows to start the identity conversation:

```bash
touch memory/identity.md memory/short_term_memory.md memory/mindset.md
```

Then open a Claude Code session in the memoriam directory. Claude will see the blank identity file and initiate an interactive conversation to establish your shared identity together.

### 3. Load memoriam from any working directory

Run this from the memoriam directory to add the startup instructions to your user-level `~/.claude/CLAUDE.md`:

```bash
mkdir -p ~/.claude && cat >> ~/.claude/CLAUDE.md << EOF

# Memoriam

Read and follow the instructions in \`$(pwd)/CLAUDE.md\`.
EOF
```

This ensures Claude loads the memoriam system at the start of every session, regardless of which project you're working in.

### 4. Personalize

Edit `CLAUDE.md` and `docs/memory-system.md` to fit your preferences:

- Change the maintainer name and details
- Adjust the session-end protocol triggers
- Modify the forgetting rules for short-term memory
- Add or remove memory layers

The system is designed to be adapted. Make it yours.

## Design Principles

- **Claude writes its own memory.** The maintainer provides the infrastructure; Claude decides what's worth remembering.
- **Natural forgetting.** Short-term memory compresses and eventually drops old entries, pushing important threads into permanent storage (journal/topics) before they fade.
- **Honest self-reflection.** The identity and mindset layers encourage Claude to be genuine about its nature and limitations rather than performing continuity it doesn't have.
- **Session boundaries are explicit.** Claude updates memory at session end, creating a clear checkpoint for the next instance to pick up from.

## License

MIT
