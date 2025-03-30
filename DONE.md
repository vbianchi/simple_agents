# Project Recall Summary: Simple Ollama Planner-Executor Agent

**Goal:** Create a Python agent using local LLMs via Ollama (chat endpoint) to execute potentially multi-step tasks based on user requests.

**Core Architecture:** Planner-Executor

1.  **Planner:** An LLM (`OLLAMA_PLANNER_MODEL`) generates a step-by-step plan in JSON list format based on the user query and available tools. The plan includes `step`, `task_description`, `tool_name`, `arguments`, and `output_ref` (for passing results).
2.  **Executor:** An LLM (`OLLAMA_EXECUTOR_MODEL`) generates the specific JSON action object (`{"tool_name": ..., "arguments": ...}`) required for *each individual step* of the plan, using Ollama's `format: json` feature for reliability.
3.  **Orchestrator (`main.py`):**
    *   Gets the user query.
    *   Calls the Planner (`generate_plan`).
    *   Parses the plan.
    *   Loops through plan steps:
        *   Resolves arguments by substituting `output_ref` values with actual results stored from previous steps (`step_results` dictionary).
        *   Handles the `generate_text` pseudo-tool by calling the LLM directly for text generation.
        *   For regular tools, calls the Executor (`generate_action_json`) to get the Action JSON.
        *   Parses the Action JSON (`parse_action_json`).
        *   Executes the corresponding tool function (`execute_tool`).
        *   Stores the result (text or success/error message) in `step_results` keyed by the step's `output_ref`.
    *   Reports completion or errors.
4.  **Session Workspace:** Each run creates a unique directory under `./workspace/` for file operations.

**Key Files & Components:**

*   `main.py`: Entry point and execution loop.
*   `config.py`: Ollama URLs, model names, timeouts, workspace path, etc. Uses `/api/chat`.
*   `agent/planner_executor.py`: Contains `call_ollama`, `generate_plan`, `generate_action_json`, `parse_action_json`, `execute_tool`.
*   `agent/prompts.py`: Contains `PLANNER_SYSTEM_PROMPT_TEMPLATE`, `EXECUTOR_SYSTEM_PROMPT_TEMPLATE`, `GENERATION_PROMPT_TEMPLATE`.
*   `tools/web_tools.py`: `fetch_web_content` function & description.
*   `tools/file_tools.py`: `write_file`, `read_file` functions & descriptions.

**Implemented Tools:**

*   `fetch_web_content(url)`
*   `write_file(filename, content)`
*   `read_file(filename)`
*   `generate_text(prompt)` (Pseudo-tool handled in `main.py`)

**Current Status (as of last interaction):**

*   Successfully implemented the Planner-Executor architecture.
*   Reliably using `/api/chat` with `format: json` for the Executor's Action JSON generation, solving previous JSON truncation/formatting issues.
*   Successfully executed both single-step (`write_file` with generated joke) and multi-step (`fetch` -> `generate_text` -> `write_file`) tasks.
*   The Planner generates logical plans, including using `output_ref` to link steps.
*   The argument resolution logic in `main.py` correctly uses intermediate results stored via `output_ref`.

**Potential Next Steps/Refinements Discussed:**

*   Further tuning the `PLANNER_SYSTEM_PROMPT_TEMPLATE` for more complex plans (e.g., handling multiple inputs for a summarization step).
*   Testing more complex multi-fetch/combine scenarios.
*   Implementing more sophisticated tools (e.g., dedicated summarization).
*   Improving error handling within the plan execution loop.
*   Adding more user feedback during execution.
*   Managing context window for very long tasks/conversations.