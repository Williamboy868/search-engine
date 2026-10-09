"""
Rank Results Module: Okapi BM25 and Modern IR Enhancements
===========================================================

This module implements the complete mathematical framework of Okapi BM25
as defined by Stephen Robertson, Steve Walker, Karen Spärck Jones, et al. (1994, 2009),
as well as modern 2026 information retrieval enhancements including:
  1. BM25+ (Lv & Zhai, 2011) - Solves the long-document over-penalization flaw.
  2. BM25L (Lv & Zhai, 2011) - Document-length regularized term frequency.
  3. Non-negative / Smoothed IDF (Robertson-Zaragoza / Lucene formulation).
  4. Term Proximity Scoring (BM25-TP / Büttcher et al., Song et al.) using positional postings.
  5. Reciprocal Rank Fusion (RRF, Cormack et al., 2009) for modern multi-signal/hybrid retrieval.

References:
  - Robertson, S. E., Walker, S., Jones, S., Hancock-Beaulieu, M. M., & Gatford, M. (1994).
    "Okapi at TREC-3". NIST Special Publication 500-225.
  - Robertson, S., & Zaragoza, H. (2009).
    "The Probabilistic Relevance Framework: BM25 and Beyond".
    Foundations and Trends in Information Retrieval, 3(4), 333-389.
  - Lv, Y., & Zhai, C. (2011).
    "Lower-bounding term frequency normalization". CIKM '11.
  - Büttcher, S., Clarke, C. L., & Cormack, G. V. (2006).
    "Term proximity scoring for robust information retrieval". SIGIR '06.
  - Cormack, G. V., Clarke, C. L., & Büttcher, S. (2009).
    "Reciprocal rank fusion outperforms condorcet and individual rank learning methods". SIGIR '09.
"""

import math
import os
import json
import re
from typing import Dict, List, Tuple, Optional, Set, Union
import Stemmer
from stopWords import STOP_WORDS

PATTERN = re.compile(r'[a-z0-9]+')
STEMMER = Stemmer.Stemmer('english')


# ============================================================================
# Section 1: Core Mathematical Functions (Robertson & Spärck Jones Formulation)
# ============================================================================

def idf_robertson_sparck_jones(
    total_docs: int,
    doc_freq: int,
    relevant_docs: int = 0,
    term_relevant_docs: int = 0
) -> float:
    """
    Computes the classic Robertson-Spärck Jones (RSJ) weight from the
    Probabilistic Relevance Framework (Binary Independence Model).

    Formula (with relevance feedback):
        w_RSJ = ln( ((r + 0.5) * (N - R - n + r + 0.5)) /
                    ((n - r + 0.5) * (R - r + 0.5)) )

    Formula (without relevance feedback, R = 0, r = 0):
        w_RSJ = ln( (N - n + 0.5) / (n + 0.5) )

    Args:
        total_docs (int): Total number of documents in the collection (N).
        doc_freq (int): Document frequency of the query term (n), i.e.,
            the number of documents containing the term.
        relevant_docs (int, optional): Total number of known relevant documents (R).
            Defaults to 0.
        term_relevant_docs (int, optional): Number of known relevant documents
            containing the term (r). Defaults to 0.

    Returns:
        float: The raw Robertson-Spärck Jones weight. Can be negative when
            n > (N / 2) in the non-relevance feedback case.
    """
    N = total_docs
    n = doc_freq
    R = relevant_docs
    r = term_relevant_docs

    numerator = (r + 0.5) * (N - R - n + r + 0.5)
    denominator = (n - r + 0.5) * (R - r + 0.5)

    if denominator <= 0 or numerator <= 0:
        return 0.0

    return math.log(numerator / denominator)


def idf_smoothed(total_docs: int, doc_freq: int) -> float:
    """
    Computes the smoothed, strictly non-negative Inverse Document Frequency (IDF).

    In the classic RSJ formula, when a term appears in more than half the collection
    (n > N / 2), the argument to the logarithm is < 1, resulting in a negative IDF.
    A negative weight unfairly penalizes documents that contain commonly occurring query terms.

    This smoothed formulation is adopted by modern systems (including Lucene,
    Elasticsearch, and Robertson & Zaragoza 2009 Section 3.4.1):

    Formula:
        IDF_smooth = ln( 1.0 + (N - n + 0.5) / (n + 0.5) )

    Args:
        total_docs (int): Total number of documents in the collection (N).
        doc_freq (int): Document frequency of the query term (n).

    Returns:
        float: Strictly positive IDF score.
    """
    N = total_docs
    n = doc_freq
    ratio = (N - n + 0.5) / (n + 0.5)
    # Ensure ratio >= 0 even in boundary edge cases
    ratio = max(0.0, ratio)
    return math.log(1.0 + ratio)


