import os
from typing import Any, Dict


def create_directory(path: str,
                     parents: bool = True,
                     exist_ok: bool = True) -> Dict[str, Any]:
    """
    Create a directory on the local file system.

    Args:
        path: Directory path to create.
        parents: Whether to create missing parent directories.
        exist_ok: If False, raise an error when the directory already exists.

    Returns:
        dict: {
            "path": absolute path,
            "created": bool,
            "error": str | None,
        }
    """
    abs_path = os.path.abspath(path)

    try:
        if parents:
            os.makedirs(abs_path, exist_ok=exist_ok)
        else:
            os.mkdir(abs_path)
    except FileExistsError:
        if exist_ok:
            return {"path": abs_path, "created": False, "error": None}
        return {"path": abs_path, "created": False, "error": "already_exists"}
    except Exception as e:
        return {"path": abs_path, "created": False, "error": f"mkdir_failed: {e}"}

    return {"path": abs_path, "created": True, "error": None}
