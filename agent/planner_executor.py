# agent/planner_executor.py
import logging
import json
import requests
import re
from pathlib import Path
from typing import List, Dict, Tuple, Any, Optional

# Import necessary config and tool functions/descriptions
from config import (
    OLLAMA_BASE_URL, OLLAMA_API_ENDPOINT, OLLAMA_API_TIMEOUT, OLLAMA_OPTIONS,
    OLLAMA_PLANNER_MODEL, OLLAMA_EXECUTOR_MODEL, MAX_LLM_RETRIES
)
# Assuming tools are in ../tools relative to this file
from tools.web_tools import fetch_web_content, WEB_TOOL_DESCRIPTIONS
from tools.file_tools import write_file, read_file, FILE_TOOL_DESCRIPTIONS
from .prompts import PLANNER_SYSTEM_PROMPT_TEMPLATE, EXECUTOR_SYSTEM_PROMPT_TEMPLATE

logger = logging.getLogger(__name__)

# --- Combine Tool Information ---
AVAILABLE_TOOLS_EXEC = {
    "fetch_web_content": fetch_web_content,
    "write_file": write_file,
    "read_file": read_file,
}
def format_tool_descriptions() -> str:
    """Formats tool descriptions for inclusion in prompts."""
    desc_string = ""
    all_descriptions = {**WEB_TOOL_DESCRIPTIONS, **FILE_TOOL_DESCRIPTIONS}
    for name, info in all_descriptions.items():
        desc_string += f"- {name}:\n"
        desc_string += f"    Description: {info['description']}\n"
        desc_string += f"    Args: {info.get('args', 'None')}\n" # Use .get for safety
        desc_string += f"    Returns: {info.get('returns', 'None')}\n"
    return desc_string
TOOL_DESCRIPTIONS_STRING = format_tool_descriptions()

# --- Core LLM Call Function (Updated for /api/chat and format: json) ---
def call_ollama(prompt: str, model: str, expect_json: bool = False) -> str:
    """
    Generic function to call Ollama API using /api/chat.
    Handles conditional JSON format enforcement.
    """
    full_url = OLLAMA_BASE_URL.rstrip('/') + '/' + OLLAMA_API_ENDPOINT.lstrip('/') # Should point to /api/chat now

    # Structure for /api/chat
    messages = [{"role": "user", "content": prompt}] # Simple user prompt for now
    # Could potentially include system message: {"role": "system", "content": "..."}

    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": OLLAMA_OPTIONS,
    }

    # Conditionally add format: json if expecting a tool call JSON
    if expect_json:
        payload["format"] = "json"
        logger.debug(f"Requesting JSON format from Ollama for model {model}")

    retries = 0
    while retries <= MAX_LLM_RETRIES:
        try:
            response = requests.post(full_url, json=payload, timeout=OLLAMA_API_TIMEOUT)
            response.raise_for_status()
            response_data = response.json()

            # --- Extract content based on /api/chat response structure ---
            if response_data.get("done", False) and "message" in response_data:
                llm_response_content = response_data["message"].get("content", "").strip()

                # If JSON was requested, Ollama *should* guarantee it's valid JSON in the content string
                # The content itself is still a string, potentially containing escaped JSON
                logger.debug(f"--- Received RAW Response Content from Ollama ---\n{llm_response_content[:1000]}...\n-----------------------------")
                return llm_response_content
            else:
                 # Handle incomplete or unexpected response structure
                 logger.error(f"Ollama chat response missing 'message' or 'done=true'. Response: {response_data}")
                 error_msg = "Error: Received incomplete or unexpected response from Ollama chat API."
            # --- End Extraction ---

        except requests.exceptions.Timeout:
            logger.error(f"Ollama API request timed out (Retry {retries+1}/{MAX_LLM_RETRIES+1})")
            error_msg = "Error: Ollama API request timed out."
        except requests.exceptions.RequestException as e:
            logger.error(f"Ollama API connection error: {e} (Retry {retries+1}/{MAX_LLM_RETRIES+1})")
            error_msg = f"Error: Could not connect to Ollama API. {e}"
        except json.JSONDecodeError as e: # Error decoding the *API's* response, not the LLM content
            logger.error(f"Error decoding Ollama API structure: {e} (Retry {retries+1}/{MAX_LLM_RETRIES+1})")
            error_msg = "Error: Received invalid structure from Ollama API."
        except Exception as e:
            logger.error(f"Unexpected error calling Ollama: {e} (Retry {retries+1}/{MAX_LLM_RETRIES+1})", exc_info=True)
            error_msg = f"Error: An unexpected error occurred calling Ollama. {e}"

        retries += 1
        if retries > MAX_LLM_RETRIES:
            logger.error("Max LLM retries exceeded.")
            return error_msg # Return the last error encountered

    return "Error: LLM call failed unexpectedly after retries."

