# tools/search_tools.py
import logging
import json
from duckduckgo_search import DDGS
from typing import List, Dict, Optional

# ---> Import config values <---
try:
    # Assuming config is at the root relative to where main.py is run
    from config import DEFAULT_SEARCH_RESULTS, MAX_SEARCH_RESULTS
except ImportError:
    # Fallback defaults if config import fails (e.g., running tool standalone)
    DEFAULT_SEARCH_RESULTS = 5
    MAX_SEARCH_RESULTS = 15

logger = logging.getLogger(__name__)

# --- Web Search Tool ---
# ---> Use DEFAULT_SEARCH_RESULTS in the signature <---
def web_search(query: str, num_results: int = DEFAULT_SEARCH_RESULTS) -> str:
    """
    Performs a web search using DuckDuckGo and returns the top results.
    Uses settings from config.py for default/max results.

    Args:
        query (str): The search query string.
        num_results (int): The maximum number of results to return (default from config).

    Returns:
        str: A formatted string containing the search results (title, URL, snippet)
             or an error message starting with 'Error:'. Returns 'Success: No results found.' if search is valid but returns nothing.
    """
    logger.info(f"Performing web search for query: '{query}' (target {num_results} results)")
    # Ensure num_results is an integer and within reasonable bounds
    try:
        target_results = int(num_results)
        if target_results <= 0:
            # ---> Use config default <---
            max_results = DEFAULT_SEARCH_RESULTS
            logger.warning(f"Invalid num_results '{num_results}', using default {DEFAULT_SEARCH_RESULTS}.")
        # ---> Use config max <---
        elif target_results > MAX_SEARCH_RESULTS:
             max_results = MAX_SEARCH_RESULTS
             logger.warning(f"num_results '{target_results}' exceeds max {MAX_SEARCH_RESULTS}, capping.")
        else:
            max_results = target_results

    except ValueError:
        # ---> Use config default <---
        max_results = DEFAULT_SEARCH_RESULTS
        logger.warning(f"Invalid num_results '{num_results}', using default {DEFAULT_SEARCH_RESULTS}.")


    try:
        # Use DDGS context manager with a timeout
        with DDGS(timeout=20) as ddgs:
            # Pass the validated max_results
            results = list(ddgs.text(query, max_results=max_results))

        if not results:
            logger.warning(f"Web search for '{query}' returned no results.")
            return f"Success: Web search for '{query}' returned no results."

        # Format the results into a readable string
        output_string = f"Search results for '{query}' (Top {len(results)} of max {max_results}):\n\n" # Clarify header
        for i, result in enumerate(results):
            title = result.get('title', 'N/A')
            href = result.get('href', 'N/A')
            body = result.get('body', 'N/A').replace('\n', ' ').strip()
            output_string += f"{i+1}. Title: {title}\n"
            output_string += f"   URL: {href}\n"
            output_string += f"   Snippet: {body}\n\n"

        logger.info(f"Web search successful, returning {len(results)} results (max requested: {max_results}).")
        # Limit overall output length
        max_output_len = 3500
        if len(output_string) > max_output_len:
            output_string = output_string[:max_output_len] + "\n... (Search results truncated)"
            logger.warning("Search results output truncated.")

        return output_string.strip()

    except Exception as e:
        logger.error(f"Error during web search for '{query}': {e}", exc_info=True)
        return f"Error: Web search failed. Details: {e}"

# --- Tool Definition Dictionary ---
SEARCH_TOOL_DESCRIPTIONS = {
    "web_search": {
        # ---> Updated description mentioning config default <---
        "description": f"Performs a web search for a given query using DuckDuckGo and returns a list of the top results (title, URL, snippet). Use this tool FIRST when you need to find information, websites, or answers online and the specific URL is not already known or provided by the user. The default number of results is {DEFAULT_SEARCH_RESULTS}, maximum is {MAX_SEARCH_RESULTS}.",
        "args": {
            "query": "string (The search term or question, e.g., 'latest AI research papers', 'official Python website', 'weather in London')",
            # ---> Updated description for num_results <---
            "num_results": f"integer (Optional, default {DEFAULT_SEARCH_RESULTS}. Specifies the maximum number of search results to retrieve. Max allowed: {MAX_SEARCH_RESULTS})"
        },
        "returns": "string (A formatted list of search results including Title, URL, and Snippet, a success message if no results are found, or an error message beginning with 'Error:')"
    }
}