# config.py
import logging

# --- Ollama / LLM Configuration ---
OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_API_ENDPOINT = "/api/chat" # Keep using generate for now
OLLAMA_PLANNER_MODEL = "mistral" # Model potentially good at planning
OLLAMA_EXECUTOR_MODEL = "mistral" # Model for executing steps (can be same or different)
OLLAMA_API_TIMEOUT = 90
OLLAMA_OPTIONS = {
    "temperature": 0.5,  # Controls randomness (higher = more creative, lower = more deterministic)
    # "num_ctx": 4096,     # Example: Set context window size (might depend on model)
    # "top_k": 40,         # Example: Consider top_k most likely tokens
    # "top_p": 0.9,        # Example: Consider tokens comprising top_p probability mass
}

# --- Agent Configuration ---
MAX_EXECUTION_ITERATIONS = 10 # Max steps in a plan to execute
MAX_LLM_RETRIES = 2 # How many times to retry LLM call on failure
CONVERSATION_HISTORY_LIMIT = 6 # For potential chat history display later

# --- Workspace Configuration ---
WORKSPACE_DIR = "./workspace" # Relative path to the main workspace folder

# --- Tool Configuration ---
# (Browser settings moved closer to web_tools, but can stay here too)
BROWSER_TYPE = "chromium"
BROWSER_HEADLESS = True
BROWSER_USER_AGENT = 'PlannerExecutorAgent/0.1 (Mozilla/5.0; Playwright)'
PAGE_LOAD_TIMEOUT = 25000
CONTENT_MAX_LENGTH = 4000

# --- Logging Configuration ---
LOG_LEVEL = logging.INFO
LOG_FORMAT = '%(asctime)s - %(levelname)s - [%(name)s] - %(message)s'