# --- Planner Function ---
def generate_plan(user_query: str) -> Optional[List[Dict[str, Any]]]:
    """Generates a multi-step plan using the Planner LLM."""
    prompt = PLANNER_SYSTEM_PROMPT_TEMPLATE.format(
        tool_descriptions_string=TOOL_DESCRIPTIONS_STRING,
        user_query=user_query
    )
    logger.info(f"Generating plan for query: {user_query} using {OLLAMA_PLANNER_MODEL}")
    # Not expecting JSON format from planner by default, but planner prompt asks for it
    raw_plan_response = call_ollama(prompt, OLLAMA_PLANNER_MODEL, expect_json=False)

    if raw_plan_response.startswith("Error:"):
        logger.error(f"Planner LLM failed: {raw_plan_response}")
        return None

    try:
        # Robustly find JSON list within potential surrounding text
        json_match = re.search(r"\[\s*\{.*?\}\s*\]", raw_plan_response, re.DOTALL)
        if not json_match:
             # Fallback: Maybe the whole response is the JSON list?
             if raw_plan_response.strip().startswith('[') and raw_plan_response.strip().endswith(']'):
                  json_str = raw_plan_response.strip()
             else:
                  logger.error(f"Could not find JSON list '[]' in planner response: {raw_plan_response}")
                  return None
        else:
             json_str = json_match.group(0)

        logger.debug(f"Extracted Plan JSON string: {json_str}")
        plan_list = json.loads(json_str)

        if not isinstance(plan_list, list):
            logger.error(f"Planner output JSON is not a list: {plan_list}")
            return None

        validated_plan = []
        for i, step in enumerate(plan_list):
            if isinstance(step, dict) and all(k in step for k in ["task_description", "tool_name", "arguments"]):
                 step["step"] = step.get("step", i + 1) # Add step number if missing
                 if not isinstance(step.get("arguments"), dict): step["arguments"] = {}
                 validated_plan.append(step)
            else:
                 logger.warning(f"Skipping invalid plan step structure: {step}")

        if not validated_plan:
             logger.error("Planner generated an empty or invalid plan.")
             return None

        logger.info(f"Generated Plan:\n{json.dumps(validated_plan, indent=2)}")
        return validated_plan

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse planner JSON. Error: {e}. JSON string tried:\n{json_str if 'json_str' in locals() else raw_plan_response}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error processing plan: {e}", exc_info=True)
        return None

# --- Executor Function (Generates Action JSON) ---
def generate_action_json(task_description: str, tool_name: str, plan_arguments: dict, input_data: Dict[str, str]) -> Optional[str]:
    """Generates the Action JSON object string for a specific step using the Executor LLM."""
    input_context = ""
    if input_data:
        input_context = "Available data from previous steps (referenced by output_ref):\n"
        for ref, data_snippet in input_data.items():
            # Show only snippets in prompt to save tokens
            input_context += f"- {ref}: {data_snippet[:200]}{'...' if len(data_snippet)>200 else ''}\n"

    prompt = EXECUTOR_SYSTEM_PROMPT_TEMPLATE.format(
        tool_descriptions_string=TOOL_DESCRIPTIONS_STRING,
        task_description=task_description,
        tool_name=tool_name,
        plan_arguments_json=json.dumps(plan_arguments),
        input_data_context=input_context
    )
    logger.info(f"Generating Action JSON for task: {task_description} (Tool: {tool_name}) using {OLLAMA_EXECUTOR_MODEL}")
    # Request JSON format explicitly
    action_json_str = call_ollama(prompt, OLLAMA_EXECUTOR_MODEL, expect_json=True)

    if action_json_str.startswith("Error:"):
        logger.error(f"Executor LLM failed: {action_json_str}")
        return None

    # --- Basic validation: Check if it looks like JSON ---
    # Ollama with format:json should guarantee valid JSON in the content string,
    # but the content *string itself* might contain escaped JSON.
    # The `parse_action_json` function will handle the actual parsing.
    action_json_str_stripped = action_json_str.strip()
    if not (action_json_str_stripped.startswith('{') and action_json_str_stripped.endswith('}')):
         # Sometimes models *still* add preamble/postamble even with format:json
         # Try extracting JSON object if possible
         json_match = re.search(r"(\{.*?\})", action_json_str_stripped, re.DOTALL)
         if json_match:
              logger.warning("Executor LLM added extra text around JSON. Extracting JSON object.")
              action_json_str = json_match.group(1)
         else:
              logger.error(f"Executor response with format:json doesn't look like JSON object: {action_json_str}")
              return None # Failed to get expected JSON object structure

    return action_json_str


