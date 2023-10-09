import requests  # for fetching the docs
import tiktoken  # for counting tokens
import re  # for cutting metadata out of doc headers
from json import dumps as json_dumps  # For debug printing

import write
import config

# OpenAI's best embeddings as of Sept 2023
EMBEDDING_MODEL = "text-embedding-ada-002"
def count_tokens(text: str, model: str = EMBEDDING_MODEL) -> int:
    """Return the number of tokens in a string."""
    encoding = tiktoken.encoding_for_model(model)
    return len(encoding.encode(text))

def fetch_tree_data():
    data_res = requests.get(
        "https://api.github.com/repos/MaximumADHD/Roblox-Client-Tracker/git/trees/roblox?recursive=true", headers=config.GH_REQ_HEADERS)
    data_res.raise_for_status()

    data = data_res.json()
    return data

SELFCLOSING_HTML_PATTERN = re.compile(r"<([^/]\w*)[^>]*/>", re.DOTALL)
HTML_PATTERN = re.compile(r"<([^/]\w*)[^>]*>.*?</\1>", re.DOTALL)
def prepare_document_for_ingest(document):
    # Replace escaped characters with their actual characters such as &mdash;
    document = document.replace("&mdash;", "—")
    document = document.replace("&ndash;", "–")
    document = document.replace("&nbsp;", " ")
    document = document.replace("&quot;", "\"")
    document = document.replace("&apos;", "'")
    document = document.replace("&lt;", "<")
    document = document.replace("&gt;", ">")
    document = document.replace("&amp;", "&")
    # Replace <li></li> with - and <ul></ul> with \n
    document = document.replace("<li>", "- ")
    document = document.replace("</li>", "\n")
    document = document.replace("<ul>", "\n")
    document = document.replace("</ul>", "\n")
    # Remove html elements like <img /> and <video></video>
    document = HTML_PATTERN.sub("", document)
    document = SELFCLOSING_HTML_PATTERN.sub("", document)

    return document


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


def replace_api_identifiers(content, object):
    if isinstance(object, list):
        for key in range(len(object)):
            item = object[key]
            if isinstance(item, str) and is_api_identifier(item):
                ref_obj = content[item]
                if 'documentation' in ref_obj and len(ref_obj) == 1:
                    # If the ref object only has a documentation, replace the identifier with the documentation
                    object[key] = ref_obj['documentation']
                else:
                    object[key] = ref_obj
            else:
                replace_api_identifiers(content, item)

    elif isinstance(object, dict):
        for key in object:
            item = object[key]
            if isinstance(item, str) and is_api_identifier(item):
                ref_obj = content[item]
                if 'documentation' in ref_obj and len(ref_obj) == 1:
                    # If the ref object only has a documentation, replace the identifier with the documentation
                    object[key] = ref_obj['documentation']
                else:
                    object[key] = ref_obj
            else:
                replace_api_identifiers(
                    content, item)

def get_api_dump():
    res = requests.get(
        "https://raw.githubusercontent.com/MaximumADHD/Roblox-Client-Tracker/roblox/API-Dump.json"
    )
    res.raise_for_status()
    dump = res.json()
    return dump

def get_api_docstrings():
    res = requests.get(
        "https://raw.githubusercontent.com/MaximumADHD/Roblox-Client-Tracker/roblox/api-docs/mini/en-us.json"
    )
    res.raise_for_status()

    api_docstrings = {}
    used_identifiers = []

    content = res.json()

    # Replace xml tags with markdown
    replace_xml_tags(content)

    # Replace identifiers with their object
    replace_api_identifiers(content, content)

    # Build the API reference
    for key in content:
        if len(content[key]) == 0:
            continue
        if re.match(r"\.Connect$", key) or re.match(r"\.Wait$", key):
            continue
        api_docstrings[key] = content[key]

    return api_docstrings

