from flask import Flask, request, jsonify, render_template_string
import chromadb
from chromadb.utils import embedding_functions
from sentence_transformers import SentenceTransformer
from keybert import KeyBERT
import logging
from textwrap import fill

# ======== CONFIGURATION ======== #
CHROMA_PATH = "./chroma_db"
EMBEDDING_MODEL = "all-MiniLM-L6-v2"
COLLECTION_NAME = "legal_docs"

# Search parameters
KEYWORD_SETTINGS = {
    "keyphrase_ngram_range": (1, 2),
    "stop_words": "english",
    "top_n": 5
}
SEARCH_RESULT_WORDS = 500    # Words to show in search results
TARGET_CONTEXT_WORDS = 1000  # Words around match to retrieve
MAX_DOCUMENT_WORDS = 10000   # Full document view

# UI Settings
RESULTS_PER_PAGE = 5
HIGHLIGHT_COLOR = "#FFF3A3"

# ======== INITIALIZATION ======== #
app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

try:
    # Load models
    embedding_model = SentenceTransformer(EMBEDDING_MODEL)
    kw_model = KeyBERT(model=embedding_model)
    
    # Connect to ChromaDB
    chroma_client = chromadb.PersistentClient(path=CHROMA_PATH)
    embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name=EMBEDDING_MODEL
    )
    collection = chroma_client.get_collection(
        name=COLLECTION_NAME,
        embedding_function=embedding_fn
    )
    logging.info(f"Connected to ChromaDB collection with {collection.count()} documents")
except Exception as e:
    logging.error(f"Initialization failed: {str(e)}")
    raise

# ======== HELPER FUNCTIONS ======== #
def get_words_around_match(full_text: str, keyword: str, num_words: int) -> str:
    """Extract words around the first keyword match"""
    try:
        text_lower = full_text.lower()
        keyword_lower = keyword.lower()
        pos = text_lower.find(keyword_lower)
        
        if pos == -1:
            return " ".join(full_text.split()[:num_words])
            
        words = full_text.split()
        pre_text = full_text[:pos]
        word_pos = len(pre_text.split())
        
        start = max(0, word_pos - num_words//2)
        end = min(len(words), word_pos + num_words//2)
        
        return " ".join(words[start:end])
    except Exception:
        return full_text[:num_words*6]  # Fallback

def format_document(text: str) -> str:
    """Format raw document text for better readability"""
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    formatted = []
    
    for para in paragraphs:
        # Preserve headings (lines in ALL CAPS)
        if para.isupper() and len(para.split()) < 10:
            formatted.append(f'<h3>{para}</h3>')
        else:
            formatted.append(f'<p>{fill(para, width=100)}</p>')
    
    return "\n".join(formatted)

# ======== ROUTES ======== #
@app.route('/api/search', methods=['GET'])
def api_search():
    query = request.args.get('q', '')
    if not query:
        return jsonify({"error": "Empty query"}), 400
    
    try:
        # Extract keywords and search
        keywords = [kw[0] for kw in kw_model.extract_keywords(query, **KEYWORD_SETTINGS)]
        results = collection.query(
            query_texts=[" ".join(keywords)],
            n_results=RESULTS_PER_PAGE,
            include=["documents", "metadatas", "distances"]
        )
        
        # Format response
        response = {"query": query, "results": []}
        
        for i in range(len(results['documents'][0])):
            full_text = results['documents'][0][i]
            meta = results['metadatas'][0][i] if results['metadatas'] else {}
            
            # Get relevant portion of text
            context = get_words_around_match(
                full_text, 
                keywords[0] if keywords else "", 
                TARGET_CONTEXT_WORDS
            )[:SEARCH_RESULT_WORDS*6]  # Approximate word limit
            
            response['results'].append({
                "preview": context + "..." if len(context) < len(full_text) else context,
                "source": meta.get("source_file", "unknown"),
                "score": float(1 - results['distances'][0][i]) if results['distances'] else 0.0,
                "doc_id": results['ids'][0][i]  # For full document retrieval
            })
        
        return jsonify(response)
    
    except Exception as e:
        logging.error(f"Search error: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/document/<doc_id>')
def get_document(doc_id):
    try:
        result = collection.get(ids=[doc_id], include=["documents", "metadatas"])
        if not result['documents']:
            return jsonify({"error": "Document not found"}), 404
            
        full_text = result['documents'][0]
        formatted_text = format_document(full_text[:MAX_DOCUMENT_WORDS*6])
        
        return jsonify({
            "content": formatted_text,
            "metadata": result['metadatas'][0] if result['metadatas'] else {}
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ======== UI ======== #
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>Hairball Search</title>
    <style>
        body { font-family: sans-serif; max-width: 1000px; margin: 0 auto; padding: 20px; }
        #search { width: 100%; padding: 12px; font-size: 16px; margin-bottom: 20px; }
        .result { margin: 25px 0; padding: 15px; border: 1px solid #ddd; border-radius: 5px; }
        .score { color: #28a745; font-size: 0.9em; margin: 5px 0; }
        .source { color: #6c757d; cursor: pointer; text-decoration: underline; }
        .highlight { background-color: ''' + HIGHLIGHT_COLOR + '''; padding: 2px 4px; }
        #document-view { margin-top: 30px; padding: 20px; background: #f8f9fa; }
        #document-view h3 { margin-top: 25px; color: #2c3e50; }
    </style>
</head>
<body>
    <h1>Document Search</h1>
    <input id="search" placeholder="Search legal documents..." autofocus>
    <div id="results"></div>
    <div id="document-view" style="display:none;"></div>

    <script>
        // Search function
        document.getElementById('search').addEventListener('input', async (e) => {
            const query = e.target.value.trim();
            if (query.length < 2) {
                document.getElementById('results').innerHTML = '';
                document.getElementById('document-view').style.display = 'none';
                return;
            }
            
            try {
                const response = await fetch(`/api/search?q=${encodeURIComponent(query)}`);
                const data = await response.json();
                
                if (data.error) {
                    document.getElementById('results').innerHTML = 
                        `<div class="error">${data.error}</div>`;
                    return;
                }
                
                let resultsHTML = '';
                data.results.forEach(result => {
                    resultsHTML += `
                        <div class="result">
                            <div>${result.preview}</div>
                            <div class="score">Relevance: ${result.score.toFixed(2)}</div>
                            <div class="source" onclick="showDocument('${result.doc_id}')">
                                View full document: ${result.source}
                            </div>
                        </div>
                    `;
                });
                
                document.getElementById('results').innerHTML = resultsHTML;
            } catch (err) {
                document.getElementById('results').innerHTML = 
                    '<div class="error">Search failed. Check console for details.</div>';
                console.error(err);
            }
        });
        
        // Document viewer
        async function showDocument(docId) {
            try {
                const response = await fetch(`/api/document/${docId}`);
                const data = await response.json();
                
                if (data.error) {
                    alert(data.error);
                    return;
                }
                
                document.getElementById('document-view').innerHTML = `
                    <h2>${data.metadata.source_file || 'Document'}</h2>
                    <div>${data.content}</div>
                `;
                document.getElementById('document-view').style.display = 'block';
                
                // Scroll to document view
                document.getElementById('document-view').scrollIntoView({
                    behavior: 'smooth'
                });
            } catch (err) {
                console.error(err);
                alert('Failed to load document');
            }
        }
    </script>
</body>
</html>
'''

@app.route('/')
def ui():
    return render_template_string(HTML_TEMPLATE)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)