def idf_floored(
    total_docs: int,
    doc_freq: int,
    epsilon: float = 0.25,
    avg_idf: float = 1.0
) -> float:
    """
    Computes the Robertson & Walker (1994) floored IDF.

    In the original Okapi TREC-3 implementation, negative IDF values were floored
    at a fraction of the average collection IDF to ensure common terms still
    contribute a positive, non-zero weight.

    Formula:
        IDF_raw = ln( (N - n + 0.5) / (n + 0.5) )
        IDF_floored = max(epsilon * avg_idf, IDF_raw)

    Args:
        total_docs (int): Total number of documents in the collection (N).
        doc_freq (int): Document frequency of the term (n).
        epsilon (float, optional): Flooring factor, typically 0.25. Defaults to 0.25.
        avg_idf (float, optional): Average IDF across all indexed vocabulary terms.
            Defaults to 1.0.

    Returns:
        float: Floored IDF score, bounded below by epsilon * avg_idf.
    """
    raw_idf = idf_robertson_sparck_jones(total_docs, doc_freq)
    floor = epsilon * avg_idf
    return max(floor, raw_idf)


def compute_length_norm(doc_len: int, avgdl: float, b: float = 0.75) -> float:
    """
    Computes the document length normalization denominator factor B(D).

    Document length normalization balances the probability that a long document
    is long because it covers many topics (verboseness) vs. merely repeating words.

    Formula:
        B(D) = (1.0 - b) + b * (|D| / avgdl)

    Properties:
        - When |D| == avgdl, B(D) == 1.0 (no length adjustment).
        - When b == 0, B(D) == 1.0 (length normalization disabled).
        - When b == 1, B(D) == |D| / avgdl (full proportional scaling).
        - Standard default is b = 0.75.

    Args:
        doc_len (int): Length of document D in non-stopword tokens (|D|).
        avgdl (float): Average document length across the entire collection.
        b (float, optional): Length normalization scaling parameter, in [0, 1].
            Defaults to 0.75.

    Returns:
        float: Document length normalization multiplier B(D).
    """
    if avgdl <= 0:
        return 1.0
    return (1.0 - b) + (b * (doc_len / avgdl))


def tf_saturation(
    term_freq: int,
    doc_len: int,
    avgdl: float,
    k1: float = 1.5,
    b: float = 0.75
) -> float:
    """
    Computes the classic Okapi BM25 term frequency saturation component.

    Term frequency saturation enforces diminishing marginal returns on repeated
    occurrences of a query term within a single document.

    Formula:
        TF_norm = (tf * (k1 + 1.0)) / (tf + k1 * B(D))
        where B(D) = (1 - b) + b * (|D| / avgdl)

    As tf -> inf, TF_norm asymptotically approaches (k1 + 1.0).
    As k1 -> 0, TF_norm approaches 1 for any tf > 0 (binary presence).
    As k1 -> inf, TF_norm approaches linear term frequency normalized by length.

    Args:
        term_freq (int): Raw frequency of the term in the document (tf).
        doc_len (int): Length of document D (|D|).
        avgdl (float): Average document length across the collection.
        k1 (float, optional): Term frequency saturation parameter, typically in [1.2, 2.0].
            Defaults to 1.5.
        b (float, optional): Length normalization parameter, in [0, 1]. Defaults to 0.75.

    Returns:
        float: Saturated and length-normalized term frequency score.
    """
    if term_freq <= 0:
        return 0.0

    B = compute_length_norm(doc_len, avgdl, b)
    numerator = term_freq * (k1 + 1.0)
    denominator = term_freq + (k1 * B)

    return numerator / denominator if denominator > 0 else 0.0


def query_term_weight(query_freq: int, k3: float = 1.2) -> float:
    """
    Computes query term frequency weighting factor for long or repetitive queries.

    In the Robertson & Spärck Jones paper, queries with multiple repeated terms
    use a saturation function similar to document term frequency.

    Formula:
        QF_weight = (qtf * (k3 + 1.0)) / (qtf + k3)

    Properties:
        - When qtf == 1 (standard query term), QF_weight == 1.0 for any k3 > 0.
        - When qtf > 1, accounts for term emphasis with diminishing returns.

    Args:
        query_freq (int): Number of times the term appears in the user query (qtf).
        k3 (float, optional): Query term saturation parameter. Defaults to 1.2.

    Returns:
        float: Query term multiplier weight.
    """
    if query_freq <= 0:
        return 0.0
    return (query_freq * (k3 + 1.0)) / (query_freq + k3)


