import os

from dotenv import load_dotenv

load_dotenv()

EMBEDDING_MODEL = "togethercomputer/m2-bert-80M-2k-retrieval"
SUMMARY_MODEL = "mistralai/Mistral-7B-Instruct-v0.3"
QUESTION_MODEL = "mistralai/Mistral-7B-Instruct-v0.3"

EMBEDDING_TOKEN_LIMIT = 1200
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
