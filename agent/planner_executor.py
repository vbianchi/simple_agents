# agent/planner_executor.py
import logging
import json
import requests
import re # Make sure re is imported
import inspect
from pathlib import Path
from typing import List, Dict, Tuple, Any, Optional

# --- CORRECTED ABSOLUTE IMPORTS ---
try:
    import config # Try direct import first
except ModuleNotFoundError:
    from .. import config

# Import tools and descriptions
from tools.web_tools import fetch_web_content, WEB_TOOL_DESCRIPTIONS
from tools.file_tools import write_file, read_file, FILE_TOOL_DESCRIPTIONS
from tools.search_tools import web_search, SEARCH_TOOL_DESCRIPTIONS
from agent.prompts import PLANNER_SYSTEM_PROMPT_TEMPLATE, EXECUTOR_SYSTEM_PROMPT_TEMPLATE, GENERATION_PROMPT_TEMPLATE
# --- END CORRECTED IMPORTS ---

logger = logging.getLogger(__name__)

# --- Use imported config ---
OLLAMA_BASE_URL = config.OLLAMA_BASE_URL
OLLAMA_API_ENDPOINT = config.OLLAMA_API_ENDPOINT
OLLAMA_API_TIMEOUT = config.OLLAMA_API_TIMEOUT
OLLAMA_OPTIONS = config.OLLAMA_OPTIONS
OLLAMA_PLANNER_MODEL = config.OLLAMA_PLANNER_MODEL
OLLAMA_EXECUTOR_MODEL = config.OLLAMA_EXECUTOR_MODEL
MAX_LLM_RETRIES = config.MAX_LLM_RETRIES

# --- Tool Definitions ---
AVAILABLE_TOOLS_EXEC = {
    "fetch_web_content": fetch_web_content,
    "write_file": write_file,
    "read_file": read_file,
    "web_search": web_search,
}

GENERATION_TOOL_DESCRIPTIONS = {
     "generate_text": {
        "description": "Generates creative or informative text based on a given prompt instruction. Use this for tasks like writing jokes, poems, summaries (if no dedicated tool exists), extracting specific information from provided text, reformatting content, or answering general knowledge questions that don't require external data.",
        "args": {"prompt": "string (The specific instruction for text generation, e.g., 'Write a short joke about computers', 'Summarize the key points from the following text: {step1_output.txt}', 'Extract the email address from this content: ...')"},
        "returns": "string (The generated text)"
    }
}

# Format ALL tool descriptions
def format_tool_descriptions() -> str:
    desc_string = ""
    all_descriptions = {
        **WEB_TOOL_DESCRIPTIONS,
        **FILE_TOOL_DESCRIPTIONS,
        **GENERATION_TOOL_DESCRIPTIONS,
        **SEARCH_TOOL_DESCRIPTIONS
    }
    for name, info in all_descriptions.items():
        args_repr = json.dumps(info.get('args', {}))
        desc_string += f"- {name}:\n"
        desc_string += f"    Description: {info['description']}\n"
        desc_string += f"    Args: {args_repr}\n"
        desc_string += f"    Returns: {info.get('returns', 'None')}\n"
    return desc_string

TOOL_DESCRIPTIONS_STRING = format_tool_descriptions()

# --- Core LLM Call Function ---
def call_ollama(prompt: str, model: str, expect_json: bool = False) -> str:
    full_url = OLLAMA_BASE_URL.rstrip('/') + '/' + OLLAMA_API_ENDPOINT.lstrip('/')
    messages = [{"role": "user", "content": prompt}]
    payload = {
        "model": model, "messages": messages, "stream": False, "options": OLLAMA_OPTIONS,
    }
    if expect_json:
        payload["format"] = "json"
        logger.debug(f"Requesting JSON format from Ollama for model {model}")

    retries = 0
    last_error_msg = "Error: Max retries exceeded."
    while retries <= MAX_LLM_RETRIES:
        try:
            logger.debug(f"Sending request to Ollama: URL={full_url}, Model={model}, JSON={expect_json}")
            response = requests.post(full_url, json=payload, timeout=OLLAMA_API_TIMEOUT)
            response.raise_for_status()
            response_data = response.json()
            if response_data.get("done", False) and "message" in response_data and isinstance(response_data["message"], dict):
                llm_response_content = response_data["message"].get("content", "").strip()
                if not llm_response_content:
                     logger.warning(f"Ollama chat response had empty content. Response: {response_data}")
                     last_error_msg = "Error: Empty content received from Ollama chat API."
                else:
                    logger.debug(f"--- Received RAW Response Content from Ollama ---\n{llm_response_content[:1000]}...\n-----------------------------")
                    return llm_response_content
            else:
                 logger.error(f"Ollama chat response format unexpected or incomplete. Response: {response_data}")
                 last_error_msg = "Error: Incomplete or unexpected format from Ollama chat API."
        except requests.exceptions.Timeout:
             logger.error(f"Ollama API call timed out (Retry {retries+1}/{MAX_LLM_RETRIES+1})")
             last_error_msg = f"Error: API call timed out after {OLLAMA_API_TIMEOUT} seconds."
        except requests.exceptions.RequestException as e:
            logger.error(f"Ollama API call failed (Retry {retries+1}/{MAX_LLM_RETRIES+1}): {e}", exc_info=True if retries >= MAX_LLM_RETRIES else False)
            last_error_msg = f"Error: API call failed. {e}"
        except Exception as e:
             logger.error(f"An unexpected error occurred during Ollama call (Retry {retries+1}/{MAX_LLM_RETRIES+1}): {e}", exc_info=True)
             last_error_msg = f"Error: An unexpected error occurred during API call. {e}"
        retries += 1;
        if retries <= MAX_LLM_RETRIES:
            logger.warning(f"Retrying Ollama call ({retries}/{MAX_LLM_RETRIES})...")
    return last_error_msg


