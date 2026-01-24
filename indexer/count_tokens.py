from config import EMBEDDING_MODEL

from transformers import AutoTokenizer

tokenizer = AutoTokenizer.from_pretrained(EMBEDDING_MODEL)

def count_tokens(text: str) -> int:
    """Return the number of tokens in a string."""
    return len(
        tokenizer.encode(
            text,
            truncation=False,
            add_special_tokens=False,
        )
    )