# ============================================================================
# Section 2: Modern 2026 Algorithmic Improvements
# ============================================================================

def tf_bm25_plus(
    term_freq: int,
    doc_len: int,
    avgdl: float,
    k1: float = 1.5,
    b: float = 0.75,
    delta: float = 1.0
) -> float:
    """
    Computes the BM25+ term frequency component (Lv & Zhai, 2011).

    Problem in Classic BM25:
        As document length |D| increases, B(D) grows indefinitely. For very long
        documents, the classic BM25 TF component approaches 0 even when the term
        appears multiple times:
            lim_{|D| -> inf} TF_norm = 0
        This severely penalizes long documents, causing relevant long documents to
        rank lower than short documents with a single accidental mention.

    Solution (BM25+):
        BM25+ introduces a lower bound delta floor (delta > 0). Every document
        containing the term is guaranteed to receive at least delta * IDF:
            TF_BM25+ = ((tf * (k1 + 1.0)) / (tf + k1 * B(D))) + delta

    Args:
        term_freq (int): Raw frequency of the term in the document (tf).
        doc_len (int): Length of document D (|D|).
        avgdl (float): Average document length across collection.
        k1 (float, optional): TF saturation parameter. Defaults to 1.5.
        b (float, optional): Length normalization parameter. Defaults to 0.75.
        delta (float, optional): Lower-bounding floor parameter (typically 0.5 to 1.0).
            Defaults to 1.0.

    Returns:
        float: BM25+ normalized term frequency score.
    """
    if term_freq <= 0:
        return 0.0

    standard_tf = tf_saturation(term_freq, doc_len, avgdl, k1, b)
    return standard_tf + delta


def tf_bm25l(
    term_freq: int,
    doc_len: int,
    avgdl: float,
    k1: float = 1.5,
    b: float = 0.75,
    delta: float = 0.5
) -> float:
    """
    Computes the BM25L (BM25 Long) term frequency component (Lv & Zhai, 2011).

    BM25L regularizes the term frequency before saturation to eliminate document
    length bias.

    Formula:
        c'(tf, D) = tf / B(D)
        if c' > 0:
            TF_BM25L = ((k1 + 1.0) * (c' + delta)) / (k1 + (c' + delta))
        else:
            0.0

    Args:
        term_freq (int): Raw frequency of the term in the document (tf).
        doc_len (int): Length of document D (|D|).
        avgdl (float): Average document length across collection.
        k1 (float, optional): TF saturation parameter. Defaults to 1.5.
        b (float, optional): Length normalization parameter. Defaults to 0.75.
        delta (float, optional): Shift parameter. Defaults to 0.5.

    Returns:
        float: BM25L normalized term frequency score.
    """
    if term_freq <= 0:
        return 0.0

    B = compute_length_norm(doc_len, avgdl, b)
    c_prime = term_freq / B if B > 0 else float(term_freq)

    shifted = c_prime + delta
    return ((k1 + 1.0) * shifted) / (k1 + shifted)


def compute_term_proximity_score(
    positions_by_term: Dict[str, List[int]],
    decay_exponent: float = 2.0,
    max_window: int = 25
) -> float:
    """
    Computes Term Proximity (BM25-TP) bonus using positional postings.

    Classic BM25 operates on a Bag-of-Words assumption, disregarding the order
    and proximity of terms in the document. Modern search engines reward documents
    where query terms occur close to each other.

    This function calculates the minimum pairwise span between distinct query terms
    and produces an inverse-distance proximity score:

    Formula:
        ProximityScore = sum_{i < j} ( 1.0 / (min_distance(q_i, q_j) ** decay_exponent) )
        where min_distance is bounded within [1, max_window].

    Args:
        positions_by_term (Dict[str, List[int]]): Dictionary mapping query term
            to list of sorted integer token positions in the document.
        decay_exponent (float, optional): Power exponent for distance decay.
            Defaults to 2.0 (quadratic decay).
        max_window (int, optional): Maximum window distance considered. Terms farther
            than this do not contribute to proximity. Defaults to 25.

    Returns:
        float: Proximity bonus score.
    """
    terms = [t for t, pos in positions_by_term.items() if pos]
    if len(terms) < 2:
        return 0.0

    total_proximity = 0.0

    # Check pairwise proximity between all pairs of matching query terms
    for i in range(len(terms)):
        for j in range(i + 1, len(terms)):
            pos_a = positions_by_term[terms[i]]
            pos_b = positions_by_term[terms[j]]

            # Two-pointer minimum distance search in O(len(pos_a) + len(pos_b))
            idx_a, idx_b = 0, 0
            min_dist = float('inf')

            while idx_a < len(pos_a) and idx_b < len(pos_b):
                p_a = pos_a[idx_a]
                p_b = pos_b[idx_b]
                dist = abs(p_a - p_b)

                if dist < min_dist:
                    min_dist = dist
                    if min_dist == 1:
                        # Adjacent words (exact bigram distance) - cannot get closer
                        break

                if p_a < p_b:
                    idx_a += 1
                else:
                    idx_b += 1

            if min_dist <= max_window:
                # Minimum distance of 1 gives 1.0; distance 2 gives 1/(2^decay)
                total_proximity += 1.0 / (float(min_dist) ** decay_exponent)

    return total_proximity


