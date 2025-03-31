# main.py
import logging
import datetime
import json
import re # Import re for brace stripping
from pathlib import Path
from typing import Optional, Dict, Any

# Colorama for colored output
from colorama import init as colorama_init
from colorama import Fore, Style

# --- CORRECTED ABSOLUTE IMPORTS ---
import config
from agent.planner_executor import (
    generate_plan,
    generate_action_json,
    parse_action_json,
    execute_tool,
    call_ollama
)
from agent.prompts import GENERATION_PROMPT_TEMPLATE
# --- END CORRECTED IMPORTS ---

# Logging setup
logging.basicConfig(level=config.LOG_LEVEL, format=config.LOG_FORMAT)
logger = logging.getLogger("main")

# --- Session Setup ---
def setup_session() -> Optional[Path]:
    try:
        workspace_path = Path(config.WORKSPACE_DIR); workspace_path.mkdir(parents=True, exist_ok=True)
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S"); session_path = workspace_path / f"session_{ts}"
        session_path.mkdir(exist_ok=True); logger.info(f"Session folder: {session_path.resolve()}"); return session_path
    except OSError as e:
        logger.error(f"Failed create directories: {e}", exc_info=True)
        print(f"{Fore.RED}Error creating directories in '{config.WORKSPACE_DIR}'. Exiting.{Style.RESET_ALL}"); return None

# --- Helper to strip quotes ---
def strip_outer_quotes(value: str) -> str:
    """Removes matching outer single or double quotes from a string if present."""
    if isinstance(value, str):
        if (value.startswith('"') and value.endswith('"')) or \
           (value.startswith("'") and value.endswith("'")):
            return value[1:-1]
    return value

# ---> NEW Helper to strip braces <---
def strip_outer_braces(value: str) -> str:
    """Removes matching outer double curly braces {{...}} from a string if present."""
    if isinstance(value, str):
         # Use regex for flexibility with potential whitespace
         match = re.match(r"^\s*\{\{(.*?)\}\}\s*$", value, re.DOTALL)
         if match:
             return match.group(1).strip() # Return the inner content
    return value

