import os  # for creating the build directory
from openai import OpenAI  # for generating embeddings and summaries
import tiktoken  # for counting tokens
import json  # for exporting results
from datetime import date  # for writing the date to the summary file

import write
import config
import creator_docs
import api_reference

openai_client = OpenAI(
    api_key=config.OPENAI_API_KEY,
)


def count_tokens(text: str) -> int:
    """Return the number of tokens in a string."""
    return len(tiktoken.get_encoding('cl100k_base').encode(text))


def get_embedding(content: [str]) -> [[float]]:
    """Return the embeddings for a list of strings."""
    response = openai_client.embeddings.create(
        input=content, model=config.EMBEDDING_MODEL, dimensions=config.EMBEDDING_DIMENSIONS)
    return [item.embedding for item in response.data]


def get_summary(content: str) -> str:
    completion = openai_client.chat.completions.create(
        model=config.SUMMARY_MODEL,
        messages=[
            {
                "role": "system",
                "content": "You are a summary generator. Your summary will be used to create vector embeddings for content to improve semantic searches. When the user provides content, respond with a summary of the content.",
            },
            {
                "role": "user",
                "content": content,
            },
        ],
    )
    return completion.choices[0].message.content


def create_docs_list(documents, reference):
    docs_list = []

    count_files = len(documents) + len(reference)
    current_file = 0

    # Handle the documents
    for filepath in documents:
        current_file += 1
        print("[" + str(current_file) + "/" +
              str(count_files) + "] Processing " + filepath)

        document = documents[filepath]

        # First, we get the metadata
        metadata = creator_docs.get_document_metadata(
            filepath=filepath, document=document)

        print("  Extracted metadata")

        # Then, we process it for ingestion
        content = creator_docs.prepare_document_for_ingest(document=document)

        print("  Prepped for ingest")

        # Then, we break it into sections using ## headers, so that we get a dict of header content -> section content
        sections = creator_docs.get_document_sections(
            content=content, metadata=metadata)

        print("  Divided sections")

        entry = {
            "type": "creator-docs",
            "title": metadata["title"],
            "content": content,
            "embeddings": [],
        }

        # Then we get the embeddings for the document, each section, and summaries
        embed_batch = []

        if count_tokens(content) < 8100:
            embed_batch.append(content)
        else:
            print("  Skipping document embedding because it has too many tokens")

        try:
            summary = get_summary(content)
            print("  Generated summary")
            if count_tokens(summary) < 8100:
                embed_batch.append(summary)
            else:
                print("  Skipping summary embedding because it has too many tokens")

        except Exception as e:
            print("  Failed to get summary", e)

        for header in sections:
            section_content = sections[header]

            embeddable_content = "# " + \
                metadata["title"] + "\n## " + metadata["description"] + \
                "\n### " + header + "\n" + section_content
            if count_tokens(embeddable_content) > 8100:
                print("  Skipping " + header +
                      " content embedding because it has too many tokens")
                continue

            embed_batch.append(embeddable_content)

        try:
            embeddings = get_embedding(embed_batch)
            entry["embeddings"] = embeddings
            print("  Generated embeddings")
            docs_list.append(entry)
            json.dump(docs_list, open("build/docs-list.json", "w"))
        except Exception as e:
            print("  Failed to get embedding for " + metadata["title"], e)

    # Handle the API reference
    for key in reference:
        current_file += 1
        print("[" + str(current_file) + "/" +
              str(count_files) + "] Processing " + key)

        embeddable_content = reference[key]

        entry = {
            "type": "api-reference",
            "title": key,
            "content": embeddable_content,
            "embeddings": [],
        }

        if count_tokens(embeddable_content) > 8100:
            print("  Skipping content embedding because it has too many tokens")
            continue

        try:
            embeddings = get_embedding([embeddable_content])
            entry["embeddings"] = embeddings
            print("  Generated embeddings")
            docs_list.append(entry)
            json.dump(docs_list, open("build/docs-list.json", "w"))
        except Exception as e:
            print("  Failed to get embedding", e)

    return docs_list


if __name__ == "__main__":
    if not os.path.exists('build'):
        os.makedirs('build')

    documents = creator_docs.get_documents()
    reference = api_reference.get_reference()

    docs_list = create_docs_list(
        documents=documents, reference=reference)

    json.dump(docs_list, open("build/docs-list.json", "w"))

    write.write_text(f"""# Roblox Documentation Index

Generated on {date.today()} from:
- https://github.com/Roblox/creator-docs @ {creator_docs.get_sha()[:7]}
- https://github.com/MaximumADHD/Roblox-Client-Tracker/tree/roblox/api-docs @ {api_reference.get_sha()[:7]}
- Embedding Model: {config.EMBEDDING_MODEL}, Embedding Dimensions: {config.EMBEDDING_DIMENSIONS}
- Summary Model: {config.SUMMARY_MODEL}

## Embeddings

With those files, {len(documents) + len(reference)} items were found, {len(docs_list)} were used, and {sum([len(item['embeddings']) for item in docs_list])} embeddings were created for them. The embeddings, along with content and metadata, can be found in `docs-list.json`.""", "build/summary.md")

    print("Documentation collection completed")
