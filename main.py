# main.py
import logging
import datetime
import json
from pathlib import Path
from typing import Optional # Make sure this is imported

# Colorama for colored output
from colorama import init as colorama_init
from colorama import Fore, Style

# Import core components from agent and config
from config import WORKSPACE_DIR, LOG_LEVEL, LOG_FORMAT, MAX_EXECUTION_ITERATIONS
# Adjusted import path
from agent.planner_executor import (
    generate_plan,
    generate_action_json,
    parse_action_json, # Use the correct parser name
    execute_tool,
    read_file # Keep read_file import
)

# Configure logging
logging.basicConfig(level=LOG_LEVEL, format=LOG_FORMAT)
logger = logging.getLogger("main")

# --- Session Setup ---
def setup_session() -> Optional[Path]:
    """Creates workspace and a unique session folder."""
    # ... (Implementation unchanged) ...
    try:
        workspace_path = Path(WORKSPACE_DIR)
        workspace_path.mkdir(parents=True, exist_ok=True)
        session_timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        session_path = workspace_path / f"session_{session_timestamp}"
        session_path.mkdir(exist_ok=True)
        logger.info(f"Created session folder: {session_path.resolve()}")
        return session_path
    except OSError as e:
        logger.error(f"Failed to create workspace or session directory: {e}", exc_info=True)
        print(f"{Fore.RED}Error: Could not create necessary directories in '{WORKSPACE_DIR}'. Exiting.{Style.RESET_ALL}")
        return None

