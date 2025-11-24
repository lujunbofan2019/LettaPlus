import os
from datetime import datetime
from typing import Any, Dict, List


def list_directory(path: str = ".",
                   recursive: bool = False,
                   include_hidden: bool = False,
                   max_entries: int | None = None) -> Dict[str, Any]:
    """
    List the contents of a directory on the local file system.

    Args:
        path: Directory to inspect. Defaults to current working directory.
        recursive: Whether to walk the directory tree recursively.
        include_hidden: Whether to include hidden files (names starting with '.').
        max_entries: Optional limit for number of entries returned.

    Returns:
        dict: {
            "path": absolute path inspected,
            "entries": [
                {
                    "name": filename,
                    "path": absolute path,
                    "type": "file" | "directory" | "symlink" | "other",
                    "size": file size in bytes or None,
                    "modified": ISO-8601 timestamp or None,
                }, ...
            ],
            "truncated": bool,  # True if entries were limited by max_entries
            "error": str | None,
        }
    """
    entries: List[Dict[str, Any]] = []
    abs_path = os.path.abspath(path)
    truncated = False

    if not os.path.exists(abs_path):
        return {"path": abs_path, "entries": entries, "truncated": truncated, "error": "path_not_found"}

    if not os.path.isdir(abs_path):
        return {"path": abs_path, "entries": entries, "truncated": truncated, "error": "not_a_directory"}

    remaining = None if max_entries is None else max_entries

    def should_include(name: str) -> bool:
        if include_hidden:
            return True
        return not name.startswith(".")

    def add_entry(name: str, full_path: str) -> None:
        nonlocal remaining, truncated
        if remaining is not None and remaining <= 0:
            truncated = True
            return
        if not should_include(name):
            return

        entry_type = "other"
        if os.path.isfile(full_path):
            entry_type = "file"
        elif os.path.isdir(full_path):
            entry_type = "directory"
        elif os.path.islink(full_path):
            entry_type = "symlink"

        size = None
        modified = None
        try:
            stat = os.stat(full_path, follow_symlinks=False)
            size = stat.st_size
            modified = datetime.fromtimestamp(stat.st_mtime).isoformat()
        except Exception:
            pass

        entries.append({
            "name": name,
            "path": full_path,
            "type": entry_type,
            "size": size,
            "modified": modified,
        })
        if remaining is not None:
            remaining -= 1

    try:
        if recursive:
            for root, dirs, files in os.walk(abs_path):
                for name in list(dirs) + list(files):
                    add_entry(name, os.path.join(root, name))
                    if remaining is not None and remaining <= 0:
                        truncated = True
                        break
                if remaining is not None and remaining <= 0:
                    break
        else:
            with os.scandir(abs_path) as scan:
                for entry in scan:
                    add_entry(entry.name, entry.path)
    except Exception as e:
        return {"path": abs_path, "entries": entries, "truncated": truncated, "error": f"scan_failed: {e}"}

    return {"path": abs_path, "entries": entries, "truncated": truncated, "error": None}
