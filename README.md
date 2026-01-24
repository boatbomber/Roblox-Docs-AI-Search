# Roblox Docs AI Search

An AI-powered semantic search system for Roblox documentation that uses vector embeddings to enable intelligent, meaning-based searches rather than simple keyword matching.

## Overview

This project consists of two main components:

- **Indexer** (Python): Processes Roblox documentation sources, generates AI embeddings, and creates a searchable index
- **Searcher** (Luau): A Roblox module that performs fast semantic searches using vector similarity

The system indexes both the [Roblox Creator Documentation](https://github.com/Roblox/creator-docs) and the [Roblox API Reference](https://github.com/MaximumADHD/Roblox-Client-Tracker), creating over 12,000 embeddings from 1,500+ documents.

## Features

### Indexer

- **Multi-source documentation processing**: Automatically fetches and processes both Creator Docs and API Reference documentation
- **Intelligent chunking**: Splits documents into sections while preserving context
- **AI-enhanced indexing**:
  - Generates embeddings using `qwen/qwen3-embedding-8b` (8192 dimensions)
  - Creates concise summaries for better semantic understanding
  - Generates hypothetical questions to improve query matching
- **Smart caching**: Saves embeddings, summaries, and questions locally to reduce API costs on subsequent runs
- **Parallel processing**: Processes documents efficiently using 24 workers
- **Automated builds**: GitHub Actions workflow automatically generates and publishes updated indexes

### Searcher

- **Fast semantic search**: K-nearest neighbors algorithm with cosine similarity
- **Automatic index loading**: Downloads pre-built index from GitHub releases
- **Configurable relevance**: Adjustable threshold to filter low-quality results
- **Optimized for Roblox**: Native compilation with strict typing for maximum performance

## Installation

### Indexer Installation

The indexer requires Python 3.8+ and uses Poetry for dependency management.

1. Clone the repository:

```bash
git clone https://github.com/boatbomber/Roblox-Docs-AI-Search.git
cd Roblox-Docs-AI-Search
```

2. Create a `.env` file with your API keys:

```env
OPENROUTER_API_KEY=sk-or-v1-XXXXXXXXXXXXXXXXXXXXXX
GITHUB_TOKEN=ghp_XXXXXXXXXXXXXXXXXXXXXXX
```

3. Install dependencies and run:

```bash
poetry install
poetry run python indexer/main.py
```

The indexer will generate a `build/index.json` file (~370 MB) along with summary statistics.

### Searcher Installation

Install via [Wally](https://wally.run):

```toml
[server-dependencies]
DocsAISearch = "boatbomber/robloxdocsaisearch@1.3.0"
```

## Usage

### Basic Search

```lua
local DocsAISearch = require(script.DocsAISearch).new({
	OpenRouterAPIKey = Secrets.OpenRouter,
	GithubKey = Secrets.Github,
	RelevanceThreshold = 0.4, -- Default: 0.4
})

-- Query returns top K most relevant documents
local results = DocsAISearch:Query("how to set sun position in the sky", 5)

for _, result in results do
	print(result.title, result.relevance)
	print(result.content)
end
```

### Preloading

For better performance on the first query, preload the index:

```lua
DocsAISearch:Load()
```

## How It Works

### Indexing Process

1. **Document Fetching**: Downloads latest documentation from GitHub repositories
2. **Processing**:
   - Extracts metadata from YAML frontmatter
   - Cleans markdown content
   - Splits into sections by headers
3. **AI Enhancement**:
   - Generates embeddings for content, sections, summaries, and hypothetical questions
   - Uses prompt prefix: "Represent this sentence for searching relevant passages:"
4. **Caching**: Stores results in `.cache/` directory using SHA-256 hashing
5. **Output**: Generates `build/index.json` with all embeddings and metadata

### Search Process

1. **Query Embedding**: User query is converted to vector using the same embedding model
2. **Similarity Calculation**: Cosine similarity computed against all indexed vectors
3. **Ranking**: Results sorted by relevance score
4. **Filtering**: Only returns results above the relevance threshold
5. **Return**: Top K documents with titles, content, and relevance scores

## Project Structure

```txt
Roblox-Docs-AI-Search/
├── indexer/             # Python indexer
│   ├── main.py          # Main orchestrator
│   ├── creator_docs.py  # Creator docs processor
│   ├── api_reference.py # API reference generator
│   ├── config.py        # Configuration
│   ├── cache.py         # Caching system
│   └── ...
├── src/
│   └── init.lua         # Roblox searcher module
├── .github/workflows/
│   └── create-index-release.yml  # Automated indexing
├── build/               # Generated index (gitignored)
├── .cache/              # Cached embeddings (gitignored)
└── pyproject.toml       # Python dependencies
```

## Configuration

### Indexer Configuration

Edit `indexer/config.py` to customize:

- Embedding and summary models
- Maximum token limits
- Document filtering rules
- API endpoints

### Searcher Configuration

Configure when initializing the searcher:

- `OpenRouterAPIKey`: Your OpenRouter API key
- `GithubKey`: GitHub personal access token for downloading releases
- `RelevanceThreshold`: Minimum similarity score (0-1) for results

## Development

### Tools

The project uses:

- **Poetry**: Python dependency management
- **Aftman**: Toolchain manager for Roblox tools
- **Rojo**: Roblox project management
- **Selene**: Lua linter
- **StyLua**: Lua code formatter

### Running Tests

```bash
# Format Lua code
stylua src/

# Lint
selene src/
```

## API Costs

The indexer uses AI APIs which incur costs:

- **Embeddings**: ~1,500 documents × multiple embeddings per document
- **Summaries**: ~1,500 documents
- **Questions**: ~1,500 documents × 3 questions

The caching system significantly reduces costs on subsequent runs by reusing previously generated embeddings.

## License

This project is licensed under the Mozilla Public License Version 2.0.

## Credits

Documentation sources:

- [Roblox Creator Documentation](https://github.com/Roblox/creator-docs)
- [Roblox API Reference](https://github.com/MaximumADHD/Roblox-Client-Tracker) by MaximumADHD
