import os  # for managing paths
import requests  # for fetching the docs
import zipfile  # for extracting the docs
import io  # for reading the zip file
import yaml  # for reading the metadata of doc files
import re  # for cutting metadata out of doc headers

import write
import config

try:
    from yaml import CLoader as Loader
except ImportError:
    from yaml import Loader


METADATA_PATTERN = re.compile("---(.+?)---", re.DOTALL)
SELFCLOSING_HTML_PATTERN = re.compile(r"<([^/]\w*)[^>]*/>", re.DOTALL)
HTML_PATTERN = re.compile(r"<([^/]\w*)[^>]*>.*?</\1>", re.DOTALL)
EXTRA_NEWLINES_PATTERN = re.compile(r"\n[\n\s]+", re.DOTALL)
INLINE_LINKS_PATTERN = re.compile(r"\[(.*?)\]\(.*?\)", re.DOTALL)
API_LINKING_WITH_NAME_PATTERN = re.compile(r"`[A-Z]\w*?\.[^\n]*?\|(.*?)`", re.DOTALL)
API_LINKING_PATTERN = re.compile(r"`[A-Z]\w*?\.([^\n]*?)`", re.DOTALL)


def fetch_tree_data():
    data_res = requests.get(
        "https://api.github.com/repos/Roblox/creator-docs/git/trees/main:content?recursive=true",
        headers=config.GH_REQ_HEADERS,
    )
    data_res.raise_for_status()

    data = data_res.json()
    return data


def is_path_allowed(path):
    # Validate file extension
    if not path.endswith(tuple(config.ALLOWLISTED_DOCUMENT_FILETYPES)):
        return False

    # Validate file path
    if not path.startswith(tuple(config.ALLOWLISTED_DOCUMENT_PATHS)):
        return False

    return True


def get_document_metadata(filepath, document):
    metadata_match = METADATA_PATTERN.match(document)

    metadata = {}
    metadata["path"] = filepath

    file_name = os.path.basename(filepath).replace(".md", "")

    if metadata_match == None:
        # Use filename as title
        metadata["title"] = file_name
        metadata["description"] = ""
    else:
        metadata_str = metadata_match.group(1)
        metadata_dict = yaml.load(metadata_str, Loader=Loader)
        metadata["title"] = metadata_dict.get("title", file_name)
        metadata["description"] = metadata_dict.get("description", "")

    if metadata["title"] == "" or metadata["title"] is None:
        metadata["title"] = file_name
    if metadata["description"] is None:
        metadata["description"] = ""

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


def get_document_sections(content, metadata):
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
    return sections


def get_documents():
    data_res = requests.get(
        "https://github.com/Roblox/creator-docs/archive/refs/heads/main.zip",
        headers=config.GH_REQ_HEADERS,
    )
    data_res.raise_for_status()
    zipped = zipfile.ZipFile(io.BytesIO(data_res.content))

    documents = {}
    documentation_filepaths = [
        path for path in zipped.namelist() if is_path_allowed(path)
    ]

    current_file = 0

    for filepath in documentation_filepaths:
        current_file += 1
        documents[filepath] = zipped.read(filepath).decode("utf-8")

    zipped.close()

    print(f"Found {len(documents)} documents")
    return documents


def get_sha():
    data = fetch_tree_data()
    write.write_text(data["sha"], "build/docs-source-commit.txt")
    return data["sha"]
