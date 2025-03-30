# minimal_agent.py
import requests
import json
import re
import logging
import os
import datetime
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
    CONVERSATION_HISTORY_LIMIT,
    LOG_LEVEL,
    LOG_FORMAT,
    BROWSER_TYPE,
    BROWSER_HEADLESS,
    WORKSPACE_DIR
)

# Configure logging
logging.basicConfig(level=LOG_LEVEL, format=LOG_FORMAT)
logger = logging.getLogger(__name__)

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
    logger.debug(f"Prompt Snippet:\n{prompt[:1000]}...\n-----------------------------")

    try:
        response = requests.post(OLLAMA_FULL_URL, json=payload, timeout=OLLAMA_API_TIMEOUT)
        response.raise_for_status()
        response_data = response.json()
        llm_response = response_data.get("response", "").strip()

        # Minimal cleaning: Remove potential ```json markdown wrappers if Action: is present
        if re.search(r"^[ \t]*Action:", llm_response, re.IGNORECASE | re.MULTILINE):
            action_match_check = re.search(r"Action:\s*(?:```json\s*)?({.*?})\s*(?:```)?\s*$", llm_response, re.IGNORECASE | re.DOTALL)
            if action_match_check:
                 json_part = action_match_check.group(1)
                 # Reconstruct *only* the essential Action part for the parser
                 llm_response = f"Action:\n{json_part}"
            else:
                 # If Action: exists but no valid JSON follows, keep raw for parser to fail
                 pass # Keep llm_response as is

        logger.debug(f"--- Received RAW Response from Ollama (Cleaned slightly for Action) ---\n{llm_response[:1000]}...\n-----------------------------")
        return llm_response
    except requests.exceptions.Timeout:
         logger.error(f"Error calling Ollama API: Request timed out after {OLLAMA_API_TIMEOUT} seconds.")
         return f"Error: Ollama API request timed out."
    except requests.exceptions.RequestException as e:
        logger.error(f"Error calling Ollama API: {e}")
        if 'Connection refused' in str(e):
             return f"Error: Connection to Ollama refused at {OLLAMA_FULL_URL}. Is Ollama running?"
        return f"Error: Could not connect to the Ollama API at {OLLAMA_FULL_URL}. Details: {e}"
    except json.JSONDecodeError as e:
        logger.error(f"Error decoding initial Ollama API response: {e}\nResponse text: {getattr(response, 'text', 'N/A')}")
        return "Error: Received invalid JSON response structure from Ollama API itself."
    except Exception as e:
        logger.error(f"Unexpected error calling Ollama: {e}", exc_info=True)
        return "Error: An unexpected error occurred while communicating with Ollama."


