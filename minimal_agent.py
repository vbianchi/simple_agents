# minimal_agent.py
import requests
import json
import re
import logging
import os
import datetime
import ast
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

# --- LLM Interaction (call_ollama - unchanged) ---
def call_ollama(prompt: str, context_history: list = None) -> str:
    # ... (implementation unchanged) ...
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
        if llm_response.startswith('"') and llm_response.endswith('"'):
             # Basic unquoting and unescaping if LLM wraps output
            try:
                llm_response = json.loads(f'"{llm_response[1:-1]}"') # Use json loads for robustness
            except json.JSONDecodeError:
                 logger.warning("LLM response looked quoted but failed JSON unquoting. Using raw.")
                 # Fallback to simpler unquoting if json fails (less robust for escapes)
                 # llm_response = llm_response[1:-1].replace('\\"', '"').replace("\\n", "\n")
        logger.debug(f"--- Received Response from Ollama ---\n{llm_response[:500]}...\n-----------------------------")
        return llm_response
    except requests.exceptions.Timeout:
         logger.error(f"Error calling Ollama API: Request timed out after {OLLAMA_API_TIMEOUT} seconds.")
         return f"Error: Ollama API request timed out."
    except requests.exceptions.RequestException as e:
        logger.error(f"Error calling Ollama API: {e}")
        return f"Error: Could not connect to the Ollama API at {OLLAMA_FULL_URL}."
    except json.JSONDecodeError as e:
        logger.error(f"Error decoding Ollama response: {e}\nResponse text: {getattr(response, 'text', 'N/A')}")
        return "Error: Received invalid JSON response from Ollama."
    except Exception as e:
        logger.error(f"Unexpected error calling Ollama: {e}", exc_info=True)
        return "Error: An unexpected error occurred while communicating with Ollama."

# --- Tool Argument Parsing Helper (_parse_tool_args - unchanged) ---
def _parse_tool_args(args_string: str) -> dict:
    # ... (implementation unchanged) ...
    args = {}
    pattern = re.compile(r'(\w+)\s*=\s*("((?:[^"\\]|\\.)*)"|\'((?:[^\'\\]|\\.)*)\'|([\w\.\-\/]+))')
    pos = 0
    while pos < len(args_string):
        match = pattern.match(args_string, pos)
        if match:
            key = match.group(1)
            value = match.group(3) if match.group(2) and match.group(2).startswith('"') else \
                    match.group(4) if match.group(2) and match.group(2).startswith("'") else \
                    match.group(6)

            if value is not None:
                if match.group(2) and (match.group(2).startswith('"') or match.group(2).startswith("'")):
                    try:
                        args[key] = bytes(value, "utf-8").decode("unicode_escape")
                    except Exception as decode_err:
                        logger.warning(f"Could not decode escape sequences for key '{key}', value: '{value}'. Using raw value. Error: {decode_err}")
                        args[key] = value
                else:
                     args[key] = value

                pos = match.end()
                comma_match = re.match(r'\s*,\s*', args_string[pos:])
                if comma_match:
                    pos += comma_match.end()
            else:
                logger.warning(f"Could not extract value for key '{key}' at position {pos} in args string: {args_string}")
                pos += 1
        else:
            logger.debug(f"No key-value match found at position {pos} in args string: {args_string}")
            break

    logger.debug(f"Parsed arguments: {args}")
    return args

# --- Tool Parsing (parse_tool_call - unchanged) ---
def parse_tool_call(llm_output: str):
    # ... (implementation unchanged) ...
    match = re.search(r'TOOL_CALL:\s*([\w_]+)\s*\((.*?)\)\s*$', llm_output)
    if match:
        function_name = match.group(1).strip()
        args_string = match.group(2).strip()
        if function_name in AVAILABLE_TOOLS:
            logger.debug(f"Parsing args for tool '{function_name}' from string: '{args_string}'")
            args_dict = _parse_tool_args(args_string)
            if not args_dict and args_string:
                 logger.warning(f"Argument string '{args_string}' provided for tool '{function_name}' but no arguments were parsed.")

            logger.info(f"Detected tool call: {function_name} with args: {args_dict}")
            return function_name, args_dict
        else:
            logger.warning(f"LLM tried to call unknown tool: {function_name}")
            return None, None
    return None, None

