import os
import shutil
from typing import Any, Dict


def move_path(source: str,
              destination: str,
              overwrite: bool = False,
              create_parents: bool = True) -> Dict[str, Any]:
    """
    Move or rename a file or directory on the local file system.

    Args:
        source: Existing path to move.
        destination: New path location.
        overwrite: Whether to overwrite the destination if it exists.
        create_parents: Create destination parent directories when missing.

    Returns:
        dict: {
            "source": absolute path of the source,
            "destination": absolute path of the destination,
            "error": str | None,
        }
    """
    abs_source = os.path.abspath(source)
    abs_dest = os.path.abspath(destination)

    if not os.path.exists(abs_source):
        return {"source": abs_source, "destination": abs_dest, "error": "source_not_found"}

    dest_parent = os.path.dirname(abs_dest)
    if dest_parent and not os.path.exists(dest_parent):
        if create_parents:
            try:
                os.makedirs(dest_parent, exist_ok=True)
            except Exception as e:
                return {"source": abs_source, "destination": abs_dest, "error": f"mkdir_failed: {e}"}
        else:
            return {"source": abs_source, "destination": abs_dest, "error": "destination_parent_missing"}

    if os.path.exists(abs_dest):
        if not overwrite:
            return {"source": abs_source, "destination": abs_dest, "error": "destination_exists"}
        if os.path.isdir(abs_dest) and not os.path.islink(abs_dest):
            try:
                shutil.rmtree(abs_dest)
            except Exception as e:
                return {"source": abs_source, "destination": abs_dest, "error": f"remove_destination_failed: {e}"}
        else:
            try:
                os.remove(abs_dest)
            except Exception as e:
                return {"source": abs_source, "destination": abs_dest, "error": f"remove_destination_failed: {e}"}

    try:
        shutil.move(abs_source, abs_dest)
    except Exception as e:
        return {"source": abs_source, "destination": abs_dest, "error": f"move_failed: {e}"}

    return {"source": abs_source, "destination": abs_dest, "error": None}
