import os
import shutil
from typing import Any, Dict


def delete_path(path: str,
                recursive: bool = False) -> Dict[str, Any]:
    """
    Delete a file or directory from the local file system.

    Args:
        path: Path to remove.
        recursive: When True, directories are removed recursively.

    Returns:
        dict: {
            "path": absolute path,
            "removed": bool,
            "error": str | None,
        }
    """
    abs_path = os.path.abspath(path)

    if not os.path.exists(abs_path):
        return {"path": abs_path, "removed": False, "error": "path_not_found"}

    try:
        if os.path.isfile(abs_path) or os.path.islink(abs_path):
            os.remove(abs_path)
        elif os.path.isdir(abs_path):
            if recursive:
                shutil.rmtree(abs_path)
            else:
                os.rmdir(abs_path)
        else:
            return {"path": abs_path, "removed": False, "error": "unsupported_type"}
    except Exception as e:
        return {"path": abs_path, "removed": False, "error": f"remove_failed: {e}"}

    return {"path": abs_path, "removed": True, "error": None}