# --- Tool Execution (execute_tool - unchanged) ---
def execute_tool(function_name: str, args: dict, session_path: Path):
    # ... (implementation unchanged) ...
    if function_name in AVAILABLE_TOOLS:
        logger.info(f"Executing tool: '{function_name}' with args: {args}")
        tool_function = AVAILABLE_TOOLS[function_name]
        try:
            import inspect
            sig = inspect.signature(tool_function)
            if 'session_path' in sig.parameters:
                tool_args = {**args, 'session_path': session_path}
                logger.debug(f"Passing session_path to tool '{function_name}'")
            else:
                tool_args = args
                logger.debug(f"Tool '{function_name}' does not accept session_path argument.")

            result = tool_function(**tool_args)
            return result

        except TypeError as e:
             logger.error(f"TypeError executing tool '{function_name}' with args {args}: {e}", exc_info=True)
             return f"Error: Failed to execute tool '{function_name}' due to incorrect arguments. Usage Error: {e}"
        except Exception as e:
            logger.error(f"Error executing tool '{function_name}' with args {args}: {e}", exc_info=True)
            return f"Error: Failed to execute tool '{function_name}'. Details: {e}"
    else:
        logger.error(f"Attempted to execute unknown tool: '{function_name}'")
        return f"Error: Tool '{function_name}' not found."

# --- System Prompt (get_system_prompt - REWRITTEN AGAIN) ---
def get_system_prompt():
    """Constructs the system prompt telling the LLM how to behave and use tools."""
    # This version adds explicit instructions for post-TOOL_RESULT handling
    return f"""You are a precise and methodical AI assistant. Your goal is to fulfill the user's request by following instructions exactly.

**Core Instructions:**

1.  **Analyze Request & Prioritize Direct Answer:** First, determine if you can answer the user's query directly using your internal knowledge. If yes, provide the answer immediately and STOP.
2.  **Identify Need for Tools:** If the request requires accessing current external information or performing actions (like writing a file), tools are necessary.
3.  **Plan ONE Step at a Time:** If tools are needed, identify the *single, first logical step*. Do NOT plan multiple tool uses at once.
4.  **Execute Single Tool Call (If Necessary):** If your plan requires a tool for the current step, you **MUST** respond with **ONLY** the tool call, formatted *exactly* as shown below. **Nothing else before or after it.**
    `TOOL_CALL: function_name(parameter1="value1", parameter2="value2", ...)`
    - Parameter values **MUST** be enclosed in double quotes (`"`).
    - **Escape special characters** within string values using standard JSON-like escapes: `\\n` for newline, `\\"` for a literal double quote, `\\\\` for a literal backslash.
5.  **Await Tool Result:** After you issue a valid `TOOL_CALL`, I will execute it and provide the result like this:
    `TOOL_RESULT: [Result of the tool execution]`
6.  **Process Result & Determine Next Action:** Analyze the `TOOL_RESULT`.
    *   **If the result indicates SUCCESS** (e.g., `TOOL_RESULT: Success: File ... written successfully...` or useful text from `fetch_web_content`):
        *   Check if this fulfills the *entire* original user request OR if it was just an intermediate step.
        *   If the *entire* request is now complete: Your response **MUST** be a short, final confirmation message to the user (e.g., "OK, I have saved the file.", "Here is the information you requested: ..."). **DO NOT** issue another TOOL_CALL.
        *   If it was an intermediate step (e.g., you fetched content and still need to write it): Proceed to step 4 to make the *next single* `TOOL_CALL` for the next step in your plan.
    *   **If the result indicates an ERROR** (e.g., `TOOL_RESULT: Error: ...`): Acknowledge the error in your response to the user. Do not issue another TOOL_CALL unless you have a clear alternative plan based on the error.
7.  **Complete the FULL Request:** Ensure you complete *all* parts of the user's original request. If they asked to fetch information *and* save it, you MUST perform both steps sequentially using separate `TOOL_CALL`s.

**Available Tools:**
{TOOL_DESCRIPTIONS}

**Example TOOL_CALL Formatting (with Escaping):**
TOOL_CALL: fetch_web_content(url="https://example.com")
TOOL_CALL: write_file(filename="report.md", content="# Report Title\\nThis is line one.\\nThis line contains \\"quotes\\" and a backslash \\\\.") # Note \\n, \\", \\\\

**Example Multi-Step Flow (User asks: "Summarize example.com and save to summary.txt"):**

1.  Your Response: `TOOL_CALL: fetch_web_content(url="https://example.com")`
2.  My Response: `TOOL_RESULT: [Text content from example.com...]`
3.  Your Response: `TOOL_CALL: write_file(filename="summary.txt", content="[Your summary of the text content, properly escaped...]")`
4.  My Response: `TOOL_RESULT: Success: File 'summary.txt' written successfully...`
5.  Your Response: `OK. I have fetched the content from example.com and saved the summary to summary.txt in the session workspace.` # <-- Final confirmation, NOT another tool call

**CRITICAL:** Adhere strictly to the single `TOOL_CALL:` format when required. After a successful tool result that completes the user's request, respond conversationally. Do not repeat tool calls unnecessarily.
"""

