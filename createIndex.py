import re
import Stemmer
from stopWords import STOP_WORDS

ID_TAG = re.compile(r'<id>.*?</id>', re.DOTALL)
TAGS = ("<page>", "<title>", "</title>", "<text>", "</text>")

def parseDoc(doc):
    """using a for loop parse the document to separate articles by removing page tags and merging title and description
    Lowercase all words and store the result in a list
    The <id> tag is removed together with its value, since Wikipedia page IDs are not used for searching.
    Pieces that are empty after cleaning (e.g. the trailing newline after the last </page>) are skipped,
    so every entry in the result is a real article and its list index is its document ID."""
    print("parsing document")
    result = []
    for piece in doc.lower().split("</page>"):
        piece = ID_TAG.sub("", piece)
        for tag in TAGS:
            piece = piece.replace(tag, "")
        piece = piece.strip()
        if piece:
            result.append(piece)
    return result




def createInvertedIndex(documentList):

    """ For each string in the list
     Get all tokens, where a token is a string of alphanumeric characters terminated by a non-alphanumeric character. The alphanumeric characters are defined to be [a-z0-9]. So, the tokens for the word ‘apple+orange’ would be ‘apple’ and ‘orange’.
     Filter out all the tokens that are in the stop words list, such as ‘a’, ‘an’, ‘the’.
     Stem each token using to finally obtain the stream of terms. Porter Stemmer removes common endings from words. For example the stemmed version of the words fish, fishes, fishing, fisher, fished are all fish
     store each token in a hashtable with value as empty arrays
     For each key in the hashtable loop through the document list and update the empty list value with the start index of the key/token example: {web:[[1,[0,3]],[2,[2]]]} where the first value of each array is the document ID
    """
    p = re.compile(r'[a-z0-9]+')
    stemmer = Stemmer.Stemmer('english')
    
    invertedIndex = {}
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
                    
    return invertedIndex
    



def main():
    """Orchestrates Inverted Index creating and writes result to text file"""
    with open('wikipedia_50000.txt','r',encoding='utf-8') as f:
        read_data = f.read()
    parsed_data = parseDoc(read_data)
    invertedIndex = createInvertedIndex(parsed_data)
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

if (__name__ == "__main__"):
    main()