def createEnumReference(enumObj, api_docstrings):
    enumKey = '@roblox/enum/' + enumObj["Name"]
    if not enumKey in api_docstrings:
        # print("Couldn't find any docsstring for Enum." + enumObj["Name"])
        return ""

    api_docstring = api_docstrings[enumKey]

    desc = api_docstring["documentation"] or ""

    code_sample = ""
    if 'code_sample' in api_docstring and api_docstring['code_sample'] != "":
        code_sample = f"\n```Lua\n{api_docstring['code_sample']}\n```"

    itemDescs = []
    if 'keys' in api_docstring and len(api_docstring['keys']) > 0:
        for itemName in api_docstring['keys']:
            itemDocstring = api_docstring['keys'][itemName]
            itemDesc = itemDocstring['documentation'] or ""
            itemCodeSample = itemDocstring['code_sample'] or ""
            if itemCodeSample != "":
                itemDesc += f"\n```Lua\n{itemCodeSample}\n```"
            if itemDesc != "":
                itemDescs.append(f"- {itemName}: {itemDesc}")
            else:
                itemDescs.append(f"- {itemName}")
    itemDescs = "\n".join(itemDescs)

    referenceDoc = prepare_document_for_ingest(f"""# {enumObj["Name"]}
{desc}{code_sample}

## Items
{itemDescs}
""")
    # write.write_text(referenceDoc, f"build/Enum_{enumObj['Name']}.md")
    return referenceDoc

