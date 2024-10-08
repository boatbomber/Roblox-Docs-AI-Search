import asyncio
import concurrent
import concurrent.futures
import json
import os
import re
import sys
from datetime import date
from typing import Any, TypedDict

import api_reference
import creator_docs
import write
from config import (
    EMBEDDING_BATCH_LIMIT,
    EMBEDDING_MODEL,
    EMBEDDING_TOKEN_LIMIT,
    INDEX_VERSION,
    QUESTION_MODEL,
    SUMMARY_MODEL,
    TOGETHERAI_API_KEY,
)
from dotenv import find_dotenv, load_dotenv
from together import Together
from tqdm import tqdm
from transformers import AutoTokenizer

load_dotenv(find_dotenv())

client = Together(api_key=TOGETHERAI_API_KEY)


class IndexEntry(TypedDict, total=False):
    title: str
    type: str
    content: int
    embeddings: list[list[float]]


tokenizer = AutoTokenizer.from_pretrained(EMBEDDING_MODEL)


def count_tokens(text: str) -> int:
    """Return the number of tokens in a string."""
    tokenized_text_result = tokenizer(text)
    return len(tokenized_text_result.get("input_ids", []))


def get_embeddings(texts: list[str], model: str = EMBEDDING_MODEL) -> list[list[float]]:
    """Return the embeddings for a list of strings."""

    if len(texts) == 0:
        print("Embedding inputs are empty")
        return []

    # First, split up any strings that are over the embedding token limit
    processed_texts = []
    for text in texts:
        text = text.replace("\n", " ")
        if count_tokens(text) < EMBEDDING_TOKEN_LIMIT:
            processed_texts.append(text)
        else:
            # Split by spaces, then combine as many as possible until the token limit is reached
            words = text.split(" ")
            chunk = []
            while len(words) > 0:
                next_word = words.pop(0)
                if (
                    count_tokens(" ".join(chunk) + " " + next_word)
                    > EMBEDDING_TOKEN_LIMIT
                ):
                    processed_texts.append(" ".join(chunk))
                    chunk = [next_word]
                else:
                    chunk.append(next_word)

    # Then, split texts into batches of EMBEDDING_BATCH_LIMIT
    batches = [
        processed_texts[i : i + EMBEDDING_BATCH_LIMIT]
        for i in range(0, len(processed_texts), EMBEDDING_BATCH_LIMIT)
    ]

    # Finally, get the embeddings for each batch
    embeddings = []
    for batch in batches:
        try:
            response = client.embeddings.create(input=batch, model=model)
            embeddings.extend([result.embedding for result in response.data])
        except Exception as e:
            print(
                batch,
                "failed to create embeddings",
                e,
            )

    return embeddings


def load_documents() -> dict[str, str]:
    documents = creator_docs.get_documents()
    documents.update(api_reference.get_reference())
    return documents


def get_summary(content: str) -> str:
    print("Getting summary for", content[:100] + ("..." if len(content) > 100 else ""))
    completion = client.chat.completions.create(
        model=SUMMARY_MODEL,
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
    summary = completion.choices[0].message.content
    return summary.strip()


def get_questions(content: str) -> list[str]:
    print(
        "Getting questions for", content[:100] + ("..." if len(content) > 100 else "")
    )
    completion = client.chat.completions.create(
        model=QUESTION_MODEL,
        messages=[
            {
                "role": "system",
                "content": "Your job is to come up with three varied questions that can be answered by the given documentation excerpt. "
                "Your questions will be used to create vector embeddings to improve semantic searches. "
                "For example, a documentation excerpt about animations can answer questions about how to make an NPC dance."
                "When the user provides a documentation excerpt, respond with three relevant questions that can be answered by the excerpt. "
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
    questions = [
        re.sub(
            r"\sin Roblox|\sin Luau?|\sin Roblox Studio", "", question, 0, re.IGNORECASE
        ).strip()
        for question in questions
    ]
    # Strip leading list markers
    questions = [
        re.sub(r"^\d+[\.\)]\s*", "", question).strip() for question in questions
    ]
    questions = [re.sub(r"^[\-\*]\s+", "", question).strip() for question in questions]
    # Remove empty questions
    questions = [question for question in questions if question]
    return questions


def process_document(
    data: tuple[str, str],
) -> IndexEntry:
    key, document = data

    embeddings_batch = []
    metadata = creator_docs.get_document_metadata(filepath=key, document=document)
    file_name = os.path.basename(key).replace(".md", "").replace(".yaml", "")
    content = creator_docs.prepare_document_for_ingest(document=document)
    lower_content = content.lower()

    embeddings_batch.append(lower_content)

    # Then, we break it into sections using ## headers, so that we get a dict of header content -> section content
    sections = creator_docs.get_document_sections(
        content=lower_content, metadata=metadata
    )

    for header in sections:
        section_content = sections[header]

        embeddable_content = (
            "# "
            + metadata.get("title", file_name)
            + "\n## "
            + metadata.get("description", "")
            + "\n### "
            + header
            + "\n"
            + section_content
        )
        embeddings_batch.append(embeddable_content.lower())

    try:
        embeddings_batch.append(get_summary(content).lower())
    except Exception as e:
        print("  Failed to get summary", e)

    try:
        questions = get_questions(content)
        for question in questions:
            embeddings_batch.append(
                "Represent this sentence for searching relevant passages: "
                + question.lower()
            )
    except Exception as e:
        print("  Failed to get questions", e)

    return {
        "title": metadata.get("title", file_name),
        "content": content,
        "embeddings": get_embeddings(embeddings_batch),
    }


def index_documents(documents: dict[str, Any]) -> list[IndexEntry]:
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        results = list(
            tqdm(
                executor.map(
                    process_document,
                    documents.items(),
                ),
                desc="Processing documents",
                total=len(documents),
                file=sys.stdout,
            )
        )

    return results


def output_results(index: list[IndexEntry]):
    json.dump(index, open("build/index.json", "w"))

    embedding_dimensions = len(index[0]["embeddings"][0])

    write.write_text(
        f"""# Roblox Documentation Index

Generated on {date.today()} from:
- https://github.com/Roblox/creator-docs @ {creator_docs.get_sha()[:7]}
- https://github.com/MaximumADHD/Roblox-Client-Tracker/tree/roblox/api-docs @ {api_reference.get_sha()[:7]}
- Embedding Model: {EMBEDDING_MODEL} ({embedding_dimensions} dimensions)
- Summary Model: {SUMMARY_MODEL}
- Question Model: {QUESTION_MODEL}
- Index Version: {INDEX_VERSION}

## Embeddings

With those files, {len(index)} index entries were created with {sum([len(entry['embeddings']) for entry in index])} embeddings total. The embeddings, along with content and metadata, can be found in `index.json`.""",
        "build/summary.md",
    )


async def main():
    if not os.path.exists("build"):
        os.makedirs("build")

    # Load
    documents = load_documents()

    # Process
    index = index_documents(documents)

    # Save
    output_results(index)


if __name__ == "__main__":
    asyncio.run(main())