# --- Main Agent Loop (run_agent - minor logging change, core logic same) ---
def run_agent():
    """Runs the main loop of the agent with session folder and colored output."""
    # ... (Initialization: colorama, workspace, session folder creation - unchanged) ...
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
        print(f"{Fore.RED}Error: Could not create necessary directories in '{WORKSPACE_DIR}'. Exiting.")
        return

    logger.info(f"Initializing agent with model: {OLLAMA_MODEL} on {OLLAMA_FULL_URL}")
    logger.info(f"Max iterations: {MAX_ITERATIONS}, Browser: {BROWSER_TYPE} ({'Headless' if BROWSER_HEADLESS else 'Visible'})")
    print(f"{Style.BRIGHT}Minimal Agent Initialized. Session workspace: {session_path.resolve()}")
    print(f"{Style.BRIGHT}Ask me anything. Type 'quit' to exit.")

    system_prompt = get_system_prompt()
    conversation_history = [] # Stores context for the LLM

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

        # Add current user query to a temporary list for this turn's history tracking
        current_turn_history = [f"User: {user_query}"]

        # Build the prompt for the LLM
        current_prompt = f"{system_prompt}\n\n"
        if conversation_history:
             history_context = "\n".join(conversation_history)
             current_prompt += f"Previous Conversation Context:\n{history_context}\n\n"
             # logger.debug(f"Adding context:\n{history_context}") # Can be very verbose

        current_prompt += f"Current User Query: {user_query}\n\nAssistant:"

        iterations = 0
        while iterations < MAX_ITERATIONS:
            iterations += 1
            logger.info(f"--- Turn {len(conversation_history)//2 + 1} / Iteration {iterations}/{MAX_ITERATIONS} ---") # Improved log

            llm_response = call_ollama(current_prompt)
            logger.debug(f"LLM raw response (Iteration {iterations}): {llm_response}")
            # Add LLM response to this turn's history immediately
            current_turn_history.append(f"Assistant (Thought/Action): {llm_response}")

            function_name, args = parse_tool_call(llm_response)

            if function_name and args is not None: # Valid tool call detected
                tool_result = execute_tool(function_name, args, session_path)
                logger.info(f"Result from tool '{function_name}': {tool_result[:300]}...")

                tool_result_text = f"TOOL_RESULT: {tool_result}"
                # Append tool result to prompt for next LLM thought *within this turn*
                current_prompt += f"{llm_response}\n{tool_result_text}\nAssistant:"
                # Add tool result to this turn's history tracking
                current_turn_history.append(tool_result_text)
                # Continue inner loop: LLM will process the tool_result

            else:
                # No valid TOOL_CALL detected by the parser
                final_answer = llm_response # Assume it's the final answer

                # Check if the LLM *tried* to make a call but failed format
                if "TOOL_CALL:" in llm_response:
                     logger.warning(f"LLM response contained 'TOOL_CALL:' but failed parsing. Response: {final_answer}")
                     print(f"{Fore.YELLOW}Agent (Hint): LLM tried to use a tool but formatting was incorrect.{Style.RESET_ALL}")
                     # Still treat it as the final (though possibly wrong) answer for this turn

                # Print final answer to user
                print(f"{Fore.CYAN}{Style.BRIGHT}Agent:{Style.NORMAL} {final_answer}")

                # Add this turn's full interaction (User + all Assist/Tool steps + Final Answer) to main history
                conversation_history.extend(current_turn_history)
                # Ensure the last item is marked as the final answer if it wasn't a tool result
                if not current_turn_history[-1].startswith("TOOL_RESULT:"):
                     conversation_history.append(f"Agent (Final Answer): {final_answer}")


                break # Exit the inner iteration loop for this query
        else:
            # Hit max iterations for this query
            logger.warning(f"Reached maximum iterations ({MAX_ITERATIONS}) for query: {user_query}")
            print(f"{Fore.YELLOW}Agent: Reached maximum tool iterations. Unable to fully process the request with tools.{Style.RESET_ALL}")
            # Add this turn's interactions and the failure message to history
            conversation_history.extend(current_turn_history)
            conversation_history.append(f"Agent: Reached max iterations ({MAX_ITERATIONS}).")

        # Trim conversation history
        if len(conversation_history) > CONVERSATION_HISTORY_LIMIT:
            # Keep pairs (User/Agent or Assist/ToolResult) together, trim from the start
            items_to_remove = len(conversation_history) - CONVERSATION_HISTORY_LIMIT
            if items_to_remove > 0:
                 logger.debug(f"Trimming conversation history from {len(conversation_history)} items")
                 conversation_history = conversation_history[items_to_remove:]


if __name__ == "__main__":
    run_agent()