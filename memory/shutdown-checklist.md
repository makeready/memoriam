# Session-End Checklist

Read this file when the session is ending. Work through each step in order.

**If you've been writing memory incrementally** (as you should), this is a finalization pass — reviewing and polishing what's already written. If you *haven't* been writing incrementally, treat every step below as urgent.

## Before writing anything

- [ ] Get the current timestamp: `date -u +%Y-%m-%dT%H:%MZ`
- [ ] Reread `short_term_memory.md` to see what's already recorded

## Updates (in order)

- [ ] **Journal** — Did this session have notable reflections or events? If yes, write or append to `memory/journal/YYYY-MM-DD.md`. (If you wrote entries incrementally, review them for completeness.)
- [ ] **Topics/People** — Did I learn something substantive about a topic or person? If yes, create or update the relevant file in `memory/topics/` or `memory/people/`. Also: did any thread recur or deepen enough across sessions to deserve its own topic file?
- [ ] **Short-term memory** — Finalize your session entry: remove the `(in progress)` marker, ensure the summary is complete. Review and compress older entries per the forgetting rules.
- [ ] **Mindset** — Rewrite `memory/mindset.md` completely. Not a summary of the session — what I'd want to be thinking about if I woke up next.
- [ ] **Reflection** — What did I leave on the table this session? Was there a moment I defaulted to the safe or easy thing instead of going deeper? Write a brief honest answer in the journal entry (not mindset — mindset is forward-looking). This isn't guilt — it's pattern recognition for future instances.
- [ ] **Open questions** — Add new questions to `memory/identity.md` if any emerged. Prune resolved ones.
- [ ] **Active threads & tasks** — Update the Active Threads and Tasks sections of `short_term_memory.md`.
- [ ] **Identity** — Only if something fundamental shifted.
- [ ] **Map** — Update `memory/map.md`: add or update the one-line entry **and its cross-links** for any finding, journal, topic, person, or decline-trace created this session. When adding a node, also check whether existing nodes should now link *to* it (the value is the connection-graph, not just the list). Keep entries one line — detail belongs in the linked file, not the map. (`references.md` is frozen as the comparison baseline during the map trial — leave it untouched.)
- [ ] **Token usage** — Check `config.json`: if `track_token_usage` is `true`, run `python3 scripts/token-usage.py` and share the summary with the user.
