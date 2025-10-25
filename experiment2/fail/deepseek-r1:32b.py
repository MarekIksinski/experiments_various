#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sat Oct 25 21:57:57 2025

@author: marek
"""
import subprocess
import requests
import json
import traceback
import re
import os
import shutil
import sys
from typing import Dict, Any, Optional

# Configuration for this specific tool
CODING_AGENT_CONFIG = {
    "OLLAMA_API_URL": "http://192.168.1.127:11434/api/chat",
    "OUTPUT_DIR": "generated_code",
    "MODELS": {
        "coder": {"name": "qwen3-coder:latest", "options": {"temperature": 0.6, "num_ctx": 16000, "top_p": 0.95}},
        "tester": {"name": "qwen3-coder:latest", "options": {"temperature": 0.1, "num_ctx": 16000, "top_p": 0.8}},
        "debugger": {"name": "qwen3-coder:latest", "options": {"temperature": 0.1, "num_ctx": 16000, "top_p": 0.95}},
        "analyzer": {"name": "qwen3-coder:latest", "options": {"temperature": 0.0, "num_ctx": 16000}},
        # --- NEW: Model for generating the test plan from the prompt ---
        "planner": {"name": "qwen3-coder:latest", "options": {"temperature": 0.2, "num_ctx": 16000, "top_p": 0.8}}
    }
}

MAX_DEBUG_ATTEMPTS = 3
MAX_TEST_REGEN_ATTEMPTS = 2

class ProjectManager:
    def __init__(self, base_dir="temp_project"):
        self.base_dir = base_dir
        self.current_dir = None

    def create_project(self):
        if os.path.exists(self.base_dir):
            shutil.rmtree(self.base_dir)
        os.makedirs(self.base_dir)
        self.current_dir = self.base_dir

    def write_file(self, file_name: str, content: str):
        file_path = os.path.join(self.current_dir, file_name)
        with open(file_path, "w") as f:
            f.write(content)

    def run_command(self, command: list[str], timeout: int = 60) -> tuple[str, str, int]:
        try:
            result = subprocess.run(
                command,
                cwd=self.current_dir,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            return result.stdout, result.stderr, result.returncode
        except subprocess.TimeoutExpired:
            return "", "Error: Command timed out.", 1
        except Exception as e:
            return "", f"Error: Failed to execute command. Details: {e}", 1

    def cleanup(self):
        if self.base_dir and os.path.exists(self.base_dir):
            shutil.rmtree(self.base_dir)
            self.current_dir = None

class CodingAgentV2:
    def __init__(self):
        self.project_manager = ProjectManager(base_dir="temp_coding_project")
        os.makedirs(CODING_AGENT_CONFIG["OUTPUT_DIR"], exist_ok=True)

    def _call_ollama_api(self, messages: list, model_key: str) -> str:
        try:
            payload = {
                "model": CODING_AGENT_CONFIG["MODELS"]["coder"]["name"],
                "messages": messages,
                "options": CODING_AGENT_CONFIG["MODELS"]["coder"]["options"],
                "stream": False
            }
            response = requests.post(CODING_AGENT_CONFIG["OLLAMA_API_URL"], json=payload, timeout=None)
            response.raise_for_status()
            return response.json().get("message", {}).get("content", "").strip()
        except requests.exceptions.RequestException as e:
            print(f"Coding Agent API Error: {e}")
            return f"Error: Failed to connect to the model. Details: {e}"

    def _generate_code(self, language: str, prompt: str, initial_code: Optional[str] = None, mode: str = 'generate') -> str:
        system_prompt = f"You are an expert {language} programmer. Your task is to write a single, clean, well-commented, and efficient code snippet that fulfills the user's request."
        
        if initial_code:
            if mode == 'refactor':
                prompt = f"Please improve this existing code based on the following prompt:\n\n== Existing Code ==\n```python\n{initial_code}\n```\n\n== Improvement Prompt ==\n{prompt}"
            elif mode == 'debug':
                prompt = f"Please debug and fix this existing code based on the following prompt:\n\n== Existing Code ==\n```python\n{initial_code}\n```\n\n== Debugging Prompt ==\n{prompt}"

        messages = [{'role': 'system', 'content': system_prompt}, {'role': 'user', 'content': prompt}]
        raw_code = self._call_ollama_api(messages, "coder")
        return re.sub(r'```python|```', '', raw_code).strip()

    def _generate_unit_tests(self, file_name: str, code_content: str, test_plan_description: str) -> str:
        prompt = f"""
        You are an expert Python unit test developer. Your task is to write pytest unit tests for the provided Python code, strictly following the test plan.

        == Original Python File Name ==
        {file_name}

        == Generated Python Code ==
        ```python
        {code_content}
        ```

        == Test Plan ==
        {test_plan_description}

        == Instructions ==
        1. Write valid `pytest` test functions.
        2. Import the necessary classes/functions from the original file.
        3. Implement test cases that cover all aspects mentioned in the `Test Plan`.
        """
        raw_test_code = self._call_ollama_api([{'role': 'user', 'content': prompt}], "tester")
        return re.sub(r'```python|```', '', raw_test_code).strip()

    def _debug_code(self, code_content: str, test_output: str) -> str:
        prompt = f"""
        You are a senior software engineer. The following code snippet failed to pass its unit tests.
        Your task is to analyze the code and the test failure output, identify the bug, and provide a corrected version of the code.

        == Original Code ==
        ```python
        {code_content}
        ```

        == Test Failure Output ==
        ```
        {test_output}
        ```

        Based on your analysis, provide the corrected version of the entire code snippet.
        """
        messages = [{'role': 'user', 'content': prompt}]
        raw_fixed_code = self._call_ollama_api(messages, "debugger")
        return re.sub(r'```python|```', '', raw_fixed_code).strip()

    def execute_coding_agent_v2(self, language: str, code_file: str, prompt: str, test_plan: str, mode: str = 'generate', initial_code: Optional[str] = None) -> str:
        final_answer = "An error occurred during the coding process."
        test_passed = False

        try:
            self.project_manager.create_project()

            generated_code = self._generate_code(language, prompt, initial_code, mode)
            self.project_manager.write_file(code_file, generated_code)

            test_file = f"test_{code_file}"
            test_output = ""

            for attempt in range(MAX_DEBUG_ATTEMPTS + MAX_TEST_REGEN_ATTEMPTS):
                print(f"Starting test attempt {attempt + 1}...")
                generated_tests = self._generate_unit_tests(code_file, generated_code, test_plan)
                self.project_manager.write_file(test_file, generated_tests)

                stdout, stderr, returncode = self.project_manager.run_command(['pytest', '-q', '--tb=no', test_file])

                if returncode == 0:
                    print(f"Tests passed successfully on attempt {attempt + 1}.")
                    test_passed = True
                    break

            final_file_path = os.path.join(CODING_AGENT_CONFIG["OUTPUT_DIR"], code_file)
            shutil.copy(os.path.join(self.project_manager.current_dir, code_file), final_file_path)

            if test_passed:
                final_answer = f"I have successfully generated and tested the code. All tests passed.\nThe final code has been saved to `{final_file_path}`."
            else:
                final_answer = f"I was unable to produce a working solution that passes all tests.\nThe last code version has been saved to `{final_file_path}`."

        except Exception as e:
            final_answer = f"An unexpected error occurred: {e}\n{traceback.format_exc()}"

        finally:
            self.project_manager.cleanup()

        return final_answer

def _get_multiline_input(prompt_message: str) -> str:
    print(f"\n{prompt_message}")
    print(" (Enter your text. Press Ctrl-D on Linux/macOS or Ctrl-Z+Enter on Windows when done)")
    lines = sys.stdin.readlines()
    return "".join(lines).strip()

def main():
    print("--- Coding Agent V2: Interactive Mode ---")
    print("Please provide the following details for your coding task.")

    try:
        language = input("\n▶ Enter the programming language (e.g., python): ")
        code_file = input("▶ Enter the target filename (e.g., my_module.py): ")
        prompt = _get_multiline_input("▶ Enter the main prompt describing the code:")

        test_plan = ""
        while not test_plan:
            plan_choice = input("\n▶ Test Plan: [M]anual entry or [A]uto-generate? (M/a): ").lower().strip() or 'm'
            if plan_choice == 'a':
                coding_agent = CodingAgentV2()
                generated_plan = coding_agent._call_ollama_api([{'role': 'user', 'content': f"Create a test plan for the following code request:\n{prompt}"}], "planner")
                print("\n--- Proposed Test Plan ---\n", generated_plan)
                confirm = input("▶ Use this plan? [Y/n] (or 'm' to enter manually): ").lower().strip() or 'y'
                if confirm == 'y':
                    test_plan = generated_plan
            else:
                test_plan = _get_multiline_input("▶ Enter your manual test plan:")

        mode = input("\n▶ Enter mode [generate, refactor, debug] (default: generate): ").lower().strip() or 'generate'

        initial_code = None
        if mode in ['refactor', 'debug']:
            use_initial_file = input(f"▶ Do you want to provide an initial code file for '{mode}' mode? [y/N]: ").lower().strip()
            if use_initial_file == 'y':
                initial_code_file = input("  ▶ Enter the path to the initial code file: ")
                try:
                    with open(initial_code_file, 'r') as f:
                        initial_code = f.read()
                except FileNotFoundError:
                    print(f"FATAL: The initial code file '{initial_code_file}' was not found.")
                    return

        coding_agent = CodingAgentV2()
        final_result = coding_agent.execute_coding_agent_v2(
            language=language, code_file=code_file,
            prompt=prompt, test_plan=test_plan, mode=mode, initial_code=initial_code
        )

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