def reciprocal_rank_fusion(
    ranked_lists: List[List[int]],
    k: int = 60
) -> List[Tuple[int, float]]:
    """
    Reciprocal Rank Fusion (RRF, Cormack et al. 2009).

    RRF is the modern 2026 industry standard for hybrid search fusion (e.g., combining
    lexical BM25, exact phrase matching, and dense semantic retrieval). Unlike raw
    score addition, RRF requires no score normalization or hyperparameter tuning.

    Formula:
        RRF_Score(d) = sum_{r in R} ( 1.0 / (k + rank_r(d)) )

    where rank_r(d) is 1-indexed rank of document d in list r, and k is a smoothing
    constant (standard default k = 60).

    Args:
        ranked_lists (List[List[int]]): List of rankings, where each ranking is an
            ordered list of document IDs (first item is rank 1).
        k (int, optional): Smoothing constant to temper the impact of top ranks.
            Defaults to 60.

    Returns:
        List[Tuple[int, float]]: Sorted list of (doc_id, rrf_score) descending.
    """
    scores: Dict[int, float] = {}

    for ranked_list in ranked_lists:
        for rank, doc_id in enumerate(ranked_list, start=1):
            scores[doc_id] = scores.get(doc_id, 0.0) + (1.0 / (k + rank))

    sorted_results = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return sorted_results


# ============================================================================
# Section 3: Index Statistics & Corpus Profiling
# ============================================================================

def compute_corpus_stats(
    index: Dict[str, Dict[int, List[int]]],
    total_docs: Optional[int] = None
) -> Tuple[Dict[int, int], float, int]:
    """
    Computes document lengths, average document length, and corpus size directly
    from an in-memory inverted index.

    Document length |D| is computed by summing the term frequencies across all terms
    occurring in document D:
        |D| = sum_{t in Vocabulary} f(t, D) = sum_{t} len(positions_{t, D})

    Average document length (avgdl) is:
        avgdl = (sum_{D} |D|) / N

    Args:
        index (Dict[str, Dict[int, List[int]]]): Inverted index mapping
            term -> { doc_id: [pos1, pos2, ...] }.
        total_docs (Optional[int], optional): Total document count if known.
            If None, derived as the count of distinct documents in the index.

    Returns:
        Tuple[Dict[int, int], float, int]:
            - doc_lengths: Dict mapping doc_id -> token count
            - avgdl: Average document length across the collection
            - N: Total document count in corpus
    """
    doc_lengths: Dict[int, int] = {}

    for term, postings in index.items():
        for doc_id, positions in postings.items():
            doc_lengths[doc_id] = doc_lengths.get(doc_id, 0) + len(positions)

    N = total_docs if total_docs is not None else len(doc_lengths)
    total_tokens = sum(doc_lengths.values())
    avgdl = (total_tokens / N) if N > 0 else 0.0

    return doc_lengths, avgdl, N


