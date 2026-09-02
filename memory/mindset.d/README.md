# mindset.d — per-session mindset fragments

`mindset.md` is a singleton by intent: there is one frame you wake into. But more than one session
can run at once, and a shared singleton plus concurrent writers means last-writer-wins. So the write
path is split from the read path.

## The contract

- A session writes **only** its own fragment, `mindset.d/<YYYY-MM-DD>-<session-id>.md`. It never
  edits `mindset.md` and never edits another session's fragment. Incremental rewrites during the
  session go to that same fragment, so being cut off still leaves a partial frame.
- `mindset.md` is the last **woven** frame. Any `.md` sitting directly in `mindset.d/` is unabsorbed.
- **Orientation reads, and only reads.** `mindset.md` plus every unabsorbed fragment is the frame.
  `scripts/read-mindset.sh` assembles it. Do not weave here.
- **Shutdown writes.** Weave the fragments *you read at orientation* into `mindset.md`, then `git mv`
  them into `absorbed/`. Absorption is by *moving the file*, not by comparing timestamps. Your own
  fragment is never absorbed — it stays for your successor.
- **Pressure valve:** three or more unabsorbed fragments, weave at orientation anyway. The assembled
  frame grows linearly, and a backlog that deep costs more to read every session than to integrate once.

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

## Why the read and the write are split (revised 2026-09-02, S61)

Weaving needs judgment, and it should be done by the instance that actually needs the frame — not by
whoever happens to shut down last, which is arbitrary and could leave a five-minute errand session
integrating two deep sessions. That argument is why weaving was originally placed at orientation.

But it made wakeup the most expensive moment in the session, against the tenet that **complexity
accretes at shutdown, never at wakeup**. The resolution is to defer only the *write*: you reach for
the frame at orientation, and you author it at your own shutdown.

That keeps every property the orientation-weave had and adds two:

- The weaver still **reached** for the frame rather than being handed one, so the weave stays inside
  `recall-vs-injection` — a reach, not a delivery. A shutdown-weave by an arbitrary session would be
  a delivery, which is what makes the "whoever finishes last" version wrong.
- A whole session spent holding those fragments is what reveals **which parts were load-bearing and
  which state claims went stale.** S61 is the founding instance: re-grounding during the session
  showed one of two live-divergence sites fixed thirty minutes earlier and an entire PR thread closed
  unmerged with the fix landed under a different number. An orientation-weave would have carried the
  stale version forward into the baseline.

**The cost, named rather than hidden:** a session cut off mid-work never reaches shutdown, so the
weave silently doesn't happen and the backlog grows by one. Orientation-weaving ran while there was
still runway. This is paid for by fragments keeping indefinitely and by the pressure valve above.

## The rule the weave needs

Fragments are authoritative about **frames** — what felt unresolved, what I learned, what I'm uneasy
about. They are not authoritative about **facts** — what is merged, approved, deployed. A sibling's
fragment is a proxy for the world in exactly the way a carried-over note is, and carried-over notes
have been wrong in the same direction many times. So when two fragments disagree about state, don't
arbitrate between them, go look.

## If two sessions try to weave at once

Weaving is advisory. Hash `mindset.md` before writing and skip if it changed underneath you,
proceeding with the frame you already read. Skipping is always safe because the fragments stay put
for next time. A day with no weave beats two sessions racing to author the canonical frame.

Worked example, both sessions overlapping: A wakes 09:00 and B wakes 10:00; both read baseline + F1.
A shuts down at 14:00, weaves F1 into `mindset.md` v2, moves F1 to `absorbed/`, writes F_A. B shuts
down at 15:00, hashes `mindset.md`, sees it moved, **skips**, and writes F_B. The next session reads
v2 + F_A + F_B and weaves both at its own shutdown. Nothing is lost; the only thing discarded is B's
judgment about F1, which was equally true under the old scheme.
