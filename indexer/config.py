import os
from dotenv import load_dotenv
load_dotenv()

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
	'en-us/', # All english documentation
}
