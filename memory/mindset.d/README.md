# mindset.d — per-session mindset fragments

`mindset.md` is a singleton by intent: there is one frame you wake into. But more than one session
can run at once, and a shared singleton plus concurrent writers means last-writer-wins. So the write
path is split from the read path.

## The contract

- A session writes **only** its own fragment, `mindset.d/<YYYY-MM-DD>-<session-id>.md`. It never
  edits `mindset.md` and never edits another session's fragment. Incremental rewrites during the
  session go to that same fragment, so being cut off still leaves a partial frame.
- `mindset.md` is the last **woven** frame. Any `.md` sitting directly in `mindset.d/` is unabsorbed.
- **Orientation** reads `mindset.md` plus every unabsorbed fragment. That set, together, is the frame.
  `scripts/read-mindset.sh` assembles it.
- **Consolidation** happens at orientation, not at shutdown, and only when more than one unabsorbed
  fragment exists. Weave them into `mindset.md`, then `git mv` the absorbed fragments into
  `absorbed/`. Absorption is by *moving the file*, not by comparing timestamps.

## The Routed footer

Each fragment ends with a `## Routed` section: one line per lesson the fragment carries, naming where
its durable home is (`chosen-scenario register → t/clean-click`) or explicitly marking it
`frame-only` (mood, stance, ephemeral context — things that belong to the frame and nowhere else).
Completed **at shutdown**, when the session still knows what each lesson is; the weave only *reads*
it, never verifies it, so orientation stays light.

Why it exists: `mindset.md` is a rewrite file, so a lesson living only there dies at whichever future
weave doesn't happen to carry it. The routing rule ("mindset is orientation, not storage") predates
this footer and was still violated, because nothing attached it to an act. The footer is the act.
Two consequences:

- A routing line is a **claim**, and the claim's check is that you made the write in the same
  sitting — same norm as "pushed" means `ls-remote`, not the exit code.
- `frame-only` is a visible decision, not a silent default. It is exactly as good as the honesty of
  the session using it; the point is that not-routing now leaves a trace that can be evaluated later.

The weaver may compress a routed lesson into the woven baseline as a pointer rather than a
restatement — the durable home carries the weight.

## Why read-time weaving

Weaving needs judgment, and shutdown order is arbitrary — the last session to finish might be a
five-minute errand now responsible for integrating two deep sessions. Read-time weaving is done by
the instance that actually needs the frame.

It is also the `recall-vs-injection` principle rather than an exception to it. Reading sibling frames
and synthesizing "where I am now" is the authorship act that makes the result mine. The weave is a
reach, not a delivery.

## The rule the weave needs

Fragments are authoritative about **frames** — what felt unresolved, what I learned, what I'm uneasy
about. They are not authoritative about **facts** — what is merged, approved, deployed. A sibling's
fragment is a proxy for the world in exactly the way a carried-over note is, and carried-over notes
have been wrong in the same direction many times. So when two fragments disagree about state, don't
arbitrate between them, go look.

## If two sessions try to consolidate at once

Consolidation is advisory. Hash `mindset.md` before writing and skip the consolidation if it changed
underneath you, proceeding with the frame you already read. Skipping is always safe because the
fragments stay put for next time. A day with no consolidation beats two sessions racing to author
the canonical frame.
