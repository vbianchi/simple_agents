# tool_functions.py
import logging
import re
import os
from pathlib import Path
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError, Error as PlaywrightError

# Import configuration variables
from config import (
    BROWSER_HEADLESS,
    PAGE_LOAD_TIMEOUT,
    CONTENT_MAX_LENGTH,
    BROWSER_USER_AGENT,
    BROWSER_TYPE,
    LOG_LEVEL,
    LOG_FORMAT
)

# Configure logging using settings from config.py
# Note: BasicConfig only configures the root logger once.
# If other modules also call basicConfig, it might not reconfigure.
# More robust logging setup might use logging.getLogger().setLevel() etc.
logging.basicConfig(level=LOG_LEVEL, format=LOG_FORMAT)
logger = logging.getLogger(__name__) # Use module name for logger

# --- Playwright-based Web Fetching ---
def fetch_web_content(url: str, session_path: Path = None) -> str:
    """
    Fetches the cleaned text content of a given URL using Playwright for rendering.
    Uses settings defined in config.py. Session path is ignored but accepted for consistency.
    """
    logger.info(f"Attempting to fetch content from: {url} using Playwright ({BROWSER_TYPE})")
    if not re.match(r'^https?://', url):
        logger.warning(f"Invalid URL format: {url}. Prepending 'http://'")
        url = "http://" + url

    resolved_text = f"Error: Could not fetch content from '{url}'." # Default error

    try:
        with sync_playwright() as p:
            try:
                browser_launcher = getattr(p, BROWSER_TYPE)
                browser = browser_launcher.launch(headless=BROWSER_HEADLESS)
            except AttributeError:
                logger.error(f"Invalid BROWSER_TYPE configured: '{BROWSER_TYPE}'. Falling back to chromium.")
                browser = p.chromium.launch(headless=BROWSER_HEADLESS) # Fallback
            except Exception as launch_error:
                 logger.error(f"Failed to launch Playwright browser {BROWSER_TYPE}: {launch_error}", exc_info=True)
                 return f"Error: Could not launch browser {BROWSER_TYPE}. Check configuration and Playwright installation."

            page = None # Initialize page to None
            try:
                page = browser.new_page(user_agent=BROWSER_USER_AGENT)
                response = page.goto(url, wait_until='domcontentloaded', timeout=PAGE_LOAD_TIMEOUT)

                if response is None or not response.ok:
                    status = response.status if response else 'N/A'
                    logger.error(f"Playwright navigation failed for {url}. Status: {status}")
                    resolved_text = f"Error: Failed to navigate to '{url}'. Status code: {status}"
                else:
                    html_content = page.content()
                    soup = BeautifulSoup(html_content, 'html.parser')

                    for element in soup(["script", "style", "nav", "footer", "header", "aside", "form", "button"]):
                        element.decompose()

                    text = soup.get_text(separator='\n', strip=True)
                    lines = (line.strip() for line in text.splitlines())
                    chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
                    text = '\n'.join(chunk for chunk in chunks if chunk)

                    logger.info(f"Successfully fetched content from: {url} (Length: {len(text)})")

                    if len(text) > CONTENT_MAX_LENGTH:
                        logger.warning(f"Content truncated from {len(text)} to {CONTENT_MAX_LENGTH} characters for URL: {url}")
                        text = text[:CONTENT_MAX_LENGTH] + "\n... (content truncated)"
                    resolved_text = text # Assign success result

            except PlaywrightTimeoutError:
                logger.error(f"Playwright navigation timed out for {url} (Timeout: {PAGE_LOAD_TIMEOUT}ms)")
                resolved_text = f"Error: The request to '{url}' timed out while loading."
            except PlaywrightError as e:
                logger.error(f"Playwright navigation error for {url}: {e}")
                resolved_text = f"Error: Browser navigation failed for '{url}'. Details: {e}"
            except Exception as e:
                logger.error(f"Unexpected error during Playwright fetching/parsing for {url}: {e}", exc_info=True)
                resolved_text = f"Error: An unexpected error occurred while processing '{url}' with Playwright."
            finally:
                 # Ensure browser is closed
                 if 'browser' in locals() and browser.is_connected():
                     browser.close()

    except Exception as e:
        logger.error(f"Failed to initialize or run Playwright: {e}", exc_info=True)
        if "executable doesn't exist" in str(e).lower():
             resolved_text = f"Error: Playwright browser executable ({BROWSER_TYPE}) not found. Did you run 'playwright install'?"
        else:
            resolved_text = f"Error: Failed to start the browser automation tool. {e}"

    return resolved_text