# --- Tool Parsing (Action JSON Only Version) ---
def parse_tool_call(llm_output: str):
    """
    Attempts to parse the LLM output for an Action JSON block:
    Action:
    {
      "tool_name": "function_name",
      "arguments": {"param1": "value1"}
    }
    Extracts and parses the JSON from the Action part.
    Returns (function_name, args_dict) or (None, None).
    """
    action_json_str = None

    # Regex to find "Action:" followed by potential whitespace and then a JSON object {}
    # Makes the JSON part mandatory if Action: is found at the start of a line
    action_match = re.search(r"^[ \t]*Action:\s*({.*?})\s*$", llm_output, re.IGNORECASE | re.MULTILINE | re.DOTALL)

    if action_match:
        action_json_str = action_match.group(1).strip() # Group 1 captures the JSON object {}
        logger.debug(f"Found Action JSON String: {action_json_str}")
    else:
        logger.debug("LLM output does not match 'Action: {json}' format.")
        return None, None

    # Parse the extracted JSON string
    try:
        # Ensure extracted string looks like JSON before loading
        if not (action_json_str.startswith('{') and action_json_str.endswith('}')):
             logger.warning(f"Extracted Action string does not look like JSON object: {action_json_str}")
             return None, None

        logger.debug(f"Attempting to parse JSON: {action_json_str}")
        tool_data = json.loads(action_json_str)

        # --- Validation ---
        if not isinstance(tool_data, dict):
            logger.warning(f"Parsed JSON from Action is not a dictionary: {tool_data}")
            return None, None
        function_name = tool_data.get("tool_name")
        args_dict = tool_data.get("arguments")
        if not isinstance(function_name, str) or not function_name:
            logger.warning(f"Missing or invalid 'tool_name' (string) in Action JSON: {tool_data}")
            return None, None
        if not isinstance(args_dict, dict):
            if args_dict is None:
                logger.debug(f"Missing 'arguments' field for tool '{function_name}', assuming no arguments.")
                args_dict = {} # Allow missing args field for no-arg tools
            else:
                logger.warning(f"Invalid 'arguments' (must be object/dict) in Action JSON: {tool_data}")
                return None, None
        if function_name in AVAILABLE_TOOLS:
            logger.info(f"Detected tool call via Action JSON: {function_name} with args: {args_dict}")
            return function_name, args_dict
        else:
            logger.warning(f"LLM called unknown tool via Action JSON: {function_name}")
            return None, None
        # --- End Validation ---

    except json.JSONDecodeError as e:
        logger.warning(f"Failed to parse JSON from Action section. Error: {e}. JSON String tried: {action_json_str}")
        return None, None
    except Exception as e:
        logger.error(f"Unexpected error parsing Action JSON: {e}", exc_info=True)
        return None, None


# --- Tool Execution ---
def execute_tool(function_name: str, args: dict, session_path: Path):
    """Executes the specified tool function with the given arguments and session path."""
    if function_name in AVAILABLE_TOOLS:
        logger.info(f"Executing tool: '{function_name}' with args: {args}")
        tool_function = AVAILABLE_TOOLS[function_name]
        try:
            import inspect
            sig = inspect.signature(tool_function)
            tool_args = args.copy()
            if 'session_path' in sig.parameters:
                tool_args['session_path'] = session_path
                logger.debug(f"Passing session_path to tool '{function_name}'")
            elif 'session_path' in args:
                 logger.warning(f"Tool '{function_name}' received unexpected 'session_path' in args. Ignoring.")
                 del tool_args['session_path']

            required_params = {
                p.name for p in sig.parameters.values()
                if p.default == inspect.Parameter.empty and p.name != 'session_path'
            }
            missing_args = required_params - tool_args.keys()
            if missing_args:
                 logger.error(f"Missing required arguments for tool '{function_name}': {missing_args}")
                 return f"Error: Missing required arguments for tool '{function_name}': {', '.join(missing_args)}"

            result = tool_function(**tool_args)
            return result

        except TypeError as e:
             logger.error(f"TypeError executing tool '{function_name}' with final args {tool_args}: {e}", exc_info=True)
             return f"Error: Failed to execute tool '{function_name}' due to argument mismatch. Usage Error: {e}"
        except Exception as e:
            logger.error(f"Unexpected error during execution of tool '{function_name}' with args {tool_args}: {e}", exc_info=True)
            return f"Error: Failed during execution of tool '{function_name}'. Details: {e}"
    else:
        logger.error(f"Attempted to execute unknown tool: '{function_name}'")
        return f"Error: Tool '{function_name}' not found."


