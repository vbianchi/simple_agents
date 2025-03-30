# main.py
import logging
import datetime
import json
from pathlib import Path
from typing import Optional

# Colorama for colored output
from colorama import init as colorama_init
from colorama import Fore, Style

# --- CORRECTED ABSOLUTE IMPORTS ---
# Import core components from agent and config
import config # Import config directly
from agent.planner_executor import (
    generate_plan,
    generate_action_json,
    parse_action_json,
    execute_tool,
    read_file,
    call_ollama # Need call_ollama for generation step
)
# Import the generation prompt template
from agent.prompts import GENERATION_PROMPT_TEMPLATE
# --- END CORRECTED IMPORTS ---


# Logging setup
logging.basicConfig(level=config.LOG_LEVEL, format=config.LOG_FORMAT) # Use config vars
logger = logging.getLogger("main")

# --- Session Setup ---
def setup_session() -> Optional[Path]:
    """Creates workspace and a unique session folder."""
    try:
        # Use config var
        workspace_path = Path(config.WORKSPACE_DIR); workspace_path.mkdir(parents=True, exist_ok=True)
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S"); session_path = workspace_path / f"session_{ts}"
        session_path.mkdir(exist_ok=True); logger.info(f"Session folder: {session_path.resolve()}"); return session_path
    except OSError as e:
        # Use config var in error message
        logger.error(f"Failed create directories: {e}", exc_info=True)
        print(f"{Fore.RED}Error creating directories in '{config.WORKSPACE_DIR}'. Exiting.{Style.RESET_ALL}"); return None

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
        if not plan: print(f"{Fore.RED}Agent: Couldn't generate a valid plan.{Style.RESET_ALL}"); continue
        print(f"{Fore.YELLOW}Agent Plan:{Style.RESET_ALL}")
        for i, step in enumerate(plan): print(f"  {i+1}. {step.get('task_description','N/A')} (Tool: {step.get('tool_name','N/A')}, Output: {step.get('output_ref','N/A')})")
        print("-" * 20)

        # --- Execution ---
        step_results = {}
        execution_successful = True
        for i, step_data in enumerate(plan):
            if i >= config.MAX_EXECUTION_ITERATIONS: # Use config variable
                 logger.warning(f"Reached max execution iterations."); print(f"{Fore.YELLOW}Agent: Reached max steps.{Style.RESET_ALL}")
                 execution_successful = False; break

            step_num = step_data.get("step", i + 1); task_desc = step_data.get("task_description", "N/A")
            tool_name = step_data.get("tool_name", "N/A"); plan_args = step_data.get("arguments", {})
            output_ref = step_data.get("output_ref")

            print(f"{Style.DIM}Executing Step {step_num}: {task_desc}... (Tool: {tool_name}){Style.RESET_ALL}")

            if not tool_name or tool_name == "N/A":
                 logger.error(f"Step {step_num} missing tool_name."); print(f"{Fore.RED}Agent: Plan error - step {step_num} missing tool.{Style.RESET_ALL}")
                 execution_successful = False; continue

            # --- Handle generate_text pseudo-tool ---
            if tool_name == "generate_text":
                generation_instruction = plan_args.get("prompt")
                if not generation_instruction:
                     tool_result = "Error: 'generate_text' tool planned without a 'prompt' argument."
                     logger.error(tool_result)
                else:
                     generation_prompt = GENERATION_PROMPT_TEMPLATE.format(generation_instruction=generation_instruction)
                     logger.info(f"Calling LLM for text generation: '{generation_instruction}'")
                     tool_result = call_ollama(generation_prompt, config.OLLAMA_EXECUTOR_MODEL, expect_json=False) # Use config
                print(f"{Style.DIM}  Result (Generated Text): {tool_result[:300]}{'...' if len(tool_result)>300 else ''}{Style.RESET_ALL}")

            # --- Handle regular tool calls ---
            else:
                # --- Prepare context AND resolve arguments for execution ---
                input_data_for_prompt = {}; # For prompt context only
                resolved_args_for_exec = plan_args.copy() # Args for the actual tool call

                for arg_name, arg_value in plan_args.items():
                    # If an argument value is a string AND matches a previous output_ref key...
                    if isinstance(arg_value, str) and arg_value in step_results:
                        ref_key = arg_value # The key (output_ref from previous step)
                        logger.info(f"Resolving argument '{arg_name}' using previous step result stored under key '{ref_key}' for step {step_num}")

                        # --- FIXED LOGIC ---
                        # Get the *actual result value* (text, success message etc.) from the dictionary
                        resolved_value = step_results[ref_key]

                        # For the *Executor's prompt context*, add a snippet
                        input_data_for_prompt[ref_key] = resolved_value[:200] + ('...' if len(resolved_value) > 200 else '')

                        # For the *actual tool execution*, replace the reference with the resolved value
                        resolved_args_for_exec[arg_name] = resolved_value
                        logger.debug(f"Resolved arg '{arg_name}' to value: {resolved_value[:100]}...")
                        # --- END FIXED LOGIC ---

                # Removed the check for execution_successful here, error handling is below

                # --- Get Action JSON from Executor ---
                action_json_content_str = generate_action_json(task_desc, tool_name, resolved_args_for_exec, input_data_for_prompt)
                if not action_json_content_str:
                    print(f"{Fore.RED}Agent: Executor failed generate action for step {step_num}. Stopping.{Style.RESET_ALL}"); execution_successful = False; break

                # --- Parse Action JSON ---
                # Use the arguments resolved above for the executor prompt, but
                # the EXECUTED arguments come from parsing the NEW action JSON
                exec_function_name, exec_args = parse_action_json(action_json_content_str)
                if not exec_function_name:
                    print(f"{Fore.RED}Agent: Failed parse action JSON for step {step_num}. Stopping.{Style.RESET_ALL}"); logger.warning(f"Failed parsing Action JSON: {action_json_content_str}"); execution_successful = False; break

                # --- Execute Tool ---
                # IMPORTANT: Use exec_args returned by the parser, NOT resolved_args_for_exec
                tool_result = execute_tool(exec_function_name, exec_args, session_path)
                print(f"{Style.DIM}  Result: {tool_result[:300]}{'...' if len(tool_result)>300 else ''}{Style.RESET_ALL}")

            # --- Store Result ---
            if output_ref:
                # Always store the direct result (generated text or tool status/content)
                step_results[output_ref] = tool_result
                logger.info(f"Stored result for step {step_num} under reference '{output_ref}'")
                # NO NEED to update based on write_file args here anymore,
                # because the next step will correctly retrieve the actual content
                # from step_results if it references this output_ref.

            # --- Handle Step Error ---
            if isinstance(tool_result, str) and tool_result.startswith("Error:"):
                  print(f"{Fore.RED}Agent: Step {step_num} failed: {tool_result}{Style.RESET_ALL}") # Show error
                  execution_successful = False; break

        # --- End of Execution Loop ---
        if execution_successful: print(f"{Fore.CYAN}{Style.BRIGHT}Agent: Plan execution completed.{Style.RESET_ALL}")
        else: print(f"{Fore.YELLOW}Agent: Plan execution finished with errors or was stopped.{Style.RESET_ALL}")


if __name__ == "__main__":
    session_path = setup_session()
    if session_path:
        run_session(session_path)