import os
from dotenv import load_dotenv
load_dotenv()

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1024
SUMMARY_MODEL = "gpt-4-turbo-preview"

INDEX_VERSION = "v0.3"

# GitHub API token
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

# OpenAI API key for embedding model
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

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
