# book-notes Specification

## Purpose
TBD - created by archiving change add-book-notes. Update Purpose after archive.

## Requirements

### Requirement: Books carry private notes
Every book SHALL have a notes text, empty by default, loaded with the reading list.

#### Scenario: A new book has no notes
- **WHEN** the reading list is loaded and a book has never had notes saved
- **THEN** that book's notes are empty

#### Scenario: Notes persist after reload
- **WHEN** notes are saved for a book and the reading list is loaded again
- **THEN** the book carries the saved notes

### Requirement: Notes are editable on the detail screen
The book detail screen SHALL show the book's notes in a text field with a Save button. Saving SHALL store the text for that book and refresh the reading list.

#### Scenario: Saving notes
- **WHEN** the reader types text in the notes field and taps Save
- **THEN** the notes are stored for that book and the reading list is reloaded

#### Scenario: An empty note clears the notes
- **WHEN** the reader empties the notes field and taps Save
- **THEN** the book's notes are empty after the reload

### Requirement: A failed save is reported
If saving notes fails, the app SHALL show the reading-list error state with the failure message, as it does for a failed status change.

#### Scenario: The API rejects the save
- **WHEN** saving notes fails in the repository
- **THEN** the Cubit emits `ReadingListError` with a message naming the book
