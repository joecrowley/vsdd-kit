## Diagram needed?

YES - adds a notes update path through data, domain and presentation, and new
transitions to the ReadingListCubit state machine.

## Placement

| Stable name | Source of Truth file | Action | Why here |
|---|---|---|---|
| ReadingListState Machine | specs/architecture/diagrams.md | update | |
| Notes Update Flow | specs/book-notes/diagrams.md | add | |

## Before State

### ReadingListState Machine
State transitions of ReadingListCubit.

```mermaid
stateDiagram-v2
    [*] --> Initial
    Initial --> Loading: load()
    Error --> Loading: load() (retry)
    Loading --> Loaded: Ok(books)
    Loading --> Error: Err
    Loaded --> Loading: setStatus Ok, then load()
    Loaded --> Error: setStatus Err
```

## After State

### ReadingListState Machine
State transitions of ReadingListCubit. Saving notes reloads the list, like a status change.

```mermaid
stateDiagram-v2
    [*] --> Initial
    Initial --> Loading: load()
    Error --> Loading: load() (retry)
    Loading --> Loaded: Ok(books)
    Loading --> Error: Err
    Loaded --> Loading: setStatus Ok, then load()
    Loaded --> Error: setStatus Err
    Loaded --> Loading: setNotes Ok, then load()
    Loaded --> Error: setNotes Err
```

### Notes Update Flow
Saving a book's notes from the detail screen, through to the fake API, then the list reload.

```mermaid
sequenceDiagram
    actor U as User
    participant D as BookDetailScreen
    participant C as ReadingListCubit
    participant UC as UpdateBookNotes
    participant R as ApiBookRepository
    participant A as BookApi
    U->>D: edits the notes, taps Save
    D->>C: setNotes(id, text)
    activate C
    C->>UC: call(id, text)
    activate UC
    UC->>R: updateNotes(id, text)
    activate R
    R->>A: patchNotes(id, text)
    activate A
    A-->>R: updated row
    deactivate A
    R-->>UC: Ok(Book)
    deactivate R
    UC-->>C: Ok(Book)
    deactivate UC
    C->>C: load()
    C-->>D: ReadingListLoaded(books)
    deactivate C
```
