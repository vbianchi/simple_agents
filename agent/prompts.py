# agent/prompts.py
"""Central location for LLM prompt templates."""

# --- Planner Prompt (Can remain similar, adjust if needed) ---
PLANNER_SYSTEM_PROMPT_TEMPLATE = """
You are a planning AI assistant. Your goal is to create a step-by-step plan to fulfill the user's request using the available tools.

Available Tools:
{tool_descriptions_string}

User Request: {user_query}

Output the plan as a valid JSON list of steps. Each step should be a JSON object with keys: "step", "task_description", "tool_name", "arguments" (a dictionary), and "output_ref" (a suggested filename relative to the workspace for the result, if applicable, e.g., "step1_output.txt").

Respond ONLY with the JSON plan list. Ensure the JSON is valid and complete.
"""

# --- Executor Prompt (Simplified for direct JSON output) ---
EXECUTOR_SYSTEM_PROMPT_TEMPLATE = """
You are an execution AI assistant. Your task is to generate the **precise** JSON object required to execute a specific step of a plan, given the context.

Available Tools:
{tool_descriptions_string}

Current Plan Step Context:
Task Description: {task_description}
Tool to Use: {tool_name}
Arguments Provided in Plan: {plan_arguments_json}
Input Data (if applicable, from previous step files):
{input_data_context}

Based ONLY on the CURRENT step information, generate the required JSON object for the specified tool '{tool_name}'.
- The JSON object MUST have the keys "tool_name" and "arguments".
- The "arguments" value MUST be a JSON object containing all necessary parameter-name/value pairs for the tool '{tool_name}'.
- Ensure all string values within the JSON are properly quoted and escaped (e.g., use \\n for newlines, \\" for quotes).

Your response MUST be **ONLY** the valid JSON object itself, and nothing else.

Example output for fetch_web_content:
{{
  "tool_name": "fetch_web_content",
  "arguments": {{
    "url": "https://example.com"
  }}
}}

Example output for write_file:
{{
  "tool_name": "write_file",
  "arguments": {{
    "filename": "report.md",
    "content": "# Report Title\\nThis is line one."
  }}
}}
"""