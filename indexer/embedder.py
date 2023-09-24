import os  # for creating the build directory
import requests # for fetching the docs
import base64 # for decoding the doc file contents
import yaml # for reading the metadata of doc files
import openai  # for generating embeddings
import pandas as pd  # for DataFrames to store article sections and embeddings
import re  # for cutting metadata out of doc headers
import tiktoken  # for counting tokens
from datetime import date # for writing the date to the summary file

import write
import config

try:
	from yaml import CLoader as Loader
except ImportError:
	from yaml import Loader

EMBEDDING_MODEL = "text-embedding-ada-002"  # OpenAI's best embeddings as of Sept 2023

openai.api_key = config.OPENAI_API_KEY

METADATA_PATTERN = re.compile("---(.+?)---", re.DOTALL)
SELFCLOSING_HTML_PATTERN = re.compile(r"<([^/]\w*)[^>]*/>", re.DOTALL)
HTML_PATTERN = re.compile(r"<([^/]\w*)[^>]*>.*?</\1>", re.DOTALL)
EXTRA_NEWLINES_PATTERN = re.compile(r"\n[\n\s]+", re.DOTALL)
INLINE_LINKS_PATTERN = re.compile(r"\[(.*?)\]\(.*?\)", re.DOTALL)
API_LINKING_WITH_NAME_PATTERN = re.compile(r"`[A-Z]\w*?\.[^\n]*?\|(.*?)`", re.DOTALL)
API_LINKING_PATTERN = re.compile(r"`[A-Z]\w*?\.([^\n]*?)`", re.DOTALL)

def count_tokens(text: str, model: str = EMBEDDING_MODEL) -> int:
    """Return the number of tokens in a string."""
    encoding = tiktoken.encoding_for_model(model)
    return len(encoding.encode(text))

def fetch_tree_data():
	data_res = requests.get("https://api.github.com/repos/Roblox/creator-docs/git/trees/main:content?recursive=true", headers=config.GH_REQ_HEADERS)
	data_res.raise_for_status()

	data = data_res.json()
	return data

def is_path_allowed(path):
	for allowed_path in config.ALLOWLISTED_DOCUMENT_PATHS:
		if path.startswith(allowed_path):
			return True

	return False

def get_documentation_filepaths(tree):
	documentation_filepaths = list(map(
		lambda item: "content/" + item["path"],
		filter(lambda item: item["type"] == "blob" and item["path"].endswith(".md") and is_path_allowed(item["path"]), tree)
	))

	return documentation_filepaths

def download_documents(documentation_filepaths):
	documents = {}

	for filepath in documentation_filepaths:
		print("Fetching " + filepath)

		res = requests.get(f"https://api.github.com/repos/Roblox/creator-docs/contents/{filepath}?ref=main", headers=config.GH_REQ_HEADERS)
		res.raise_for_status()

		content_encoded = res.json()["content"]
		content = base64.b64decode(content_encoded.encode("utf-8")).decode("utf-8")

		documents[filepath] = content

	return documents

def get_document_metadata(filepath, document):
	metadata_match = METADATA_PATTERN.match(document)

	metadata = {}
	metadata["path"] = filepath

	if metadata_match == None:
		print("> Failed to get metadata for " + filepath)
		# Use filename as title
		metadata["title"] = os.path.basename(filepath).replace(".md", "")
		metadata["description"] = ""
	else:
		metadata_str = metadata_match.group(1)
		metadata_dict = yaml.load(metadata_str, Loader=Loader)
		metadata["title"] = metadata_dict["title"] or os.path.basename(filepath).replace(".md", "")
		metadata["description"] = metadata_dict["description"] or ""

	return metadata

