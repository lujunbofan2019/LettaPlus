"""
Utility functions for the skill CLI.
"""

import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import yaml
except ImportError:
    yaml = None


# ANSI color codes for terminal output
class Colors:
    """ANSI color codes for terminal output."""
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"

    @classmethod
    def disable(cls):
        """Disable colors (for non-TTY output)."""
        cls.RESET = ""
        cls.BOLD = ""
        cls.DIM = ""
        cls.RED = ""
        cls.GREEN = ""
        cls.YELLOW = ""
        cls.BLUE = ""
        cls.MAGENTA = ""
        cls.CYAN = ""


# Disable colors if not a TTY
if not sys.stdout.isatty():
    Colors.disable()


def find_project_root(start_path: Optional[Path] = None) -> Optional[Path]:
    """
    Find the project root by looking for skills_src/ directory.

    Searches upward from start_path (default: current directory).
    """
    if start_path is None:
        start_path = Path.cwd()

    current = start_path.resolve()
    while current != current.parent:
        if (current / "skills_src").is_dir():
            return current
        # Also check for skills_src in current directory
        if current.name == "skills_src" and current.is_dir():
            return current.parent
        current = current.parent

    return None


def get_skills_dir(args) -> Path:
    """Get the skills_src directory path from args or auto-detect."""
    if args.skills_dir:
        return Path(args.skills_dir)

    # Try environment variable
    env_path = os.environ.get("SKILLS_SRC_DIR")
    if env_path:
        return Path(env_path)

    # Auto-detect from current directory
    root = find_project_root()
    if root:
        return root / "skills_src"

    # Default to current directory
    return Path.cwd() / "skills_src"


def get_generated_dir(args) -> Path:
    """Get the generated output directory path from args or auto-detect."""
    if args.generated_dir:
        return Path(args.generated_dir)

    # Try environment variable
    env_path = os.environ.get("GENERATED_DIR")
    if env_path:
        return Path(env_path)

    # Auto-detect from current directory
    root = find_project_root()
    if root:
        return root / "generated"

    # Default to current directory
    return Path.cwd() / "generated"


def load_yaml_file(path: Path) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    Load and parse a YAML file.

    Returns:
        (data, error) tuple - data is None if error occurred
    """
    if yaml is None:
        return None, "PyYAML not installed. Run: pip install pyyaml"

    if not path.exists():
        return None, f"File not found: {path}"

    try:
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            return data, None
    except yaml.YAMLError as e:
        return None, f"YAML parse error: {e}"
    except Exception as e:
        return None, f"Error reading file: {e}"


def save_yaml_file(path: Path, data: Dict[str, Any]) -> Optional[str]:
    """
    Save data to a YAML file.

    Returns:
        Error message if failed, None on success
    """
    if yaml is None:
        return "PyYAML not installed. Run: pip install pyyaml"

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            yaml.safe_dump(
                data,
                f,
                default_flow_style=False,
                allow_unicode=True,
                sort_keys=False
            )
        return None
    except Exception as e:
        return f"Error writing file: {e}"


def print_success(message: str):
    """Print a success message in green."""
    print(f"{Colors.GREEN}✓{Colors.RESET} {message}")


def print_error(message: str):
    """Print an error message in red."""
    print(f"{Colors.RED}✗{Colors.RESET} {message}", file=sys.stderr)


def print_warning(message: str):
    """Print a warning message in yellow."""
    print(f"{Colors.YELLOW}!{Colors.RESET} {message}", file=sys.stderr)


def print_info(message: str):
    """Print an info message in blue."""
    print(f"{Colors.BLUE}i{Colors.RESET} {message}")


def print_header(message: str):
    """Print a header message in bold."""
    print(f"\n{Colors.BOLD}{message}{Colors.RESET}")


def format_table(headers: List[str], rows: List[List[str]], max_widths: Optional[List[int]] = None) -> str:
    """
    Format data as a simple ASCII table.

    Args:
        headers: Column headers
        rows: List of rows, each row is a list of cell values
        max_widths: Optional maximum width for each column

    Returns:
        Formatted table string
    """
    if not rows:
        return ""

    # Calculate column widths
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            if i < len(widths):
                widths[i] = max(widths[i], len(str(cell)))

    # Apply max widths if specified
    if max_widths:
        widths = [min(w, m) if m else w for w, m in zip(widths, max_widths + [0] * len(widths))]

    # Format header
    header_line = "  ".join(h.ljust(w) for h, w in zip(headers, widths))
    separator = "  ".join("-" * w for w in widths)

    # Format rows
    formatted_rows = []
    for row in rows:
        cells = []
        for i, cell in enumerate(row):
            cell_str = str(cell)
            if i < len(widths):
                if len(cell_str) > widths[i]:
                    cell_str = cell_str[:widths[i] - 3] + "..."
                cells.append(cell_str.ljust(widths[i]))
            else:
                cells.append(cell_str)
        formatted_rows.append("  ".join(cells))

    return "\n".join([header_line, separator] + formatted_rows)


def prompt_input(prompt: str, default: Optional[str] = None) -> str:
    """
    Prompt user for input with optional default.

    Args:
        prompt: The prompt to display
        default: Default value if user enters nothing

    Returns:
        User input or default value
    """
    if default:
        full_prompt = f"{prompt} [{default}]: "
    else:
        full_prompt = f"{prompt}: "

    try:
        value = input(full_prompt).strip()
        return value if value else (default or "")
    except EOFError:
        return default or ""


def prompt_confirm(prompt: str, default: bool = False) -> bool:
    """
    Prompt user for yes/no confirmation.

    Args:
        prompt: The prompt to display
        default: Default value if user enters nothing

    Returns:
        True for yes, False for no
    """
    if default:
        suffix = "[Y/n]"
    else:
        suffix = "[y/N]"

    try:
        value = input(f"{prompt} {suffix}: ").strip().lower()
        if not value:
            return default
        return value in ("y", "yes", "1", "true")
    except EOFError:
        return default


def prompt_choice(prompt: str, choices: List[str], default: Optional[str] = None) -> str:
    """
    Prompt user to choose from a list of options.

    Args:
        prompt: The prompt to display
        choices: List of valid choices
        default: Default choice

    Returns:
        Selected choice
    """
    print(f"{prompt}")
    for i, choice in enumerate(choices, 1):
        marker = "*" if choice == default else " "
        print(f"  {marker} {i}. {choice}")

    while True:
        if default:
            value = input(f"Enter number or name [{default}]: ").strip()
        else:
            value = input("Enter number or name: ").strip()

        if not value and default:
            return default

        # Try as number
        try:
            idx = int(value) - 1
            if 0 <= idx < len(choices):
                return choices[idx]
        except ValueError:
            pass

        # Try as name
        if value in choices:
            return value

        print(f"Invalid choice. Please enter 1-{len(choices)} or a valid name.")