# --- Planner Function ---
def generate_plan(user_query: str) -> Optional[List[Dict[str, Any]]]:
    """Generates a multi-step plan using the Planner LLM."""
    prompt = PLANNER_SYSTEM_PROMPT_TEMPLATE.format(
        tool_descriptions_string=TOOL_DESCRIPTIONS_STRING,
        user_query=user_query
    )
    logger.info(f"Generating plan for query: {user_query} using {OLLAMA_PLANNER_MODEL}")
    raw_plan_response = call_ollama(prompt, OLLAMA_PLANNER_MODEL, expect_json=False)

    if raw_plan_response.startswith("Error:"):
        logger.error(f"Planner LLM failed: {raw_plan_response}")
        return None

    try:
        # Attempt to find JSON list within the response
        json_match = re.search(r"\[\s*(\{.*?\})\s*\]", raw_plan_response, re.DOTALL | re.MULTILINE)
        json_str = ""
        if json_match:
            json_str = json_match.group(0)
            logger.debug("Found JSON list using regex.")
        elif raw_plan_response.strip().startswith('[') and raw_plan_response.strip().endswith(']'):
             json_str = raw_plan_response.strip()
             logger.debug("Found JSON list by checking start/end brackets.")
        else:
             logger.error(f"Could not find JSON list structure in planner response: {raw_plan_response}")
             return None

        # ---> ADD PRE-PROCESSING STEP <---
        # Remove potential line comments (#...) that break JSON parsing
        cleaned_json_str = re.sub(r"\s*#.*", "", json_str)
        if cleaned_json_str != json_str:
             logger.warning("Removed potential comments from plan JSON before parsing.")
        logger.debug(f"Attempting to parse Cleaned Plan JSON string: {cleaned_json_str}")
        # ---> PARSE THE CLEANED STRING <---
        plan_list = json.loads(cleaned_json_str)

        if not isinstance(plan_list, list):
            raise ValueError("Planner output JSON is not a list")

        # Validate the structure of each step
        validated_plan = []
        all_known_tools = list(AVAILABLE_TOOLS_EXEC.keys()) + list(GENERATION_TOOL_DESCRIPTIONS.keys())

        for i, step in enumerate(plan_list):
            if not isinstance(step, dict):
                 logger.warning(f"Skipping plan step {i+1}: not a dictionary. Step: {step}")
                 continue
            required_keys = ["task_description", "tool_name", "arguments"]
            if not all(k in step for k in required_keys):
                 logger.warning(f"Skipping plan step {i+1}: missing required keys ({required_keys}). Step: {step}")
                 continue
            step["step"] = step.get("step", i + 1)
            if not isinstance(step.get("arguments"), dict):
                logger.warning(f"Step {step.get('step')} arguments are not a dict: {step.get('arguments')}. Setting to empty dict.")
                step["arguments"] = {}
            tool_name = step.get("tool_name")
            if not isinstance(tool_name, str) or tool_name not in all_known_tools:
                logger.warning(f"Skipping plan step {step.get('step')} with unknown or invalid tool: '{tool_name}'")
                continue
            if "output_ref" not in step:
                step["output_ref"] = None
            validated_plan.append(step)

        if not validated_plan:
            if isinstance(plan_list, list) and not plan_list:
                 logger.info("Planner generated an empty plan (JSON `[]`), indicating no action needed.")
                 return []
            else:
                raise ValueError("Planner generated an empty or invalid plan after validation.")

        logger.info(f"Generated Validated Plan:\n{json.dumps(validated_plan, indent=2)}")
        return validated_plan

    except json.JSONDecodeError as json_err:
         # Log the *cleaned* string that failed parsing
         logger.error(f"Failed to parse JSON from planner response. Error: {json_err}. Cleaned String: {cleaned_json_str}", exc_info=True)
         return None
    except Exception as e:
        logger.error(f"Failed processing planner response. Error: {e}. Response:\n{raw_plan_response}", exc_info=True)
        return None