def prepare_document_for_ingest(document):
	# Remove metadata header (---...---)
	document = METADATA_PATTERN.sub("", document)
	# Remove html elements like <img /> and <video></video>
	document = HTML_PATTERN.sub("", document)
	document = SELFCLOSING_HTML_PATTERN.sub("", document)
	# Remove links but keep the text [text](url)
	document = INLINE_LINKS_PATTERN.sub(r"\1", document)
	# Remove extra newlines
	document = EXTRA_NEWLINES_PATTERN.sub("\n\n", document)
	# Remove Roblox's custom API linking
	document = API_LINKING_WITH_NAME_PATTERN.sub(r"`\1`", document)
	document = API_LINKING_PATTERN.sub(r"`\1`", document)

	return document


def create_documentation_dataframe(documents):
	data = {
		'path': [],
		'title': [],
		'section': [],
		'content': [],
		'embedding': [],
	}

	count_files = len(documents)
	current_file = 0

	for filepath in documents:
		document = documents[filepath]

		current_file += 1

		# First, we get the metadata
		metadata = get_document_metadata(filepath=filepath, document=document)

		# Then, we process it for ingestion
		content = prepare_document_for_ingest(document=document)

		# Then, we break it into sections using ## headers, so that we get a dict of header content -> section content
		sections = {}
		split_content = content.split("\n## ")
		for section in split_content:
			sectionlines = section.split("\n", 1)
			if len(sectionlines) == 0:
				continue
			elif len(sectionlines) == 1:
				# With only one line, we just use it as content and use the title as the header
				sections[metadata["title"]] = sectionlines[0]
				continue
			else:
				# We have multiple lines, so line one is likely the header and the rest is the content
				section_header = sectionlines[0].strip()
				if section_header == "":
					section_header = metadata["title"]
				section_content = "\n".join(sectionlines[1:])
				sections[section_header] = section_content
				continue

		print("[" + str(current_file) + "/" + str(count_files) + "] Generating data for the " + str(len(sections)) + " sections in " + metadata["title"])

		# Then we get the embeddings for each section
		embed_batch = []
		for header in sections:
			section_content = sections[header]

			data["path"].append(metadata["path"])
			data["title"].append(metadata["title"])
			data["section"].append(header)
			data["content"].append(section_content)

			embeddable_content = "# " + metadata["title"] + "\n## " + metadata["description"] + "\n### " + header + "\n" + section_content
			if count_tokens(embeddable_content) > 8100:
				print("  Skipping " + header + "content embedding because it has too many tokens")
				embed_batch.append("# " + metadata["title"] + "\n## " + metadata["description"] + "\n### " + header)
				continue

			embed_batch.append(embeddable_content)

		try:
			response = openai.Embedding.create(model=EMBEDDING_MODEL, input=embed_batch)
			data["embedding"].extend(list(map(lambda data: data['embedding'], response['data'])))
		except:
			print("Failed to get embedding for " + header)
			data["embedding"].extend([None] * len(embed_batch))

	return pd.DataFrame(data)


if __name__ == "__main__":
	if not os.path.exists('build'):
		os.makedirs('build')

	print("Fetching documentation info...")
	data = fetch_tree_data()

	sha = data["sha"]
	tree = data["tree"]
	truncated = data["truncated"]

	write.write_text(sha, "build/docs-source-commit.txt")

	# TODO: Do a recursive scan if truncated
	if truncated:
		print("Cannot handle truncated paths yet")
		exit(1)

	documentation_filepaths = get_documentation_filepaths(tree)
	print(len(documentation_filepaths), "documents found")

	documents = download_documents(documentation_filepaths)
	documentation_dataframe = create_documentation_dataframe(documents=documents)

	documentation_dataframe.to_json("build/docs-embeddings.json", orient="records")
	write.write_json(documentation_filepaths, "build/indexed-files.json")

	write.write_text(f"""# Roblox Documentation Index

Generated on {date.today()} from https://github.com/Roblox/creator-docs @ {sha[:7]}

## Files

{len(documentation_filepaths)} files indexed. The full list of files can be found in `indexed-files.json`.

## Embeddings

With those files, {documentation_dataframe['embedding'].count()} sections were found and embedded. The embeddings, along with content and metadata, can be found in `docs-embeddings.json`.""", "build/summary.md")

	print("Documentation collection completed")
