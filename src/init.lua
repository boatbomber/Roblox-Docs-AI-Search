--!native
--!optimize 2
--!strict

local HttpService = game:GetService("HttpService")

local types = require(script.types)
local versioning = require(script.versioning)
local util = require(script.util)

local DocsAISearch = {}
DocsAISearch.__index = DocsAISearch

function DocsAISearch.new(config: types.Config)
	assert(type(config) == "table", "DocsAISearch.new must be called with a config table")
	assert(type(config.GithubKey) == "string", "DocsAISearch.new config['GithubKey'] must be a string")
	assert(type(config.TogetherAIKey) == "string", "DocsAISearch.new config['TogetherAIKey'] must be a string")
	assert(
		config.RelevanceThreshold == nil or type(config.RelevanceThreshold) == "number",
		"DocsAISearch.new config['RelevanceThreshold'] must be a number or nil"
	)
	assert(
		config.IndexSourceRepo == nil
			or (type(config.IndexSourceRepo) == "string" and string.find(config.IndexSourceRepo, "/") ~= nil),
		"DocsAISearch.new config['IndexSourceUrl'] must be a string (in 'owner/repo' format) or nil"
	)

	local self = setmetatable({
		Documents = {},
		IsLoaded = false,
		RelevanceThreshold = config.RelevanceThreshold or 0.4,
		_IndexSourceRepo = config.IndexSourceRepo or "boatbomber/Roblox-Docs-AI-Search",
		_GithubKey = config.GithubKey,
		_TogetherAIKey = config.TogetherAIKey,
		_embeddingModel = "togethercomputer/m2-bert-80M-8k-retrieval",
		_IsLoading = false,
	}, DocsAISearch)

	return self
end

