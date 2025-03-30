import requests
import json
import re
import logging
# This now imports the Playwright version of the tool function indirectly
from tool_functions import AVAILABLE_TOOLS, TOOL_DESCRIPTIONS

# --- Configuration ---
OLLAMA_URL = "http://localhost:11434/api/generate" # Or /api/chat if using chat endpoint
OLLAMA_MODEL = "llama3.2" # CHANGE THIS to your desired local model
MAX_ITERATIONS = 5 # Limit the number of tool calls per user query to prevent loops

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- LLM Interaction ---
def call_ollama(prompt: str, context_history: list = None) -> str:
    """Sends a prompt to the OLLAMA API and gets a response."""
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {
             "temperature": 0.7,
             # "num_ctx": 4096 # Example: Set context window size if needed
        }
    }
    logger.debug(f"--- Sending Prompt to Ollama ---\n{prompt}\n-----------------------------")
    try:
        response = requests.post(OLLAMA_URL, json=payload, timeout=60) # Timeout for LLM generation
        response.raise_for_status()
        response_data = response.json()
        llm_response = response_data.get("response", "").strip()
        logger.debug(f"--- Received Response from Ollama ---\n{llm_response}\n-----------------------------")
        return llm_response
    except requests.exceptions.RequestException as e:
        logger.error(f"Error calling Ollama API: {e}")
        return f"Error: Could not connect to the Ollama API at {OLLAMA_URL}. Is Ollama running?"
    except json.JSONDecodeError as e:
        logger.error(f"Error decoding Ollama response: {e}\nResponse text: {response.text}")
        return "Error: Received invalid response from Ollama."
    except Exception as e:
        logger.error(f"Unexpected error calling Ollama: {e}", exc_info=True)
        return "Error: An unexpected error occurred while communicating with Ollama."


# --- Tool Parsing and Execution ---
def parse_tool_call(llm_output: str):
    """
    Parses the LLM output for a tool call.
    Looks for a pattern like: TOOL_CALL: function_name(arg1="value1", arg2="value2")
    Returns (function_name, args_dict) or (None, None).
    """
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

# --- System Prompt ---
def get_system_prompt():
    """Constructs the system prompt telling the LLM how to behave and use tools."""
    # TOOL_DESCRIPTIONS is imported from tool_functions.py and now describes the Playwright tool
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
    print("Minimal Agent Initialized (using Playwright). Ask me anything. Type 'quit' to exit.")
    system_prompt = get_system_prompt()
    conversation_history = []

    while True:
        user_query = input("You: ")
        if user_query.lower() == 'quit':
            break

        current_prompt = f"{system_prompt}\n\nPrevious Conversation:\n"
        if conversation_history:
             current_prompt += "\n".join(conversation_history[-2:]) + "\n"

        current_prompt += f"\nCurrent User Query: {user_query}\n\nAssistant:"

        iterations = 0
        while iterations < MAX_ITERATIONS:
            iterations += 1
            logger.info(f"--- Iteration {iterations} ---")

            llm_response = call_ollama(current_prompt)
            conversation_history.append(f"Assistant (Internal Thought/Action): {llm_response}")

            function_name, args = parse_tool_call(llm_response)

            if function_name and args:
                # This now calls the Playwright version of fetch_web_content
                tool_result = execute_tool(function_name, args)
                logger.info(f"Tool Result: {tool_result[:200]}...")

                current_prompt += f"{llm_response}\nTOOL_RESULT: {tool_result}\nAssistant:"
                conversation_history.append(f"TOOL_RESULT: {tool_result}")

            else:
                print(f"Agent: {llm_response}")
                conversation_history.append(f"Agent (Final Answer): {llm_response}")
                break
        else:
            print("Agent: Reached maximum tool iterations. Unable to fully process the request.")
            conversation_history.append("Agent: Reached max iterations.")


if __name__ == "__main__":
    run_agent()