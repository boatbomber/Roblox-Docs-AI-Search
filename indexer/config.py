import os

from dotenv import load_dotenv

load_dotenv()

EMBEDDING_MODEL = "qwen/qwen3-embedding-8b"
SUMMARY_MODEL = "openai/gpt-oss-20b"
QUESTION_MODEL = "openai/gpt-oss-20b"

EMBEDDING_TOKEN_LIMIT = 16000
EMBEDDING_BATCH_LIMIT = 25

INDEX_VERSION = "v2.0.0"

# GitHub API token
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

# OpenRouter API key for embedding & summary model
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

GH_REQ_HEADERS = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}

ALLOWLISTED_DOCUMENT_PATHS = {
    "creator-docs-main/content/en-us/",  # All english documentation
}
BLOCKLISTED_DOCUMENT_PATHS = {
    "creator-docs-main/content/en-us/art/characters/facial-animation/facs-poses-reference",  # Just a bunch of videos, not helpful to us
}
ALLOWLISTED_DOCUMENT_FILETYPES = {
    ".md",  # Tutorials
    # '.yaml', # API Reference
}
