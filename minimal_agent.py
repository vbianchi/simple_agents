# minimal_agent.py
import requests
import json
import re
import logging
import os
import datetime
import ast # For safer evaluation of simple literals if needed in parser
from pathlib import Path

# Colorama for colored output
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
    CONVERSATION_HISTORY_LIMIT, # Added limit config
    LOG_LEVEL,
    LOG_FORMAT,
    BROWSER_TYPE,
    BROWSER_HEADLESS,
    WORKSPACE_DIR
)

# Configure logging using settings from config.py
logging.basicConfig(level=LOG_LEVEL, format=LOG_FORMAT)
logger = logging.getLogger(__name__) # Use module name for logger

# Construct the full API URL
OLLAMA_FULL_URL = OLLAMA_BASE_URL.rstrip('/') + '/' + OLLAMA_API_ENDPOINT.lstrip('/')

# --- LLM Interaction ---
def call_ollama(prompt: str, context_history: list = None) -> str:
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
        # Clean up potential LLM tendency to wrap response in quotes
        if llm_response.startswith('"') and llm_response.endswith('"'):
            llm_response = llm_response[1:-1].replace('\\"', '"').replace("\\n", "\n")
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


# --- Tool Argument Parsing Helper ---
def _parse_tool_args(args_string: str) -> dict:
    """Parses the arguments string from a tool call into a dictionary."""
    args = {}
    # Regex to find key="value" pairs. Handles basic escaped quotes inside values.
    # Matches key= followed by "..." or '...' or an unquoted value.
    pattern = re.compile(r'(\w+)\s*=\s*("((?:[^"\\]|\\.)*)"|\'((?:[^\'\\]|\\.)*)\'|([\w\.\-\/]+))') # Added / to unquoted allow simple paths (handle with care)
    pos = 0
    while pos < len(args_string):
        match = pattern.match(args_string, pos)
        if match:
            key = match.group(1)
            # Find the matched value group (double quote, single quote, or unquoted)
            value = match.group(3) if match.group(2) and match.group(2).startswith('"') else \
                    match.group(4) if match.group(2) and match.group(2).startswith("'") else \
                    match.group(6) # Unquoted value group

            if value is not None:
                # Decode basic escape sequences (\n, \t, \", \', \\) for quoted strings
                if match.group(2) and (match.group(2).startswith('"') or match.group(2).startswith("'")):
                    try:
                        args[key] = bytes(value, "utf-8").decode("unicode_escape")
                    except Exception as decode_err:
                        logger.warning(f"Could not decode escape sequences for key '{key}', value: '{value}'. Using raw value. Error: {decode_err}")
                        args[key] = value # Fallback
                else: # Unquoted value - keep as string (safer than literal_eval)
                     args[key] = value

                pos = match.end() # Move position past the matched argument
                # Consume trailing comma and whitespace if present
                comma_match = re.match(r'\s*,\s*', args_string[pos:])
                if comma_match:
                    pos += comma_match.end()
            else:
                # This shouldn't happen with the current regex if it matches, but good for safety
                logger.warning(f"Could not extract value for key '{key}' at position {pos} in args string: {args_string}")
                pos += 1 # Move forward to avoid infinite loop
        else:
            # No match found, break or log unexpected char? For now, just move on.
            logger.debug(f"No key-value match found at position {pos} in args string: {args_string}")
            break # Stop parsing if pattern doesn't match

    logger.debug(f"Parsed arguments: {args}")
    return args


