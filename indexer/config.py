import os
from dotenv import load_dotenv
load_dotenv()

EMBEDDING_MODEL = "togethercomputer/m2-bert-80M-8k-retrieval"
SUMMARY_MODEL = "meta-llama/Llama-3-70b-chat-hf"

EMBEDDING_TOKEN_LIMIT = 8000
EMBEDDING_BATCH_LIMIT = 1000

INDEX_VERSION = "v1.0"

# GitHub API token
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

# TogetherAI API key for embedding & summary model
TOGETHERAI_API_KEY = os.getenv("TOGETHERAI_API_KEY")

GH_REQ_HEADERS = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}

ALLOWLISTED_DOCUMENT_PATHS = {
    'creator-docs-main/content/en-us/',  # All english documentation
}
ALLOWLISTED_DOCUMENT_FILETYPES = {
    '.md',  # Tutorials
    # '.yaml', # API Reference
}
