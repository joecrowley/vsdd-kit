## Context

A book has a title, an author and a reading status. Changing the status already goes
through every layer: `BookDetailScreen` → `ReadingListCubit.setStatus` →
`UpdateReadingStatus` → `ApiBookRepository.updateStatus` → `BookApi.patchStatus`,
then the Cubit reloads the list. Notes need the same path.

## Goals / Non-Goals

**Goals:**
- Store and show plain-text notes per book, editable on the detail screen.
- Follow the existing status-update shape, so the two paths read alike.

**Non-Goals:**
- Rich text, note history, or notes on the list screen.
- Fixing the brief "Book not found" while the list reloads after a save. It already
  happens for status changes and is its own change.

## Decisions

- **D1: A dedicated `UpdateBookNotes` use case**, mirroring `UpdateReadingStatus`,
  rather than widening `UpdateReadingStatus`. One use case per user intent keeps
  each one trivially testable.
- **D2: `BookRepository.updateNotes(id, text)` returns `Result<Book>`**, following
  the decision *Result Not Exceptions*: `ApiBookRepository` catches API errors and
  returns `Err`.
- **D3: `BookApi.patchNotes(id, text)`**, next to `patchStatus`. Alternative
  considered: one generic `patchBook(id, changes)`. Rejected for now, to keep the
  change small and parallel to the status path.
- **D4: Save button, not save-on-type.** Each save is a round trip that reloads the
  list, so saving on every keystroke would flicker and hammer the API.
- **D5: Reload after a save**, like `setStatus`, so the list and the detail screen
  show what the API stored.

## Risks / Trade-offs

- [The reload briefly replaces the detail screen with "Book not found"] → Known for
  status changes too. Out of scope here (see Non-Goals).
- [Unsaved text is lost if the reader leaves the screen] → Acceptable for private
  notes. An explicit Save makes it clear when text is stored.