# --- Main Execution Loop ---
def run_session(session_path: Path):
    """Handles the main interaction loop for a session."""
    # ... (Initialization and user input loop unchanged) ...
    colorama_init(autoreset=True)
    print(f"{Style.BRIGHT}Planner-Executor Agent Initialized.")
    print(f"Session workspace: {session_path.resolve()}")
    print(f"{Style.BRIGHT}Ask me anything complex. Type 'quit' to exit.")

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

        # --- Planning Step ---
        print(f"{Style.DIM}Generating plan...{Style.RESET_ALL}")
        plan = generate_plan(user_query) # Calls the planner

        if not plan:
            print(f"{Fore.RED}Agent: Sorry, I couldn't generate a valid plan for that request.{Style.RESET_ALL}")
            continue

        print(f"{Fore.YELLOW}Agent Plan:{Style.RESET_ALL}")
        for i, step in enumerate(plan):
             print(f"  {i+1}. {step.get('task_description', 'N/A')} (Tool: {step.get('tool_name', 'N/A')}, Output: {step.get('output_ref', 'N/A')})") # Show output ref
        print("-" * 20)

        # --- Execution Step ---
        step_results = {} # Stores results string by output_ref filename
        execution_successful = True

        for i, step_data in enumerate(plan):
             if i >= MAX_EXECUTION_ITERATIONS:
                  logger.warning(f"Reached max execution iterations ({MAX_EXECUTION_ITERATIONS}). Stopping plan.")
                  print(f"{Fore.YELLOW}Agent: Reached maximum execution steps. Stopping.{Style.RESET_ALL}")
                  execution_successful = False
                  break

             step_num = step_data.get("step", i + 1)
             task_desc = step_data.get("task_description", "N/A")
             tool_name = step_data.get("tool_name", "N/A")
             plan_args = step_data.get("arguments", {})
             output_ref = step_data.get("output_ref") # Filename for saving/referencing result

             print(f"{Style.DIM}Executing Step {step_num}: {task_desc}... (Tool: {tool_name}){Style.RESET_ALL}")

             if not tool_name or tool_name == "N/A":
                  logger.error(f"Plan step {step_num} is missing 'tool_name'. Skipping.")
                  print(f"{Fore.RED}Agent: Error in plan - step {step_num} missing tool name. Skipping.{Style.RESET_ALL}")
                  execution_successful = False
                  continue

             # --- Prepare context/input data from previous steps ---
             input_data_for_prompt = {} # Snippets for prompt context
             resolved_args_for_exec = plan_args.copy() # Args to potentially pass to tool

             for arg_name, arg_value in plan_args.items():
                 # If an argument value is a string AND matches a previous output_ref filename...
                 if isinstance(arg_value, str) and arg_value in step_results:
                     ref_filename = arg_value
                     logger.info(f"Reading input file '{ref_filename}' for step {step_num}, arg '{arg_name}'")
                     file_content = read_file(filename=ref_filename, session_path=session_path)

                     if file_content.startswith("Error:"):
                          logger.error(f"Failed to read input file '{ref_filename}' for step {step_num}. Error: {file_content}")
                          print(f"{Fore.RED}Agent: Error executing plan - could not read required input file '{ref_filename}'. Stopping.{Style.RESET_ALL}")
                          execution_successful = False
                          break # Stop execution
                     else:
                          # Store snippet for the Executor's prompt context
                          input_data_for_prompt[ref_filename] = file_content
                          # Update the argument value for the *actual tool execution*
                          resolved_args_for_exec[arg_name] = file_content

             if not execution_successful: break # Exit outer loop if reading failed

             # --- Get Action JSON from Executor LLM (requesting JSON format) ---
             action_json_content_str = generate_action_json(
                 task_description=task_desc,
                 tool_name=tool_name,
                 plan_arguments=resolved_args_for_exec, # Give executor potentially resolved args
                 input_data=input_data_for_prompt # Give executor snippets of input data
             )

             if not action_json_content_str:
                  print(f"{Fore.RED}Agent: Executor LLM failed to generate valid action for step {step_num}. Stopping plan.{Style.RESET_ALL}")
                  execution_successful = False
                  break

             # --- Parse the Action JSON ---
             # parse_action_json handles the potential double-parse
             exec_function_name, exec_args = parse_action_json(action_json_content_str)

             if not exec_function_name:
                  print(f"{Fore.RED}Agent: Failed to parse tool action JSON for step {step_num}. Stopping plan.{Style.RESET_ALL}")
                  logger.warning(f"Failed parsing Action JSON content string: {action_json_content_str}")
                  execution_successful = False
                  break

             # --- Execute the Tool ---
             tool_result = execute_tool(exec_function_name, exec_args, session_path)
             print(f"{Style.DIM}  Result: {tool_result[:300]}{'...' if len(tool_result)>300 else ''}{Style.RESET_ALL}")

             # --- Store Result ---
             if output_ref:
                 # Store the raw result string (content or success/error)
                 # More sophisticated handling might be needed if tools return complex objects
                 step_results[output_ref] = tool_result
                 logger.info(f"Stored result for step {step_num} under reference '{output_ref}'")
                 # If the tool just executed was write_file and it succeeded,
                 # we might want to store the content that was written,
                 # not just the success message, for potential later reading.
                 if exec_function_name == "write_file" and tool_result.startswith("Success:"):
                       # The content is already in exec_args['content']
                       step_results[output_ref] = exec_args.get("content", "Error: Content missing in write args")
                       logger.info(f"Updating result for '{output_ref}' to the written content.")


             # --- Handle Tool Error ---
             if tool_result.startswith("Error:"):
                  print(f"{Fore.RED}Agent: Tool execution failed for step {step_num}. Stopping plan.{Style.RESET_ALL}")
                  execution_successful = False
                  break # Stop plan on tool error

        # --- End of Execution Loop ---
        if execution_successful:
            print(f"{Fore.CYAN}{Style.BRIGHT}Agent: Plan execution completed.{Style.RESET_ALL}")
        else:
             print(f"{Fore.YELLOW}Agent: Plan execution finished with errors or was stopped.{Style.RESET_ALL}")


if __name__ == "__main__":
    session_path = setup_session()
    if session_path:
        run_session(session_path)