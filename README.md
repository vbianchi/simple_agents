# Minimal Ollama Agent with Playwright Web Browsing

This project implements a minimal "agentic" AI using Python, connecting to a local Ollama instance and featuring a web browsing tool powered by **Playwright**. This allows the agent to interact with modern, JavaScript-heavy websites more effectively than simple HTTP requests.

The goal is to demonstrate a basic agent loop with enhanced tool capability, showing how to integrate browser automation for information gathering.

This repository is available at: [https://github.com/vbianchi/simple_agents](https://github.com/vbianchi/simple_agents)

## Features

*   **Ollama Integration:** Connects to your running Ollama instance via its REST API.
*   **Local LLM Usage:** Uses instruction-following models available in your Ollama installation (e.g., Llama 3, Mistral).
*   **Playwright Tool Use:** Implements a `fetch_web_content` tool using Playwright to launch a headless browser (Chromium by default), render pages (including executing JavaScript), and extract the main textual content.
*   **Handles Dynamic Content:** Capable of extracting information from websites that rely heavily on JavaScript to display content.
*   **Simple Agent Loop:** Demonstrates the cycle of input -> LLM planning -> tool use -> result processing -> final response.
*   **Command-Line Interface:** Interact directly via your terminal.
*   **Extensible:** Designed for adding more tools later.

## Prerequisites

1.  **Python:** Python 3.7+ installed.
2.  **Ollama:** Ollama installed and **running**. ([https://ollama.com/](https://ollama.com/)).
3.  **Ollama Model:** An instruction-following model pulled into Ollama (e.g., `ollama pull llama3`). Configure the model name in `minimal_agent.py`.
4.  **Python Libraries:** `requests`, `beautifulsoup4`, and `playwright`.
5.  **Playwright Browsers:** Browser binaries for Playwright need to be installed separately.

## Installation

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/vbianchi/simple_agents.git
    cd simple_agents
    ```

2.  **Create and Activate a Python Virtual Environment:**
    *   macOS/Linux:
        ```bash
        python3 -m venv venv
        source venv/bin/activate
        ```
    *   Windows:
        ```bash
        python -m venv venv
        .\venv\Scripts\activate
        ```

3.  **Install Python Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Install Playwright Browsers:** This crucial step downloads the browser binaries (like Chromium) that Playwright controls.
    ```bash
    playwright install
    ```
    *(This might take a few minutes as it downloads browser executables).*

## Configuration

Before running, check `minimal_agent.py`:

1.  **`OLLAMA_URL`**: Ensure it points to your Ollama instance (default: `http://localhost:11434/api/generate`).
2.  **`OLLAMA_MODEL`**: **Change `"llama3"`** to the exact name of the Ollama model you want to use.

## Usage

1.  Ensure your Ollama service is running.
2.  Make sure your virtual environment is activated (`source venv/bin/activate` or equivalent).
3.  Run the agent script from the project directory:
    ```bash
    python minimal_agent.py
    ```
4.  The agent will initialize (mentioning Playwright) and prompt `You:`.
5.  Enter your query. If the agent needs web info, it will silently launch a headless browser via Playwright to fetch and render the page.
6.  The agent provides its final answer.
7.  Type `'quit'` to exit.

**Example Interaction:**

Minimal Agent Initialized. Ask me anything. Type 'quit' to exit.
You: What is the main topic of the Ollama website at ollama.com?
Agent: Ollama allows users to get up and running with large language models locally. It provides tools for running, creating, and sharing these models. Key features mentioned include a library of models, model customization capabilities, and support across different operating systems (macOS, Linux, Windows) and platforms like Docker. It emphasizes ease of use for developers and researchers working with LLMs locally.
You: quit

*(Note: The agent's internal thought process, including potential `TOOL_CALL` and `TOOL_RESULT` steps, happens behind the scenes but might be visible in logs if debugging is enabled).*

## How it Works

1.  **System Prompt:** Instructs the LLM on its role, the `fetch_web_content` tool (powered by Playwright), and the `TOOL_CALL` format.
2.  **User Query & LLM Call:** The user's query is sent to Ollama.
3.  **Response Analysis:** Checks if the LLM output is a `TOOL_CALL` for `fetch_web_content`.
4.  **Tool Execution (Playwright):**
    *   If a tool call is detected, the `fetch_web_content` function in `tool_functions.py` is executed.
    *   It uses `sync_playwright` to launch a headless Chromium browser.
    *   Navigates to the requested URL, allowing JavaScript to execute.
    *   Extracts the rendered HTML content.
    *   Uses BeautifulSoup to clean the HTML and extract the main text.
    *   Returns the cleaned text or an error message.
    *   Closes the browser.
5.  **Feedback Loop:** The `TOOL_RESULT` (fetched text or error) is sent back to the LLM within an updated prompt.
6.  **Final Output:** The LLM generates the final answer based on the processed information.

## Limitations & Considerations

*   **Resource Intensive:** Playwright launches real browser processes, requiring significantly more CPU and RAM than `requests`.
*   **Slower:** Fetching takes longer due to browser launch and page rendering time.
*   **Installation Complexity:** Requires the extra `playwright install` step.
*   **Error Handling:** Basic Playwright errors (timeouts, navigation failures) are handled, but complex browser/website issues might still occur.
*   **Basic Agent Structure:** Still uses a simple loop, context management, and synchronous execution.

This version provides more powerful web interaction capabilities, forming a stronger base for a more capable agent, while still keeping the core agent logic relatively simple.