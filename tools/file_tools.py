# tools/file_tools.py
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# --- Helper to strip quotes ---
def strip_outer_quotes(value: str) -> str:
    """Removes matching outer single or double quotes from a string if present."""
    if isinstance(value, str):
        if (value.startswith('"') and value.endswith('"')) or \
           (value.startswith("'") and value.endswith("'")):
            return value[1:-1]
    return value

# --- File Writing Tool ---
def write_file(filename: str, content: str, session_path: Path) -> str:
    """Writes the given content to a file within the current session's workspace."""
    if not session_path or not isinstance(session_path, Path):
        logger.error("write_file tool called without a valid session_path.")
        return "Error: Internal agent error - session path not provided."

    # ---> Clean the filename by stripping quotes FIRST <---
    cleaned_filename_quotes = strip_outer_quotes(filename)
    # Then sanitize for path safety
    cleaned_filename = Path(cleaned_filename_quotes).name
    if cleaned_filename != cleaned_filename_quotes or not cleaned_filename or cleaned_filename.startswith("."):
         logger.error(f"Invalid or unsafe filename provided to write_file after cleaning: Original='{filename}', Cleaned='{cleaned_filename}'")
         return f"Error: Invalid or unsafe filename '{filename}'. No paths allowed, cannot start with '.', cannot be empty."
    # Use the finally cleaned name
    filename_to_use = cleaned_filename

    try:
        session_path.mkdir(parents=True, exist_ok=True)
        file_path = session_path.resolve() / filename_to_use # Use cleaned name
        logger.info(f"Attempting to write file: {file_path}")

        resolved_session_path = session_path.resolve()
        if not str(file_path.parent.resolve()).startswith(str(resolved_session_path)):
             logger.error(f"Security Error: Write path '{file_path}' is outside session path '{resolved_session_path}'")
             return "Error: Security constraints prevent writing to the specified path."

        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)

        logger.info(f"Successfully wrote {len(content)} characters to file: {file_path}")
        return f"Success: File '{filename_to_use}' written to workspace." # Report cleaned name

    except OSError as e:
        logger.error(f"Error writing file '{filename_to_use}' to {session_path}: {e}", exc_info=True)
        return f"Error: Could not write file '{filename_to_use}'. OS Error: {e}"
    except Exception as e:
        logger.error(f"Unexpected error writing file '{filename_to_use}': {e}", exc_info=True)
        return f"Error: An unexpected error occurred writing file '{filename_to_use}'."

# --- File Reading Tool ---
def read_file(filename: str, session_path: Path) -> str:
    """Reads the content of a file from the current session's workspace."""
    if not session_path or not isinstance(session_path, Path):
        logger.error("read_file tool called without a valid session_path.")
        return "Error: Internal agent error - session path not provided."

    # ---> Clean the filename by stripping quotes FIRST <---
    cleaned_filename_quotes = strip_outer_quotes(filename)
    # Then sanitize for path safety
    cleaned_filename = Path(cleaned_filename_quotes).name
    if cleaned_filename != cleaned_filename_quotes or not cleaned_filename or cleaned_filename.startswith("."):
         logger.error(f"Invalid or unsafe filename provided to read_file after cleaning: Original='{filename}', Cleaned='{cleaned_filename}'")
         return f"Error: Invalid or unsafe filename '{filename}'. No paths allowed, cannot start with '.', cannot be empty."
    # Use the finally cleaned name
    filename_to_use = cleaned_filename

    try:
        file_path = session_path.resolve() / filename_to_use # Use cleaned name

        resolved_session_path = session_path.resolve()
        if not str(file_path.parent.resolve()).startswith(str(resolved_session_path)):
             logger.error(f"Security Error: Read path '{file_path}' is outside session path '{resolved_session_path}'")
             return "Error: Security constraints prevent reading from the specified path."

        if not file_path.is_file():
            logger.warning(f"File not found for reading: {file_path}")
            return f"Error: File '{filename_to_use}' not found in the workspace."

        logger.info(f"Attempting to read file: {file_path}")
        content = file_path.read_text(encoding='utf-8')
        logger.info(f"Successfully read {len(content)} characters from file: {file_path}")
        return content

    except OSError as e:
        logger.error(f"Error reading file '{filename_to_use}' from {session_path}: {e}", exc_info=True)
        return f"Error: Could not read file '{filename_to_use}'. OS Error: {e}"
    except Exception as e:
        logger.error(f"Unexpected error reading file '{filename_to_use}': {e}", exc_info=True)
        return f"Error: An unexpected error occurred reading file '{filename_to_use}'."


# --- Tool Definition Dictionary (for documentation/prompting) ---
FILE_TOOL_DESCRIPTIONS = {
    "write_file": {
        "description": "Writes the provided text content to a file with the specified filename within the current session's secure workspace. Use this to save results, notes, or generated text.",
        "args": {
            "filename": "string (The name of the file, e.g., 'report.txt', 'notes.md'. Must not contain paths like / or \\, and should not start with '.').",
            "content": "string (The full text content to write to the file.)"
        },
        "returns": "string ('Success: File...' or 'Error:...')"
    },
    "read_file": {
        "description": "Reads the full text content of a previously written file from the current session's secure workspace.",
        "args": {"filename": "string (The name of the file to read, e.g., 'report.txt'. Must not contain paths or start with '.')."},
        "returns": "string (The content of the file, or an error message starting with 'Error:')"
    }
}