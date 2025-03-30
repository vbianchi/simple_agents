import logging
import re
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError, Error as PlaywrightError

# Import configuration variables
from config import (
    BROWSER_HEADLESS,
    PAGE_LOAD_TIMEOUT,
    CONTENT_MAX_LENGTH,
    BROWSER_USER_AGENT,
    BROWSER_TYPE, # Added
    LOG_LEVEL,    # Added
    LOG_FORMAT    # Added
)

# Configure logging using settings from config.py
logging.basicConfig(level=LOG_LEVEL, format=LOG_FORMAT)
logger = logging.getLogger(__name__) # Use module name for logger

# --- Playwright-based Web Fetching ---
def fetch_web_content(url: str) -> str:
    """
    Fetches the cleaned text content of a given URL using Playwright for rendering.
    Uses settings defined in config.py.
    """
    logger.info(f"Attempting to fetch content from: {url} using Playwright ({BROWSER_TYPE})")
    if not re.match(r'^https?://', url):
        logger.warning(f"Invalid URL format: {url}. Prepending 'http://'")
        url = "http://" + url

    try:
        with sync_playwright() as p:
            try:
                # Select browser type based on config
                browser_launcher = getattr(p, BROWSER_TYPE)
                browser = browser_launcher.launch(headless=BROWSER_HEADLESS)
            except AttributeError:
                logger.error(f"Invalid BROWSER_TYPE configured: '{BROWSER_TYPE}'. Falling back to chromium.")
                browser = p.chromium.launch(headless=BROWSER_HEADLESS) # Fallback just in case
            except Exception as launch_error: # Catch other potential launch errors
                 logger.error(f"Failed to launch Playwright browser {BROWSER_TYPE}: {launch_error}", exc_info=True)
                 return f"Error: Could not launch browser {BROWSER_TYPE}. Check configuration and Playwright installation."


            page = browser.new_page(user_agent=BROWSER_USER_AGENT)

            try:
                response = page.goto(url, wait_until='domcontentloaded', timeout=PAGE_LOAD_TIMEOUT)

                if response is None or not response.ok:
                    status = response.status if response else 'N/A'
                    logger.error(f"Playwright navigation failed for {url}. Status: {status}")
                    browser.close()
                    return f"Error: Failed to navigate to '{url}'. Status code: {status}"

                html_content = page.content()
                soup = BeautifulSoup(html_content, 'html.parser')

                for element in soup(["script", "style", "nav", "footer", "header", "aside", "form", "button"]):
                    element.decompose()

                text = soup.get_text(separator='\n', strip=True)
                lines = (line.strip() for line in text.splitlines())
                chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
                text = '\n'.join(chunk for chunk in chunks if chunk)

                logger.info(f"Successfully fetched content from: {url} (Length: {len(text)})")

                # Use CONTENT_MAX_LENGTH from config
                if len(text) > CONTENT_MAX_LENGTH:
                    logger.warning(f"Content truncated from {len(text)} to {CONTENT_MAX_LENGTH} characters for URL: {url}")
                    text = text[:CONTENT_MAX_LENGTH] + "\n... (content truncated)"

                browser.close()
                return text

            except PlaywrightTimeoutError:
                logger.error(f"Playwright navigation timed out for {url} (Timeout: {PAGE_LOAD_TIMEOUT}ms)")
                browser.close()
                return f"Error: The request to '{url}' timed out while loading."
            except PlaywrightError as e:
                logger.error(f"Playwright navigation error for {url}: {e}")
                browser.close()
                return f"Error: Browser navigation failed for '{url}'. Details: {e}"
            except Exception as e:
                logger.error(f"Unexpected error during Playwright fetching/parsing for {url}: {e}", exc_info=True)
                if 'browser' in locals() and browser.is_connected():
                     browser.close()
                return f"Error: An unexpected error occurred while processing '{url}' with Playwright."
            finally:
                 # Ensure browser is closed even if errors occur mid-process
                 if 'browser' in locals() and browser.is_connected():
                     browser.close()


    except Exception as e:
        logger.error(f"Failed to initialize or run Playwright: {e}", exc_info=True)
        if "executable doesn't exist" in str(e).lower():
             return f"Error: Playwright browser executable ({BROWSER_TYPE}) not found. Did you run 'playwright install'?"
        return f"Error: Failed to start the browser automation tool. {e}"

# --- Tool Dictionary (structure remains the same) ---
AVAILABLE_TOOLS = {
    "fetch_web_content": fetch_web_content
}

# --- Tool Descriptions ---
# Updated description slightly to mention dynamic content aspect more clearly
TOOL_DESCRIPTIONS = f"""
Available Tools:
- fetch_web_content(url: str): Fetches the main textual content from a given web URL. Uses a browser ({BROWSER_TYPE}) to render the page, making it suitable for dynamic websites that rely on JavaScript. Example URL format: "https://example.com".
"""