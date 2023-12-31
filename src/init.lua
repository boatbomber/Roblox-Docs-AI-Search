--!native
--!optimize 2
--!strict

local HttpService = game:GetService("HttpService")

export type Config = {
	GithubKey: string,
	OpenAIKey: string,
	ScoreThreshold: number?,
	IndexSourceUrl: string?,
}

export type Vector = { number }

export type SourceDocument = {
	type: string,
	title: string,
	content: string,
	embedding: Vector?,
}

export type Document = {
	type: string,
	title: string,
	content: string,
}


export type NeighborInfo = {
	score: number,
	item: SourceDocument,
}

local DocsAISearch = {}
DocsAISearch.__index = DocsAISearch

function DocsAISearch.new(config: Config)
	assert(type(config) == "table", "DocsAISearch.new must be called with a config table")
	assert(type(config.GithubKey) == "string", "DocsAISearch.new config['GithubKey'] must be a string")
	assert(type(config.OpenAIKey) == "string", "DocsAISearch.new config['OpenAIKey'] must be a string")
	assert(config.ScoreThreshold == nil or type(config.ScoreThreshold) == "number", "DocsAISearch.new config['ScoreThreshold'] must be a number or nil")
	assert(config.IndexSourceUrl == nil or type(config.IndexSourceUrl) == "string", "DocsAISearch.new config['IndexSourceUrl'] must be a string or nil")

	local self = setmetatable({
		Documents = {},
		IsLoaded = false,
		ScoreThreshold = config.ScoreThreshold or 0.75,
		_IndexSourceUrl = config.IndexSourceUrl or "https://github.com/boatbomber/Roblox-Docs-AI-Search/releases/latest/download/docs-embeddings.json",
		_GithubKey = config.GithubKey,
		_OpenAIKey = config.OpenAIKey,
		_IsLoading = false,
	}, DocsAISearch)

	return self
end

function DocsAISearch:_cosineSimilarityUnit(a: Vector, b: Vector): number
	-- Because the vectors are unit vectors, the dot product is the cosine similarity
	-- since magnitude is 1 for both vectors
	local dot = 0
	for i, ai in a do
		dot += ai * b[i]
	end
	return dot
end

function DocsAISearch:_requestVectorEmbedding(text: string): { token_usage: number, embedding: Vector?}?
	assert(type(text) == "string", "DocumentationIndex:_requestVectorEmbedding must be called with a string")

	local success, response = pcall(HttpService.RequestAsync, HttpService, {
		Url = "https://api.openai.com/v1/embeddings",
		Method = "POST",
		Headers = {
			["Content-Type"] = "application/json",
			["Authorization"] = "Bearer " .. self._OpenAIKey,
		},
		Body = HttpService:JSONEncode({
			model = "text-embedding-ada-002",
			input = text,
		}),
	})

	if not success then
		warn("Failed to get reply from OpenAI:", response)
		return
	end

	if response.StatusCode ~= 200 then
		warn("OpenAI responded with error code:", response.StatusCode, response.StatusMessage, response.Body)
		return
	end

	local decodeSuccess, decodeResponse = pcall(HttpService.JSONDecode, HttpService, response.Body)
	if not decodeSuccess then
		warn("Failed to decode OpenAI response body:", decodeResponse, response.Body)
		return
	end

	return {
		token_usage = (decodeResponse.usage.total_tokens or 0),
		embedding = decodeResponse.data[1].embedding,
	}
end

function DocsAISearch:_findKNearestNeighbors(vector: Vector, k: number): { NeighborInfo }
	local nearestNeighbors: { NeighborInfo } = table.create(k + 1)

	local function pushItem(item: SourceDocument, score: number)
		table.insert(nearestNeighbors, {score = score, item = item})
		local index = #nearestNeighbors

		while index > 1 do
			local parentIndex = math.floor(index / 2)
			if nearestNeighbors[index].score < nearestNeighbors[parentIndex].score then
				nearestNeighbors[index], nearestNeighbors[parentIndex] = nearestNeighbors[parentIndex], nearestNeighbors[index]
				index = parentIndex
			else
				break
			end
		end
	end

	-- For our dataset size, a linear search is fine. If we add more documents, we can use ANN search algorithms.
	for _, document: SourceDocument in ipairs(self.Documents) do
		if not document.embedding then
			continue
		end
		local score = self:_cosineSimilarityUnit(document.embedding, vector)

		if score :: number >= self.ScoreThreshold then
			pushItem(document, score)

			if #nearestNeighbors > k then
				table.remove(nearestNeighbors, 1) -- Remove the smallest (min) score item
			end
		end
	end

	-- Sort the top K neighbors by score
	table.sort(nearestNeighbors, function(a, b)
		return a.score > b.score
	end)
	return nearestNeighbors
end

function DocsAISearch:Load()
	-- Don't load redundantly
	if self.IsLoaded then
		return
	end
	-- If already loading in another thread, just wait for that to finish
	if self._IsLoading then
		repeat
			task.wait()
		until self.IsLoaded
		return
	end

	self._IsLoading = true

	local loadSuccess, loadResponse = pcall(HttpService.RequestAsync, HttpService, {
		Url = self._IndexSourceUrl,
		Method = "GET",
		Headers = {
			Authorization = "bearer " .. self._GithubKey,
		},
	})

	if not loadSuccess then
		warn("Failed to load index:", loadResponse)
		return
	end

	if loadResponse.StatusCode ~= 200 then
		warn("GitHub release download responded with error code:", loadResponse.StatusCode, loadResponse.StatusMessage, loadResponse.Body)
		return
	end

	local decodeSuccess, decodeResponse = pcall(HttpService.JSONDecode, HttpService, loadResponse.Body)
	if not decodeSuccess then
		warn("Failed to decode GitHub release download response body:", decodeResponse, loadResponse.Body)
		return
	end

	self.Documents = decodeResponse
	self.IsLoaded = true
	self._IsLoading = false
end

function DocsAISearch:Query(query: string, count: number?): { token_usage: number, result: { error: string?, documents: { Document }?} }
	assert(type(query) == "string", "DocsAISearch:Query query must be a string")
	assert(count == nil or type(count) == "number", "DocsAISearch:Query count must be a number or nil")

	if not self.IsLoaded then
		-- Ensure the index is loaded (happens on first call if user didn't preload by calling Load themselves)
		self:Load()
	end

	local queryEmbedding = self:_requestVectorEmbedding(query)
	if not queryEmbedding then
		return {
			token_usage = 0,
			result = {
				error = "Failed to get query embedding",
			},
		}
	end

	local k = math.max(count or 2, 1)
	local nearestNeighbors = self:_findKNearestNeighbors(queryEmbedding.embedding, k)

	if #nearestNeighbors == 0 then
		return {
			token_usage = queryEmbedding.token_usage,
			result = {
				error = "No results found",
			},
		}
	end

	local results = table.create(k)
	for i, neighbor in ipairs(nearestNeighbors) do
		results[i] = {
			type = neighbor.item.type or "",
			title = neighbor.item.title or "",
			content = neighbor.item.content or "",
		}
	end

	return {
		token_usage = queryEmbedding.token_usage,
		result = {
			documents = results,
		},
	}
end

return DocsAISearch