# --- Tool Parsing ---
def parse_tool_call(llm_output: str):
    """
    Parses the LLM output for a tool call in the format:
    TOOL_CALL: function_name(key1="value1", key2="value2")
    Returns (function_name, args_dict) or (None, None).
    """
    # Regex to capture function name and the argument string within parentheses
    match = re.search(r'TOOL_CALL:\s*([\w_]+)\s*\((.*?)\)\s*$', llm_output) # Allow underscores in func name, match till end $
    if match:
        function_name = match.group(1).strip()
        args_string = match.group(2).strip()
        if function_name in AVAILABLE_TOOLS:
            logger.debug(f"Parsing args for tool '{function_name}' from string: '{args_string}'")
            args_dict = _parse_tool_args(args_string) # Use the helper function
            # Simple validation: Check if any args were parsed if the string wasn't empty
            if not args_dict and args_string:
                 logger.warning(f"Argument string '{args_string}' provided for tool '{function_name}' but no arguments were successfully parsed.")
                 # Decide how to handle: return None, or proceed with empty args? Proceeding cautiously.
                 # return None, None # Option: Treat as parse failure

            logger.info(f"Detected tool call: {function_name} with args: {args_dict}")
            return function_name, args_dict
        else:
            logger.warning(f"LLM tried to call unknown tool: {function_name}")
            return None, None
    return None, None


# --- Tool Execution ---
def execute_tool(function_name: str, args: dict, session_path: Path): # Added session_path
    """Executes the specified tool function with the given arguments and session path."""
    if function_name in AVAILABLE_TOOLS:
        logger.info(f"Executing tool: '{function_name}' with args: {args}")
        tool_function = AVAILABLE_TOOLS[function_name]
        try:
            # Prepare args to potentially include session_path if the tool accepts it
            import inspect
            sig = inspect.signature(tool_function)
            if 'session_path' in sig.parameters:
                tool_args = {**args, 'session_path': session_path}
                logger.debug(f"Passing session_path to tool '{function_name}'")
            else:
                tool_args = args # Tool doesn't accept session_path
                logger.debug(f"Tool '{function_name}' does not accept session_path argument.")

            result = tool_function(**tool_args)
            return result

        except TypeError as e:
            # This might catch cases where required args are missing, etc.
             logger.error(f"TypeError executing tool '{function_name}' with args {args}: {e}", exc_info=True)
             return f"Error: Failed to execute tool '{function_name}' due to incorrect arguments. Usage Error: {e}"
        except Exception as e:
            logger.error(f"Error executing tool '{function_name}' with args {args}: {e}", exc_info=True)
            return f"Error: Failed to execute tool '{function_name}'. Details: {e}"
    else:
        logger.error(f"Attempted to execute unknown tool: '{function_name}'")
        return f"Error: Tool '{function_name}' not found."


# --- System Prompt ---
def get_system_prompt():
    """Constructs the system prompt telling the LLM how to behave and use tools."""
    # TOOL_DESCRIPTIONS is imported from tool_functions and includes the new tool
    return f"""You are a helpful AI assistant. Your goal is to answer the user's query using available tools when necessary.
You have access to the following tools:
{TOOL_DESCRIPTIONS}

To use a tool, respond ONLY with the following format ON A SINGLE LINE:
TOOL_CALL: function_name(parameter1="value1", parameter2="value2", ...)

Parameter values MUST be enclosed in double quotes. Use standard escape sequences like \\n for newlines and \\" for literal quotes within the string value if needed. String values can span multiple lines using \\n.

Examples:
TOOL_CALL: fetch_web_content(url="https://example.com")
TOOL_CALL: write_file(filename="summary.txt", content="This is the first line.\\nThis is the second line.")

After you make a tool call, I will execute the tool and provide you with the result in the format:
TOOL_RESULT: [Result of the tool execution]

You should then use this result (e.g., the text fetched, or the success/error message from write_file) to formulate your final answer to the user's original query.
If you can answer the query directly without using a tool, just provide the answer.
If a tool execution results in an error, acknowledge the error and try to proceed or inform the user you couldn't retrieve the information.
Provide your final answer directly to the user. Do not include "TOOL_CALL" or "TOOL_RESULT" in your final response to the user.
"""


