# Architecture Diagrams

Cross-cutting, system-wide diagrams for vsdd_testdrive. Each `## <Stable Name>`
section is a merge target for archived OpenSpec changes. Keep the names stable.

## Module Hierarchy

Dependency direction between the application's top-level modules. Arrows point
from the dependent module to its dependency.

```mermaid
flowchart TD
    MAIN["main.dart - entry point"] --> APP["app.dart - ReadingListApp, GoRouter, DI wiring"]
    APP --> PRESENTATION["presentation - screens and ReadingListCubit"]
    APP --> DATA["data - BookApi, ApiBookRepository"]
    PRESENTATION --> DOMAIN["domain - Book, BookId, Result, BookRepository, use cases"]
    DATA --> DOMAIN
```

## Status Update Flow

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

## ReadingListState Machine

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
