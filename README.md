# Minimal Ollama Agent with Web Fetching Tool

This project demonstrates a bare-bones, from-scratch implementation of an "agentic" AI using Python. It connects to a locally running Ollama instance to leverage local Large Language Models (LLMs) and includes a basic tool-using capability: fetching content from web pages.

The primary goal is educational, showcasing the fundamental components of an agent loop: prompt engineering for tool use, tool definition, tool execution, and feeding results back to the LLM.

## Features

*   **Ollama Integration:** Connects directly to your running Ollama instance via its REST API.
*   **Local LLM Usage:** Leverages any instruction-following model you have downloaded in Ollama (e.g., Llama 3, Mistral, Phi-3).
*   **Basic Tool Use:** Implements a `fetch_web_content` tool allowing the agent to retrieve textual information from URLs.
*   **Simple Agent Loop:** Demonstrates the cycle of receiving input, planning (implicitly via LLM response), potentially using a tool, and generating a final response.
*   **Command-Line Interface:** Interact with the agent directly in your terminal.
*   **Extensible:** Designed with clear separation to facilitate adding more tools.

## Prerequisites

1.  **Python:** Python 3.7+ installed.
2.  **Ollama:** Ollama installed and **running**. You can find installation instructions at [https://ollama.com/](https://ollama.com/).
3.  **Ollama Model:** At least one instruction-following model pulled into Ollama. Example:
    ```bash
    ollama pull llama3
    ```
    *(You will need to configure the agent script to use the specific model name you pulled).*
4.  **Python Libraries:** `requests` for API calls and `beautifulsoup4` for basic HTML parsing.

## Installation

1.  **Clone the repository (or download the files):**
    ```bash
    # If you put this code in a Git repository:
    # git clone <your-repository-url>
    # cd <repository-directory>

    # Otherwise, just ensure you have the .py files in the same directory.
    ```

2.  **Install required libraries:**
    ```bash
    pip install requests beautifulsoup4
    ```

## Configuration

Before running, you might need to adjust settings within `minimal_agent.py`:

1.  **`OLLAMA_URL`**: Ensure this points to your running Ollama instance. The default (`http://localhost:11434/api/generate`) is usually correct for standard local installations. If you are using the newer `/api/chat` endpoint structure with Ollama, you might need to adjust the API call logic slightly.
2.  **`OLLAMA_MODEL`**: **Important:** Change the default value (`"llama3"`) to the exact name of the model you have pulled in Ollama and wish to use (e.g., `"mistral"`, `"phi3"`).

## Usage

1.  Make sure your Ollama service is running in the background.
2.  Run the agent script from your terminal:
    ```bash
    python minimal_agent.py
    ```
3.  The agent will initialize and prompt you for input (`You:`).
4.  Type your query and press Enter.
5.  The agent will interact with the LLM. If it decides to use the `fetch_web_content` tool, you will see log messages indicating the tool call and result (these are internal agent logs, not part of the final response).
6.  The agent will then provide its final answer.
7.  Type `'quit'` to exit the agent.

**Example Interaction:**

Minimal Agent Initialized. Ask me anything. Type 'quit' to exit.
You: What is the main topic of the Ollama website at ollama.com?
Agent: Ollama allows users to get up and running with large language models locally. It provides tools for running, creating, and sharing these models. Key features mentioned include a library of models, model customization capabilities, and support across different operating systems (macOS, Linux, Windows) and platforms like Docker. It emphasizes ease of use for developers and researchers working with LLMs locally.
You: quit

*(Note: The agent's internal thought process, including potential `TOOL_CALL` and `TOOL_RESULT` steps, happens behind the scenes but might be visible in logs if debugging is enabled).*

## How it Works

1.  **System Prompt:** A detailed prompt is constructed that instructs the LLM on its role, the available tools, and the *exact* format to use when it needs to call a tool (`TOOL_CALL: function_name(arg_name="value")`).
2.  **User Query:** The user's input is added to the prompt.
3.  **LLM Call:** The combined prompt is sent to the configured Ollama model.
4.  **Response Analysis:** The script checks the LLM's response:
    *   If it matches the `TOOL_CALL` format, the script parses the function name and arguments.
    *   If it doesn't match, the response is treated as the final answer.
5.  **Tool Execution:** If a tool call was detected:
    *   The corresponding Python function in `tool_functions.py` is executed with the provided arguments (e.g., `fetch_web_content` is called with the URL).
    *   The result (or an error message) is captured.
6.  **Feedback Loop:** The original `TOOL_CALL` and the `TOOL_RESULT:` are appended to the conversation history/prompt, and the LLM is called *again*, asking it to formulate a final answer using the new information.
7.  **Final Output:** The agent prints the final response generated by the LLM (either directly or after processing tool results).

## Extending with New Tools

Adding new tools follows a simple pattern:

1.  **Define Function:** Create a new Python function for your tool in `tool_functions.py`. It should take specific arguments and return a string result.
2.  **Register Tool:** Add the function name (as a string) and the function reference to the `AVAILABLE_TOOLS` dictionary in `tool_functions.py`.
3.  **Describe Tool:** Add a description of the new tool, including its function signature (name and arguments), to the `TOOL_DESCRIPTIONS` string in `tool_functions.py`. This string is used in the system prompt to tell the LLM about the tool.
4.  **Enhance Parsing (If Needed):** If your new tool uses arguments other than `url="value"`, you may need to update the `parse_tool_call` function in `minimal_agent.py` to correctly extract arguments for different tools (e.g., using more flexible regular expressions or argument parsing logic).

## Limitations

*   **Basic Tool Parsing:** Relies on simple string matching (`TOOL_CALL:...`). More complex interactions or argument types might require more robust parsing.
*   **Simple Context Management:** Only includes the immediate previous turn (LLM response/tool result) in the prompt context for the feedback loop. Does not maintain a long conversational history effectively.
*   **Error Handling:** Basic error handling for API calls and tool execution is included, but complex failure scenarios might not be handled gracefully.
*   **No Streaming:** Waits for the full Ollama response; doesn't process tokens as they arrive.
*   **Synchronous Tool Execution:** Tools are run sequentially, blocking the agent loop.

This project serves as a starting point. Concepts like more advanced prompting, structured output parsing (e.g., JSON), better memory management, asynchronous operations, and more sophisticated agent frameworks (like LangChain or LlamaIndex) build upon these fundamental ideas.