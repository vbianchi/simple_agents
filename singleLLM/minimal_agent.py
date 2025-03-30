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
    logger.debug(f"Prompt Snippet:\n{prompt[:500]}...\n-----------------------------")

    try:
        response = requests.post(OLLAMA_FULL_URL, json=payload, timeout=OLLAMA_API_TIMEOUT)
        response.raise_for_status()
        response_data = response.json()
        llm_response = response_data.get("response", "").strip()

        # Clean up potential markdown code blocks around JSON (common LLM behavior)
        if llm_response.startswith("```json"):
             llm_response = llm_response[len("```json"):].strip()
             if llm_response.endswith("```"):
                  llm_response = llm_response[:-len("```")].strip()
        elif llm_response.startswith("```"):
             llm_response = llm_response[len("```"):].strip()
             if llm_response.endswith("```"):
                  llm_response = llm_response[:-len("```")].strip()

        # Attempt to cleanup if LLM wraps the response in extra quotes
        if llm_response.startswith('"') and llm_response.endswith('"'):
            try:
                potential_json_content = f'"{llm_response[1:-1]}"'
                decoded_content = json.loads(potential_json_content)
                if isinstance(decoded_content, str):
                     llm_response = decoded_content
            except json.JSONDecodeError:
                 logger.warning("LLM response looked quoted but failed JSON unquoting. Using raw stripped value.")
                 llm_response = llm_response[1:-1]

        logger.debug(f"--- Received Response from Ollama (Processed) ---\n{llm_response[:500]}...\n-----------------------------")
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


# --- Tool Parsing (JSON Version) ---
def parse_tool_call(llm_output: str):
    """
    Attempts to parse the LLM output as a JSON object representing a tool call.
    Expected JSON format:
    {
      "tool_name": "function_name",
      "arguments": {"param1": "value1", "param2": "value2"}
    }
    Returns (function_name, args_dict) or (None, None).
    """
    llm_output_stripped = llm_output.strip()
    if not (llm_output_stripped.startswith('{') and llm_output_stripped.endswith('}')):
         logger.debug("LLM output does not look like JSON.")
         return None, None

    try:
        logger.debug(f"Attempting to parse LLM output as JSON: {llm_output_stripped}")
        tool_data = json.loads(llm_output_stripped)

        if not isinstance(tool_data, dict):
            logger.warning(f"Parsed JSON is not a dictionary: {tool_data}")
            return None, None

        function_name = tool_data.get("tool_name")
        args_dict = tool_data.get("arguments")

        if not isinstance(function_name, str) or not function_name:
            logger.warning(f"Missing or invalid 'tool_name' (string) in JSON: {tool_data}")
            return None, None

        if not isinstance(args_dict, dict):
            if args_dict is None:
                logger.debug(f"Missing 'arguments' field for tool '{function_name}', assuming no arguments needed.")
                args_dict = {}
            else:
                logger.warning(f"Invalid 'arguments' (must be object/dict) in JSON for tool '{function_name}': {tool_data}")
                return None, None

        if function_name in AVAILABLE_TOOLS:
            logger.info(f"Detected tool call via JSON: {function_name} with args: {args_dict}")
            return function_name, args_dict
        else:
            logger.warning(f"LLM called unknown tool via JSON: {function_name}")
            return None, None

    except json.JSONDecodeError as e:
        logger.warning(f"Failed to parse LLM output as JSON tool call. Error: {e}. Output: {llm_output}")
        return None, None
    except Exception as e:
        logger.error(f"Unexpected error parsing JSON tool call: {e}", exc_info=True)
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


