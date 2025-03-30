import requests
import json
import re
import logging

# Import necessary to color the output
from colorama import init as colorama_init
from colorama import Fore, Style

# Import necessary functions/variables from other modules
from tool_functions import AVAILABLE_TOOLS, TOOL_DESCRIPTIONS

# Import configuration variables
from config import (
    OLLAMA_BASE_URL,
    OLLAMA_API_ENDPOINT,
    OLLAMA_MODEL,
    OLLAMA_API_TIMEOUT,
    OLLAMA_OPTIONS,
    MAX_ITERATIONS,
    LOG_LEVEL,
    LOG_FORMAT,
    BROWSER_TYPE,
    BROWSER_HEADLESS
)

# Configure logging (colorama doesn't easily color standard logging via basicConfig)
logging.basicConfig(level=LOG_LEVEL, format=LOG_FORMAT)
logger = logging.getLogger(__name__) # Use module name for logger

# Construct the full API URL
OLLAMA_FULL_URL = OLLAMA_BASE_URL.rstrip('/') + '/' + OLLAMA_API_ENDPOINT.lstrip('/')

# --- LLM Interaction (call_ollama - unchanged) ---
def call_ollama(prompt: str, context_history: list = None) -> str:
    # ... (function content remains the same)
    """Sends a prompt to the OLLAMA API and gets a response using config settings."""
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": OLLAMA_OPTIONS,
    }
    logger.debug(f"--- Sending Prompt to Ollama ({OLLAMA_MODEL}) ---")
    logger.debug(f"Prompt Snippet:\n{prompt[:500]}...\n-----------------------------")

    try:
        response = requests.post(OLLAMA_FULL_URL, json=payload, timeout=OLLAMA_API_TIMEOUT)
        response.raise_for_status()
        response_data = response.json()
        llm_response = response_data.get("response", "").strip()
        logger.debug(f"--- Received Response from Ollama ---\n{llm_response[:500]}...\n-----------------------------")
        return llm_response
    except requests.exceptions.Timeout:
         logger.error(f"Error calling Ollama API: Request timed out after {OLLAMA_API_TIMEOUT} seconds.")
         return f"Error: Ollama API request timed out. The model might be taking too long to respond, or the network is slow."
    except requests.exceptions.RequestException as e:
        logger.error(f"Error calling Ollama API: {e}")
        return f"Error: Could not connect to the Ollama API at {OLLAMA_FULL_URL}. Is Ollama running? Details: {e}"
    except json.JSONDecodeError as e:
        logger.error(f"Error decoding Ollama response: {e}\nResponse text: {getattr(response, 'text', 'N/A')}")
        return "Error: Received invalid JSON response from Ollama."
    except Exception as e:
        logger.error(f"Unexpected error calling Ollama: {e}", exc_info=True)
        return "Error: An unexpected error occurred while communicating with Ollama."

# --- Tool Parsing (parse_tool_call - unchanged) ---
def parse_tool_call(llm_output: str):
    # ... (function content remains the same)
    """Parses the LLM output for a tool call."""
    match = re.search(r'TOOL_CALL:\s*(\w+)\(url="([^"]*)"\)', llm_output)
    if match:
        function_name = match.group(1)
        url = match.group(2)
        if function_name in AVAILABLE_TOOLS:
            logger.info(f"Detected tool call: {function_name} with url='{url}'")
            return function_name, {"url": url}
        else:
            logger.warning(f"LLM tried to call unknown tool: {function_name}")
            return None, None
    return None, None

# --- Tool Execution (execute_tool - unchanged from previous version) ---
def execute_tool(function_name: str, args: dict):
    # ... (function content remains the same, including the added log)
    """Executes the specified tool function with the given arguments."""
    if function_name in AVAILABLE_TOOLS:
        logger.info(f"Executing tool: '{function_name}' with args: {args}")
        tool_function = AVAILABLE_TOOLS[function_name]
        try:
            result = tool_function(**args)
            return result
        except Exception as e:
            logger.error(f"Error executing tool '{function_name}' with args {args}: {e}", exc_info=True)
            return f"Error: Failed to execute tool '{function_name}'."
    else:
        logger.error(f"Attempted to execute unknown tool: '{function_name}'")
        return f"Error: Tool '{function_name}' not found."

