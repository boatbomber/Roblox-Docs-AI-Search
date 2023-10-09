import requests  # for fetching the docs
import re  # for cutting metadata out of doc headers
from json import dumps as json_dumps # For debug printing

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


def replace_api_identifiers(content, used_identifiers, object, should_mark_used=True):
    if isinstance(object, list):
        for key in range(len(object)):
            item = object[key]
            if isinstance(item, str) and is_api_identifier(item):
                if should_mark_used:
                    used_identifiers.append(item)
                ref_obj = content[item]
                if 'documentation' in ref_obj and len(ref_obj) == 1:
                    # If the ref object only has a documentation, replace the identifier with the documentation
                    object[key] = ref_obj['documentation']
                else:
                    object[key] = ref_obj
            else:
                replace_api_identifiers(content, used_identifiers, item)

    elif isinstance(object, dict):
        for key in object:
            item = object[key]
            if isinstance(item, str) and is_api_identifier(item):
                if should_mark_used:
                    used_identifiers.append(item)
                ref_obj = content[item]
                if 'documentation' in ref_obj and len(ref_obj) == 1:
                    # If the ref object only has a documentation, replace the identifier with the documentation
                    object[key] = ref_obj['documentation']
                else:
                    object[key] = ref_obj
            else:
                replace_api_identifiers(content, used_identifiers, item, key != "keys")


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

    # Remove links, empty properties, and unhelpful properties
    for key in content:
        content[key].pop('learn_more_link', None)

        # Remove keys when they don't link to anything helpful
        if 'keys' in content[key]:
            # Check if keys matches
            keys = content[key]['keys']
            if len(keys) == 3 and 'Name' in keys and 'Value' in keys and 'EnumType' in keys:
                content[key].pop('keys', None)

        # Overloads objects are just links to other objects
        if 'overloads' in content[key]:
            content[key].pop('overloads', None)

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

        if len(new_obj) == 0:
            continue

        content[key] = new_obj

    # Replace identifiers with their object
    replace_api_identifiers(content, used_identifiers, content)

    # Build the API reference
    for key in content:
        if key in used_identifiers:
            continue
        api_reference[key] = content[key]

    # print(json_dumps(api_reference, indent=2))

    return api_reference


def get_sha():
    data = fetch_tree_data()
    write.write_text(data["sha"], "build/api-source-commit.txt")
    return data["sha"]