# --- Main Agent Loop ---
def run_agent():
    """Runs the main loop of the agent with session folder and colored output."""
    colorama_init(autoreset=True) # Initialize colorama

    # --- Create Workspace and Session Folder ---
    workspace_path = Path(WORKSPACE_DIR)
    session_path = None # Initialize session_path
    try:
        workspace_path.mkdir(parents=True, exist_ok=True)
        session_timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        session_path = workspace_path / f"session_{session_timestamp}"
        session_path.mkdir(exist_ok=True)
        logger.info(f"Created session folder: {session_path.resolve()}")
    except OSError as e:
        logger.error(f"Failed to create workspace or session directory: {e}", exc_info=True)
        print(f"{Fore.RED}Error: Could not create necessary directories in '{WORKSPACE_DIR}'. Exiting.")
        return # Exit if we can't create the folder
    # --- End Session Folder Creation ---

    logger.info(f"Initializing agent with model: {OLLAMA_MODEL} on {OLLAMA_FULL_URL}")
    logger.info(f"Max iterations: {MAX_ITERATIONS}, Browser: {BROWSER_TYPE} ({'Headless' if BROWSER_HEADLESS else 'Visible'})")
    print(f"{Style.BRIGHT}Minimal Agent Initialized. Session workspace: {session_path.resolve()}") # Show session path
    print(f"{Style.BRIGHT}Ask me anything. Type 'quit' to exit.")

    system_prompt = get_system_prompt()
    conversation_history = []

    while True:
        try:
            user_query = input(f"{Fore.GREEN}You: {Style.RESET_ALL}")
        except EOFError:
             print(f"\n{Style.DIM}Exiting.")
             break
        if user_query.lower() == 'quit':
            break
        if not user_query:
            continue

        current_prompt = f"{system_prompt}\n\n"
        # Add conversation history to prompt
        if conversation_history:
             history_context = "\n".join(conversation_history) # Include full recent history
             current_prompt += f"Previous Conversation Context:\n{history_context}\n\n"
             logger.debug(f"Adding context:\n{history_context}")

        current_prompt += f"Current User Query: {user_query}\n\nAssistant:"

        iterations = 0
        while iterations < MAX_ITERATIONS:
            iterations += 1
            logger.info(f"--- Iteration {iterations}/{MAX_ITERATIONS} ---")

            llm_response = call_ollama(current_prompt)
            # Log the raw LLM response before parsing tool calls
            logger.debug(f"LLM raw response (Iteration {iterations}): {llm_response}")
            current_turn_llm_output = f"Assistant (Internal Thought/Action): {llm_response}" # Store for history

            function_name, args = parse_tool_call(llm_response)

            if function_name and args is not None: # Check args is not None (parse success)
                # Execute the tool, passing the session_path
                tool_result = execute_tool(function_name, args, session_path)
                logger.info(f"Result from tool '{function_name}': {tool_result[:300]}...") # Increased snippet length

                tool_result_text = f"TOOL_RESULT: {tool_result}"
                # Add LLM's action and tool result to context for the next LLM call *within this turn*
                current_prompt += f"{llm_response}\n{tool_result_text}\nAssistant:"
                # Append *this turn's* LLM output and tool result to the main history
                conversation_history.append(current_turn_llm_output)
                conversation_history.append(tool_result_text)
                # Continue the inner loop to let LLM process the tool result

            else:
                # No tool call detected or parse failed, assume final answer for this query
                print(f"{Fore.CYAN}{Style.BRIGHT}Agent:{Style.NORMAL} {llm_response}")
                # Append user query and final answer to history for the *next* user query
                conversation_history.append(f"User: {user_query}")
                conversation_history.append(f"Agent (Final Answer): {llm_response}")
                break # Exit the inner iteration loop for this query
        else:
            # Hit max iterations for this query
            logger.warning(f"Reached maximum iterations ({MAX_ITERATIONS}) for query: {user_query}")
            print(f"{Fore.YELLOW}Agent: Reached maximum tool iterations. Unable to fully process the request with tools.")
            # Append failure state to history
            conversation_history.append(f"User: {user_query}")
            conversation_history.append(f"Agent: Reached max iterations ({MAX_ITERATIONS}). Could not complete request.")

        # Trim conversation history to the configured limit
        if len(conversation_history) > CONVERSATION_HISTORY_LIMIT:
            logger.debug(f"Trimming conversation history from {len(conversation_history)} items to {CONVERSATION_HISTORY_LIMIT}")
            conversation_history = conversation_history[-CONVERSATION_HISTORY_LIMIT:]


if __name__ == "__main__":
    run_agent()