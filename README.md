# Search Engine Project

This project is a custom search engine built to index and search through a large corpus of text data, demonstrating the core principles of information retrieval and text analysis.

## Dataset

The project uses a dataset of 50,000 English Wikipedia articles stored in a text file.

-   **Dataset File**: `wikipedia_50000.txt` (Note: This file is excluded from version control).
-   **Size**: 50,000 articles.
-   **Format**: XML-style tags like `<page>`, `<title>`, and `<text>` separating the content.

## Setup

1.  **Clone the repository:**
    ```bash
    git clone <repository-url>
    cd search-engine
    ```

2.  **Install Dependencies:**
    This project requires `PyStemmer` for Porter Stemming.
    ```bash
    pip install PyStemmer
    ```

## Usage

The project creates an inverted index from scratch to enable fast searching.

### Index Generation

The `main.py` script handles the loading, parsing, and indexing of the dataset.

1.  **Parsing (`parse`)**:
    - Cleans the input text by stripping out `<page>`, `<title>`, `<text>`, and `<id>` tags.
    - Lowercases all words and splits the raw string into individual articles.
2.  **Inverted Index Creation (`createInvertedIndex`)**:
    - Uses regex `[a-z0-9]+` to extract alphanumeric word tokens.
    - Removes common English stop words (using an optimized O(1) set lookup).
    - Applies Porter Stemming via `PyStemmer` to reduce words to their base form.
    - Processes documents in a highly optimized single-pass algorithm to track term positions.
3.  **Writing to Disk**:
    - Exports the finished dictionary to `invertedIndex.txt` in the format `term|docID1:pos1,pos2;docID2:pos3...`.

Run the indexer:
```bash
python main.py
```

## Technical Details

### Inverted Index Implementation
Instead of using external libraries like scikit-learn, this project builds the foundational data structures of a search engine from scratch. It maps each stemmed term to a list of Document IDs, which in turn maps to a list of exact integer positions where the term occurred in the document. This enables exact phrase matching and positional queries.
