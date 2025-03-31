# Simple Ollama Planner-Executor Agent
## Codename TIMO: The Incredible Machine Open-Source

This project implements a Python-based AI agent that uses locally running Large Language Models (LLMs) via Ollama to accomplish tasks. It employs a **Planner-Executor** architecture to handle multi-step requests more reliably than simpler agent loops.

The agent can:
*   Understand user requests.
*   Generate a step-by-step plan using an LLM (Planner).
*   Execute each step of the plan, which may involve:
    *   Generating text using an LLM (e.g., writing jokes, summaries).
    *   Calling external tools (fetching web content via Playwright, writing files, reading files).
*   Use Ollama's chat endpoint with JSON format enforcement for reliable tool call generation by the LLM (Executor).
*   Manage tasks within dedicated session workspaces.

This repository is available at: [https://github.com/vbianchi/simple_agents](https://github.com/vbianchi/simple_agents)

## Features

*   **Planner-Executor Architecture:** Separates the task of planning from the task of executing individual steps, improving reliability for multi-step operations.
*   **Ollama Integration:** Connects to a running Ollama instance using the `/api/chat` endpoint.
*   **Reliable JSON Tool Calls:** Leverages Ollama's `format: json` feature for the Executor LLM to ensure tool calls are generated in a valid, parsable JSON format.
*   **Local LLM Usage:** Configurable to use different models available in Ollama for Planning and Execution.
*   **Tool Suite:**
    *   `fetch_web_content`: Fetches web content using Playwright (handles JavaScript).
    *   `write_file`: Writes content to files within a session-specific workspace.
    *   `read_file`: Reads content from files within the session workspace.
    *   `generate_text` (Pseudo-Tool): Uses the LLM for creative text generation tasks within the plan.
*   **Session Workspaces:** Creates a unique directory under `./workspace/` for each run to store generated files securely.
*   **Intermediate Result Handling:** Passes data between plan steps using output references (`output_ref`) resolved via an in-memory dictionary (`step_results`).
*   **Modern Tooling:** Uses `uv` for fast environment and package management.
*   **Colored Output:** Uses `colorama` for more readable terminal interaction.
*   **Centralized Configuration:** Key settings managed in `config.py`.

## Architecture Overview

1.  **Input:** The user provides a request to `main.py`.
2.  **Planning:** `main.py` calls `agent.planner_executor.generate_plan`. This function prompts the Planner LLM (e.g., `mistral`, `llama3`) with the user request and available tools, asking it to generate a step-by-step plan as a JSON list. The plan specifies the tool, arguments, and how results (`output_ref`) should link between steps.
3.  **Execution Loop:** `main.py` iterates through the generated plan steps.
4.  **Argument Resolution:** For each step, `main.py` checks the planned arguments. If an argument value matches an `output_ref` from a previous step, it retrieves the actual result (e.g., fetched text, generated joke) from an internal dictionary (`step_results`).
5.  **Action Generation/Execution:**
    *   **If `generate_text` tool:** `main.py` calls the Executor LLM directly with a generation prompt. The result is stored.
    *   **If regular tool:** `main.py` calls `agent.planner_executor.generate_action_json`. This prompts the Executor LLM (e.g., `llama3.2`) using `format: json`, providing the current step's details and resolved arguments. The Executor LLM *only* returns the required JSON action object (`{"tool_name": ..., "arguments": ...}`).
    *   `main.py` calls `agent.planner_executor.parse_action_json` to validate the received JSON.
    *   `main.py` calls `agent.planner_executor.execute_tool`, which runs the corresponding Python tool function (from `tools/`) with the arguments from the JSON.
6.  **Result Storage:** The output of the tool execution or text generation is stored in the `step_results` dictionary, keyed by the `output_ref` defined in the plan.
7.  **Loop/Completion:** The agent proceeds to the next plan step or reports completion/errors.

## Prerequisites

1.  **Python:** Python 3.8+ recommended.
2.  **uv:** The `uv` package manager installed. ([uv installation guide](https://github.com/astral-sh/uv#installation)).
3.  **Ollama:** Ollama installed and **running**. ([https://ollama.com/](https://ollama.com/)). Ensure it supports the `/api/chat` endpoint and `format: json`.
4.  **Ollama Models:** At least one capable instruction-following model installed (e.g., `ollama pull llama3.2`, `ollama pull mistral`, `ollama pull llama3.2`). Configure the desired Planner and Executor models in `config.py`.
5.  **Playwright Browsers:** Browser binaries for Playwright need to be installed.

## Installation

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/vbianchi/simple_agents.git # Or your repo URL
    cd simple_agents
    ```

2.  **Create and Activate Virtual Environment (using `uv`):**
    ```bash
    # Specify your Python version if desired
    uv venv --python 3.12
    # Activate (adjust path for your OS/shell)
    source .venv/bin/activate
    ```

3.  **Install Python Dependencies (using `uv`):**
    ```bash
    uv pip install -r requirements.txt
    ```

4.  **Install Playwright Browsers:**
    ```bash
    playwright install
    ```

## Configuration

**All major settings are located in `config.py`**. Edit this file to adjust:

*   **Ollama Settings:**
    *   `OLLAMA_BASE_URL`: URL of your Ollama instance.
    *   `OLLAMA_API_ENDPOINT`: Should be `/api/chat`.
    *   `OLLAMA_PLANNER_MODEL`: Model used for generating the plan.
    *   `OLLAMA_EXECUTOR_MODEL`: Model used for generating Action JSON and for `generate_text`.
    *   `OLLAMA_API_TIMEOUT`: Timeout for API calls.
    *   `OLLAMA_OPTIONS`: Dictionary for LLM parameters (e.g., `temperature`).
*   **Agent Settings:**
    *   `MAX_EXECUTION_ITERATIONS`: Max plan steps to execute.
    *   `MAX_LLM_RETRIES`: How many times to retry a failing Ollama API call.
*   **Workspace Settings:**
    *   `WORKSPACE_DIR`: Path to the directory for session folders.
*   **Playwright/Browser Settings:**
    *   `BROWSER_TYPE`, `BROWSER_HEADLESS`, `PAGE_LOAD_TIMEOUT`, `CONTENT_MAX_LENGTH`.
*   **Logging Settings:**
    *   `LOG_LEVEL`, `LOG_FORMAT`.

## Usage

1.  Ensure Ollama service is running.
2.  Activate your virtual environment (`source .venv/bin/activate`).
3.  Modify `config.py` if needed (especially model names).
4.  Run the main agent script:
    ```bash
    python main.py
    ```
5.  The agent will initialize, show the session workspace path, and prompt `You:`.
6.  Enter your request (e.g., "Fetch the top headlines from example.com and write them to headlines.txt", "Write a python function to calculate fibonacci and save it as fib.py").
7.  The agent will display the generated plan.
8.  It will then execute each step, showing tool calls and results.
9.  Files created by `write_file` will appear in the session-specific subfolder within `./workspace/`.
10. Type `'quit'` to exit.

## Project Structure

```bash
simple_agents/
├── .venv/ # Virtual environment directory (created by uv)
├── agent/ # Core agent logic
│ ├── init.py
│ ├── planner_executor.py # Planner/Executor LLM calls, tool execution
│ └── prompts.py # System prompt templates
├── tools/ # Tool implementations
│ ├── init.py
│ ├── file_tools.py # write_file, read_file
│ └── web_tools.py # fetch_web_content
├── workspace/ # Root for session folders (created automatically)
├── config.py # Central configuration
├── main.py # Main script to run the agent session
├── requirements.txt # Python dependencies
├── README.md # This file
└── .gitignore # Git ignore rules
```

## How it Works (Detailed Flow)

1.  `main.py` starts, sets up logging, and creates a unique session folder inside `WORKSPACE_DIR`.
2.  The user provides a query.
3.  `main.py` calls `generate_plan` in `agent/planner_executor.py`.
4.  `generate_plan` formats the `PLANNER_SYSTEM_PROMPT_TEMPLATE` (including tool descriptions and the user query) and calls the `OLLAMA_PLANNER_MODEL` via `call_ollama`.
5.  The Planner LLM ideally returns a JSON list representing the plan steps.
6.  `generate_plan` parses and validates this JSON list, returning it to `main.py`.
7.  `main.py` displays the plan and initializes an empty dictionary `step_results` to hold outputs.
8.  `main.py` loops through each `step_data` in the plan:
    *   It identifies the `tool_name`, planned `arguments`, and `output_ref`.
    *   **Argument Resolution:** It iterates through the `plan_args`. If an argument's value (e.g., `"step1_output.txt"`) exists as a key in `step_results`, it retrieves the actual data (e.g., fetched text) stored under that key and uses this actual data when preparing arguments for the next step.
    *   **Tool Handling:**
        *   If `tool_name` is `generate_text`: It formats the `GENERATION_PROMPT_TEMPLATE` with the instruction from the plan's arguments and calls `call_ollama` (using `OLLAMA_EXECUTOR_MODEL`, no JSON format needed). The returned text is the `tool_result`.
        *   If `tool_name` is a standard tool: It calls `generate_action_json`. This function formats the `EXECUTOR_SYSTEM_PROMPT_TEMPLATE` (including the step task, tool name, resolved arguments, and snippets of input data) and calls `call_ollama` (using `OLLAMA_EXECUTOR_MODEL` with `expect_json=True`). The LLM *should* return only the valid JSON action object string.
        *   `main.py` receives this JSON string, calls `parse_action_json` to load it into a Python dictionary.
        *   `main.py` calls `execute_tool` with the parsed tool name, arguments, and the `session_path`. `execute_tool` finds the correct Python function in `tools/` and runs it. The function's return value (content, success/error message) is the `tool_result`.
    *   **Store Result:** The `tool_result` (generated text or tool output) is stored in the `step_results` dictionary using the step's `output_ref` as the key.
    *   **Error Check:** If `tool_result` indicates an error, the loop breaks.
9.  After the loop (or break), `main.py` prints a final status message.

## Limitations & Considerations

*   **LLM Dependency:** The quality of the plan generated by the Planner LLM and the correctness of the Action JSON from the Executor LLM are critical. Performance varies significantly between models.
*   **Planning Logic:** The Planner might generate illogical or inefficient plans. Prompt engineering is key.
*   **State Management:** Currently uses an in-memory dictionary (`step_results`) keyed by `output_ref`. For very large outputs or longer plans, explicitly writing *all* intermediate outputs to files and having tools read *only* files might be more robust (but slightly slower).
*   **Error Handling:** Basic error handling exists, but complex recovery (e.g., replanning on tool failure) is not implemented.
*   **Context Window:** Long plans or large intermediate results passed as context might exceed the LLM's context limit.
*   **Sequential Execution:** Steps are executed one after another.

## Future Enhancements

*   Implement more robust state management (explicit intermediate files for all `output_ref`s).
*   Add more tools (web search API, code execution sandbox, summarization tool).
*   Improve Planner prompting with few-shot examples or more advanced techniques.
*   Implement plan validation and revision logic.
*   Add better error handling and retry mechanisms for specific tool failures.
*   Explore context window management strategies.
*   Consider using different, specialized LLMs for Planning vs. Execution vs. Generation.

This revised architecture provides a much more solid foundation for building more capable and reliable agents using local LLMs.
