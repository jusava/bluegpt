from typing import List

def chunk_text(text: str) -> List[str]:
    """
    Chunk by a reasonable size but prefer to split on newlines when possible.
    """
    # Chunk by a reasonable size but prefer to split on newlines when possible.
    if not text:
        return [""]
    parts: List[str] = []
    buffer = ""
    for line in text.splitlines(keepends=True):
        if len(buffer) + len(line) > 400:
            parts.append(buffer)
            buffer = line
        else:
            buffer += line
    if buffer:
        parts.append(buffer)
    return parts or [text]
