## Why

Readers want to jot down why they picked a book up, or what they thought of it, next
to the book itself. Today a book only carries a title, an author and a reading status.

## What Changes

- Books gain a private `notes` field (plain text, empty by default).
- The book detail screen shows the notes in a text field with a **Save** button.
- Saving sends the notes through the same layers as a status change: Cubit, a new
  `UpdateBookNotes` use case, the repository and the fake API, then reloads the list.
- Saving an empty text clears the notes.

## Capabilities

### New Capabilities

- `book-notes`: keeping private notes on a book, and editing them on the detail screen.

### Modified Capabilities

None. Reading status behaviour doesn't change.

## Impact

- `lib/domain`: `Book` (new `notes` field), `BookRepository` (new `updateNotes`), new
  `usecases/update_book_notes.dart`.
- `lib/data`: `BookApi` (notes in each row, a new call to patch them),
  `ApiBookRepository` (maps notes, implements `updateNotes`).
- `lib/presentation`: `ReadingListCubit` (new `setNotes`),
  `book_detail/book_detail_screen.dart` (notes field and Save button).
- `lib/app.dart`: wires the new use case into the Cubit.
- `test/`: Cubit tests for saving notes.
