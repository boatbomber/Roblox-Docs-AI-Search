export type Config = {
	GithubKey: string,
	TogetherAIKey: string,
	RelevanceThreshold: number?,
	IndexSourceRepo: string?,
}

export type Vector = { number }

export type SourceDocument = {
	type: string,
	title: string,
	content: string,
	embeddings: { Vector },
}

export type Document = {
	type: string,
	title: string,
	content: string,
	relevance: number,
}

export type NeighborInfo = {
	relevance: number,
	item: SourceDocument,
}

return nil
