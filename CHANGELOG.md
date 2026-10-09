# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Added
- **BM25 Ranking Engine (`rankResults.py`)**:
  - Implemented the complete classical Robertson-Spärck Jones (Okapi BM25, 1994, 2009) mathematical framework:
    - Term Frequency Saturation (`tf_saturation`) controlled by parameter $k_1$.
    - Document Length Normalization factor $B(D) = (1 - b) + b \cdot \frac{|D|}{\text{avgdl}}$ controlled by parameter $b$.
    - Robertson-Spärck Jones weight (`idf_robertson_sparck_jones`) with relevance feedback ($R, r$) and non-feedback formulations.
    - Query Term Frequency Saturation (`query_term_weight`) controlled by parameter $k_3$.
  - Researched and implemented modern 2026 Information Retrieval improvements:
    - **BM25+ (Lv & Zhai, 2011)** (`tf_bm25_plus`): Added lower-bound delta floor ($\delta = 1.0$) to prevent unfair penalization of long documents.
    - **BM25L (Lv & Zhai, 2011)** (`tf_bm25l`): Length-regularized term frequency before saturation.
    - **Non-Negative Smoothed IDF** (`idf_smoothed`): Lucene / Robertson-Zaragoza logarithmic smoothing to eliminate negative IDF on high-frequency terms, plus Robertson & Walker floored IDF (`idf_floored`).
    - **Term Proximity Scoring (BM25-TP)** (`compute_term_proximity_score`): Efficient $O(P_1 + P_2)$ pairwise positional distance scoring that rewards phrase-like proximity using positional postings.
    - **Reciprocal Rank Fusion (RRF)** (`reciprocal_rank_fusion`): Hybrid retrieval consensus ranking ($k = 60$) for fusing multiple search signals.
  - Provided comprehensive mathematical docstrings and formulas for all functions and classes.
  - Implemented the `BM25Ranker` class supporting score explanation, candidate filtering, and the convenience functional helper `rank_query`.

- **Corpus Metadata Caching (`createIndex.py` & `corpus_metadata.json`)**:
  - Enhanced `createIndex.py` to extract and preserve Wikipedia `<title>` tags during document parsing.
  - Updated single-pass inverted index generation to record document token lengths ($|D|$) with zero added overhead.
  - Emitted `corpus_metadata.json` alongside `invertedIndex.txt` storing $N$, $\text{avgdl}$, `doc_lengths`, and `titles` to eliminate the need to read raw 270MB text files at query time.

- **Integrated BM25 into Query Engine (`queryIndex.py`)**:
  - Refactored search execution into a Two-Stage Retrieval pipeline: Stage 1 Boolean candidate retrieval (`AndQuery` / `PhraseQuery`) followed by Stage 2 BM25+ relevance ranking.
  - Added graceful fallback to free-text BM25 ranking when multi-term AND queries return zero exact matches.
  - Upgraded interactive search CLI to display formatted tables with Rank, Doc ID, BM25 Score, and Wikipedia article titles.

- **Repository Cleanliness**:
  - Added `corpus_metadata.json` to `.gitignore`.

### Changed
- Refactored `queryIndex.py` initialization to load lightweight index metadata in milliseconds without parsing raw corpus text.
- Renamed `main.py` to `create-index.py` to better reflect its purpose as the index builder.
- Renamed `parse` function to `parseDoc` in `create-index.py`.
- Re-architected `createInvertedIndex` for a massive performance gain: switched from a cross-referencing O(V*N) approach to a single-pass O(N) document traversal.
- Updated the stop words collection to use a `set` instead of a `list` for O(1) lookup times.
- Switched inverted index file writing to use `.write()` instead of the non-existent `.writeLine()`.

### Fixed
- Fixed word position tracking in `createInvertedIndex` to count logical token positions (ignoring stop words) instead of string character offsets, enabling correct phrase queries.
- Fixed the `parse` function to properly replace XML/HTML tags in the document list (strings are immutable, so elements are now modified in-place using `enumerate`).
- Fixed tokenization regex (`[a-z0-9]+` instead of `[a-z0-9]`) so it extracts full words rather than single characters.
- Fixed a major index corruption bug where the actual document IDs were being overwritten by loop counter index values during the write phase.
- Fixed an f-string syntax error that occurred in older Python versions when quoting strings inside the `.join()` method.
- Fixed page splitting logic in `parseDoc` to prevent empty pieces from being added as documents.
- Fixed `<id>` tag removal in `parseDoc` to use regex, ensuring the entire tag and its contents are removed.
