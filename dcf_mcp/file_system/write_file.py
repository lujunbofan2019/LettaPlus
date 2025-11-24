import os
from typing import Any, Dict


def write_file(path: str,
               content: str,
               append: bool = False,
               encoding: str = "utf-8",
               create_parents: bool = True) -> Dict[str, Any]:
    """
    Write text content to a file on the local file system.

    Args:
        path: Target file path.
        content: Text content to write.
        append: If True, content is appended instead of overwriting.
        encoding: Encoding to use when writing.
        create_parents: Create parent directories when they do not exist.

    Returns:
        dict: {
            "path": absolute path,
            "bytes_written": int | None,
            "mode": "append" | "overwrite",
            "error": str | None,
        }
    """
    abs_path = os.path.abspath(path)
    parent_dir = os.path.dirname(abs_path)

    if parent_dir and not os.path.exists(parent_dir):
        if create_parents:
            try:
                os.makedirs(parent_dir, exist_ok=True)
            except Exception as e:
                return {"path": abs_path, "bytes_written": None, "mode": None, "error": f"mkdir_failed: {e}"}
        else:
            return {"path": abs_path, "bytes_written": None, "mode": None, "error": "parent_missing"}

    mode = "a" if append else "w"
    try:
        with open(abs_path, mode, encoding=encoding) as f:
            f.write(content)
    except Exception as e:
        return {"path": abs_path, "bytes_written": None, "mode": "append" if append else "overwrite", "error": f"write_failed: {e}"}

    return {
        "path": abs_path,
        "bytes_written": len(content.encode(encoding)),
        "mode": "append" if append else "overwrite",
        "error": None,
    }
