import requests  # for fetching the docs
import re  # for cutting metadata out of doc headers
from datetime import date  # for writing the date to the summary file

import write
import config


def fetch_tree_data():
    data_res = requests.get(
        "https://api.github.com/repos/MaximumADHD/Roblox-Client-Tracker/git/trees/roblox?recursive=true", headers=config.GH_REQ_HEADERS)
    data_res.raise_for_status()

    data = data_res.json()
    return data


def is_api_identifier(x):
    return re.match(r"^@\w+/", x)


def replace_xml_tags(item):
    if isinstance(item, list):
        for i in range(len(item)):
            if isinstance(item[i], str):
                bolded = re.sub(r"<strong>(.*?)</strong>", r"**\1**", item[i])
                italicized = re.sub(r"<em>(.*?)</em>", r"*\1*", bolded)
                monospaced = re.sub(r"<code>(.*?)</code>", r"`\1`", italicized)
                item[i] = monospaced
            elif isinstance(item[i], list):
                replace_xml_tags(item[i])
            elif isinstance(item[i], dict):
                replace_xml_tags(item[i])

    elif isinstance(item, dict):
        for prop in item:
            if isinstance(item[prop], str):
                bolded = re.sub(r"<strong>(.*?)</strong>",
                                r"**\1**", item[prop])
                italicized = re.sub(r"<em>(.*?)</em>", r"*\1*", bolded)
                monospaced = re.sub(r"<code>(.*?)</code>", r"`\1`", italicized)
                item[prop] = monospaced
            elif isinstance(item[prop], list):
                replace_xml_tags(item[prop])
            elif isinstance(item[prop], dict):
                replace_xml_tags(item[prop])


def replace_api_identifiers(content, used_identifiers, object):
    if isinstance(object, list):
        for i in range(len(object)):
            item = object[i]
            if isinstance(item, str) and is_api_identifier(item):
                used_identifiers.append(item)
                object[i] = content[item]
            else:
                replace_api_identifiers(content, used_identifiers, item)

    elif isinstance(object, dict):
        for prop in object:
            if isinstance(object[prop], str) and is_api_identifier(object[prop]):
                used_identifiers.append(object[prop])
                object[prop] = content[object[prop]]
            else:
                replace_api_identifiers(
                    content, used_identifiers, object[prop])


def get_reference():
    res = requests.get(
        "https://raw.githubusercontent.com/MaximumADHD/Roblox-Client-Tracker/roblox/api-docs/mini/en-us.json"
    )
    res.raise_for_status()

    api_reference = {}
    used_identifiers = []

    content = res.json()

    # Replace xml tags with markdown
    replace_xml_tags(content)

    # Remove links and empty properties
    for key in content:
        content[key].pop('learn_more_link', None)

        new_obj = {}
        for prop in content[key]:
            item = content[key][prop]
            if isinstance(item, str) and item == "":
                continue
            elif isinstance(item, list) and len(item) == 0:
                continue
            elif isinstance(item, dict) and len(item) == 0:
                continue
            new_obj[prop] = content[key][prop]
        content[key] = new_obj

    # Replace identifiers with their object
    replace_api_identifiers(content, used_identifiers, content)

    # Build the API reference
    for key in content:
        if key in used_identifiers:
            continue
        api_reference[key] = content[key]

    return api_reference


def get_sha():
    data = fetch_tree_data()
    write.write_text(data["sha"], "build/api-source-commit.txt")
    return data["sha"]
