import os  # for creating the build directory
from typing import List
from together import Together  # for generating embeddings and summaries
import tiktoken  # for counting tokens
import json  # for exporting results
from datetime import date  # for writing the date to the summary file
import re

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
    # First, split up any strings that are over the embedding token limit
    for i, text in enumerate(texts):
        if count_tokens(text) > config.EMBEDDING_TOKEN_LIMIT:
            texts.pop(i) # Remove the text that is too large
            chunks = [text[i:i + config.EMBEDDING_TOKEN_LIMIT] for i in range(0, len(text), config.EMBEDDING_TOKEN_LIMIT)]
            # Insert the chunks into texts, without overwriting any other texts
            for chunk in chunks:
                texts.insert(i, chunk)

    # Then, split texts into batches
    batches = [texts[i:i + config.EMBEDDING_BATCH_LIMIT] for i in range(0, len(texts), config.EMBEDDING_BATCH_LIMIT)]
    # Finally, get the embeddings for each batch
    outputs = [client.embeddings.create(model=model, input=[text.replace("\n", " ") for text in batch]) for batch in batches]
    # Join them together for the final output
    return [output.data[i].embedding for output in outputs for i in range(len(output.data))]

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

def get_questions(content: str) -> List[str]:
    completion = client.chat.completions.create(
        model=config.SUMMARY_MODEL,
        messages=[
            {
                "role": "system",
                "content": "Your job is to come up with questions that can be answered by the given documentation excerpt. "
                    "Your questions will be used to create vector embeddings to improve semantic searches. "
                    "For example, a documentation excerpt about animations can answer questions about how to make an NPC dance."
                    "When the user provides a documentation excerpt, respond with several relevant questions that can be answered by the excerpt. "
                    "Do NOT include any text other than the questions. Put each question on a new line.",
            },
            {
                "role": "user",
                "content": content,
            },
        ],
    )
    questions = completion.choices[0].message.content.splitlines()
    # Strip "in Roblox" and "in Luau" and "in Roblox Studio" from the question text
    return [re.sub(r"\sin Roblox|\sin Luau|\sin Roblox Studio", "", question, 0, re.IGNORECASE) for question in questions]



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
            "embedding_texts": [],
        }


        entry["embedding_texts"].append(lower_content)

        for header in sections:
            section_content = sections[header]

            embeddable_content = "# " + \
                metadata["title"] + "\n## " + metadata["description"] + \
                "\n### " + header + "\n" + section_content
            lower_embeddable_content = embeddable_content.lower()
            entry["embedding_texts"].append(lower_embeddable_content)

        try:
            summary = get_summary(content)
            lower_summary = summary.lower()
            print("  Generated summary")
            entry["embedding_texts"].append(lower_summary)
        except Exception as e:
            print("  Failed to get summary", e)

        try:
            questions = get_questions(content)
            print("  Generated questions")
            for question in questions:
                lower_question = question.lower()
                entry["embedding_texts"].append(lower_question)
        except Exception as e:
            print("  Failed to get questions", e)

        docs_list.append(entry)

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
            "embedding_texts": [],
        }

        entry["embedding_texts"].append(lower_embeddable_content)

        try:
            summary = get_summary(embeddable_content)
            lower_summary = summary.lower()
            print("  Generated summary")
            entry["embedding_texts"].append(lower_summary)
        except Exception as e:
            print("  Failed to get summary", e)

        try:
            questions = get_questions(embeddable_content)
            print("  Generated questions")
            for question in questions:
                lower_question = question.lower()
                entry["embedding_texts"].append(lower_question)
        except Exception as e:
            print("  Failed to get questions", e)

        docs_list.append(entry)

    return docs_list


if __name__ == "__main__":
    if not os.path.exists('build'):
        os.makedirs('build')

    documents = creator_docs.get_documents()
    reference = api_reference.get_reference()

    docs_list = create_docs_list(
        documents=documents, reference=reference)

    print(f"Created {len(docs_list)} data entries, generating embeddings now...")

    for i, entry in enumerate(docs_list):
        print(f"  Embedding {i}/{len(docs_list)}: {entry['title']} ({len(entry["embedding_texts"])} chunks)")
        entry["embeddings"] = get_embeddings(entry["embedding_texts"])
        del entry["embedding_texts"]


    json.dump(docs_list, open("build/index.json", "w"))

    write.write_text(f"""# Roblox Documentation Index

Generated on {date.today()} from:
- https://github.com/Roblox/creator-docs @ {creator_docs.get_sha()[:7]}
- https://github.com/MaximumADHD/Roblox-Client-Tracker/tree/roblox/api-docs @ {api_reference.get_sha()[:7]}
- Embedding Model: {config.EMBEDDING_MODEL}
- Summary & Questions Model: {config.SUMMARY_MODEL}
- Index Version: {config.INDEX_VERSION}

## Embeddings

With those files, {len(documents) + len(reference)} docs were found, {len(docs_list)} were used, and {sum([len(item['embeddings']) for item in docs_list])} embeddings were created for them. The embeddings, along with content and metadata, can be found in `index.json`.""", "build/summary.md")

    print("Documentation collection completed")
