# Project TIMO: Phased Development Plan

This document outlines the planned enhancements for the Simple Ollama Planner-Executor Agent (TIMO), building upon the existing architecture.

## Phase 1: Enable Web Discovery (Core Search Capability)

*   **Goal:** Allow the agent to find information online when specific URLs are not provided by the user.
*   **Tasks:**
    *   [ ] **Add Dependency:** Add `duckduckgo-search` library to `requirements.txt`.
    *   [ ] **Implement Tool:** Create `tools/search_tools.py` containing a `web_search(query, num_results)` function using `duckduckgo-search`. Include tool descriptions dictionary (`SEARCH_TOOL_DESCRIPTIONS`).
    *   [ ] **Integrate Tool:**
        *   Import `web_search` and `SEARCH_TOOL_DESCRIPTIONS` into `agent/planner_executor.py`.
        *   Add `web_search` to the `AVAILABLE_TOOLS_EXEC` dictionary.
        *   Modify `format_tool_descriptions()` to include the search tool description.
        *   Update tool validation checks in `generate_plan` and `parse_action_json` to recognize `web_search`.
    *   [ ] **Enhance Planner Prompt:** Update `PLANNER_SYSTEM_PROMPT_TEMPLATE` in `agent/prompts.py`:
        *   Include `web_search` in the list of available tools.
        *   Add instructions explaining *when* to use `web_search` (i.e., when URLs are unknown).
        *   Provide new examples demonstrating plans that use `web_search` first (e.g., search -> write results, search -> extract URL -> fetch).
    *   [ ] **Testing:** Test scenarios like "Find websites about X", "Search for Y and save the results".

## Phase 2: Enable PDF Document Handling

*   **Goal:** Allow the agent to extract text content from PDF files found online.
*   **Prerequisites:** Phase 1 completed.
*   **Tasks:**
    *   [ ] **Choose & Add Dependency:** Select a PDF parsing library (e.g., `PyMuPDF` (fitz) or `PyPDF2`) and add it to `requirements.txt`.
    *   [ ] **Modify `fetch_web_content` Tool:** Update the function in `tools/web_tools.py`:
        *   Check the `Content-Type` header of the HTTP response.
        *   If `application/pdf`, download the file to the `session_path` instead of trying to parse HTML. Use a predictable filename or derive one from the URL/headers.
        *   Return a success message indicating the PDF was downloaded (e.g., "Success: Downloaded PDF file 'downloaded_report.pdf'").
    *   [ ] **Implement PDF Extraction Tool:** Create `tools/pdf_tools.py` (or add to `file_tools.py`):
        *   Implement a function `extract_text_from_pdf(filename)` that takes a filename (relative to `session_path`).
        *   Use the chosen library to open the PDF from the workspace and extract its text content.
        *   Return the extracted text or an error message.
        *   Include tool descriptions dictionary (`PDF_TOOL_DESCRIPTIONS`).
    *   [ ] **Integrate Extraction Tool:** Add the new PDF extraction tool and its description to `agent/planner_executor.py` (similar to Phase 1 integration steps).
    *   [ ] **Enhance Planner Prompt:** Update `PLANNER_SYSTEM_PROMPT_TEMPLATE`:
        *   Include the PDF extraction tool.
        *   Add instructions/examples showing the sequence: `fetch_web_content` (downloads PDF) -> `extract_text_from_pdf` -> use extracted text.
    *   [ ] **Testing:** Test scenarios involving finding and processing information contained within PDF documents linked online.

## Phase 3: Improve Data Extraction and Complex Planning

*   **Goal:** Enhance the agent's ability to pull specific information from fetched content (HTML/PDF text) and handle more complex multi-step workflows.
*   **Prerequisites:** Phase 1 & 2 completed.
*   **Tasks:**
    *   [ ] **Refine Extraction Prompts:** Experiment with and refine the `GENERATION_PROMPT_TEMPLATE` and how it's used in `main.py` for the `generate_text` pseudo-tool when the task involves extracting specific data points (e.g., "Extract the table from...", "Find the values for X, Y, Z in...").
    *   [ ] **Enhance Planner Prompt (Complex Chains):** Add more sophisticated examples to `PLANNER_SYSTEM_PROMPT_TEMPLATE` demonstrating complex chains like search -> select URL -> fetch -> extract data -> format -> write (e.g., based on Scenario 2: Dutch Farms, Scenario 3: Product Comparison). Emphasize breaking down complex requests.
    *   [ ] **Intermediate Data Handling:** Review if the current `output_ref` mechanism and passing full text via `step_results` is sufficient for large data, or if intermediate results should always be written to files and read back (consider trade-offs). *Decision needed based on testing.*
    *   [ ] **Testing:** Focus on scenarios requiring structured data extraction (tables, specs) and aggregation from multiple sources. Evaluate the reliability of LLM-based extraction via `generate_text`.

## Phase 4: Robustness, Advanced Tools, and User Experience

*   **Goal:** Make the agent more reliable, capable with specialized tasks, and potentially more interactive.
*   **Tasks (Select based on priority/need):**
    *   [ ] **Context Window Management:** Investigate strategies if context limits are hit (e.g., summarizing intermediate results, using rolling context windows).
    *   [ ] **Error Handling & Replanning:** Implement more sophisticated error handling in `main.py`. Could the agent attempt to retry a failed step with different parameters, or even trigger a replan if a core step fails?
    *   [ ] **Explore Dedicated Parsing Tools:** For tasks like extracting tables from HTML, investigate dedicated libraries (like `pandas.read_html`) and potentially wrap them as new tools if LLM extraction proves unreliable for certain structures.
    *   [ ] **Add More Tools:** Consider adding tools based on common needs (e.g., dedicated summarization model/API, code execution sandbox, specific API integrations).
    *   [ ] **User Feedback/Interaction:** Add options for more verbose logging during execution, or potentially pause and ask the user for clarification/confirmation at key decision points (e.g., which URL to follow).