def createClassReference(classObj, api_docstrings):
    classKey = "@roblox/globaltype/" + classObj["Name"]
    if not classKey in api_docstrings:
        # print("Couldn't find any docsstring for " + classObj["Name"])
        return ""

    api_docstring = api_docstrings[classKey]

    desc = api_docstring["documentation"] or ""

    code_sample = ""
    if 'code_sample' in api_docstring and api_docstring['code_sample'] != "":
        code_sample = f"\n```Lua\n{api_docstring['code_sample']}\n```"

    propertyDescs = []
    methodDescs = []
    eventDescs = []
    callbackDescs = []

    for member in classObj["Members"]:
        if "Tags" in member and "Deprecated" in member['Tags']:
            continue
        memberKey = classKey + "." + member["Name"]
        # print(memberKey)

        if member["MemberType"] == "Property":
            memberBaseDesc = f"### {member['Name']} ({member['ValueType']['Name']})"
            if not memberKey in api_docstrings:
                # print("Couldn't find any docsstring for property " + classObj['Name'] + "." + member["Name"])
                propertyDescs.append(memberBaseDesc)
                continue
            memberDocstring = api_docstrings[memberKey]
            memberDesc = memberDocstring['documentation'] or ""
            memberCodeSample = memberDocstring['code_sample'] or ""
            if memberCodeSample != "":
                memberDesc += f"\n```Lua\n{memberCodeSample}\n```"
            if memberDesc != "":
                propertyDescs.append(memberBaseDesc + "\n- " + memberDesc)
            else:
                propertyDescs.append(memberBaseDesc)

        elif member["MemberType"] == "Function":
            if not memberKey in api_docstrings:
                # print("Couldn't find any docsstring for method " + classObj['Name'] + "." + member["Name"])
                # Use fallback info from dump
                memberParamsDesc = []
                for param in member["Parameters"]:
                    memberParamsDesc.append(f"- {param['Name']}: {param['Type']['Name']}")
                memberParamsDesc = "\n".join(memberParamsDesc)

                memberReturnsDesc = f"- {member['ReturnType']['Name']}"

                memberDesc = f"### {member['Name']} ({member['ReturnType']['Name']})"
                if memberParamsDesc != "":
                    memberDesc += f"\n\n**Parameters**\n{memberParamsDesc}"
                if memberReturnsDesc != "":
                    memberDesc += f"\n\n**Returns**\n{memberReturnsDesc}"
                memberDesc += "\n"

                methodDescs.append(memberDesc)
                continue

            memberDocstring = api_docstrings[memberKey]
            memberParamsDesc = []
            for i in range(len(memberDocstring['params'])):
                param = memberDocstring['params'][i]
                if param['name'] == "self":
                    continue
                dumpParam = member["Parameters"][i-1]

                memberParamsDesc.append(f"- {param['name']}: {dumpParam['Type']['Name']}\n{param['documentation']}")
            memberParamsDesc = "\n".join(memberParamsDesc)

            memberReturnsDesc = []
            if len(memberDocstring['returns']) == 0:
                memberReturnsDesc.append(f"- {member['ReturnType']['Name']}")
            else:
                for ret in memberDocstring['returns']:
                    memberReturnsDesc.append(f"- {member['ReturnType']['Name']}: {ret['documentation'] if isinstance(ret, dict) else ret}")
            memberReturnsDesc = "\n".join(memberReturnsDesc)

            memberSummary = memberDocstring['documentation'] or ""
            memberCodeSample = memberDocstring['code_sample'] or ""
            if memberCodeSample != "":
                memberCodeSample = f"\n```Lua\n{memberCodeSample}\n```"

            memberDesc = f"### {member['Name']} ({member['ReturnType']['Name']})"
            if memberSummary != "":
                memberDesc += f"\n{memberSummary}"
            if memberParamsDesc != "":
                memberDesc += f"\n\n**Parameters**\n{memberParamsDesc}"
            if memberReturnsDesc != "":
                memberDesc += f"\n\n**Returns**\n{memberReturnsDesc}"
            if memberCodeSample != "":
                memberDesc += f"\n\n**Example**\n{memberCodeSample}"
            memberDesc += "\n"

            methodDescs.append(memberDesc)

        elif member["MemberType"] == "Callback":
            if not memberKey in api_docstrings:
                # print("Couldn't find any docsstring for method " + classObj['Name'] + "." + member["Name"])
                # Use fallback info from dump
                memberParamsDesc = []
                for param in member["Parameters"]:
                    memberParamsDesc.append(f"- {param['Name']}: {param['Type']['Name']}")
                memberParamsDesc = "\n".join(memberParamsDesc)

                memberReturnsDesc = f"- {member['ReturnType']['Name']}"

                memberDesc = f"### {member['Name']} ({member['ReturnType']['Name']})"
                if memberParamsDesc != "":
                    memberDesc += f"\n\n**Parameters**\n{memberParamsDesc}"
                if memberReturnsDesc != "":
                    memberDesc += f"\n\n**Returns**\n{memberReturnsDesc}"
                memberDesc += "\n"

                callbackDescs.append(memberDesc)
                continue

            memberDocstring = api_docstrings[memberKey]
            memberParamsDesc = []
            for i in range(len(memberDocstring['params'])):
                param = memberDocstring['params'][i]
                dumpParam = member["Parameters"][i]

                memberParamsDesc.append(f"- {param['name']}: {dumpParam['Type']['Name']}\n{param['documentation']}")
            memberParamsDesc = "\n".join(memberParamsDesc)

            memberReturnsDesc = []
            if len(memberDocstring['returns']) == 0:
                memberReturnsDesc.append(f"- {member['ReturnType']['Name']}")
            else:
                for ret in memberDocstring['returns']:
                    memberReturnsDesc.append(f"- {member['ReturnType']['Name']}: {ret['documentation'] if isinstance(ret, dict) else ret}")
            memberReturnsDesc = "\n".join(memberReturnsDesc)

            memberSummary = memberDocstring['documentation'] or ""
            memberCodeSample = memberDocstring['code_sample'] or ""
            if memberCodeSample != "":
                memberCodeSample = f"\n```Lua\n{memberCodeSample}\n```"

            memberDesc = f"### {member['Name']} ({member['ReturnType']['Name']})"
            if memberSummary != "":
                memberDesc += f"\n{memberSummary}"
            if memberParamsDesc != "":
                memberDesc += f"\n\n**Parameters**\n{memberParamsDesc}"
            if memberReturnsDesc != "":
                memberDesc += f"\n\n**Returns**\n{memberReturnsDesc}"
            if memberCodeSample != "":
                memberDesc += f"\n\n**Example**\n{memberCodeSample}"
            memberDesc += "\n"

            callbackDescs.append(memberDesc)

        elif member["MemberType"] == "Event":
            if not memberKey in api_docstrings:
                # print("Couldn't find any docsstring for event " + classObj['Name'] + "." + member["Name"])
                # Use fallback info from dump
                memberParamsDesc = []
                for param in member["Parameters"]:
                    memberParamsDesc.append(f"- {param['Name']}: {param['Type']['Name']}")
                memberParamsDesc = "\n".join(memberParamsDesc)

                memberDesc = f"### {member['Name']}"
                if memberParamsDesc != "":
                    memberDesc += f"\n\n**Parameters**\n{memberParamsDesc}"
                memberDesc += "\n"

                eventDescs.append(memberDesc)
                continue

            memberDocstring = api_docstrings[memberKey]
            memberParamsDesc = []
            for param in member["Parameters"]:
                memberParamsDesc.append(f"- {param['Name']}: {param['Type']['Name']}")
            memberParamsDesc = "\n".join(memberParamsDesc)

            memberSummary = memberDocstring['documentation'] or ""
            memberCodeSample = memberDocstring['code_sample'] or ""
            if memberCodeSample != "":
                memberCodeSample = f"\n```Lua\n{memberCodeSample}\n```"

            memberDesc = f"### {member['Name']}"
            if memberSummary != "":
                memberDesc += f"\n{memberSummary}"
            if memberParamsDesc != "":
                memberDesc += f"\n\n**Parameters**\n{memberParamsDesc}"
            if memberCodeSample != "":
                memberDesc += f"\n\n**Example**\n{memberCodeSample}"
            memberDesc += "\n"

            eventDescs.append(memberDesc)
        else:
            print("Unhandled member type: " + classObj['Name'] + '.' + member['Name'] + '.' + member["MemberType"])

    propertyDescs = "\n\n".join(propertyDescs)
    methodDescs = "\n\n".join(methodDescs)
    eventDescs = "\n\n".join(eventDescs)
    callableDescs = "\n\n".join(callbackDescs)

    if desc == '' and code_sample == '' and propertyDescs == '' and methodDescs == '' and eventDescs == '' and callableDescs == '':
        return ""

    referenceDoc = f"# {classObj['Name']}\n{desc}{code_sample}"
    if propertyDescs != "":
        referenceDoc += f"\n\n## Properties\n\n{propertyDescs}"
    if methodDescs != "":
        referenceDoc += f"\n\n## Methods\n\n{methodDescs}"
    if eventDescs != "":
        referenceDoc += f"\n\n## Events\n\n{eventDescs}"
    if callableDescs != "":
        referenceDoc += f"\n\n## Callbacks\n\n{callableDescs}"
    referenceDoc += "\n"

    referenceDoc = prepare_document_for_ingest(referenceDoc)
    tokens = count_tokens(referenceDoc)
    if tokens > 8100:
        print("Skipping " + classObj['Name'] + " because it has too many tokens (" + str(tokens) + ")")
        return ""

    # write.write_text(referenceDoc, f"build/Class_{classObj['Name']}.md")
    return referenceDoc

def get_reference():
    api_dump = get_api_dump()
    api_docstrings = get_api_docstrings()

    api_reference = {}

    for enumObj in api_dump["Enums"]:
        enum_reference = createEnumReference(enumObj, api_docstrings)
        if enum_reference != "":
            api_reference['Enum.' + enumObj["Name"]] = enum_reference

    for classObj in api_dump["Classes"]:
        class_reference = createClassReference(classObj, api_docstrings)
        if class_reference != "":
            api_reference[classObj["Name"]] = class_reference

    print("Found " + str(len(api_reference)) + " api references")
    # print(json_dumps(api_reference, indent=2))
    return api_reference

def get_sha():
    data = fetch_tree_data()
    write.write_text(data["sha"], "build/api-source-commit.txt")
    return data["sha"]
