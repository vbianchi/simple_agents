"""
Central configuration file for the Minimal Ollama Agent.
Modify values here to change agent behavior.
"""

import logging

# --- Ollama / LLM Configuration ---
OLLAMA_BASE_URL = "http://localhost:11434"   # Base URL for your Ollama instance
OLLAMA_API_ENDPOINT = "/api/generate"       # API endpoint (use /api/chat for chat models structure)
OLLAMA_MODEL = "llama3.2"                     # The Ollama model to use (e.g., "llama3", "mistral", "phi3")
OLLAMA_API_TIMEOUT = 90                     # Seconds to wait for the Ollama API to respond

# Optional parameters passed directly to the Ollama API in the "options" field
# Refer to Ollama documentation for available options: https://github.com/ollama/ollama/blob/main/docs/modelfile.md#valid-parameters-and-values
OLLAMA_OPTIONS = {
    "temperature": 0.7,  # Controls randomness (higher = more creative, lower = more deterministic)
    # "num_ctx": 4096,     # Example: Set context window size (might depend on model)
    # "top_k": 40,         # Example: Consider top_k most likely tokens
    # "top_p": 0.9,        # Example: Consider tokens comprising top_p probability mass
}

# --- Agent Configuration ---
MAX_ITERATIONS = 5  # Maximum number of tool calls allowed per single user query to prevent loops
CONVERSATION_HISTORY_LIMIT = 6 # Max number of items (turns) to keep in short-term history

# --- Playwright Tool Configuration ---
BROWSER_TYPE = "chromium"  # Which browser to use: "chromium", "firefox", or "webkit"
BROWSER_HEADLESS = True    # Run browser without a visible UI window? (True=Invisible, False=Visible for debugging)
BROWSER_USER_AGENT = 'MinimalAgent/0.4 (Mozilla/5.0; Playwright)' # How the browser identifies itself
PAGE_LOAD_TIMEOUT = 25000  # Milliseconds to wait for page navigation to complete (e.g., 25 seconds)
CONTENT_MAX_LENGTH = 4000  # Max characters of text to extract from a webpage (to avoid huge contexts)

# --- Workspace Configuration ---
WORKSPACE_DIR = "./workspace" # Relative path to the main workspace folder

# --- Logging Configuration ---
LOG_LEVEL = logging.INFO  # Minimum level of logs to display (DEBUG, INFO, WARNING, ERROR, CRITICAL)
LOG_FORMAT = '%(asctime)s - %(levelname)s - [%(name)s] - %(message)s' # Format for log messages