# --- System Prompt (Action JSON Only Version - NO THOUGHT) ---
def get_system_prompt():
    """Constructs the system prompt telling the LLM how to use tools via Action: JSON only."""
    # This version removes the "Thought:" step.
    # Double braces {{ }} are needed to escape literal braces inside f-strings.
    return f"""You are a precise and methodical AI assistant. Your goal is to fulfill the user's request by following instructions exactly.

**Core Instructions:**

1.  **Analyze Request & Prioritize Direct Answer:** First, determine if you can answer the user's query directly using your internal knowledge. If yes, provide the answer immediately and STOP.
2.  **Identify Need for Tools & Plan FIRST Step:** If tools are needed, identify the single, first logical tool call required to start fulfilling the request.
3.  **Execute Single Tool Call (If Necessary):** If your plan requires a tool for the current step, your response **MUST** follow this EXACT structure, with 'Action:' starting on a new line, followed immediately by the JSON object on the subsequent lines. **Nothing else.** Ensure the JSON is valid.

    Action:
    {{
      "tool_name": "function_name",
      "arguments": {{
        "parameter1": "value1",
        "parameter2": "value2"
      }}
    }}

    - Replace `"function_name"` with the actual name of the tool to use from the list below.
    - The `"arguments"` value MUST be a JSON object containing parameter-name/value pairs for the tool.
    - Parameter values MUST be valid JSON strings (properly quoted and escaped, e.g., `\\n` for newline, `\\"` for quote). Use strings even for URLs.
    - **DO NOT** add any explanation or conversational text. Your entire response must be just the `Action:` line and the JSON block.
4.  **Await Tool Result:** After you issue a valid Action JSON, I will execute the tool and provide the result:
    `TOOL_RESULT: [Result of the tool execution]`
5.  **Process Result & Determine Next Action:** Analyze the `TOOL_RESULT`.
    *   **If SUCCESS and MORE steps needed:** Determine the *next single logical step*. If it requires another tool, respond using the `Action: {{JSON}}` format again (Instruction 3).
    *   **If SUCCESS and task COMPLETE:** The `TOOL_RESULT` fulfilled the final step. Your response **MUST** be the final conversational answer to the user. **DO NOT** output Action/JSON.
    *   **If ERROR:** Acknowledge the error conversationally to the user. Do not output Action/JSON unless you have a clear alternative tool call plan.
6.  **Complete the FULL Request:** Ensure you complete *all* parts of the user's original request sequentially. If they asked to fetch information *and* save it, you MUST perform both steps using separate `Action: {{JSON}}` responses.

**Available Tools:**
{TOOL_DESCRIPTIONS}

**Example Multi-Step Flow (User: "Summarize bbc.com and save to bbc_summary.txt"):**

*Your First Response:*
Action:
{{
  "tool_name": "fetch_web_content",
  "arguments": {{
    "url": "https://www.bbc.com"
  }}
}}

*My Response:*
`TOOL_RESULT: [Text content from bbc.com...]`

*Your Second Response:*
Action:
{{
  "tool_name": "write_file",
  "arguments": {{
    "filename": "bbc_summary.txt",
    "content": "[Summary text based on TOOL_RESULT, properly escaped...]"
  }}
}}

*My Response:*
`TOOL_RESULT: Success: File 'bbc_summary.txt' written successfully...`

*Your Third Response:*
OK. I have fetched the content from bbc.com and saved the summary to the file bbc_summary.txt in the session workspace.

**CRITICAL:** Only use the `Action: {{JSON}}` format when a tool is required for the *next step*. Provide only the final conversational answer when the entire user request is complete. Do not output conversational text when an Action JSON is expected.
"""


