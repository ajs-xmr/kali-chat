#!/usr/bin/env python3
"""
Legal Text Processor (TXT → ChromaDB)
- Processes text files from ./cleaned_texts/
- Extracts keywords using config-defined model
- Stores in ChromaDB with embeddings
"""

import hashlib
from pathlib import Path
from typing import List, Dict, Optional
import chromadb
from sentence_transformers import SentenceTransformer
from transformers import pipeline, AutoTokenizer
from config import (  # Shared config
    CHROMA_PATH,
    EMBEDDING_MODEL,
    KEYWORD_SETTINGS,
    EXTRACT_WORDS,
    SUMMARY_MAX_WORDS
)

# --- Initialize ChromaDB ---
chroma_client = chromadb.PersistentClient(path=CHROMA_PATH)
embedding_fn = chromadb.utils.embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name=EMBEDDING_MODEL
)
chroma_collection = chroma_client.get_or_create_collection(
    name="legal_docs",
    embedding_function=embedding_fn,
    metadata={"hnsw:space": "cosine"}
)

# --- Model Initialization ---
print("Loading models...")
try:
    embedding_model = SentenceTransformer(EMBEDDING_MODEL)
    summarizer = pipeline(
        "summarization",
        model="facebook/bart-large-cnn",
        tokenizer="facebook/bart-large-cnn",
        device=-1  # CPU
    )
except Exception as e:
    raise RuntimeError(f"Model loading failed: {str(e)}")

# --- Helper Functions ---
def generate_md5(text: str) -> str:
    return hashlib.md5(text.encode()).hexdigest()

def extract_first_n_words(text: str, n: int) -> str:
    return " ".join(text.split()[:n])

def legal_summarize(text: str) -> str:
    try:
        summary = summarizer(
            extract_first_n_words(text, EXTRACT_WORDS),
            max_length=SUMMARY_MAX_WORDS,
            min_length=int(SUMMARY_MAX_WORDS * 0.7),
            no_repeat_ngram_size=3,
            truncation=True
        )
        return summary[0]["summary_text"].strip()
    except Exception as e:
        print(f"Summarization failed: {str(e)}")
        return extract_first_n_words(text, SUMMARY_MAX_WORDS)

def extract_keywords(text: str) -> List[str]:
    from keybert import KeyBERT
    kw_model = KeyBERT(model=embedding_model)
    keywords = kw_model.extract_keywords(text, **KEYWORD_SETTINGS)
    return [kw[0] for kw in keywords]

# --- Processing Pipeline ---
def process_file(input_path: Path) -> bool:
    try:
        text = input_path.read_text(encoding="utf-8")
        doc_id = generate_md5(text)
        
        summary = legal_summarize(text)
        keywords = extract_keywords(summary)
        
        chroma_collection.add(
            ids=doc_id,
            documents=[text],
            metadatas=[{
                "source_file": input_path.name,
                "keywords": ", ".join(keywords),
                "summary": summary
            }],
            embeddings=[embedding_model.encode(text).tolist()]
        )
        return True
        
    except Exception as e:
        print(f"Failed processing {input_path.name}: {str(e)}")
        return False

# --- Main Execution ---
if __name__ == "__main__":
    input_dir = Path("./cleaned_texts")
    processed = sum(
        1 for f in input_dir.glob("*.txt") 
        if process_file(f)
    )
    
    print(f"\nProcessed {processed} files")
    print(f"Total documents: {chroma_collection.count()}")