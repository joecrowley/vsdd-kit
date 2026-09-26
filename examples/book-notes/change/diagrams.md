## Diagram needed?

YES - adds a notes update path through data, domain and presentation, and new
transitions to the ReadingListCubit state machine.

## Placement

| Stable name | Source of Truth file | Action | Why here |
|---|---|---|---|
| ReadingListState Machine | specs/architecture/diagrams.md | update | |
| Status Update Flow | specs/architecture/diagrams.md | update | |
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

### Status Update Flow
How changing a book's reading status travels from the detail screen to the fake
API and back, including the full list reload after a successful write.

```mermaid
sequenceDiagram
    actor U as User
    participant D as BookDetailScreen
    participant C as ReadingListCubit
    participant UC as UpdateReadingStatus
    participant R as ApiBookRepository
    participant A as BookApi
    U->>D: selects a status segment
    D->>C: setStatus(id, status)
    activate C
    C->>UC: call(id, status)
    activate UC
    UC->>R: updateStatus(id, status)
    activate R
    R->>A: patchStatus(id, status)
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

### Status Update Flow
How changing a book's reading status travels from the detail screen to the fake
API and back, including the full list reload after a successful write. The API
call is the generic `patchBook`, shared with notes.

```mermaid
sequenceDiagram
    actor U as User
    participant D as BookDetailScreen
    participant C as ReadingListCubit
    participant UC as UpdateReadingStatus
    participant R as ApiBookRepository
    participant A as BookApi
    U->>D: selects a status segment
    D->>C: setStatus(id, status)
    activate C
    C->>UC: call(id, status)
    activate UC
    UC->>R: updateStatus(id, status)
    activate R
    R->>A: patchBook(id, status: name)
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
    R->>A: patchBook(id, notes: text)
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

## Deviations

- **Proposed:** `BookApi.patchNotes(id, text)`, next to `patchStatus` (design D3).
  **Built:** one `BookApi.patchBook(id, changes)`, used for notes and status alike.
  `ApiBookRepository.updateStatus` now calls `patchBook(id, {'status': ...})`, so the
  Status Update Flow changed too, and got a Placement row.
  **Why:** a reviewer asked for one PATCH path for all book fields during apply
  (the redirect in the testdrive walkthrough, §5.5): it avoids a second copy of the
  latency, lookup and 404 handling.