def load_titles(
    wiki_filepath: str = "wikipedia_50000.txt",
    cache_filepath: str = "titles.json"
) -> Dict[int, str]:
    """
    Loads Wikipedia article titles from cache or extracts them from the raw corpus.

    Args:
        wiki_filepath (str, optional): Path to wikipedia raw dataset. Defaults to "wikipedia_50000.txt".
        cache_filepath (str, optional): Path to JSON titles cache file. Defaults to "titles.json".

    Returns:
        Dict[int, str]: Mapping from doc_id to article title.
    """
    if os.path.exists(cache_filepath):
        try:
            with open(cache_filepath, 'r', encoding='utf-8') as f:
                return {int(k): v for k, v in json.load(f).items()}
        except Exception:
            pass

    titles: Dict[int, str] = {}
    if os.path.exists(wiki_filepath):
        print(f"Loading article titles from {wiki_filepath}...")
        with open(wiki_filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        raw_titles = re.findall(r'<title>(.*?)</title>', content)
        titles = {i: t.strip() for i, t in enumerate(raw_titles)}
        try:
            with open(cache_filepath, 'w', encoding='utf-8') as f:
                json.dump(titles, f)
        except Exception:
            pass
    return titles


def load_or_build_corpus_metadata(
    wiki_filepath: str = "wikipedia_50000.txt",
    cache_filepath: str = "corpus_metadata.json"
) -> Tuple[Dict[int, str], Dict[int, int], float, int]:
    """
    Loads or precomputes document titles and token lengths from the Wikipedia
    dataset, caching the results to disk as JSON for instant future loading.

    This enables sub-millisecond ranking queries while providing human-readable
    Wikipedia article titles in search result displays.

    Args:
        wiki_filepath (str, optional): Path to wikipedia raw dataset.
            Defaults to "wikipedia_50000.txt".
        cache_filepath (str, optional): Path to cache file.
            Defaults to "corpus_metadata.json".

    Returns:
        Tuple[Dict[int, str], Dict[int, int], float, int]:
            - titles: Dict mapping doc_id -> article title string
            - doc_lengths: Dict mapping doc_id -> non-stop token count
            - avgdl: Average document length
            - N: Total document count
    """
    if os.path.exists(cache_filepath):
        try:
            with open(cache_filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            titles = {int(k): v for k, v in data['titles'].items()}
            doc_lengths = {int(k): v for k, v in data['doc_lengths'].items()}
            avgdl = float(data['avgdl'])
            N = int(data['N'])
            return titles, doc_lengths, avgdl, N
        except Exception:
            pass  # Fallback to computing if cache is corrupted

    titles: Dict[int, str] = {}
    doc_lengths: Dict[int, int] = {}

    if not os.path.exists(wiki_filepath):
        return titles, doc_lengths, 0.0, 0

    print(f"Building metadata cache from {wiki_filepath} (one-time setup)...")
    title_regex = re.compile(r'<title>(.*?)</title>', re.DOTALL | re.IGNORECASE)
    id_regex = re.compile(r'<id>.*?</id>', re.DOTALL)
    tags_regex = re.compile(r'</?(?:page|title|text)>', re.IGNORECASE)

    with open(wiki_filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    pages = content.split("</page>")
    valid_doc_id = 0

    for piece in pages:
        piece = id_regex.sub("", piece)
        title_match = title_regex.search(piece)
        clean_text = tags_regex.sub("", piece).strip()

        if not clean_text:
            continue

        raw_title = title_match.group(1).strip() if title_match else f"Document #{valid_doc_id}"
        titles[valid_doc_id] = raw_title

        # Count non-stopword tokens matching the indexer's tokenization logic
        token_count = 0
        for m in PATTERN.finditer(clean_text.lower()):
            tok = m.group()
            if tok not in STOP_WORDS:
                token_count += 1

        doc_lengths[valid_doc_id] = token_count
        valid_doc_id += 1

    N = len(doc_lengths)
    total_tokens = sum(doc_lengths.values())
    avgdl = (total_tokens / N) if N > 0 else 0.0

    # Save to disk
    try:
        with open(cache_filepath, 'w', encoding='utf-8') as f:
            json.dump({
                'titles': titles,
                'doc_lengths': doc_lengths,
                'avgdl': avgdl,
                'N': N
            }, f)
        print(f"Metadata cached to {cache_filepath} ({N} documents).")
    except Exception as e:
        print(f"Warning: Could not save metadata cache: {e}")

    return titles, doc_lengths, avgdl, N


# ============================================================================
# Section 4: BM25Ranker Engine Class
# ============================================================================

class BM25Ranker:
    """
    Production-grade BM25 Search Engine Ranker.

    Supports:
      - Classic Okapi BM25 (Robertson et al., 1994, 2009)
      - BM25+ (Lv & Zhai, 2011) with customizable delta floor
      - BM25L (Lv & Zhai, 2011) with length regularization
      - Non-negative smoothed IDF (Lucene default) or classical RSJ / floored IDF
      - Term Proximity (BM25-TP) positional boosts
      - Relevance feedback RSJ weights
      - Query term frequency weighting (k3)
    """

    def __init__(
        self,
        index: Dict[str, Dict[int, List[int]]],
        doc_lengths: Optional[Dict[int, int]] = None,
        avgdl: Optional[float] = None,
        total_docs: Optional[int] = None,
        titles: Optional[Dict[int, str]] = None,
        k1: float = 1.5,
        b: float = 0.75,
        k3: float = 1.2,
        delta: float = 1.0,
        variant: str = "bm25+",
        idf_method: str = "smoothed",
        proximity_weight: float = 0.5
    ):
        """
        Initializes the BM25Ranker with an inverted index and corpus parameters.

        Args:
            index (Dict[str, Dict[int, List[int]]]): Inverted index mapping
                term -> { doc_id: [pos1, pos2, ...] }.
            doc_lengths (Optional[Dict[int, int]], optional): Precomputed document lengths.
                If None, calculated from the inverted index.
            avgdl (Optional[float], optional): Average document length. If None, calculated.
            total_docs (Optional[int], optional): Total document count N. If None, calculated.
            titles (Optional[Dict[int, str]], optional): Document titles dictionary.
            k1 (float, optional): Term frequency saturation parameter (default 1.5).
            b (float, optional): Length normalization parameter (default 0.75).
            k3 (float, optional): Query term frequency parameter (default 1.2).
            delta (float, optional): BM25+ / BM25L lower bound parameter (default 1.0).
            variant (str, optional): Algorithm variant: 'bm25', 'bm25+', or 'bm25l'.
                Defaults to 'bm25+'.
            idf_method (str, optional): IDF formulation: 'smoothed', 'rsj', or 'floored'.
                Defaults to 'smoothed'.
            proximity_weight (float, optional): Weight multiplier for term proximity bonus.
                Defaults to 0.5. Set to 0.0 to disable proximity.
        """
        self.index = index
        self.k1 = k1
        self.b = b
        self.k3 = k3
        self.delta = delta
        self.variant = variant.lower()
        self.idf_method = idf_method.lower()
        self.proximity_weight = proximity_weight
        self.titles = titles or {}

        # Initialize or calculate corpus statistics
        if doc_lengths is None or avgdl is None or total_docs is None:
            calc_lengths, calc_avgdl, calc_N = compute_corpus_stats(index, total_docs)
            self.doc_lengths = doc_lengths if doc_lengths is not None else calc_lengths
            self.avgdl = avgdl if avgdl is not None else calc_avgdl
            self.N = total_docs if total_docs is not None else calc_N
        else:
            self.doc_lengths = doc_lengths
            self.avgdl = avgdl
            self.N = total_docs

        # Precompute average IDF for floored variant if needed
        self.avg_idf = 1.0
        self._idf_cache: Dict[str, float] = {}

    def get_idf(self, term: str) -> float:
        """
        Retrieves or calculates the IDF score for a term with caching.

        Args:
            term (str): Stemmed query term.

        Returns:
            float: Precomputed or newly evaluated IDF score.
        """
        if term in self._idf_cache:
            return self._idf_cache[term]

        postings = self.index.get(term, {})
        df = len(postings)

        if df == 0:
            score = 0.0
        elif self.idf_method == "smoothed":
            score = idf_smoothed(self.N, df)
        elif self.idf_method == "floored":
            score = idf_floored(self.N, df, epsilon=0.25, avg_idf=self.avg_idf)
        elif self.idf_method == "rsj":
            score = idf_robertson_sparck_jones(self.N, df)
        else:
            score = idf_smoothed(self.N, df)

        self._idf_cache[term] = score
        return score

    def calculate_tf_score(self, tf: int, doc_len: int) -> float:
        """
        Calculates the normalized TF component according to the selected variant.

        Args:
            tf (int): Raw term frequency.
            doc_len (int): Length of the document.

        Returns:
            float: Normalized TF component.
        """
        if self.variant == "bm25+":
            return tf_bm25_plus(tf, doc_len, self.avgdl, self.k1, self.b, self.delta)
        elif self.variant == "bm25l":
            return tf_bm25l(tf, doc_len, self.avgdl, self.k1, self.b, self.delta)
        else:
            # Classic BM25
            return tf_saturation(tf, doc_len, self.avgdl, self.k1, self.b)

    def score_document(
        self,
        doc_id: int,
        query_terms: List[str],
        query_freqs: Dict[str, int],
        explain: bool = False
    ) -> Union[float, Tuple[float, Dict]]:
        """
        Computes the complete BM25 relevance score of document D for query Q.

        Formula:
            Score(D, Q) = sum_{t in Q} [ IDF(t) * TF_norm(t, D) * QF_weight(t) ]
                          + Proximity_Weight * ProximityBonus(D, Q)

        Args:
            doc_id (int): ID of document to score.
            query_terms (List[str]): List of distinct stemmed query terms.
            query_freqs (Dict[str, int]): Mapping of term -> frequency in query.
            explain (bool, optional): If True, returns an explanation breakdown dict.
                Defaults to False.

        Returns:
            Union[float, Tuple[float, Dict]]: The numeric score, or (score, details).
        """
        doc_len = self.doc_lengths.get(doc_id, int(self.avgdl))
        total_score = 0.0
        positions_by_term: Dict[str, List[int]] = {}
        term_details = {}

        for term in query_terms:
            postings = self.index.get(term, {})
            positions = postings.get(doc_id, [])

            if not positions:
                continue

            tf = len(positions)
            positions_by_term[term] = positions

            idf = self.get_idf(term)
            tf_comp = self.calculate_tf_score(tf, doc_len)
            qf_weight = query_term_weight(query_freqs[term], self.k3)

            term_score = idf * tf_comp * qf_weight
            total_score += term_score

            if explain:
                term_details[term] = {
                    'tf': tf,
                    'idf': idf,
                    'tf_norm': tf_comp,
                    'qf_weight': qf_weight,
                    'term_score': term_score
                }

        # Add Term Proximity bonus if enabled
        proximity_score = 0.0
        if self.proximity_weight > 0.0 and len(positions_by_term) >= 2:
            proximity_score = compute_term_proximity_score(positions_by_term)
            total_score += (self.proximity_weight * proximity_score)

        if explain:
            explanation = {
                'doc_id': doc_id,
                'doc_len': doc_len,
                'avgdl': self.avgdl,
                'term_details': term_details,
                'proximity_score': proximity_score,
                'proximity_bonus': self.proximity_weight * proximity_score,
                'total_score': total_score
            }
            return total_score, explanation

        return total_score

    def rank(
        self,
        query: str,
        top_k: int = 10,
        candidate_docs: Optional[Set[int]] = None,
        min_term_match: int = 1
    ) -> List[Tuple[int, float, str]]:
        """
        Ranks candidate documents for a given search query string.

        Execution Pipeline:
          1. Tokenize, remove stop words, and stem query terms.
          2. Compute candidate documents:
             - If candidate_docs is provided (e.g., from an AND or Phrase query filter),
               only score those documents.
             - Otherwise, candidate documents are retrieved using an inverted index OR
               pool (documents containing at least min_term_match query terms).
          3. Score each candidate document using the configured BM25 variant.
          4. Sort candidates in descending order of score and return the top K.

        Args:
            query (str): Raw input query string.
            top_k (int, optional): Number of top documents to return. Defaults to 10.
            candidate_docs (Optional[Set[int]], optional): Optional restriction set of
                document IDs to rank.
            min_term_match (int, optional): Minimum distinct query terms a document must
                contain to be scored when candidate_docs is None. Defaults to 1.

        Returns:
            List[Tuple[int, float, str]]: List of (doc_id, bm25_score, title) sorted descending.
        """
        # Tokenize and stem query
        raw_tokens = []
        for m in PATTERN.finditer(query.lower()):
            token = m.group()
            if token not in STOP_WORDS:
                raw_tokens.append(STEMMER.stemWord(token))

        if not raw_tokens:
            return []

        # Count term frequencies in query
        query_freqs: Dict[str, int] = {}
        for t in raw_tokens:
            query_freqs[t] = query_freqs.get(t, 0) + 1

        query_terms = list(query_freqs.keys())

        # Collect candidate document set
        if candidate_docs is not None:
            candidates = candidate_docs
        else:
            doc_term_counts: Dict[int, int] = {}
            for term in query_terms:
                postings = self.index.get(term, {})
                for doc_id in postings.keys():
                    doc_term_counts[doc_id] = doc_term_counts.get(doc_id, 0) + 1

            candidates = {
                d for d, cnt in doc_term_counts.items()
                if cnt >= min_term_match
            }

        if not candidates:
            return []

        # Score candidate documents
        scored_docs = []
        for doc_id in candidates:
            score = self.score_document(doc_id, query_terms, query_freqs)
            if score > 0.0:
                title = self.titles.get(doc_id, f"Article #{doc_id}")
                scored_docs.append((doc_id, score, title))

        # Sort descending by score
        scored_docs.sort(key=lambda x: x[1], reverse=True)
        return scored_docs[:top_k]


def rank_query(
    query: str,
    index: Dict[str, Dict[int, List[int]]],
    top_k: int = 10,
    candidate_docs: Optional[Set[int]] = None,
    variant: str = "bm25+",
    k1: float = 1.5,
    b: float = 0.75,
    k3: float = 1.2,
    delta: float = 1.0,
    proximity_weight: float = 0.5
) -> List[Tuple[int, float, str]]:
    """
    Convenience functional interface to rank documents for a query.

    Instantiates a temporary BM25Ranker with the supplied index and parameters
    and retrieves top-ranked documents.

    Args:
        query (str): Raw search query text.
        index (Dict[str, Dict[int, List[int]]]): Inverted index dictionary.
        top_k (int, optional): Number of results to return. Defaults to 10.
        candidate_docs (Optional[Set[int]], optional): Restrict ranking to this set.
        variant (str, optional): Algorithm variant ('bm25', 'bm25+', 'bm25l').
            Defaults to 'bm25+'.
        k1 (float, optional): TF saturation parameter. Defaults to 1.5.
        b (float, optional): Document length normalization parameter. Defaults to 0.75.
        k3 (float, optional): Query term saturation parameter. Defaults to 1.2.
        delta (float, optional): Lower-bound delta parameter. Defaults to 1.0.
        proximity_weight (float, optional): Proximity bonus weight. Defaults to 0.5.

    Returns:
        List[Tuple[int, float, str]]: Ranked results (doc_id, score, title).
    """
    ranker = BM25Ranker(
        index=index,
        variant=variant,
        k1=k1,
        b=b,
        k3=k3,
        delta=delta,
        proximity_weight=proximity_weight
    )
    return ranker.rank(query, top_k=top_k, candidate_docs=candidate_docs)


# ============================================================================
# Section 5: CLI Runner & Interactive Demonstration
# ============================================================================

def main():
    """
    Interactive test and CLI demonstration runner for the BM25 ranker.

    Loads the inverted index from invertedIndex.txt, loads/builds metadata
    cache, and allows interactive search queries comparing classic BM25,
    BM25+, and Term Proximity ranking.
    """
    print("=" * 70)
    print("BM25 Ranking Engine - Okapi & Modern Enhancements (2026)")
    print("=" * 70)

    index_path = "invertedIndex.txt"
    if not os.path.exists(index_path):
        print(f"Error: {index_path} not found. Please run createIndex.py first.")
        return

    # Load index from queryIndex module
    print(f"Loading inverted index from {index_path}...")
    from queryIndex import parseIndex
    index = parseIndex(index_path)
    print(f"Loaded index containing {len(index)} unique vocabulary terms.")

    # Load corpus metadata
    titles, doc_lengths, avgdl, N = load_or_build_corpus_metadata()

    # Initialize Ranker (using state-of-the-art BM25+ with proximity bonus)
    ranker = BM25Ranker(
        index=index,
        doc_lengths=doc_lengths,
        avgdl=avgdl,
        total_docs=N,
        titles=titles,
        k1=1.5,
        b=0.75,
        k3=1.2,
        delta=1.0,
        variant="bm25+",
        idf_method="smoothed",
        proximity_weight=0.5
    )

    print(f"Corpus Profile: N = {ranker.N} docs | avgdl = {ranker.avgdl:.2f} tokens")
    print(f"Default Algorithm: BM25+ (delta=1.0, k1=1.5, b=0.75) + Term Proximity")
    print("-" * 70)

    while True:
        try:
            query = input("\nEnter search query (or 0 to Exit): ").strip()
            if query == "0" or not query:
                break

            results = ranker.rank(query, top_k=10)

            if not results:
                print(f"No matching documents found for '{query}'.")
                continue

            print(f"\nTop {len(results)} Ranked Results for '{query}':")
            print(f"{'Rank':<5} {'Doc ID':<8} {'Score':<10} {'Title'}")
            print("-" * 70)
            for rank, (doc_id, score, title) in enumerate(results, start=1):
                print(f"{rank:<5} {doc_id:<8} {score:<10.4f} {title}")

        except (KeyboardInterrupt, EOFError):
            break

    print("\nExiting search engine. Happy searching!")


if __name__ == "__main__":
    main()
