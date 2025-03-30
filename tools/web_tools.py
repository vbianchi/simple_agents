# tools/web_tools.py
import logging
import re
from pathlib import Path
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError, Error as PlaywrightError

# Import necessary configs - adjusted path
from config import (
    BROWSER_HEADLESS,
    PAGE_LOAD_TIMEOUT,
    CONTENT_MAX_LENGTH,
    BROWSER_USER_AGENT,
    BROWSER_TYPE
)

logger = logging.getLogger(__name__)

def fetch_web_content(url: str, session_path: Path) -> str: # Accept session_path
    """
    Fetches the cleaned text content of a given URL using Playwright for rendering.
    Session path is currently ignored but accepted for interface consistency.
    """
    logger.info(f"Attempting to fetch content from: {url} using Playwright ({BROWSER_TYPE})")
    # --- Add URL scheme if missing ---
    if not re.match(r'^https?://', url):
        logger.warning(f"Invalid URL format: {url}. Prepending 'http://'")
        url = "http://" + url

    resolved_text = f"Error: Could not fetch content from '{url}'."
    try:
        with sync_playwright() as p:
            # ... (rest of the playwright logic is identical to previous version) ...
            # ... ensure browser is launched, page navigated, content parsed, limited, closed ...
             try:
                browser_launcher = getattr(p, BROWSER_TYPE)
                browser = browser_launcher.launch(headless=BROWSER_HEADLESS)
             except Exception as launch_error:
                 logger.error(f"Failed to launch Playwright browser {BROWSER_TYPE}: {launch_error}", exc_info=True)
                 return f"Error: Could not launch browser {BROWSER_TYPE}."

             page = None
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
                    logger.info(f"Successfully fetched content from: {url} (Raw Length: {len(text)})")
                    if len(text) > CONTENT_MAX_LENGTH:
                        logger.warning(f"Content truncated from {len(text)} to {CONTENT_MAX_LENGTH} characters for URL: {url}")
                        text = text[:CONTENT_MAX_LENGTH] + "\n... (content truncated)"
                    resolved_text = text

             except PlaywrightTimeoutError:
                logger.error(f"Playwright navigation timed out for {url} (Timeout: {PAGE_LOAD_TIMEOUT}ms)")
                resolved_text = f"Error: The request to '{url}' timed out."
             except PlaywrightError as e:
                logger.error(f"Playwright navigation error for {url}: {e}")
                resolved_text = f"Error: Browser navigation failed for '{url}'. Details: {e}"
             except Exception as e:
                logger.error(f"Unexpected error during Playwright processing for {url}: {e}", exc_info=True)
                resolved_text = f"Error: An unexpected error occurred processing '{url}'."
             finally:
                 if 'browser' in locals() and browser.is_connected():
                     browser.close()

    except Exception as e:
        logger.error(f"Failed to initialize or run Playwright: {e}", exc_info=True)
        if "executable doesn't exist" in str(e).lower():
             resolved_text = f"Error: Playwright browser executable ({BROWSER_TYPE}) not found. Did you run 'playwright install'?"
        else:
             resolved_text = f"Error: Failed to start the browser automation tool."

    return resolved_text

# --- Tool Definition Dictionary (for documentation/prompting) ---
# We'll load tools dynamically in the agent now, but keep descriptions handy
WEB_TOOL_DESCRIPTIONS = {
    "fetch_web_content": {
        "description": "Fetches the main textual content from a given web URL using a browser. Use this for accessing current online information.",
        "args": {"url": "string (The full URL to fetch, e.g., 'https://example.com')"},
        "returns": "string (The extracted text content or an error message starting with 'Error:')"
    }
}