# --- Tool Parsing (Parses the string *containing* JSON) ---
def parse_action_json(action_json_content_str: str) -> Tuple[Optional[str], Optional[dict]]:
    """
    Parses the JSON object string returned by the Executor LLM.
    Handles the "double parse" needed if Ollama wraps JSON in a string.
    """
    try:
        # First, parse the outer string which might contain escaped JSON
        # Use json.loads on the raw content string from the message
        logger.debug(f"Attempting to parse raw content string: {action_json_content_str[:500]}...")
        tool_data = json.loads(action_json_content_str)
        logger.debug(f"Successfully parsed content string into tool_data: {tool_data}")

        # --- Validation (same as before) ---
        if not isinstance(tool_data, dict):
            logger.warning(f"Parsed JSON data is not a dictionary: {tool_data}")
            return None, None
        function_name = tool_data.get("tool_name")
        args_dict = tool_data.get("arguments")
        if not isinstance(function_name, str) or not function_name:
            logger.warning(f"Missing or invalid 'tool_name' in JSON: {tool_data}")
            return None, None
        if not isinstance(args_dict, dict):
            if args_dict is None: args_dict = {}
            else:
                logger.warning(f"Invalid 'arguments' (must be object/dict) in JSON: {tool_data}")
                return None, None
        if function_name in AVAILABLE_TOOLS_EXEC:
            logger.info(f"Parsed Action JSON: Tool={function_name}, Args={args_dict}")
            return function_name, args_dict
        else:
            logger.warning(f"Action JSON specified unknown tool: {function_name}")
            return None, None
        # --- End Validation ---

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON object from LLM content string. Error: {e}. String was: {action_json_content_str}")
        return None, None
    except Exception as e:
        logger.error(f"Unexpected error parsing Action JSON content: {e}", exc_info=True)
        return None, None


# --- Tool Execution ---
def execute_tool(function_name: str, args: dict, session_path: Path) -> str:
    """Executes the specified tool function found in AVAILABLE_TOOLS_EXEC."""
    # ... (Implementation unchanged) ...
    if function_name in AVAILABLE_TOOLS_EXEC:
        logger.info(f"Executing tool: '{function_name}' with args: {args}")
        tool_function = AVAILABLE_TOOLS_EXEC[function_name]
        try:
            import inspect
            sig = inspect.signature(tool_function)
            tool_args = args.copy()
            if 'session_path' in sig.parameters:
                tool_args['session_path'] = session_path
            elif 'session_path' in args:
                 del tool_args['session_path']

            required_params = { p.name for p in sig.parameters.values()
                                if p.default == inspect.Parameter.empty and p.name != 'session_path' }
            missing_args = required_params - tool_args.keys()
            if missing_args:
                 error_msg = f"Error: Missing required arguments for tool '{function_name}': {', '.join(missing_args)}"
                 logger.error(error_msg)
                 return error_msg

            result = tool_function(**tool_args)
            return str(result)

        except TypeError as e:
             error_msg = f"Error: Failed to execute tool '{function_name}' due to argument mismatch. Usage Error: {e}"
             logger.error(error_msg, exc_info=True)
             return error_msg
        except Exception as e:
            error_msg = f"Error: Failed during execution of tool '{function_name}'. Details: {e}"
            logger.error(error_msg, exc_info=True)
            return error_msg
    else:
        error_msg = f"Error: Tool '{function_name}' not found in available tools."
        logger.error(error_msg)
        return error_msg