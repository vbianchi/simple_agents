# Project Recall Summary: Simple Ollama Planner-Executor Agent - 31-03-2025

## 1. Goal:
Create a Python agent using local LLMs (via Ollama `/api/chat`) employing a **Planner-Executor** architecture to handle potentially multi-step user requests, including web interaction and file operations.

## 2. Current Status:
*   **Architecture:** Functional Planner-Executor implemented.
*   **Core Tools:** `fetch_web_content` (Playwright), `write_file`, `read_file`, `generate_text` (pseudo-tool handled in `main.py`).
*   **Web Discovery (Phase 1 - ✅ Completed):** Successfully added and integrated a `web_search` tool (using `duckduckgo-search`). Default/max search results are configurable in `config.py`.
*   **Robust Execution:** `main.py` now handles argument resolution *after* parsing the Executor's JSON, robustly substituting `output_ref` values from `step_results` even if the Executor misformats placeholders (e.g., extra quotes/braces). File tools also clean filenames.
*   **Testing:** Successfully tested simple search-and-save workflows.

## 3. Current Bottleneck/Challenge:
*   The **Planner LLM** (tested with `mistral` and `phi4`) struggles to generate correct plans for more complex tasks requiring multiple web fetches derived from initial search results (e.g., the "ramen recipe summary" task).
*   Common failure modes include:
    *   Skipping necessary intermediate `fetch_web_content` steps entirely.
    *   Attempting to process/summarize directly from the `web_search` result snippets instead of fetching full page content.
    *   Failing to correctly plan the extraction of individual URLs before fetching.
*   Extensive prompt engineering, including detailed workflow instructions and examples, has not reliably solved this planning limitation with the tested models.

## 4. Agreed Next Step (Start of Next Session):
*   Implement a **Rule-Based Judge/Evaluator** within the plan validation logic in `agent/planner_executor.py` (likely modifying or adding to the checks after `plan_list = json.loads(cleaned_json_str)`).
*   **Initial Rules:** Focus on adding specific checks for known failure patterns observed:
    *   Detect if `generate_text` is planned to directly process the output of `web_search` for extraction/summarization without intermediate `fetch_web_content` steps.
    *   Perform basic validation of `output_ref` flow (e.g., ensure a step referenced by `output_ref` exists earlier in the plan).
*   **Goal:** To reject these logically flawed plans *before* execution, saving time and preventing nonsensical results or errors.

## 5. Overall Plan (Future):
Once the Judge provides better plan validation, we can resume the phased TODO list: Phase 2 (PDF Handling), Phase 3 (Improved Data Extraction/Complex Planning), Phase 4 (Robustness/Advanced Tools).



# Project Recall Summary: Simple Ollama Planner-Executor Agent - 30-03-2025

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
