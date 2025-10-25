#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Simplified Coding Agent V2 (Single File Script)
"""

import requests
import json
import traceback
import re
import os
import shutil
import sys # Needed for interactive multi-line input

CODING_AGENT_CONFIG = {
    "OLLAMA_API_URL": "http://192.168.1.127:11434/api/chat",
    "OUTPUT_DIR": "generated_code",
    "MODELS": {
        "coder": {"name": "qwen3-coder:latest", "options": {"temperature": 0.6, "num_ctx": 16000, "top_p": 0.95}},
        "tester": {"name": "qwen3-coder:latest", "options": {"temperature": 0.1, "num_ctx": 16000, "top_p": 0.8}},
    }
}

class CodingAgentV2:
    def __init__(self):
        os.makedirs(CODING_AGENT_CONFIG["OUTPUT_DIR"], exist_ok=True)

    def _call_ollama_api(self, messages: list, model_key: str) -> str:
        """Internal helper to send requests to the Ollama API."""
        model_config = CODING_AGENT_CONFIG["MODELS"].get(model_key)
        if not model_config:
            raise ValueError(f"Model key '{model_key}' not found in config.")

        try:
            payload = {
                "model": model_config["name"],
                "messages": messages,
                "options": model_config["options"],
                "stream": False
            }
            response = requests.post(CODING_AGENT_CONFIG["OLLAMA_API_URL"], json=payload, timeout=None)
            response.raise_for_status()
            return response.json().get("message", {}).get("content", "").strip()
        except requests.exceptions.RequestException as e:
            print(f"Coding Agent API Error: {e}")
            return f"Error: Failed to connect to '{model_config['name']}' API. Details: {e}"

    def _generate_code(self, language: str, prompt: str) -> str:
        """Generates a code snippet based on a natural language prompt."""
        print(f"  -> Generating {language} code...")
        system_prompt = f"""You are an expert {language} programmer. Your task is to write a single, clean, well-commented, and efficient code snippet that fulfills the user's request.
        Respond with ONLY the code snippet, enclosed in a single markdown code block. Do not include any explanations or conversational text outside the code block."""

        messages = [{'role': 'system', 'content': system_prompt}, {'role': 'user', 'content': prompt}]
        raw_code = self._call_ollama_api(messages, "coder")
        cleaned_code = re.sub(r'```python|```', '', raw_code).strip()
        return cleaned_code

    def _generate_unit_tests(self, code_content: str) -> str:
        """Generates unit tests based on the provided code content."""
        print("  -> Generating unit tests...")
        prompt = f"""
        You are an expert Python unit test developer. Your task is to write pytest unit tests for the provided Python code.

        == Generated Python Code ==
        ```python
        {code_content}
        ```

        == Instructions ==
        1. Write valid `pytest` test functions.
        2. Import necessary classes/functions from the original file.
        3. Implement test cases that cover all aspects of the code.
        4. Return ONLY the Python code for the unit tests without markdown fences.
        """
        raw_test_code = self._call_ollama_api([{'role': 'user', 'content': prompt}], "tester")
        cleaned_test_code = re.sub(r'```python|```', '', raw_test_code).strip()
        return cleaned_test_code

    def execute_coding_agent_v2(self, language: str, code_file: str, prompt: str) -> str:
        """Orchestrates the entire code generation and testing process."""
        try:
            generated_code = self._generate_code(language, prompt)
            print(f"  -> Saving code to '{code_file}'...")
            with open(code_file, "w") as f:
                f.write(generated_code)

            test_file = f"test_{code_file}"
            generated_tests = self._generate_unit_tests(generated_code)
            print(f"  -> Saving tests to '{test_file}'...")
            with open(test_file, "w") as f:
                f.write(generated_tests)

            # Run pytest (assuming it's installed in the environment)
            print("  -> Running unit tests...")
            test_output = os.popen(f"pytest -q --tb=no {test_file}").read()

            if "FAILED" not in test_output:
                return f"Code generation and testing successful. All tests passed.\n\nFinal code:\n```python\n{generated_code}\n```\n\nTest results:\n{test_output}"
            else:
                return f"Code generation failed. Tests did not pass.\n\nGenerated code:\n```python\n{generated_code}\n```\n\nTest output:\n{test_output}"

        except Exception as e:
            return f"An error occurred during execution: {e}\n{traceback.format_exc()}"

def _get_multiline_input(prompt_message: str) -> str:
    """Helper function to get multi-line input from the user."""
    print(f"\n{prompt_message}")
    print(" (Enter your text. Press Ctrl-D on Linux/macOS or Ctrl-Z+Enter on Windows when done)")
    lines = sys.stdin.readlines()
    return "".join(lines).strip()

def main():
    """Main function to run the agent in an interactive CLI mode."""
    print("--- Coding Agent V2: Interactive Mode ---")
    try:
        language = input("\n▶ Enter the programming language (e.g., python): ")
        code_file = input("▶ Enter the target filename (e.g., my_module.py): ")
        prompt = _get_multiline_input("▶ Enter the main prompt describing the code:")

        coding_agent = CodingAgentV2()
        final_result = coding_agent.execute_coding_agent_v2(language, code_file, prompt)
        print("\n" + "="*50)
        print("          AGENT EXECUTION COMPLETE")
        print("="*50 + "\n")
        print(final_result)

    except KeyboardInterrupt:
        print("\n\n--- Operation cancelled by user. Exiting. ---")
    except Exception as e:
        print(f"\n--- An unexpected error occurred: {e} ---")

if __name__ == "__main__":
    main()