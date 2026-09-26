# Architecture Decisions

Cross-cutting rules this project has learned, usually from a fix. Read this file
before writing a change's design.md (or tasks.md, when the change has no design).
A design that breaks a rule must say so under `## Decisions` in its design.md:
`Overrides: <Stable Name> - <why>`.

Each rule is one `## <Stable Name>` section with Rule, Why, Applies to and Source.
Keep entries short. Retire an entry (delete it) when the code no longer has the
problem it guards against, and say so in the archive summary of that change.

## Result Not Exceptions

**Rule:** Fallible operations return the sealed `Result<T>` (`Ok`/`Err`); they never throw across layer boundaries.
**Why:** The domain and data layers are built around `Result` (see `lib/domain/result.dart`, `ApiBookRepository`); throwing bypasses the pattern and makes errors untestable with mocktail.
**Applies to:** `lib/domain/`, `lib/data/`, and any new repository or use case.
**Source:** install

## Fvm For Flutter Commands

**Rule:** Run Flutter commands through `fvm` (`fvm flutter test`, `fvm flutter run`), not bare `flutter`.
**Why:** The project pins its SDK via `.fvmrc`; bare `flutter` may use a different SDK and give inconsistent build or test results.
**Applies to:** All shell commands that invoke Flutter or Dart tooling.
**Source:** install
