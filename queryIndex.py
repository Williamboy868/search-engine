import os
import re
import Stemmer
from stopWords import STOP_WORDS
import symspellpy
from rankResults import BM25Ranker, load_or_build_corpus_metadata

# Initialize SymSpell for query correction
sym_spell = symspellpy.SymSpell(max_dictionary_edit_distance=2, prefix_length=7)
dictionary_path = os.path.join(os.path.dirname(symspellpy.__file__), "frequency_dictionary_en_82_765.txt")
sym_spell.load_dictionary(dictionary_path, term_index=0, count_index=1)

PATTERN = re.compile(r'[a-z0-9]+')
STEMMER = Stemmer.Stemmer('english')

def process_query(query_string):
    """Processes a query string into a list of stemmed tokens (matches index creation)."""
    tokens = []
    for match in PATTERN.finditer(query_string.lower()):
        token = match.group()
        if token not in STOP_WORDS:
            tokens.append(STEMMER.stemWord(token))
    return tokens

def parseIndex(filepath):
    """
    Reads the inverted index from disk into memory.
    Format: { term: { docID: [pos1, pos2, ...] } }
    """
    invertedIndex = {}
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            
            try:
                term, postings_str = line.split('|')
            except ValueError:
                continue # Skip malformed lines
                
            doc_dict = {}
            if postings_str:
                for doc_posting in postings_str.split(';'):
                    if not doc_posting:
                        continue
                    doc_id, positions = doc_posting.split(':')
                    doc_dict[int(doc_id)] = [int(p) for p in positions.split(',')]
            
            invertedIndex[term] = doc_dict
            
    return invertedIndex

def AndQuery(userQuery, index):
    """Returns a list of docIDs that contain ALL of the terms in the query."""
    terms = process_query(userQuery)
    if not terms:
        return []
        
    doc_sets = [set(index.get(term, {}).keys()) for term in terms]
    if not doc_sets:
        return []
        
    common_docs = set.intersection(*doc_sets)
    return list(common_docs)

def PhraseQuery(userQuery, index):
    """Returns a list of docIDs that contain the EXACT phrase."""
    terms = process_query(userQuery)
    if not terms:
        return []
        
    # First, find documents that contain ALL the terms (Intersection)
    doc_sets = [set(index.get(term, {}).keys()) for term in terms]
    if not doc_sets:
        return []
        
    common_docs = set.intersection(*doc_sets)
    if not common_docs:
        return []
        
    result = []
    # Now, check positional alignment for each document
    for doc in common_docs:
        # Get positions for the first term
        base_positions = index[terms[0]][doc]
        
        # Check if there is any base_position that forms a phrase
        for p in base_positions:
            is_phrase = True
            for i in range(1, len(terms)):
                # We expect the i-th term to be at position (p + i)
                if (p + i) not in index[terms[i]][doc]:
                    is_phrase = False
                    break
            
            if is_phrase:
                result.append(doc)
                break # Found the phrase in this document, move to next doc
                
    return result

def checkQueryType(query, index):
    query = query.strip()
    if query.startswith('"') and query.endswith('"'):
        return PhraseQuery(query[1:-1], index)
    else:
        return AndQuery(query, index)


def main():
    print("Loading index...")
    filepath = 'invertedIndex.txt'
    try:
        index = parseIndex(filepath)
        print(f"Index loaded successfully with {len(index)} terms.")
    except FileNotFoundError:
        print(f"Error: Could not find {filepath}. Please ensure you have run create-index.py first.")
        return

    print("Initializing BM25 Ranker...")
    titles, doc_lengths, avgdl, N = load_or_build_corpus_metadata()
    ranker = BM25Ranker(
        index=index,
        doc_lengths=doc_lengths if doc_lengths else None,
        avgdl=avgdl if avgdl > 0 else None,
        total_docs=N if N > 0 else None,
        titles=titles if titles else None,
        variant="bm25+",
        proximity_weight=0.5
    )
    print(f"BM25 Ranker ready (Corpus size: {ranker.N} docs | avgdl: {ranker.avgdl:.2f} tokens).")
    
    while True:
        query = input("\nAsk what you want to know (or 0 to Exit): ")
        if query == '0':
            break
            
        is_phrase = query.strip().startswith('"') and query.strip().endswith('"')
        
        # Remove punctuation to avoid false positive spell corrections
        clean_query = " ".join(re.findall(r'[a-zA-Z0-9]+', query))
        
        if not clean_query:
            print("Please enter a valid query.")
            continue
            
        try:
            # Correct the query
            suggestions = sym_spell.lookup_compound(clean_query, max_edit_distance=2, ignore_non_words=True)
            if suggestions:
                corrected_query = suggestions[0].term
                if corrected_query.lower() != clean_query.lower():
                    print(f"Showing search results for [{corrected_query}]")
                    query = corrected_query
                else:
                    query = clean_query

            if is_phrase:
                query = f'"{query}"'

            res = checkQueryType(query, index)
            raw_query = query[1:-1] if is_phrase else query

            if res:
                # Rank matching candidate documents using BM25+ with proximity weighting
                ranked_results = ranker.rank(raw_query, candidate_docs=set(res), top_k=10)
                print(f"\nFound {len(res)} matching documents. Top {len(ranked_results)} ranked results:")
                print(f"{'Rank':<5} {'Doc ID':<8} {'Score':<10} {'Title'}")
                print("-" * 65)
                for rank, (doc_id, score, title) in enumerate(ranked_results, start=1):
                    print(f"{rank:<5} {doc_id:<8} {score:<10.4f} {title}")
            else:
                print(f"No documents matched the strict {'phrase' if is_phrase else 'AND'} criteria for [{query}].")
                if not is_phrase:
                    # Fallback to free-text BM25 ranking across the corpus
                    print("Falling back to free-text BM25 ranking...")
                    ranked_results = ranker.rank(clean_query, top_k=10)
                    if ranked_results:
                        print(f"\nTop {len(ranked_results)} Free-Text Ranked Results:")
                        print(f"{'Rank':<5} {'Doc ID':<8} {'Score':<10} {'Title'}")
                        print("-" * 65)
                        for rank, (doc_id, score, title) in enumerate(ranked_results, start=1):
                            print(f"{rank:<5} {doc_id:<8} {score:<10.4f} {title}")
                    else:
                        print("No matching documents found in corpus.")
        except Exception as e:
            print(f"Error processing query: {e}")
        
if __name__ == "__main__":
    main()