function DocsAISearch:_cosineSimilarityUnit(queryVector: types.Vector, comparisons: { types.Vector }): number
	-- Because the vectors are unit vectors, the dot product is the cosine similarity
	-- since magnitude is 1 for both vectors
	local dots = table.create(#comparisons, 0)
	for comparisonIndex, comparisonVector in comparisons do
		for componentIndex, queryComponent in queryVector do
			dots[comparisonIndex] += queryComponent * comparisonVector[componentIndex]
		end
	end
	return math.max(table.unpack(dots))
end

function DocsAISearch:_requestVectorEmbedding(text: string): { token_usage: number, embedding: types.Vector? }?
	assert(type(text) == "string", "DocumentationIndex:_requestVectorEmbedding must be called with a string")

	local success, response = pcall(HttpService.RequestAsync, HttpService, {
		Url = "https://api.together.xyz/v1/embeddings",
		Method = "POST",
		Headers = {
			["Content-Type"] = "application/json",
			["Authorization"] = "Bearer " .. self._TogetherAIKey,
		},
		Body = HttpService:JSONEncode({
			model = self._embeddingModel,
			input = text,
		}),
	})

	if not success then
		warn("Failed to get reply from TogetherAI:", response)
		return
	end

	if response.StatusCode ~= 200 then
		warn("TogetherAI responded with error code:", response.StatusCode, response.StatusMessage, response.Body)
		return
	end

	local decodeSuccess, decodeResponse = pcall(HttpService.JSONDecode, HttpService, response.Body)
	if not decodeSuccess then
		warn("Failed to decode TogetherAI response body:", decodeResponse, response.Body)
		return
	end

	local usage = if decodeResponse.usage then decodeResponse.usage else { total_tokens = 0 }

	return {
		token_usage = usage.total_tokens or 0,
		embedding = decodeResponse.data[1].embedding,
	}
end

function DocsAISearch:_findKNearestNeighbors(vector: types.Vector, k: number): { types.NeighborInfo }
	local nearestNeighbors: { types.NeighborInfo } = table.create(k + 1)

	-- For our dataset size, a linear search is acceptable. If we add more documents, we can use ANN search algorithms.
	local worstRelevance, count = 1, 0
	for _, document: types.SourceDocument in self.Documents do
		local relevance: number = self:_cosineSimilarityUnit(vector, document.embeddings)
		if relevance < self.RelevanceThreshold then
			-- Drop results below threshold
			continue
		end

		if count == 0 then
			-- First pushed item
			nearestNeighbors[1] = { relevance = relevance, item = document }
			worstRelevance = relevance
			count = 1
			continue
		end

		if count == k and relevance < worstRelevance then
			-- We already have k items and this one is worse than all of them
			continue
		end

		-- Find the correct insert spot
		for index, neighbor in nearestNeighbors do
			if neighbor.relevance < relevance then
				table.insert(nearestNeighbors, index, { relevance = relevance, item = document })
				break
			end
		end

		-- Remove the worst item if we have too many
		if count == k then
			nearestNeighbors[#nearestNeighbors] = nil
		else
			count += 1
		end

		-- Update the worst relevance
		worstRelevance = nearestNeighbors[#nearestNeighbors].relevance
	end

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

	local releasesSuccess, releasesResponse = pcall(HttpService.RequestAsync, HttpService, {
		Url = "https://api.github.com/repos/" .. (self._IndexSourceRepo :: string) .. "/releases?per_page=10",
		Method = "GET",
		Headers = {
			Authorization = "bearer " .. self._GithubKey,
		},
	})

	if not releasesSuccess then
		warn("Failed to get releases from GitHub:", releasesResponse)
		self._IsLoading = false
		return
	end

	if releasesResponse.StatusCode ~= 200 then
		warn(
			"GitHub releases info responded with error code:",
			releasesResponse.StatusCode,
			releasesResponse.StatusMessage,
			releasesResponse.Body
		)
		self._IsLoading = false
		return
	end

	local releasesDecodeSuccess, releasesDecodeResponse =
		pcall(HttpService.JSONDecode, HttpService, releasesResponse.Body)

	if not releasesDecodeSuccess then
		warn("Failed to decode GitHub releases response body:", releasesDecodeResponse, releasesResponse.Body)
		self._IsLoading = false
		return
	end

	local indexUrl = nil
	for _, release in releasesDecodeResponse do
		local releaseVersion = string.match(release.body, "Index Version: (v[%d%.]+)") or "v0.2"
		if not versioning:isSupportedVersion(releaseVersion) then
			continue
		end

		for _, asset in release.assets do
			if string.find(asset.name, "index.json", 1, true) then
				indexUrl = asset.browser_download_url
				break
			end
		end

		if not indexUrl then
			continue
		end

		-- Use the embedder model for this index
		local embeddingModel = string.match(release.body, "Embedding Model: ([^\n]+)")
		if embeddingModel then
			self._embeddingModel = util.stripString(embeddingModel)
		end

		break
	end

	if not indexUrl then
		warn("Failed to find index.json in GitHub releases")
		self._IsLoading = false
		return
	end

	local loadSuccess, loadResponse = pcall(HttpService.RequestAsync, HttpService, {
		Url = indexUrl,
		Method = "GET",
		Headers = {
			Authorization = "bearer " .. self._GithubKey,
		},
	})

	if not loadSuccess then
		warn("Failed to load index:", loadResponse)
		self._IsLoading = false
		return
	end

	if loadResponse.StatusCode ~= 200 then
		warn(
			"GitHub index.json download responded with error code:",
			loadResponse.StatusCode,
			loadResponse.StatusMessage,
			loadResponse.Body
		)
		self._IsLoading = false
		return
	end

	local decodeSuccess, decodeResponse = pcall(HttpService.JSONDecode, HttpService, loadResponse.Body)
	if not decodeSuccess then
		warn("Failed to decode GitHub release download response body:", decodeResponse, loadResponse.Body)
		self._IsLoading = false
		return
	end

	self.Documents = decodeResponse
	self._embeddingDimensions = #decodeResponse[1].embeddings[1]
	self.IsLoaded = true
	self._IsLoading = false
end

function DocsAISearch:Query(
	query: string,
	count: number?
): { token_usage: number, result: { error: string?, documents: { types.Document }? } }
	assert(type(query) == "string", "DocsAISearch:Query query must be a string")
	assert(count == nil or type(count) == "number", "DocsAISearch:Query count must be a number or nil")

	if not self.IsLoaded then
		-- Ensure the index is loaded (happens on first call if user didn't preload by calling Load themselves)
		self:Load()
	end

	local queryEmbedding =
		self:_requestVectorEmbedding("Represent this sentence for searching relevant passages: " .. string.lower(query))
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
			relevance = neighbor.relevance,
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
