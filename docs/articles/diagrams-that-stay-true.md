# Architecture diagrams that stay true to the code, even when an AI writes it

Every team I've worked with has an architecture diagram. Almost none of them trust it.

It's correct the day someone draws it. After that, nothing connects it to the code, so
every change that touches structure makes it a little more wrong, and nobody notices.
A few months later people stop looking at it. Then they stop updating it. Then new
starters are told to "just read the code".

That isn't a discipline problem. Keeping a diagram current takes effort now and pays
off later, and nothing tells you when it has fallen behind. Any process built like
that drifts.

## AI agents make it worse

Coding agents change the numbers. An agent can restructure ten files in a few
minutes, far faster than anyone updates a diagram by hand. And when an agent writes
the code and a person skims a 600-line diff, the understanding of what changed
structurally may not exist anywhere. The diff shows every line. It doesn't show that a
call now skips a layer, or that a state machine gained a state the UI never handles.

Spec-driven tools like [OpenSpec](https://github.com/Fission-AI/OpenSpec) help a lot.
Intent is written down as requirements, and each change is a delta against a living
spec. But requirements describe behaviour, not structure. Two implementations can pass
the same scenarios with completely different architectures.

So I tried giving diagrams the same treatment specs get.

## The idea: diagrams are part of the change

Visual Spec-Driven Development (VSDD) adds one step to OpenSpec's change pipeline:
`proposal → diagrams → specs → design → tasks`. The project keeps one set of Mermaid
diagrams as its Source of Truth, one section per diagram, each with a stable name.
Every change then does four things:

1. **Decide whether structure changes.** Each change starts with a gate:
   `Diagram needed?` Most bug fixes answer `NO` in one line and move on. `YES` is for
   changes to navigation, a state machine, a data flow, topology or a schema.
2. **Draw the change before building it.** The agent copies the affected diagrams
   verbatim as the Before state, and draws the After state under the same names. A
   small Placement table says which diagram file each one belongs in, and whether it's
   updated, added, moved or removed. A person reviews this before any code exists,
   which is when changing the design costs a sentence of feedback.
3. **Check the diagram against the code.** After the build, every participant and
   arrow in the After state has to exist in the code. Where the build differs from the
   plan, the diagram is corrected, and a Deviations note records what was proposed,
   what was built, and why.
4. **Merge on archive.** The After state replaces the matching sections of the Source
   of Truth, and only those. The Before/After pair and the Deviations note stay with
   the archived change as history.

Step 3 is the one that matters. Without it, you'd be merging the plan, and a plan
drifts from the code as easily as any hand-drawn diagram.

## A real change

Here is one change from start to finish. It's unedited, and it's in the kit as a
[worked example](https://github.com/joecrowley/vsdd-kit/tree/main/examples/book-notes).
The app is a small Flutter reading list: flutter_bloc, go_router, and a fake API.

**The request:** let readers keep private notes on a book, editable on the detail
screen.

**Propose.** The agent wrote the proposal, then the diagrams. The gate said yes: a
new update path through every layer, and new transitions in the list's state machine.
The Placement table put the new flow in the new capability's own diagram file, and
updated the shared state machine:

```markdown
| Stable name | Source of Truth file | Action |
|---|---|---|
| ReadingListState Machine | specs/architecture/diagrams.md | update |
| Notes Update Flow | specs/book-notes/diagrams.md | add |
```

The After state added two transitions to the state machine, and a sequence diagram for
saving a note: the detail screen calls the Cubit, then a new `UpdateBookNotes` use
case, the repository, and finally a new `BookApi.patchNotes` call.

**Build, and a change of plan.** Partway through, a reviewer asked for one generic
`patchBook(id, changes)` API call for every book field, instead of a separate
`patchNotes`. (In this run the request is scripted: the kit's walkthrough makes it on
purpose, to show what happens.) It's a reasonable request, and exactly the kind of
mid-build change that leaves documentation behind.

**The check.** Before the change could count as done, every arrow in the After state
was traced to the code. Two didn't match. The notes flow still showed `patchNotes`,
which no longer existed. The more interesting one was a diagram the change had never
mentioned. `patchBook` had replaced the old `patchStatus` call too, so the existing
Status Update Flow was now wrong:

```diff
 ## Status Update Flow
-    R->>A: patchStatus(id, status)
+    R->>A: patchBook(id, status: name)
```

The fix went into the same change. The Status Update Flow got its own Placement row
and Before copy, both flows got `patchBook`, and a Deviations note recorded why (shortened here):

```markdown
- **Proposed:** `BookApi.patchNotes(id, text)`, next to `patchStatus`.
  **Built:** one `BookApi.patchBook(id, changes)`, used for notes and status alike.
  **Why:** a reviewer asked for one PATCH path for all book fields during apply.
```

**Archive.** The merge applied exactly the Placement rows:

```text
replaced: ReadingListState Machine in specs/architecture/diagrams.md
replaced: Status Update Flow in specs/architecture/diagrams.md
added (appended): Notes Update Flow to specs/book-notes/diagrams.md
```

The module hierarchy diagram had no row, so it wasn't touched. The project's diagrams
now show the code as it is, including a flow the proposal never mentioned. Without the
check, they would show a `patchStatus` call that no longer exists, and the next person
to trust them would be misled.

The kit's own tests replay this archive on every run, so if a later version of the
kit changes how merges behave, the example fails the tests.

## What it costs

VSDD isn't free, and I'd rather say so up front:

- **Review time.** A few minutes on each change that alters structure. Most changes
  don't, and say so in one line.
- **Tokens.** The agent reads and copies the affected diagram sections. Only those,
  not the whole set.
- **Mermaid that doesn't parse.** LLMs are bad at large, unconstrained diagrams. VSDD
  asks for small diagrams with one concern each, in a Mermaid subset models handle
  reliably, and a validator catches the rest, including in CI.
- **Discipline.** A hotfix that bypasses the process leaves a diagram stale. The next
  change in that area compares its Before state with the code, so the drift shows up
  then, instead of never.

It's not for everything. Throwaway prototypes, tiny codebases one person holds in
their head, and work that is mostly content or styling won't get much from it. It
pays off where structure matters and changes often: layered apps, stateful clients,
services, and especially code that agents write a lot of.

## How it's built

The kit sits on top of OpenSpec rather than replacing it:

- a custom OpenSpec schema that adds the `diagrams` step
- an overlay that adds the VSDD steps to the skills OpenSpec generates for each AI
  tool, and re-applies them after `openspec update` (which overwrites edits)
- a validator that keeps LLM-written Mermaid parseable, checks that Before copies are
  verbatim, and checks that each diagram lives with the capability it describes
- a deterministic merge script for the archive step
- an installer that does the mechanical setup, stops to ask whenever a decision is
  yours, and can be rolled back

It installs into all 40 AI tools OpenSpec supports. I've used it end to end with
Claude Code, and tested the installed files for the others.

There's also a small bonus I didn't plan: a decisions log. When a fix reveals a
pattern that could recur, the archive step proposes a one-line rule, and later
designs read the log first. In one test run, a list-refresh bug fixed in one feature
reappeared, line for line, in the next feature that wrote data. That's the gap it's
meant to close.

## Try it

You need Node (for the OpenSpec CLI), Python 3.9 or later, and
[uv](https://docs.astral.sh/uv/):

```bash
npm install -g @fission-ai/openspec
uvx --from git+https://github.com/joecrowley/vsdd-kit@v0.3.1 vsdd-kit guide
```

`guide` prints the runbook. Ask your agent to follow it. It installs on a separate
branch, seeds the first diagrams from your code, and asks you only about decisions
that are yours.

The code is at [github.com/joecrowley/vsdd-kit](https://github.com/joecrowley/vsdd-kit).
[The case for VSDD](https://github.com/joecrowley/vsdd-kit/blob/main/docs/WHY_VSDD.md)
goes further into the benefits, costs and objections.

I'd most like to hear from people who try it on a real codebase, especially where it
gets in the way. Open an issue, or tell me where the diagrams drifted anyway.
