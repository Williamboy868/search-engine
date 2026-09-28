# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Added
- Added `invertedIndex.txt` to `.gitignore`.
- Expanded the list of stop words to further reduce the index size.
- Added progress logs in `createInvertedIndex` to track indexing status (prints every 5,000 documents).

### Changed
- Re-architected `createInvertedIndex` for a massive performance gain: switched from a cross-referencing O(V*N) approach to a single-pass O(N) document traversal.
- Updated the stop words collection to use a `set` instead of a `list` for O(1) lookup times.
- Switched inverted index file writing to use `.write()` instead of the non-existent `.writeLine()`.

### Fixed
- Fixed the `parse` function to properly replace XML/HTML tags in the document list (strings are immutable, so elements are now modified in-place using `enumerate`).
- Fixed tokenization regex (`[a-z0-9]+` instead of `[a-z0-9]`) so it extracts full words rather than single characters.
- Fixed a major index corruption bug where the actual document IDs were being overwritten by loop counter index values during the write phase.
- Fixed an f-string syntax error that occurred in older Python versions when quoting strings inside the `.join()` method.