# --- Main Execution Loop ---
def run_session(session_path: Path):
    colorama_init(autoreset=True)
    print(f"{Style.BRIGHT}Planner-Executor Agent Initialized."); print(f"Session workspace: {session_path.resolve()}")
    print(f"{Style.BRIGHT}Ask me anything complex. Type 'quit' to exit.")

    while True:
        try: user_query = input(f"{Fore.GREEN}You: {Style.RESET_ALL}")
        except EOFError: print(f"\n{Style.DIM}Exiting.{Style.RESET_ALL}"); break
        if user_query.lower() == 'quit': break
        if not user_query: continue

        # --- Planning ---
        print(f"{Style.DIM}Generating plan...{Style.RESET_ALL}")
        plan = generate_plan(user_query)
        if plan is None:
             print(f"{Fore.RED}Agent: Couldn't generate a valid plan.{Style.RESET_ALL}"); continue
        if not plan:
            print(f"{Fore.YELLOW}Agent: Plan is empty, nothing to execute.{Style.RESET_ALL}"); continue

        print(f"{Fore.YELLOW}Agent Plan:{Style.RESET_ALL}")
        for i, step in enumerate(plan): print(f"  {i+1}. {step.get('task_description','N/A')} (Tool: {step.get('tool_name','N/A')}, Output: {step.get('output_ref','N/A')})")
        print("-" * 20)

        # --- Execution ---
        step_results: Dict[str, Any] = {}
        execution_successful = True
        for i, step_data in enumerate(plan):
            if i >= config.MAX_EXECUTION_ITERATIONS:
                 logger.warning(f"Reached max execution iterations."); print(f"{Fore.YELLOW}Agent: Reached max steps.{Style.RESET_ALL}")
                 execution_successful = False; break

            step_num = step_data.get("step", i + 1); task_desc = step_data.get("task_description", "N/A")
            tool_name = step_data.get("tool_name", "N/A"); plan_args = step_data.get("arguments", {})
            output_ref = step_data.get("output_ref")

            print(f"{Style.DIM}Executing Step {step_num}: {task_desc}... (Tool: {tool_name}){Style.RESET_ALL}")

            if not tool_name or tool_name == "N/A":
                 logger.error(f"Step {step_num} missing tool_name."); print(f"{Fore.RED}Agent: Plan error - step {step_num} missing tool.{Style.RESET_ALL}")
                 execution_successful = False; break

            tool_result = None

            # --- Handle generate_text pseudo-tool ---
            if tool_name == "generate_text":
                resolved_generation_instruction = plan_args.get("prompt", "")
                if isinstance(resolved_generation_instruction, str):
                     # Strip quotes and braces before checking key for prompt substitution
                     potential_key = strip_outer_braces(strip_outer_quotes(resolved_generation_instruction))
                     if potential_key in step_results:
                        logger.info(f"Resolving 'generate_text' prompt using previous step result '{potential_key}'")
                        resolved_generation_instruction = step_results[potential_key]
                     else:
                         # Use the stripped value if it changed
                         resolved_generation_instruction = potential_key if potential_key != resolved_generation_instruction else resolved_generation_instruction

                if not resolved_generation_instruction or not isinstance(resolved_generation_instruction, str):
                     tool_result = "Error: 'generate_text' tool planned without a valid 'prompt' argument or resolved input."
                     logger.error(tool_result)
                else:
                     generation_prompt = GENERATION_PROMPT_TEMPLATE.format(generation_instruction=resolved_generation_instruction)
                     logger.info(f"Calling LLM for text generation instruction: '{resolved_generation_instruction[:100]}...'")
                     tool_result = call_ollama(generation_prompt, config.OLLAMA_EXECUTOR_MODEL, expect_json=False)
                print(f"{Style.DIM}  Result (Generated Text): {str(tool_result)[:300]}{'...' if len(str(tool_result))>300 else ''}{Style.RESET_ALL}")

            # --- Handle regular tool calls ---
            else:
                # Prepare context FOR EXECUTOR PROMPT (using placeholders from plan)
                input_data_for_prompt = {}
                args_for_executor_prompt = plan_args.copy()
                for arg_name, arg_value in plan_args.items():
                    if isinstance(arg_value, str) and arg_value in step_results:
                        ref_key = arg_value
                        resolved_value = step_results[ref_key]
                        input_data_for_prompt[ref_key] = str(resolved_value)[:200] + ('...' if len(str(resolved_value)) > 200 else '')

                # Get Action JSON from Executor
                action_json_content_str = generate_action_json(
                    task_desc, tool_name, args_for_executor_prompt, input_data_for_prompt
                )
                if not action_json_content_str:
                    print(f"{Fore.RED}Agent: Executor failed generate action for step {step_num}. Stopping.{Style.RESET_ALL}"); execution_successful = False; break

                # Parse Action JSON
                exec_function_name, exec_args = parse_action_json(action_json_content_str)
                if not exec_function_name or exec_args is None:
                    print(f"{Fore.RED}Agent: Failed parse action JSON for step {step_num}. Stopping.{Style.RESET_ALL}"); logger.warning(f"Failed parsing Action JSON: {action_json_content_str}"); execution_successful = False; break

                # --- Resolve Arguments AFTER Parsing (More Robust) ---
                final_exec_args = {}
                for arg_name, arg_value in exec_args.items():
                    resolved = False
                    if isinstance(arg_value, str):
                        # ---> Try resolving in order of likelihood: braces->quotes->as_is <---
                        potential_key_braces = strip_outer_braces(arg_value)
                        potential_key_quotes = strip_outer_quotes(arg_value)
                        potential_key_both = strip_outer_braces(potential_key_quotes) # Strip quotes then braces

                        keys_to_check = [
                            potential_key_both,  # Check 'content'
                            potential_key_braces, # Check '{{content}}'
                            potential_key_quotes, # Check '"content"'
                            arg_value             # Check original value e.g. '"{content}"'
                        ]
                        # Remove duplicates while preserving order somewhat
                        unique_keys_to_check = list(dict.fromkeys(keys_to_check))

                        for key_attempt in unique_keys_to_check:
                             if key_attempt in step_results:
                                resolved_value = step_results[key_attempt]
                                final_exec_args[arg_name] = resolved_value
                                logger.info(f"Resolved argument '{arg_name}' for execution using step result '{key_attempt}'")
                                logger.debug(f"Resolved value preview: {str(resolved_value)[:100]}...")
                                resolved = True
                                break # Stop checking once resolved

                        if not resolved:
                             # Not a key, use literal value - prefer stripped of quotes/braces if possible
                             cleaned_literal = potential_key_both
                             final_exec_args[arg_name] = cleaned_literal
                             if cleaned_literal != arg_value:
                                 logger.debug(f"Used literal value for arg '{arg_name}' after cleaning quotes/braces: '{cleaned_literal}'")

                    if not resolved and not isinstance(arg_value, str):
                        # Argument value is not a string (e.g., number), use it directly
                        final_exec_args[arg_name] = arg_value
                        resolved = True # Mark as handled

                    if not resolved: # Should not happen if logic above is correct
                         logger.warning(f"Argument '{arg_name}' with value '{arg_value}' was not resolved or used as literal.")
                         final_exec_args[arg_name] = arg_value # Fallback to original value


                # --- End of Updated Resolution Logic ---

                # Execute Tool (using fully resolved arguments)
                tool_result = execute_tool(exec_function_name, final_exec_args, session_path)
                print(f"{Style.DIM}  Result: {str(tool_result)[:300]}{'...' if len(str(tool_result))>300 else ''}{Style.RESET_ALL}")


            # --- Store Result ---
            if tool_result is None:
                 tool_result = f"Error: Tool {tool_name} did not return a result for step {step_num}."
                 logger.error(tool_result)

            if output_ref:
                step_results[output_ref] = tool_result
                logger.info(f"Stored result for step {step_num} under reference '{output_ref}'")

            # --- Handle Step Error ---
            if isinstance(tool_result, str) and tool_result.startswith("Error:"):
                  print(f"{Fore.RED}Agent: Step {step_num} failed: {tool_result}{Style.RESET_ALL}")
                  execution_successful = False; break

        # --- End of Execution Loop ---
        if execution_successful: print(f"{Fore.CYAN}{Style.BRIGHT}Agent: Plan execution completed.{Style.RESET_ALL}")
        else: print(f"{Fore.YELLOW}Agent: Plan execution finished with errors or was stopped.{Style.RESET_ALL}")


if __name__ == "__main__":
    session_path = setup_session()
    if session_path:
        try:
            run_session(session_path)
        except KeyboardInterrupt:
             print(f"\n{Style.DIM}Execution interrupted by user. Exiting.{Style.RESET_ALL}")
        except Exception as e:
             logger.error("An uncaught exception occurred in the main loop.", exc_info=True)
             print(f"{Fore.RED}{Style.BRIGHT}An unexpected error occurred: {e}{Style.RESET_ALL}")