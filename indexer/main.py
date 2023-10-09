import os  # for creating the build directory
import openai  # for generating embeddings
import pandas as pd  # for DataFrames to store article sections and embeddings
import tiktoken  # for counting tokens
import json
from datetime import date  # for writing the date to the summary file

import write
import config
import creator_docs
import api_reference

# OpenAI's best embeddings as of Sept 2023
EMBEDDING_MODEL = "text-embedding-ada-002"

openai.api_key = config.OPENAI_API_KEY


def count_tokens(text: str, model: str = EMBEDDING_MODEL) -> int:
    """Return the number of tokens in a string."""
    encoding = tiktoken.encoding_for_model(model)
    return len(encoding.encode(text))


def create_dataframe(documents, reference):
    data = {
        'type': [],
        'title': [],
        'content': [],
        'embedding': [],
    }

    count_files = len(documents) + len(reference)
    current_file = 0

    # Handle the documents
    for filepath in documents:
        document = documents[filepath]

        current_file += 1

        # First, we get the metadata
        metadata = creator_docs.get_document_metadata(
            filepath=filepath, document=document)

        # Then, we process it for ingestion
        content = creator_docs.prepare_document_for_ingest(document=document)

        # Then, we break it into sections using ## headers, so that we get a dict of header content -> section content
        sections = creator_docs.get_document_sections(content=content, metadata=metadata)

        print("[" + str(current_file) + "/" + str(count_files) + "] Generating data for the " +
              str(len(sections)) + " sections in " + metadata["title"])

        # Then we get the embeddings for each section
        embed_batch = []
        for header in sections:
            section_content = sections[header]

            data["type"].append("creator-docs")
            data["title"].append(metadata["title"] + " / " + header)
            data["content"].append(section_content)

            embeddable_content = "# " + \
                metadata["title"] + "\n## " + metadata["description"] + \
                "\n### " + header + "\n" + section_content
            if count_tokens(embeddable_content) > 8100:
                print("  Skipping " + header +
                      " content embedding because it has too many tokens")
                embed_batch.append(
                    "# " + metadata["title"] + "\n## " + metadata["description"] + "\n### " + header)
                continue

            embed_batch.append(embeddable_content)

        # try:
        #     response = openai.Embedding.create(
        #         model=EMBEDDING_MODEL, input=embed_batch)
        #     data["embedding"].extend(
        #         list(map(lambda data: data['embedding'], response['data'])))
        # except:
        #   print("Failed to get embedding for " + header)
        data["embedding"].extend([None] * len(embed_batch))

    # Handle the API reference
    reference_embed_batch = []
    for key in reference:
        # Turn the ref object into a string
        content = json.dumps(reference[key])

        current_file += 1
        print("[" + str(current_file) + "/" + str(count_files) + "] Generating data for " + key)

        data["type"].append("api-reference")
        data["title"].append(key)
        data["content"].append(content)

        embeddable_content = "# " + key + "\n" + content
        if count_tokens(embeddable_content) > 8100:
            print("  Skipping " + key +
                  " content embedding because it has too many tokens")
            reference_embed_batch.append(
                "# " + key + "\n" + (reference[key]['description'] if 'description' in reference[key] else ""))
            continue

        reference_embed_batch.append(embeddable_content)

    # try:
    #     response = openai.Embedding.create(
    #         model=EMBEDDING_MODEL, input=reference_embed_batch)
    #     data["embedding"].extend(
    #         list(map(lambda data: data['embedding'], response['data'])))
    # except:
    #     print("Failed to get embedding for " + key)
    data["embedding"].extend([None] * len(reference_embed_batch))

    # Build and return the DataFrame
    return pd.DataFrame(data)


if __name__ == "__main__":
    if not os.path.exists('build'):
        os.makedirs('build')

    documents = creator_docs.get_documents()
    reference = api_reference.get_reference()

    embeddings_dataframe = create_dataframe(
        documents=documents, reference=reference)

    embeddings_dataframe.to_json(
        "build/docs-embeddings.json", orient="records")

    write.write_text(f"""# Roblox Documentation Index

Generated on {date.today()} from:
- https://github.com/Roblox/creator-docs @ {creator_docs.get_sha()[:7]}
- https://github.com/MaximumADHD/Roblox-Client-Tracker/tree/roblox/api-docs @ {api_reference.get_sha()[:7]}

## Embeddings

With those files, {embeddings_dataframe['embedding'].count()} items were found and embedded. The embeddings, along with content and metadata, can be found in `docs-embeddings.json`.""", "build/summary.md")

    print("Documentation collection completed")
