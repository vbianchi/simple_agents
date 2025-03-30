import requests
import json
import re
import logging

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

# Configure logging using settings from config.py
logging.basicConfig(level=LOG_LEVEL, format=LOG_FORMAT)
logger = logging.getLogger(__name__) # Use module name for logger

# Construct the full API URL from config parts
OLLAMA_FULL_URL = OLLAMA_BASE_URL.rstrip('/') + '/' + OLLAMA_API_ENDPOINT.lstrip('/')

# --- LLM Interaction ---
def call_ollama(prompt: str, context_history: list = None) -> str:
    """Sends a prompt to the OLLAMA API and gets a response using config settings."""
    # Use configuration for model, options, and timeout
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": OLLAMA_OPTIONS, # Use options dict from config
        # "context": context_history # If using generate endpoint with history management
    }
    logger.debug(f"--- Sending Prompt to Ollama ({OLLAMA_MODEL}) ---")
    logger.debug(f"Prompt Snippet:\n{prompt[:500]}...\n-----------------------------") # Log only snippet

    try:
        # Use full URL and timeout from config
        response = requests.post(OLLAMA_FULL_URL, json=payload, timeout=OLLAMA_API_TIMEOUT)
        response.raise_for_status()
        response_data = response.json()
        llm_response = response_data.get("response", "").strip()
        logger.debug(f"--- Received Response from Ollama ---\n{llm_response[:500]}...\n-----------------------------") # Log snippet
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

# --- Tool Parsing and Execution (No changes needed here, uses AVAILABLE_TOOLS from tool_functions) ---
def parse_tool_call(llm_output: str):
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

def execute_tool(function_name: str, args: dict):
    """Executes the specified tool function with the given arguments."""
    if function_name in AVAILABLE_TOOLS:
        tool_function = AVAILABLE_TOOLS[function_name]
        try:
            result = tool_function(**args)
            return result
        except Exception as e:
            logger.error(f"Error executing tool {function_name} with args {args}: {e}", exc_info=True)
            return f"Error: Failed to execute tool '{function_name}'."
    else:
        return f"Error: Tool '{function_name}' not found."

# --- System Prompt (No changes needed, uses TOOL_DESCRIPTIONS from tool_functions) ---
def get_system_prompt():
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

# --- Main Agent Loop ---
def run_agent():
    """Runs the main loop of the agent."""
    # Log the configuration being used
    logger.info(f"Initializing agent with model: {OLLAMA_MODEL} on {OLLAMA_FULL_URL}")
    logger.info(f"Max iterations: {MAX_ITERATIONS}, Browser: {BROWSER_TYPE} ({'Headless' if BROWSER_HEADLESS else 'Visible'})")
    print(f"Minimal Agent Initialized (using Playwright/{BROWSER_TYPE} & Ollama/{OLLAMA_MODEL}). Ask me anything. Type 'quit' to exit.")
    system_prompt = get_system_prompt()
    conversation_history = []

    while True:
        try:
            user_query = input("You: ")
        except EOFError: # Handle Ctrl+D or piped input ending
             print("\nExiting.")
             break
        if user_query.lower() == 'quit':
            break
        if not user_query: # Skip empty input
            continue

        current_prompt = f"{system_prompt}\n\nPrevious Conversation:\n"
        if conversation_history:
             # Simple history: just include last LLM thought and tool result if any
             history_context = "\n".join(conversation_history[-2:])
             current_prompt += history_context + "\n"
             logger.debug(f"Adding context:\n{history_context}")


        current_prompt += f"\nCurrent User Query: {user_query}\n\nAssistant:"

        iterations = 0
        while iterations < MAX_ITERATIONS: # Use MAX_ITERATIONS from config
            iterations += 1
            logger.info(f"--- Iteration {iterations}/{MAX_ITERATIONS} ---")

            llm_response = call_ollama(current_prompt)
            # Simple way to keep track of the conversation flow for the next turn's context
            current_turn_llm_output = f"Assistant (Internal Thought/Action): {llm_response}"


            function_name, args = parse_tool_call(llm_response)

            if function_name and args:
                tool_result = execute_tool(function_name, args)
                logger.info(f"Tool Result snippet: {tool_result[:200]}...")

                # Prepare next prompt with tool result
                tool_result_text = f"TOOL_RESULT: {tool_result}"
                current_prompt += f"{llm_response}\n{tool_result_text}\nAssistant:"
                # Add both LLM's action and the tool result to history for the *next* LLM call
                conversation_history.append(current_turn_llm_output)
                conversation_history.append(tool_result_text)

            else:
                # No tool call detected, assume this is the final answer for this query
                print(f"Agent: {llm_response}")
                # Add final answer to history (though it won't be used as context for *this* query anymore)
                conversation_history.append(f"Agent (Final Answer): {llm_response}")
                break # Exit the inner iteration loop for this query
        else:
            # Hit max iterations
            logger.warning(f"Reached maximum iterations ({MAX_ITERATIONS}) for query: {user_query}")
            print("Agent: Reached maximum tool iterations. Unable to fully process the request with tools.")
            conversation_history.append(f"Agent: Reached max iterations ({MAX_ITERATIONS}).")

        # Optional: Trim conversation history to prevent it from growing indefinitely
        # A simple strategy: keep only the last N interactions (e.g., last 4 items = 2 turns)
        history_limit = 6 # Keep last N items (adjust as needed)
        if len(conversation_history) > history_limit:
            logger.debug(f"Trimming conversation history from {len(conversation_history)} items")
            conversation_history = conversation_history[-history_limit:]


if __name__ == "__main__":
    run_agent()