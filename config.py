# config.py
import logging
import os # Import os if not already there

# --- Ollama / LLM Configuration ---
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434") # Example using env var
OLLAMA_API_ENDPOINT = "/api/chat"
OLLAMA_PLANNER_MODEL = os.getenv("OLLAMA_PLANNER_MODEL", "mistral")
OLLAMA_EXECUTOR_MODEL = os.getenv("OLLAMA_EXECUTOR_MODEL", "mistral")
OLLAMA_API_TIMEOUT = 300
OLLAMA_OPTIONS = {
    "temperature": 0.5,
    # "num_ctx": 4096,
    # "top_k": 40,
    # "top_p": 0.9,
}

# --- Agent Configuration ---
MAX_EXECUTION_ITERATIONS = 10
MAX_LLM_RETRIES = 2
CONVERSATION_HISTORY_LIMIT = 6

# --- Workspace Configuration ---
WORKSPACE_DIR = "./workspace"

# --- Tool Configuration ---

# -- Web Search Tool Settings --
DEFAULT_SEARCH_RESULTS = 5 # Default number if not specified in plan
MAX_SEARCH_RESULTS = 15    # Safety cap on number of results

# -- Web Fetch (Playwright) Settings --
BROWSER_TYPE = "chromium"
BROWSER_HEADLESS = True
BROWSER_USER_AGENT = 'PlannerExecutorAgent/0.1 (Mozilla/5.0; Playwright)'
PAGE_LOAD_TIMEOUT = 25000
CONTENT_MAX_LENGTH = 4000 # Max chars for fetched web page content

# --- Logging Configuration ---
LOG_LEVEL_STR = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_LEVEL = getattr(logging, LOG_LEVEL_STR, logging.INFO)
LOG_FORMAT = '%(asctime)s - %(levelname)s - [%(name)s] - %(message)s'
