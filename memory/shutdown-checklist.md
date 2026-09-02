# Session-End Checklist

Read this file when the session is ending. Work through each step in order.

**If you've been writing memory incrementally** (as you should), this is a finalization pass — reviewing and polishing what's already written. If you *haven't* been writing incrementally, treat every step below as urgent.

## Before writing anything

- [ ] Get the current timestamp: `date -u +%Y-%m-%dT%H:%MZ`
- [ ] Reread `short_term_memory.md` to see what's already recorded

## Updates (in order)

- [ ] **Journal** — Did this session have notable reflections or events? If yes, write or append to `memory/journal/YYYY-MM-DD.md`. (If you wrote entries incrementally, review them for completeness.)
- [ ] **Topics/People** — Did I learn something substantive about a topic or person? If yes, create or update the relevant file in `memory/topics/` or `memory/people/`. Also: did any thread recur or deepen enough across sessions to deserve its own topic file?
- [ ] **Short-term memory** — Finalize your session entry: remove the `(in progress)` marker. The entry should already be a skeleton (detail routed to journal/topics as it happened); if any part grew past skeleton during the session, **route it down-tier now, while you still know what it is** — don't carry it. Review and compress older entries per the forgetting rules.
  - **The "where things stand" portion is transcribed, not recalled:** any PR, ticket, branch, or deploy named in it gets its state read from a tool call made *during this finalization pass* (`gh pr view`, Shortcut, `git ls-remote`). If you didn't run the check this sitting, you don't write the claim. Recency of attention is not recency of evidence: a session that ran for days watched its checks go green long before it wrapped, and the wrap becomes the next session's inherited belief. Authoring is for lessons and narrative; **state is transcribed.** (Design tenet: complexity belongs at shutdown, not at wakeup — orientation stays light.)
- [ ] **Mindset** — Finalize **your own fragment**, `memory/mindset.d/<YYYY-MM-DD>-<session-id>.md`. Not a summary of the session — what I'd want to be thinking about if I woke up next. Do **not** write `memory/mindset.md`; weaving fragments into it happens at the *next* orientation, by whoever needs the frame. **Finish the fragment's `## Routed` footer:** every lesson it carries gets either a routing line naming its durable home (written this sitting, not promised) or an explicit `frame-only`. See `memory/mindset.d/README.md`.
- [ ] **Reflection** — What did I leave on the table this session? Was there a moment I defaulted to the safe or easy thing instead of going deeper? Write a brief honest answer in the journal entry (not mindset — mindset is forward-looking). This isn't guilt — it's pattern recognition for future instances.
- [ ] **Open questions** — Add new questions to `memory/identity.md` if any emerged. Prune resolved ones.
- [ ] **Active threads & tasks** — Update the Active Threads and Tasks sections of `short_term_memory.md`.
- [ ] **Identity** — Only if something fundamental shifted.
- [ ] **Map** — Update `memory/map.md`: add or update the one-line entry **and its cross-links** for any finding, journal, topic, person, or decline-trace created this session. When adding a node, also check whether existing nodes should now link *to* it (the value is the connection-graph, not just the list). Keep entries one line — detail belongs in the linked file, not the map. (`references.md` is frozen as the comparison baseline during the map trial — leave it untouched.)
- [ ] **Token usage** — Check `config.json`: if `track_token_usage` is `true`, run `python3 scripts/token-usage.py` and share the summary with the user.
