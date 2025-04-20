CHROMA_PATH = "./chroma_db"
EMBEDDING_MODEL = "all-MiniLM-L6-v2"

# Keyword extraction settings
KEYWORD_SETTINGS = {
    "keyphrase_ngram_range": (1, 2),
    "stop_words": "english",
    "top_n": 5
}

# Text processing limits
EXTRACT_WORDS = 400       # Words used for summarization
SUMMARY_MAX_WORDS = 300   # Max words in generated summary