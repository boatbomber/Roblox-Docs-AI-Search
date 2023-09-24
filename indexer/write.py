import json

def write_text(data: str, filename: str):
	print(f"Writing {filename}")
	with open(filename, "w", encoding="utf-8") as f:
		f.write(data)


def write_json(data, filename: str):
	print(f"Writing {filename}")
	with open(filename, "w", encoding="utf-8") as f:
		json.dump(data, f, ensure_ascii=False, indent="\t")
		f.write("\n")