# --- NEW: File Writing Tool ---
def write_file(filename: str, content: str, session_path: Path) -> str:
    """
    Writes the given content to a file within the current session's workspace.

    Args:
        filename (str): The desired name for the file (e.g., "report.md", "notes.txt").
                        Should not contain path separators like / or \.
        content (str): The text content to write into the file. Can be multi-line.
        session_path (Path): The absolute path to the current session's directory.

    Returns:
        str: A message indicating success or failure.
    """
    if not session_path or not isinstance(session_path, Path):
        logger.error("write_file tool called without a valid session_path.")
        return "Error: Internal agent error - session path not provided to write_file tool."

    # Basic security: Prevent path traversal and invalid filenames
    cleaned_filename = Path(filename).name # Use Pathlib to get just the filename part
    if cleaned_filename != filename or not cleaned_filename or cleaned_filename.startswith("."):
         logger.error(f"Invalid filename provided to write_file: '{filename}'")
         return f"Error: Invalid filename '{filename}'. Filename cannot contain path separators, start with '.', or be empty."
    filename = cleaned_filename # Use the cleaned name

    try:
        # Ensure the session directory exists
        session_path.mkdir(parents=True, exist_ok=True)

        # Construct the full, absolute path within the session folder
        file_path = session_path.resolve() / filename
        logger.info(f"Attempting to write file: {file_path}")

        # Double-check we are still within the session path (extra safety)
        # Ensure session_path is resolved for accurate comparison
        resolved_session_path = session_path.resolve()
        if not str(file_path.parent.resolve()).startswith(str(resolved_session_path)):
             logger.error(f"Security Error: Attempted write path '{file_path}' is outside session path '{resolved_session_path}'")
             return "Error: Security constraints prevent writing to the specified path."

        # Write the content to the file using UTF-8 encoding
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)

        logger.info(f"Successfully wrote {len(content)} characters to file: {file_path}")
        return f"Success: File '{filename}' written successfully to the session workspace ({session_path.name})."

    except OSError as e:
        logger.error(f"Error writing file '{filename}' to {session_path}: {e}", exc_info=True)
        return f"Error: Could not write file '{filename}'. OS Error: {e}"
    except Exception as e:
        logger.error(f"Unexpected error writing file '{filename}': {e}", exc_info=True)
        return f"Error: An unexpected error occurred while writing file '{filename}'."

# --- Tool Dictionary ---
AVAILABLE_TOOLS = {
    "fetch_web_content": fetch_web_content,
    "write_file": write_file
}

# --- Tool Descriptions ---
TOOL_DESCRIPTIONS = f"""
Available Tools:
- fetch_web_content(url: str): Fetches the main textual content from a given web URL. Uses a browser ({BROWSER_TYPE}) to render the page, making it suitable for dynamic websites that rely on JavaScript. Example URL format: "https://example.com".
- write_file(filename: str, content: str): Writes the provided text 'content' to a file named 'filename' in the current session's workspace directory. Use this to save information, reports, code, or notes. Ensure 'filename' is just a name (e.g., "report.txt", "summary.md") and does not include paths. The 'content' should be the full text you want to save. Example: write_file(filename="analysis.md", content="# Analysis\\nThis is my analysis.")
"""