# --- Executor Function ---
def generate_action_json(task_description: str, tool_name: str, plan_arguments: dict, input_data: Dict[str, str]) -> Optional[str]:
    input_context = ""
    if input_data:
        input_context = "Available data from previous steps (referenced by output_ref):\n"
        for ref, data_snippet in input_data.items():
            input_context += f"- {ref}: {data_snippet[:200]}{'...' if len(data_snippet)>200 else ''}\n"

    prompt = EXECUTOR_SYSTEM_PROMPT_TEMPLATE.format(
        tool_descriptions_string=TOOL_DESCRIPTIONS_STRING,
        task_description=task_description,
        tool_name=tool_name,
        plan_arguments_json=json.dumps(plan_arguments),
        input_data_context=input_context
    )
    logger.info(f"Generating Action JSON for task: '{task_description}' (Tool: {tool_name}) using {OLLAMA_EXECUTOR_MODEL}")

    action_json_str = call_ollama(prompt, OLLAMA_EXECUTOR_MODEL, expect_json=True)

    if action_json_str.startswith("Error:"):
        logger.error(f"Executor LLM failed: {action_json_str}")
        return None

    action_json_str_stripped = action_json_str.strip()
    if not (action_json_str_stripped.startswith('{') and action_json_str_stripped.endswith('}')):
         json_match = re.search(r"(\{.*?\})", action_json_str_stripped, re.DOTALL)
         if json_match:
             logger.warning("Executor LLM added extra text around JSON object. Extracting JSON.")
             action_json_str = json_match.group(1)
         else:
             logger.error(f"Executor response doesn't look like JSON object: {action_json_str}")
             return None
    return action_json_str


# --- Tool Parsing ---
def parse_action_json(action_json_content_str: str) -> Tuple[Optional[str], Optional[dict]]:
    try:
        logger.debug(f"Attempting to parse Action JSON content string: {action_json_content_str[:500]}...")
        tool_data = json.loads(action_json_content_str)
        logger.debug(f"Successfully parsed content string into tool_data: {tool_data}")

        if not isinstance(tool_data, dict):
            logger.warning(f"Parsed JSON data is not a dictionary: {tool_data}")
            return None, None
        function_name = tool_data.get("tool_name")
        args_dict = tool_data.get("arguments")
        if not isinstance(function_name, str) or not function_name:
            logger.warning(f"Missing or invalid 'tool_name' in Action JSON: {tool_data}")
            return None, None
        if not isinstance(args_dict, dict):
            if args_dict is None:
                logger.debug(f"Action JSON 'arguments' is null, converting to empty dict.")
                args_dict = {}
            else:
                logger.warning(f"Invalid 'arguments' (must be object/dict or null) in Action JSON: {tool_data}")
                return None, None
        if function_name in AVAILABLE_TOOLS_EXEC:
            logger.info(f"Parsed Action JSON: Tool='{function_name}', Args={args_dict}")
            return function_name, args_dict
        else:
            if function_name in GENERATION_TOOL_DESCRIPTIONS:
                 logger.warning(f"Action JSON specified 'generate_text' tool - this should be handled directly.")
                 return None, None
            else:
                logger.warning(f"Action JSON specified unknown execution tool: '{function_name}'")
                return None, None
    except json.JSONDecodeError as json_err:
        logger.error(f"Failed to parse Action JSON content. Error: {json_err}. String: {action_json_content_str}", exc_info=True)
        return None, None
    except Exception as e:
        logger.error(f"Unexpected error parsing Action JSON. Error: {e}. String: {action_json_content_str}", exc_info=True)
        return None, None


# --- Tool Execution ---
def execute_tool(function_name: str, args: dict, session_path: Path) -> str:
    if function_name in AVAILABLE_TOOLS_EXEC:
        logger.info(f"Executing tool: '{function_name}' with args: {args}")
        tool_function = AVAILABLE_TOOLS_EXEC[function_name]
        try:
            sig = inspect.signature(tool_function)
            tool_args = args.copy()
            if 'session_path' in sig.parameters:
                tool_args['session_path'] = session_path
            elif 'session_path' in tool_args:
                 del tool_args['session_path']
            required_params = {
                p.name for p in sig.parameters.values()
                if p.default == inspect.Parameter.empty and p.name != 'session_path'
            }
            provided_args = set(tool_args.keys())
            missing_args = required_params - provided_args
            if missing_args:
                error_msg = f"Error: Missing required arguments for tool '{function_name}': {', '.join(missing_args)}"
                logger.error(error_msg)
                return error_msg
            result = tool_function(**tool_args)
            result_str = str(result)
            logger.debug(f"Tool '{function_name}' executed. Raw result type: {type(result)}, Str result preview: {result_str[:200]}...")
            return result_str
        except Exception as e:
            error_msg = f"Error executing tool '{function_name}' with args {args}. Details: {e}"
            logger.error(error_msg, exc_info=True)
            return error_msg
    else:
        error_msg = f"Error: Tool '{function_name}' not found in AVAILABLE_TOOLS_EXEC for execution."
        logger.error(error_msg)
        return error_msg