import os
from typing import Any, Dict


def read_file(path: str,
              offset: int = 0,
              length: int | None = None,
              encoding: str = "utf-8") -> Dict[str, Any]:
    """
    Read text from a file on the local file system.

    Args:
        path: File path to read.
        offset: Byte offset to start reading from.
        length: Number of bytes to read. Reads to end of file when None.
        encoding: Text encoding to apply when decoding the file.

    Returns:
        dict: {
            "path": absolute path,
            "content": str | None,
            "bytes_read": int | None,
            "error": str | None,
        }
    """
    abs_path = os.path.abspath(path)

    if not os.path.exists(abs_path):
        return {"path": abs_path, "content": None, "bytes_read": None, "error": "path_not_found"}

    if not os.path.isfile(abs_path):
        return {"path": abs_path, "content": None, "bytes_read": None, "error": "not_a_file"}

    try:
        with open(abs_path, "rb") as f:
            if offset:
                f.seek(offset)
            data = f.read() if length is None else f.read(length)
    except Exception as e:
        return {"path": abs_path, "content": None, "bytes_read": None, "error": f"read_failed: {e}"}

    try:
        content = data.decode(encoding)
    except Exception as e:
        return {"path": abs_path, "content": None, "bytes_read": len(data), "error": f"decode_failed: {e}"}

    return {"path": abs_path, "content": content, "bytes_read": len(data), "error": None}
