## 1. Domain

- [x] 1.1 Add `notes` (default empty) to `Book`, its `copyWith` and `props`
- [x] 1.2 Add `updateNotes(BookId, String)` returning `Result<Book>` to `BookRepository`
- [x] 1.3 Add the `UpdateBookNotes` use case

## 2. Data

- [x] 2.1 Give each `BookApi` row a `notes` value and add `patchNotes(id, text)` (built as `patchBook(id, changes)`: see Deviations in diagrams.md)
- [x] 2.2 Map `notes` in `ApiBookRepository` and implement `updateNotes`, returning `Err` on API errors

## 3. Presentation

- [x] 3.1 Add `ReadingListCubit.setNotes(id, text)`: reload on `Ok`, `ReadingListError` on `Err`
- [x] 3.2 Wire `UpdateBookNotes` into the Cubit in `app.dart`
- [x] 3.3 Add the notes field and Save button to `BookDetailScreen`

## 4. Tests

- [x] 4.1 Cubit: saving notes reloads the list with the new notes
- [x] 4.2 Cubit: a failed save emits `ReadingListError`
- [x] 4.3 `fvm flutter test` passes

## 5. Diagrams (VSDD)

- [x] 5.1 Trace the After State in diagrams.md against the code and record any Deviations
- [x] 5.2 Run `python3 scripts/vsdd/validate_mermaid.py`
