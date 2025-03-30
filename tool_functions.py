import logging
import re
from bs4 import BeautifulSoup
# New imports for Playwright
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError, Error as PlaywrightError

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Playwright-based Web Fetching ---
def fetch_web_content(url: str) -> str:
    """
    Fetches the cleaned text content of a given URL using Playwright for rendering.

    Args:
        url (str): The URL to fetch content from.

    Returns:
        str: The extracted and cleaned text content of the rendered page, or an error message.
    """
    logger.info(f"Attempting to fetch content from: {url} using Playwright")
    if not re.match(r'^https?://', url):
        logger.warning(f"Invalid URL format: {url}. Prepending 'http://'")
        url = "http://" + url # Basic attempt to fix common missing scheme

    try:
        with sync_playwright() as p:
            # Launch Chromium (you can also use p.firefox or p.webkit)
            # headless=True runs the browser without a visible UI window
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(
                user_agent='MinimalAgent/0.2 (Mozilla/5.0; Playwright)' # Identify the bot
            )

            try:
                # Navigate to the URL. 'domcontentloaded' waits until the basic HTML is loaded.
                # 'load' waits for all resources (images, etc.) - might be slower.
                # 'networkidle' waits until network activity quiets down - useful for SPAs.
                # Increased timeout for potentially slow-loading pages.
                response = page.goto(url, wait_until='domcontentloaded', timeout=20000) # 20 second timeout

                if response is None or not response.ok:
                    status = response.status if response else 'N/A'
                    logger.error(f"Playwright navigation failed for {url}. Status: {status}")
                    browser.close()
                    return f"Error: Failed to navigate to '{url}'. Status code: {status}"

                # Get the fully rendered HTML content after JavaScript execution
                html_content = page.content()

                # --- Use BeautifulSoup for cleanup (similar to before) ---
                soup = BeautifulSoup(html_content, 'html.parser')

                # Remove script, style, nav, footer elements etc.
                for element in soup(["script", "style", "nav", "footer", "header", "aside", "form", "button"]):
                    element.decompose()

                # Get text, strip whitespace, remove blank lines
                text = soup.get_text(separator='\n', strip=True)
                lines = (line.strip() for line in text.splitlines())
                chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
                text = '\n'.join(chunk for chunk in chunks if chunk)

                logger.info(f"Successfully fetched and cleaned content from: {url} (Length: {len(text)})")

                # Limit the content length
                max_length = 4000
                if len(text) > max_length:
                    logger.warning(f"Content truncated from {len(text)} to {max_length} characters for URL: {url}")
                    text = text[:max_length] + "\n... (content truncated)"

                browser.close()
                return text

            except PlaywrightTimeoutError:
                logger.error(f"Playwright navigation timed out for {url}")
                browser.close()
                return f"Error: The request to '{url}' timed out while loading."
            except PlaywrightError as e:
                logger.error(f"Playwright navigation error for {url}: {e}")
                browser.close()
                return f"Error: Browser navigation failed for '{url}'. Details: {e}"
            except Exception as e: # Catch other potential errors during processing
                logger.error(f"Unexpected error during Playwright fetching or parsing for {url}: {e}", exc_info=True)
                if 'browser' in locals() and browser.is_connected():
                     browser.close()
                return f"Error: An unexpected error occurred while processing the URL '{url}' with Playwright."

    except Exception as e:
        # Catch errors during Playwright startup (e.g., browser not installed)
        logger.error(f"Failed to initialize or run Playwright: {e}", exc_info=True)
        if "executable doesn't exist" in str(e).lower():
             return "Error: Playwright browser executable not found. Did you run 'playwright install'?"
        return f"Error: Failed to start the browser automation tool. {e}"


# --- Tool Dictionary (remains the same structure) ---
AVAILABLE_TOOLS = {
    "fetch_web_content": fetch_web_content
}

TOOL_DESCRIPTIONS = """
Available Tools:
- fetch_web_content(url: str): Fetches the main textual content from a given web URL using a browser to render JavaScript. Use this when you need current information or details from a specific webpage, especially if it might be dynamic. Example URL format: "https://example.com".
"""
