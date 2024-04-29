import os  # for creating the build directory
from typing import List
from together import Together  # for generating embeddings and summaries
import tiktoken  # for counting tokens
import json  # for exporting results
from datetime import date  # for writing the date to the summary file

import write
import config
import creator_docs
import api_reference

client = Together(api_key=config.TOGETHERAI_API_KEY)




def count_tokens(text: str) -> int:
    """Return the number of tokens in a string."""
    return len(tiktoken.get_encoding('cl100k_base').encode(text))

def get_embeddings(texts: List[str], model: str = config.EMBEDDING_MODEL) -> List[List[float]]:
    """Return the embeddings for a list of strings."""
    outputs = client.embeddings.create(model=model, input=[text.replace("\n", " ") for text in texts])
    return [outputs.data[i].embedding for i in range(len(texts))]


def get_summary(content: str) -> str:
    completion = client.chat.completions.create(
        model=config.SUMMARY_MODEL,
        messages=[
            {
                "role": "system",
                "content": "You are a summary generator. "
                    "Your summary will be used to create vector embeddings for content to improve semantic searches. "
                    "When the user provides content, respond with a summary of the content. "
                    "Do NOT include any text other than the summary. Keep your summary to just a few sentences.",
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
        lower_content = content.lower()

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

        if count_tokens(lower_content) < 8100:
            embed_batch.append(lower_content)
        else:
            print("  Skipping document embedding because it has too many tokens")

        try:
            summary = get_summary(content)
            lower_summary = summary.lower()
            print("  Generated summary")
            if count_tokens(lower_summary) < 8100:
                embed_batch.append(lower_summary)
            else:
                print("  Skipping summary embedding because it has too many tokens")

        except Exception as e:
            print("  Failed to get summary", e)

        for header in sections:
            section_content = sections[header]

            embeddable_content = "# " + \
                metadata["title"] + "\n## " + metadata["description"] + \
                "\n### " + header + "\n" + section_content
            lower_embeddable_content = embeddable_content.lower()
            if count_tokens(lower_embeddable_content) > 8100:
                print("  Skipping " + header +
                      " content embedding because it has too many tokens")
                continue

            embed_batch.append(lower_embeddable_content)

        try:
            embeddings = get_embeddings(embed_batch)
            entry["embeddings"] = embeddings
            print("  Generated embeddings")
            docs_list.append(entry)
        except Exception as e:
            print("  Failed to get embedding for " + metadata["title"], e)

    # Handle the API reference
    for key in reference:
        current_file += 1
        print("[" + str(current_file) + "/" +
              str(count_files) + "] Processing " + key)

        embeddable_content = reference[key]
        lower_embeddable_content = embeddable_content.lower()

        entry = {
            "type": "api-reference",
            "title": key,
            "content": embeddable_content,
            "embeddings": [],
        }

        if count_tokens(lower_embeddable_content) > 8100:
            print("  Skipping content embedding because it has too many tokens")
            continue

        try:
            embeddings = get_embeddings([lower_embeddable_content])
            entry["embeddings"] = embeddings
            print("  Generated embeddings")
            docs_list.append(entry)
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

    json.dump(docs_list, open("build/index.json", "w"))

    write.write_text(f"""# Roblox Documentation Index

Generated on {date.today()} from:
- https://github.com/Roblox/creator-docs @ {creator_docs.get_sha()[:7]}
- https://github.com/MaximumADHD/Roblox-Client-Tracker/tree/roblox/api-docs @ {api_reference.get_sha()[:7]}
- Embedding Model: {config.EMBEDDING_MODEL}, Embedding Dimensions: {config.EMBEDDING_DIMENSIONS}
- Summary Model: {config.SUMMARY_MODEL}
- Index Version: {config.INDEX_VERSION}

## Embeddings

With those files, {len(documents) + len(reference)} items were found, {len(docs_list)} were used, and {sum([len(item['embeddings']) for item in docs_list])} embeddings were created for them. The embeddings, along with content and metadata, can be found in `index.json`.""", "build/summary.md")

    print("Documentation collection completed")
