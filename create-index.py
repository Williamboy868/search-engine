import re
import Stemmer

def parseDoc(doc):
    """using a for loop parse the document to separate articles by removing page tags and merging title and description
    Lowercase all words and store the result in a list"""
    print("parsing document")
    result = doc.lower().split("</page>")
    for idx, i in enumerate(result):
        result[idx] = i.replace("<page>", "").replace("</page>", "").replace("<title>", "").replace("</title>", "").replace("<text>", "").replace("</text>", "").replace("<id>", "").replace("</id>", "")
    return result




def createInvertedIndex(documentList):

    """ For each string in the list
     Get all tokens, where a token is a string of alphanumeric characters terminated by a non-alphanumeric character. The alphanumeric characters are defined to be [a-z0-9]. So, the tokens for the word ‘apple+orange’ would be ‘apple’ and ‘orange’.
     Filter out all the tokens that are in the stop words list, such as ‘a’, ‘an’, ‘the’.
     Stem each token using to finally obtain the stream of terms. Porter Stemmer removes common endings from words. For example the stemmed version of the words fish, fishes, fishing, fisher, fished are all fish
     store each token in a hashtable with value as empty arrays
     For each key in the hashtable loop through the document list and update the empty list value with the start index of the key/token example: {web:[[1,[0,3]],[2,[2]]]} where the first value of each array is the document ID
    """
    stop_words = {"a", "an", "the", "by", "is", "they", "that", "them", "for", "are", "and", "in", "was", "were", "but", "as", "with", "of", "to", "it", "on", "at", "this", "or", "from", "which", "not", "be", "have", "has", "had", "will", "would", "shall", "should", "may", "might", "must", "can", "could"}
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
            if token not in stop_words:
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