# --- System Prompt (JSON Version - NO TRIPLE BACKTICKS in examples) ---
def get_system_prompt():
    """Constructs the system prompt telling the LLM how to behave and use tools via JSON."""
    # This version uses indentation for JSON examples to avoid chat display issues.
    # Note: Double braces {{ }} are needed to escape literal braces inside f-strings.
    return f"""You are a precise and methodical AI assistant. Your goal is to fulfill the user's request by following instructions exactly.

**Core Instructions:**

1.  **Analyze Request & Prioritize Direct Answer:** First, determine if you can answer the user's query directly using your internal knowledge. If yes, provide the answer immediately and STOP.
2.  **Identify Need for Tools:** If the request requires accessing current external information or performing actions (like writing a file), tools are necessary.
3.  **Plan ONE Step at a Time:** If tools are needed, identify the *single, first logical step*. Do NOT plan multiple tool uses at once.
4.  **Execute Single Tool Call (If Necessary):** If your plan requires a tool for the current step, you **MUST** respond with **ONLY** a single JSON object formatted *exactly* as shown below. **Nothing else before or after it.** Ensure the JSON is valid.

    Example JSON Structure:
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
    - **DO NOT** add any explanation or conversational text outside the JSON object. Your entire response must be just the JSON structure.
5.  **Await Tool Result:** After you issue a valid JSON tool call, I will execute it and provide the result like this:
    `TOOL_RESULT: [Result of the tool execution]`
6.  **Process Result & Determine Next Action:** Analyze the `TOOL_RESULT`.
    *   **If the result indicates SUCCESS:** Check if this completes the *entire* original user request OR if it was an intermediate step.
        *   If the *entire* request is complete: Your response **MUST** be a short, final confirmation message to the user (e.g., "OK, I have saved the file."). **DO NOT** output JSON.
        *   If it was an intermediate step (e.g., fetched content, still need to write): Proceed to step 4 to make the *next single* JSON tool call.
    *   **If the result indicates an ERROR:** Acknowledge the error in your response to the user. Do not output JSON unless you have a clear alternative tool call plan.
7.  **Complete the FULL Request:** Ensure you complete *all* parts of the user's original request sequentially.

**Available Tools:**
{TOOL_DESCRIPTIONS}

**Example JSON Tool Call Formatting:**

*Fetching Web Content:*
    {{
      "tool_name": "fetch_web_content",
      "arguments": {{
        "url": "https://example.com"
      }}
    }}

*Writing a File:*
    {{
      "tool_name": "write_file",
      "arguments": {{
        "filename": "report.md",
        "content": "# Report Title\\nThis is line one.\\nThis line contains \\"quotes\\"."
      }}
    }}

**CRITICAL:** Adhere strictly to the single JSON object format when using a tool. Only provide conversational text for the final answer *after all necessary tool steps are complete*.
"""


# --- Main Agent Loop ---
def run_agent():
    """Runs the main loop of the agent with session folder, colored output, and JSON tool calls."""
    colorama_init(autoreset=True) # Initialize colorama

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
    conversation_history = [] # Stores context for the LLM

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
            current_turn_history.append(f"Assistant (Thought/Action): {llm_response}")

            # --- Attempt to parse the response as a JSON tool call ---
            function_name, args = parse_tool_call(llm_response)

            if function_name and args is not None: # Valid JSON tool call detected and parsed
                tool_result = execute_tool(function_name, args, session_path)
                logger.info(f"Result from tool '{function_name}': {tool_result[:300]}...")

                tool_result_text = f"TOOL_RESULT: {tool_result}"
                # Add the ORIGINAL llm_response (the JSON string) and the tool result text to the prompt context
                current_prompt += f"{llm_response}\n{tool_result_text}\nAssistant:"
                current_turn_history.append(tool_result_text)
                # Continue inner loop

            else:
                # No valid JSON TOOL_CALL detected by the parser
                final_answer = llm_response

                if llm_response.strip().startswith('{') and llm_response.strip().endswith('}'):
                     logger.warning(f"LLM response looked like JSON but failed parsing/validation. Response: {final_answer}")
                     print(f"{Fore.YELLOW}Agent (Hint): LLM tried to use a tool via JSON but formatting/validation failed.{Style.RESET_ALL}")

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