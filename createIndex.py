import json
import re
import Stemmer
from stopWords import STOP_WORDS

ID_TAG = re.compile(r'<id>.*?</id>', re.DOTALL)
TITLE_TAG = re.compile(r'<title>(.*?)</title>', re.DOTALL | re.IGNORECASE)
TAGS = ("<page>", "<title>", "</title>", "<text>", "</text>")

def parseDoc(doc):
    """Parse the document to separate articles by extracting titles and body text.
    The <id> tag is removed together with its value, since Wikipedia page IDs are not used for searching.
    Pieces that are empty after cleaning (e.g. the trailing newline after the last </page>) are skipped,
    so every entry in the result is a real article and its list index is its document ID.
    
    Returns:
        tuple: (documentList, titlesList)
    """
    print("parsing document")
    result = []
    titles = []
    for piece in doc.split("</page>"):
        title_match = TITLE_TAG.search(piece)
        clean_piece = piece.lower()
        clean_piece = ID_TAG.sub("", clean_piece)
        for tag in TAGS:
            clean_piece = clean_piece.replace(tag, "")
        clean_piece = clean_piece.strip()
        if clean_piece:
            title = title_match.group(1).strip() if title_match else f"Document #{len(result)}"
            titles.append(title)
            result.append(clean_piece)
    return result, titles


def createInvertedIndex(documentList):
    """ For each string in the list
     Get all tokens, where a token is a string of alphanumeric characters terminated by a non-alphanumeric character. The alphanumeric characters are defined to be [a-z0-9].
     Filter out all the tokens that are in the stop words list, such as 'a', 'an', 'the'.
     Stem each token using Porter Stemmer to obtain the stream of terms.
     Tracks exact term positions and document lengths (|D|) for BM25 ranking.
     
     Returns:
         tuple: (invertedIndex, doc_lengths)
    """
    p = re.compile(r'[a-z0-9]+')
    stemmer = Stemmer.Stemmer('english')
    
    invertedIndex = {}
    doc_lengths = {}
    total_docs = len(documentList)
    print(f"creating inverted index for {total_docs} documents...")
    for docId, document in enumerate(documentList):
        if (docId + 1) % 5000 == 0:
            print(f"Processed {docId + 1}/{total_docs} documents...")
        iterator = p.finditer(document)
        valid_word_position = 0
        for match in iterator:
            token = match.group()
            if token not in STOP_WORDS:
                stemmed = stemmer.stemWord(token)
                pos = valid_word_position
                
                if stemmed not in invertedIndex:
                    invertedIndex[stemmed] = []
                    
                if not invertedIndex[stemmed] or invertedIndex[stemmed][-1][0] != docId:
                    invertedIndex[stemmed].append([docId, [pos]])
                else:
                    invertedIndex[stemmed][-1][1].append(pos)
                
                valid_word_position += 1
        doc_lengths[docId] = valid_word_position
                    
    return invertedIndex, doc_lengths


def main():
    """Orchestrates Inverted Index and Corpus Metadata creation, writing results to disk."""
    with open('wikipedia_50000.txt', 'r', encoding='utf-8') as f:
        read_data = f.read()
    parsed_data, titles = parseDoc(read_data)
    invertedIndex, doc_lengths = createInvertedIndex(parsed_data)
    
    print("writing index to disk...")
    # {web:[[1,[0,3]],[2,[2]]]}
    # term|docID1:pos1,pos2;docID2:pos3,pos4,pos5;
    terms = invertedIndex.keys()
    with open('invertedIndex.txt', 'w', encoding='utf-8') as f:
        for term in terms:
            docs = invertedIndex[term]
            docList = []
            for item in docs:
                actualDocId = item[0]
                positions = item[1]
                docList.append(f"{actualDocId}:{','.join(map(str, positions))}")
            f.write(f"{term}|{';'.join(docList)}\n")

    print("writing corpus metadata cache to disk...")
    total_docs = len(parsed_data)
    total_tokens = sum(doc_lengths.values())
    avgdl = (total_tokens / total_docs) if total_docs > 0 else 0.0
    metadata = {
        "N": total_docs,
        "avgdl": avgdl,
        "doc_lengths": doc_lengths,
        "titles": {i: t for i, t in enumerate(titles)}
    }
    with open('corpus_metadata.json', 'w', encoding='utf-8') as f:
        json.dump(metadata, f)

    print(f"Indexing complete! Processed {total_docs} docs (avgdl: {avgdl:.2f} tokens).")

if __name__ == "__main__":
    main()