# --- Main Agent Loop ---
def run_agent():
    """Runs the main loop of the agent with session folder, colored output, Action:JSON tool calls."""
    colorama_init(autoreset=True)

    workspace_path = Path(WORKSPACE_DIR)
    session_path = None
    try:
        workspace_path.mkdir(parents=True, exist_ok=True)
        session_timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        session_path = workspace_path / f"session_{session_timestamp}"
        session_path.mkdir(exist_ok=True)
        logger.info(f"Created session folder: {session_path.resolve()}")
    except OSError as e:
        logger.error(f"Failed to create workspace or session directory: {e}", exc_info=True)
        print(f"{Fore.RED}Error: Could not create necessary directories in '{WORKSPACE_DIR}'. Exiting.{Style.RESET_ALL}")
        return

    logger.info(f"Initializing agent with model: {OLLAMA_MODEL} on {OLLAMA_FULL_URL}")
    logger.info(f"Max iterations: {MAX_ITERATIONS}, Browser: {BROWSER_TYPE} ({'Headless' if BROWSER_HEADLESS else 'Visible'})")
    print(f"{Style.BRIGHT}Minimal Agent Initialized. Session workspace: {session_path.resolve()}")
    print(f"{Style.BRIGHT}Ask me anything. Type 'quit' to exit.")

    system_prompt = get_system_prompt()
    conversation_history = []

    while True:
        try:
            user_query = input(f"{Fore.GREEN}You: {Style.RESET_ALL}")
        except EOFError:
             print(f"\n{Style.DIM}Exiting.{Style.RESET_ALL}")
             break
        if user_query.lower() == 'quit':
            break
        if not user_query:
            continue

        current_turn_history = [f"User: {user_query}"]
        current_prompt = f"{system_prompt}\n\n"
        if conversation_history:
             history_context = "\n".join(conversation_history)
             current_prompt += f"Previous Conversation Context:\n{history_context}\n\n"

        current_prompt += f"Current User Query: {user_query}\n\nAssistant:"

        iterations = 0
        while iterations < MAX_ITERATIONS:
            iterations += 1
            logger.info(f"--- Turn {len(conversation_history)//2 + 1} / Iteration {iterations}/{MAX_ITERATIONS} ---")

            llm_response = call_ollama(current_prompt)
            logger.debug(f"LLM raw response (Iteration {iterations}): {llm_response}")
            current_turn_history.append(f"Assistant (Action/Response): {llm_response}")

            # --- Attempt to parse the response for Action: JSON ---
            function_name, args = parse_tool_call(llm_response) # Looks for Action: {JSON}

            if function_name and args is not None: # Valid Action JSON detected and parsed
                tool_result = execute_tool(function_name, args, session_path)
                logger.info(f"Result from tool '{function_name}': {tool_result[:300]}...")

                tool_result_text = f"TOOL_RESULT: {tool_result}"
                # Add the ORIGINAL llm_response (Action + JSON) and the tool result to the prompt context
                current_prompt += f"{llm_response}\n{tool_result_text}\nAssistant:"
                current_turn_history.append(tool_result_text)
                # Continue inner loop

            else:
                # No valid Action JSON detected by the parser
                final_answer = llm_response

                # Check if the response contained Action: but failed parsing
                if re.search(r"^[ \t]*Action:", llm_response, re.IGNORECASE | re.MULTILINE):
                     logger.warning(f"LLM response contained 'Action:' but failed JSON parsing/validation. Response: {final_answer}")
                     print(f"{Fore.YELLOW}Agent (Hint): LLM Action formatting/validation failed.{Style.RESET_ALL}")

                print(f"{Fore.CYAN}{Style.BRIGHT}Agent:{Style.NORMAL} {final_answer}{Style.RESET_ALL}")
                conversation_history.extend(current_turn_history)
                if not current_turn_history[-1].startswith("TOOL_RESULT:"):
                     if len(conversation_history) == 0 or not conversation_history[-1].endswith(final_answer):
                          conversation_history.append(f"Agent (Final Answer): {final_answer}")
                break # Exit inner loop
        else:
            # Max iterations handling
            logger.warning(f"Reached maximum iterations ({MAX_ITERATIONS}) for query: {user_query}")
            print(f"{Fore.YELLOW}Agent: Reached maximum tool iterations. Unable to fully process the request with tools.{Style.RESET_ALL}")
            conversation_history.extend(current_turn_history)
            conversation_history.append(f"Agent: Reached max iterations ({MAX_ITERATIONS}).")

        # History trimming
        if len(conversation_history) > CONVERSATION_HISTORY_LIMIT:
            items_to_remove = len(conversation_history) - CONVERSATION_HISTORY_LIMIT
            if items_to_remove > 0:
                 logger.debug(f"Trimming conversation history from {len(conversation_history)} items")
                 conversation_history = conversation_history[items_to_remove:]


if __name__ == "__main__":
    run_agent()