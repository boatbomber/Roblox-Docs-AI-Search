# Roblox-Docs-AI-Search
AI vector embeddings of Roblox informational documents for semantic search

## Indexer

Grabs content from the creator-docs repo, processes and chunks them, feeds that through TogetherAI, and spits out `build/`.
The GitHub workflow puts those outputs into a release so that you don't need to do this expensive step every time.

### How to run the indexer yourself

Create a `.env` file:
```
TOGETHERAI_API_KEY=xx-XXXXXXXXXXXXXXXXXXXXXX
GITHUB_TOKEN=xxx_XXXXXXXXXXXXXXXXXXXXXXX
```

Then run:

```bash
pip install -r indexer/requirements.txt
python indexer/main.py
```

## Searcher

Enables fast semantic searching with vector KNN querying.

### Installation

Install using wally:

```toml
[server-dependencies]
DocsAISearch = "boatbomber/robloxdocsaisearch@1.2.0"
```

### Usage

```Lua
local DocsAISearch = require(script.DocsAISearch).new({
	TogetherAIKey = Secrets.TogetherAI,
	GithubKey = Secrets.Github,
	RelevanceThreshold = 0.3,
})

-- Optionally, preload via DocsAISearch:Load(), otherwise it'll load the index upon first query

local results = DocsAISearch:Query("how to set sun position in the sky", 2)
```

