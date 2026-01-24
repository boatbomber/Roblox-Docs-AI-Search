import argparse
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
from cache import generate_cache_key, get_cache_stats, get_cached, set_cached
from config import (
    EMBEDDING_BATCH_LIMIT,
    EMBEDDING_MODEL,
    EMBEDDING_TOKEN_LIMIT,
    INDEX_VERSION,
    OPENROUTER_API_KEY,
    QUESTION_MODEL,
    SUMMARY_MODEL,
)
from count_tokens import count_tokens
from dotenv import find_dotenv, load_dotenv
from openai import OpenAI
from tqdm import tqdm

load_dotenv(find_dotenv())

client = OpenAI(api_key=OPENROUTER_API_KEY, base_url="https://openrouter.ai/api/v1")


class IndexEntry(TypedDict, total=False):
    title: str
    type: str
    content: int
    embeddings: list[list[float]]


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
            current_chunk_tokens = 0

            for next_word in words:
                # Count tokens for the next word (with space prefix if not first word)
                if chunk:
                    word_with_space = " " + next_word
                    next_word_tokens = count_tokens(word_with_space)
                else:
                    next_word_tokens = count_tokens(next_word)

                # Check if adding this word would exceed the limit
                if (
                    current_chunk_tokens + next_word_tokens > EMBEDDING_TOKEN_LIMIT
                    and chunk
                ):
                    # Finalize current chunk and start a new one
                    processed_texts.append(" ".join(chunk))
                    chunk = [next_word]
                    current_chunk_tokens = count_tokens(next_word)
                else:
                    # Add word to current chunk
                    chunk.append(next_word)
                    current_chunk_tokens += next_word_tokens

            # Don't forget the last chunk
            if chunk:
                processed_texts.append(" ".join(chunk))

    # Check cache for each processed text
    embeddings = [None] * len(processed_texts)
    texts_to_fetch = []  # (index, text) pairs for cache misses

    for i, text in enumerate(processed_texts):
        cache_key = generate_cache_key(text, model)
        cached = get_cached("embeddings", cache_key)
        if cached is not None:
            embeddings[i] = cached
        else:
            texts_to_fetch.append((i, text))

    # If all cached, return early
    if not texts_to_fetch:
        return embeddings

    # Split cache misses into batches
    batches = []
    current_batch = []
    for idx, text in texts_to_fetch:
        current_batch.append((idx, text))
        if len(current_batch) >= EMBEDDING_BATCH_LIMIT:
            batches.append(current_batch)
            current_batch = []
    if current_batch:
        batches.append(current_batch)

    # Fetch embeddings for cache misses
    for batch in batches:
        batch_texts = [text for _, text in batch]
        try:
            response = client.embeddings.create(input=batch_texts, model=model)
            for (idx, text), result in zip(batch, response.data):
                embedding = result.embedding
                embeddings[idx] = embedding
                # Cache the new embedding
                cache_key = generate_cache_key(text, model)
                set_cached("embeddings", cache_key, embedding, model)
        except Exception as e:
            print(
                batch_texts,
                "failed to create embeddings",
                e,
            )

    # Filter out any None values (failed embeddings)
    return [e for e in embeddings if e is not None]


def load_documents() -> dict[str, str]:
    documents = creator_docs.get_documents()
    documents.update(api_reference.get_reference())
    return documents


def get_summary(content: str) -> str:
    print("Getting summary for", content[:100] + ("..." if len(content) > 100 else ""))
    # Check cache first
    cache_key = generate_cache_key(content, SUMMARY_MODEL)
    cached = get_cached("summaries", cache_key)
    if cached is not None:
        return cached

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

    result = completion.choices[0].message.content.strip()

    # Cache the result
    set_cached("summaries", cache_key, result, SUMMARY_MODEL)

    return result


def get_questions(content: str) -> list[str]:
    print(
        "Getting questions for", content[:100] + ("..." if len(content) > 100 else "")
    )
    # Check cache first
    cache_key = generate_cache_key(content, SUMMARY_MODEL)
    cached = get_cached("questions", cache_key)
    if cached is not None:
        return cached

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

    # Cache the result
    set_cached("questions", cache_key, questions, SUMMARY_MODEL)

    return questions


def process_document(
    data: tuple[str, str, bool],
) -> IndexEntry:
    key, document, enable_questions = data

    embeddings_batch = []
    metadata = creator_docs.get_document_metadata(filepath=key, document=document)
    file_name = os.path.basename(key).replace(".md", "").replace(".yaml", "")
    content = creator_docs.prepare_document_for_ingest(document=document)

    embeddings_batch.append(content)

    # Then, we break it into sections using ## headers, so that we get a dict of header content -> section content
    sections = creator_docs.get_document_sections(content=content, metadata=metadata)

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
        embeddings_batch.append(embeddable_content)

    try:
        embeddings_batch.append(get_summary(content))
    except Exception as e:
        print("  Failed to get summary", e)

    if enable_questions:
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


def index_documents(
    documents: dict[str, Any], enable_questions: bool = False
) -> list[IndexEntry]:
    # Add enable_questions flag to each document tuple
    document_data = [(key, doc, enable_questions) for key, doc in documents.items()]

    with concurrent.futures.ThreadPoolExecutor(max_workers=24) as executor:
        results = list(
            tqdm(
                executor.map(
                    process_document,
                    document_data,
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
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Index Roblox documentation")
    parser.add_argument(
        "--enable-questions",
        action="store_true",
        help="Enable question generation for embeddings (increases cost and index size)",
    )
    args = parser.parse_args()

    if not os.path.exists("build"):
        os.makedirs("build")

    # Log initial cache stats
    initial_stats = get_cache_stats()
    if initial_stats:
        print(f"Cache loaded: {initial_stats}")
    else:
        print("Starting with empty cache")

    if args.enable_questions:
        print("Question generation is ENABLED")
    else:
        print("Question generation is DISABLED (use --enable-questions to enable)")

    # Load
    documents = load_documents()

    # Process
    index = index_documents(documents, enable_questions=args.enable_questions)

    # Log final cache stats
    final_stats = get_cache_stats()
    print(f"Cache stats after processing: {final_stats}")

    # Save
    output_results(index)


if __name__ == "__main__":
    asyncio.run(main())