# --- System Prompt (get_system_prompt - unchanged) ---
def get_system_prompt():
    # ... (function content remains the same)
    """Constructs the system prompt telling the LLM how to behave and use tools."""
    return f"""You are a helpful AI assistant. Your goal is to answer the user's query.
You have access to the following tools:
{TOOL_DESCRIPTIONS}

To use a tool, respond ONLY with the following format ON A SINGLE LINE:
TOOL_CALL: function_name(arg_name="value")

Example:
TOOL_CALL: fetch_web_content(url="https://example.com")

After you make a tool call, I will execute the tool and provide you with the result in the format:
TOOL_RESULT: [Result of the tool execution]

You should then use this result to formulate your final answer to the user's original query.
If you can answer the query directly without using a tool, just provide the answer.
Do not include explanations about *why* you are calling the tool in the TOOL_CALL line itself. Just make the call.
If a tool execution results in an error, acknowledge the error and try to proceed or inform the user you couldn't retrieve the information.
Provide your final answer directly to the user. Do not include "TOOL_CALL" or "TOOL_RESULT" in your final response to the user.
"""


# --- Main Agent Loop (run_agent - MODIFIED for color output) ---
def run_agent():
    """Runs the main loop of the agent with colored output."""
    # --- Initialize colorama ---
    # autoreset=True automatically adds Style.RESET_ALL after each print()
    colorama_init(autoreset=True)
    # --- End colorama init ---

    logger.info(f"Initializing agent with model: {OLLAMA_MODEL} on {OLLAMA_FULL_URL}")
    logger.info(f"Max iterations: {MAX_ITERATIONS}, Browser: {BROWSER_TYPE} ({'Headless' if BROWSER_HEADLESS else 'Visible'})")

    # --- Use colorama for initial print ---
    print(f"{Style.BRIGHT}Minimal Agent Initialized (using Playwright/{BROWSER_TYPE} & Ollama/{OLLAMA_MODEL}). Ask me anything. Type 'quit' to exit.")
    # --- End initial print modification ---

    system_prompt = get_system_prompt()
    conversation_history = []

    while True:
        try:
            # --- Use colorama for the input prompt ---
            user_query = input(f"{Fore.GREEN}You: {Style.RESET_ALL}") # Need reset here as input() doesn't auto-reset
            # --- End input prompt modification ---
        except EOFError:
             # --- Optional: color the exit message ---
             print(f"\n{Style.DIM}Exiting.")
             # --- End exit message ---
             break
        if user_query.lower() == 'quit':
            break
        if not user_query:
            continue

        current_prompt = f"{system_prompt}\n\nPrevious Conversation:\n"
        if conversation_history:
             history_context = "\n".join(conversation_history[-2:])
             current_prompt += history_context + "\n"
             logger.debug(f"Adding context:\n{history_context}")

        current_prompt += f"\nCurrent User Query: {user_query}\n\nAssistant:"

        iterations = 0
        while iterations < MAX_ITERATIONS:
            iterations += 1
            logger.info(f"--- Iteration {iterations}/{MAX_ITERATIONS} ---")

            llm_response = call_ollama(current_prompt)
            current_turn_llm_output = f"Assistant (Internal Thought/Action): {llm_response}"

            function_name, args = parse_tool_call(llm_response)

            if function_name and args:
                tool_result = execute_tool(function_name, args)
                logger.info(f"Result from tool '{function_name}': {tool_result[:200]}...")

                tool_result_text = f"TOOL_RESULT: {tool_result}"
                current_prompt += f"{llm_response}\n{tool_result_text}\nAssistant:"
                conversation_history.append(current_turn_llm_output)
                conversation_history.append(tool_result_text)

            else:
                # --- Use colorama for the Agent's final response ---
                # Using BRIGHT style to make the "Agent:" label stand out more
                print(f"{Fore.CYAN}{Style.BRIGHT}Agent:{Style.NORMAL} {llm_response}")
                # --- End agent response modification ---
                conversation_history.append(f"Agent (Final Answer): {llm_response}")
                break
        else:
            logger.warning(f"Reached maximum iterations ({MAX_ITERATIONS}) for query: {user_query}")
            # --- Optional: Color the max iterations warning ---
            print(f"{Fore.YELLOW}Agent: Reached maximum tool iterations. Unable to fully process the request with tools.")
            # --- End max iterations warning modification ---
            conversation_history.append(f"Agent: Reached max iterations ({MAX_ITERATIONS}).")

        history_limit = 6
        if len(conversation_history) > history_limit:
            logger.debug(f"Trimming conversation history from {len(conversation_history)} items")
            conversation_history = conversation_history[-history_limit:]


if __name__ == "__main__":
    run_agent()