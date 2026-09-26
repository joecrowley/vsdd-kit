# Show HN post (draft)

Post once the repository is public and the `uvx` install command works from a clean
machine.

## Title

Up to 80 characters. Pick one:

```text
Show HN: VSDD – architecture diagrams that AI agents keep in sync with the code
Show HN: Architecture diagrams checked against the code in each AI-made change
Show HN: Before/After Mermaid diagrams for every structural change, for OpenSpec
```

## URL

```text
https://github.com/joecrowley/vsdd-kit
```

## First comment

Post this yourself as soon as the submission is up. It's plain text, because HN
doesn't render Markdown. Paste the article's URL where marked, or delete that line if
the article isn't published yet.

```text
Hi HN. I built this because every architecture diagram I've relied on has been out of date, and AI coding agents change structure faster than anyone redraws it.

VSDD is an add-on for OpenSpec, a spec-driven workflow for AI coding agents. Every change that alters structure carries a Before/After Mermaid diagram. The agent draws it before building, and a person reviews it while changing the design is still cheap. After the build, every arrow in the After diagram is traced to the code. Where the build differs from the plan, the diagram is corrected and a short Deviations note says why. On archive, the After diagram is merged into the project's diagrams, section by section, and nothing else is touched.

The repo has an unedited worked example on a small Flutter app. The part I find most convincing: a mid-build change (scripted, in that run) swapped one API call for another, and the check found it had also changed an existing flow the proposal never mentioned. That diagram was fixed in the same change, instead of going stale.

Costs: a few minutes of review on changes that alter structure (most don't, and say so in one line), some extra tokens, and your team has to work through OpenSpec's change flow. I've used it end to end with Claude Code. The installer supports all 40 tools OpenSpec does, but beyond Claude Code, OpenCode and Qwen Code that's tested structurally, not in daily use.

Longer write-up: <ARTICLE URL>

I'd especially like to hear where it gets in the way, or where your diagrams drifted anyway.
```

## On the day

- Post on a weekday morning, US Eastern time, when you can stay around for two or
  three hours.
- Reply to every question, and agree plainly with fair criticism. Limitations stated
  honestly go down better than a defence.
- Don't ask anyone to upvote it. HN penalises vote rings, and it's against the rules.
- If it sinks without comments, that's common. You can repost once, some weeks later,
  with a better title.
