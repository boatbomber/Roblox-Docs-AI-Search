import os
from dotenv import load_dotenv

load_dotenv()

EMBEDDING_MODEL = "WhereIsAI/UAE-Large-V1"
SUMMARY_MODEL = "meta-llama/Llama-3-70b-chat-hf"

EMBEDDING_TOKEN_LIMIT = 500
EMBEDDING_BATCH_LIMIT = 25

INDEX_VERSION = "v1.1"

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
    "creator-docs-main/content/en-us/",  # All english documentation
}
BLOCKLISTED_DOCUMENT_PATHS = {
    "creator-docs-main/content/en-us/art/characters/facial-animation/facs-poses-reference",  # Just a bunch of videos, not helpful to us
}
ALLOWLISTED_DOCUMENT_FILETYPES = {
    ".md",  # Tutorials
    # '.yaml', # API Reference
}
