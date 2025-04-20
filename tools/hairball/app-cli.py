from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel
from typing import List, Optional
import re
import chromadb
from chromadb.utils import embedding_functions
from sentence_transformers import SentenceTransformer
from keybert import KeyBERT
from config import (
    CHROMA_PATH,
    EMBEDDING_MODEL,
    KEYWORD_SETTINGS,
    SUMMARY_MAX_WORDS
)
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Models ---
class SearchResult(BaseModel):
    snippet: str
    keywords: List[str]
    source_file: str
    score: float
    summary: str
    section: Optional[str] = None

class SearchResponse(BaseModel):
    query: str
    refined_query: str
    results: List[SearchResult]

# --- Initialize Services ---
try:
    logger.info("Loading embedding model...")
    embedding_model = SentenceTransformer(EMBEDDING_MODEL)
    kw_model = KeyBERT(model=embedding_model)
    
    logger.info("Connecting to ChromaDB...")
    chroma_client = chromadb.PersistentClient(path=CHROMA_PATH)
    embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name=EMBEDDING_MODEL
    )
    chroma_collection = chroma_client.get_collection(
        name="legal_docs",
        embedding_function=embedding_fn
    )
    doc_count = chroma_collection.count()
    logger.info(f"Collection contains {doc_count} documents")
    
except Exception as e:
    logger.error(f"Initialization failed: {str(e)}")
    raise RuntimeError(f"Service initialization failed: {str(e)}")

# --- Helper Functions ---
def refine_query(question: str) -> str:
    try:
        if not question.strip():
            return ""
        keywords = kw_model.extract_keywords(question, **KEYWORD_SETTINGS)
        return " ".join([kw[0] for kw in keywords])
    except Exception as e:
        logger.error(f"Query refinement failed: {str(e)}")
        return question  # Fallback to original query

def extract_section_header(text: str, position: int) -> Optional[str]:
    try:
        prev_newline = text.rfind("\n\n", 0, position)
        if prev_newline == -1:
            return None
        
        candidate = text[prev_newline:position].strip()
        section_pattern = re.compile(r"^(Article|Section|§)\s+\d+[\.\d]*")
        if match := section_pattern.search(candidate):
            return match.group(0)
        return None
    except Exception:
        return None

def extract_relevant_snippet(full_text: str, keywords: List[str]) -> str:
    try:
        if not full_text:
            return "No content available"
            
        if not keywords:
            return " ".join(full_text.split()[:SUMMARY_MAX_WORDS])
            
        positions = [full_text.lower().find(kw.lower()) for kw in keywords if kw]
        valid_positions = [p for p in positions if p > -1]
        
        if not valid_positions:
            return " ".join(full_text.split()[:SUMMARY_MAX_WORDS])
            
        first_pos = min(valid_positions)
        words = full_text.split()
        word_pos = len(full_text[:first_pos].split())
        
        start = max(0, word_pos - SUMMARY_MAX_WORDS//2)
        end = min(len(words), word_pos + SUMMARY_MAX_WORDS//2)
        
        snippet = " ".join(words[start:end])
        if header := extract_section_header(full_text, first_pos):
            snippet = f"{header}\n\n{snippet}"
        
        return snippet[:SUMMARY_MAX_WORDS*6]
    except Exception:
        return full_text[:500]  # Fallback

# --- API Setup ---
app = FastAPI(title="Legal Document Search API")

@app.get("/search", response_model=SearchResponse)
async def search(
    q: str = Query(..., description="Natural language legal question"),
    n_results: int = Query(3, description="Number of results to return")
):
    try:
        if not q.strip():
            raise HTTPException(status_code=400, detail="Empty query")
            
        refined_q = refine_query(q)
        logger.info(f"Searching for: '{q}' (refined: '{refined_q}')")
        
        # Safely query ChromaDB
        try:
            results = chroma_collection.query(
                query_texts=[refined_q],
                n_results=n_results,
                include=["documents", "metadatas", "distances"]
            )
        except Exception as e:
            logger.error(f"ChromaDB query failed: {str(e)}")
            raise HTTPException(status_code=500, detail="Search service unavailable")

        # Validate results structure
        if not results or not isinstance(results, dict):
            return SearchResponse(
                query=q,
                refined_query=refined_q,
                results=[]
            )

        search_results = []
        for i in range(len(results.get("documents", [[]])[0])):
            try:
                doc = results["documents"][0][i]
                meta = results["metadatas"][0][i] if results.get("metadatas") and len(results["metadatas"]) > 0 and len(results["metadatas"][0]) > i else {}
                score = results["distances"][0][i] if results.get("distances") and len(results["distances"]) > 0 and len(results["distances"][0]) > i else 1.0
                
                keywords = meta.get("keywords", "").split(", ") if meta and "keywords" in meta else []
                source_file = meta.get("source_file", "unknown") if meta else "unknown"
                summary = meta.get("summary", "") if meta else ""
                
                search_results.append(SearchResult(
                    snippet=extract_relevant_snippet(doc, keywords),
                    keywords=keywords,
                    source_file=source_file,
                    summary=summary,
                    score=float(1 - score),
                    section=extract_section_header(doc, doc.find(keywords[0])) if keywords else None
                ))
            except Exception as e:
                logger.error(f"Error processing result {i}: {str(e)}")
                continue
                
        return SearchResponse(
            query=q,
            refined_query=refined_q,
            results=search_results
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Search error: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/health")
async def health_check():
    try:
        count = chroma_collection.count()
        return {
            "status": "healthy",
            "documents": count,
            "collection": "legal_docs",
            "embedding_model": EMBEDDING_MODEL
        }
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        return {"status": "unhealthy", "error": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)