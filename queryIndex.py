import re
import Stemmer

STOP_WORDS = {"a", "an", "the", "by", "is", "they", "that", "them", "for", "are", "and", "in", "was", "were", "but", "as", "with", "of", "to", "it", "on", "at", "this", "or", "from", "which", "not", "be", "have", "has", "had", "will", "would", "shall", "should", "may", "might", "must", "can", "could"}
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

def oneWordQuery(userQuery, index):
    """Returns a list of docIDs for a single word query."""
    terms = process_query(userQuery)
    if not terms:
        return []
    
    term = terms[0]
    return list(index.get(term, {}).keys())

def FreeTextQuery(userQuery, index):
    """Returns a list of docIDs that contain ANY of the terms in the query."""
    terms = process_query(userQuery)
    docs = set()
    
    for term in terms:
        # Get documents for this term and add to the set (Union)
        docs.update(index.get(term, {}).keys())
        
    return list(docs)

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
    splittedQuery = query.split(' ')
    if len(splittedQuery) == 1:   
        return oneWordQuery(query, index)
    elif len(splittedQuery) == 2:
        return FreeTextQuery(query, index)
    else:
        return PhraseQuery(query, index)


def main():
    print("Loading index... (this may take a moment for large indices)")
    filepath = 'invertedIndex.txt'
    try:
        index = parseIndex(filepath)
        print(f"Index loaded successfully with {len(index)} terms.")
    except FileNotFoundError:
        print(f"Error: Could not find {filepath}. Please ensure you have run create-index.py first.")
        return
    
    while True:
        query = input("\nEnter query (or 0 to Exit): ")
        if query == '0':
            break
        try:
            res = checkQueryType(query, index)
            print(f"Found {len(res)} documents: {res[:20]}{'...' if len(res) > 20 else ''}")
        except Exception as e:
            print(f"Error processing query: {e}")
        
if __name__ == "__main__":
    main()
