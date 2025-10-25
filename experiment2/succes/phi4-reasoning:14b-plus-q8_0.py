#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Simplified Coding Agent V2 – Single File Version
This tool generates code based on a natural language prompt,
runs unit tests against it (using an external API), and can even try to debug failing code.
All database‐related functionality has been removed.
"""

import requests
import json
import traceback
import re
import os
import shutil
import sys
from typing import Optional, List, Tuple
import subprocess

# Global configuration for the coding agent (API URL, output directory and model settings)
CODING_AGENT_CONFIG = {
    "OLLAMA_API_URL": "http://192.168.1.127:11434/api/chat",
    "OUTPUT_DIR": "generated_code",
    "MODELS": {
        "coder": {"name": "qwen3-coder:latest", "options": {"temperature": 0.6, "num_ctx": 16000, "top_p": 0.95}},
        "tester": {"name": "qwen3-coder:latest", "options": {"temperature": 0.1, "num_ctx": 16000, "top_p": 0.8}},
        "debugger": {"name": "qwen3-coder:latest", "options": {"temperature": 0.1, "num_ctx": 16000, "top_p": 0.95}},
        "analyzer": {"name": "qwen3-coder:latest", "options": {"temperature": 0.0, "num_ctx": 16000}},
        "planner": {"name": "qwen3-coder:latest", "options": {"temperature": 0.2, "num_ctx": 16000, "top_p": 0.8}}
    }
}

MAX_DEBUG_ATTEMPTS = 3
MAX_TEST_REGEN_ATTEMPTS = 2

# -----------------------------------------------------------------------------
# Simplified ProjectManager – handles a temporary directory for the project.
# -----------------------------------------------------------------------------
class ProjectManager:
    def __init__(self, base_dir: str = "temp_coding_project"):
        self.base_dir = base_dir
        self.current_dir = None

    def create_project(self):
        print(f"ProjectManager: Creating new project directory at '{self.base_dir}'...")
        if os.path.exists(self.base_dir):
            shutil.rmtree(self.base_dir)
            print("ProjectManager: Removed old directory.")
        os.makedirs(self.base_dir)
        self.current_dir = self.base_dir
        print("ProjectManager: Directory created.")

    def write_file(self, file_name: str, content: str):
        if not self.current_dir:
            raise RuntimeError("No project directory exists. Call create_project() first.")
        file_path = os.path.join(self.current_dir, file_name)
        print(f"ProjectManager: Writing file '{file_name}'...")
        with open(file_path, "w") as f:
            f.write(content)

    def run_command(self, command: List[str], timeout: int = 60) -> Tuple[str, str, int]:
        if not self.current_dir:
            raise RuntimeError("No project directory exists. Call create_project() first.")
        print(f"ProjectManager: Executing command: {' '.join(command)}")
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
            print(f"ProjectManager: Cleaning up project directory '{self.base_dir}'...")
            shutil.rmtree(self.base_dir)
            self.current_dir = None
            print("ProjectManager: Cleanup complete.")

# -----------------------------------------------------------------------------
# CodingAgentV2 – generates code, creates unit tests, runs them and can debug failures.
# -----------------------------------------------------------------------------
class CodingAgentV2:
    def __init__(self, project_manager: ProjectManager):
        self.project_manager = project_manager
        os.makedirs(CODING_AGENT_CONFIG["OUTPUT_DIR"], exist_ok=True)

    def _call_ollama_api(self, messages: list, model_key: str) -> str:
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
            print(f"CodingAgentV2 API Error: {e}")
            return f"Error: Failed to connect to '{model_config['name']}' API. Details: {e}"

    def _generate_test_plan(self, language: str, code_prompt: str) -> str:
        print("  -> [CodingAgentV2] Generating test plan from prompt...")
        prompt = f"""
You are an expert Quality Assurance (QA) engineer. Your task is to create a detailed, step-by-step test plan for a piece of code that will be written in {language}.
Analyze the following user request and break it down into a numbered list of specific test cases.

== User Code Request ==
{code_prompt}

== Instructions ==
1. Identify the core functionalities described in the request.
2. For each functionality, define at least one "happy path" test case (i.e., it works with normal, expected inputs).
3. Identify and create test cases for edge conditions (e.g., empty inputs, zero, large numbers, empty strings).
4. Identify and create test cases for error conditions (e.g., invalid input types, division by zero).
5. Format your output as a clean, numbered list.
        
Example Output:
1. Test the add function with two positive integers.
2. Test the add function with a positive and a negative integer.
3. Test the divide function with a non-zero denominator.
4. Test that the divide function raises a ValueError when the denominator is zero.
"""
        messages = [{'role': 'user', 'content': prompt}]
        return self._call_ollama_api(messages, "planner")

    def _generate_code(self, language: str, prompt: str, initial_code: Optional[str] = None, mode: str = 'generate') -> str:
        print(f"  -> [CodingAgentV2] Generating {language} code in {mode} mode...")
        system_prompt = f"""You are an expert {language} programmer. Your task is to write a single, clean, well-commented, and efficient code snippet that fulfills the user's request.
Respond with ONLY the code snippet, enclosed in a single markdown code block. Do not include any explanations or conversational text outside the code block."""
        
        user_message = prompt
        if initial_code:
            if mode == 'refactor':
                user_message = f"Please improve this existing code based on the following prompt:\n\n== Existing Code ==\n```python\n{initial_code}\n```\n\n== Improvement Prompt ==\n{prompt}"
            elif mode == 'debug':
                user_message = f"Please debug and fix this existing code based on the following prompt and a test plan that will be provided:\n\n== Existing Code ==\n```python\n{initial_code}\n```\n\n== Debugging Prompt ==\n{prompt}"
        
        messages = [{'role': 'system', 'content': system_prompt}, {'role': 'user', 'content': user_message}]
        raw_code = self._call_ollama_api(messages, "coder")
        return re.sub(r'```python|```', '', raw_code).strip()

    def _generate_unit_tests(self, file_name: str, code_content: str, test_plan_description: str) -> str:
        print("  -> [CodingAgentV2] Generating unit tests...")
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
1. Write valid `pytest` test functions. Name the test file `test_{file_name.replace('.py', '')}.py`.
2. Import the necessary classes/functions from the original file.
3. Implement test cases that cover all aspects mentioned in the `Test Plan`.
4. For negative test cases (e.g., expected errors), use `pytest.raises`.
5. Use assertions (`assert`) to verify expected behavior.
6. Return ONLY the Python code for the unit tests. Do NOT include any explanations or markdown fences.
"""
        raw_test_code = self._call_ollama_api([{'role': 'user', 'content': prompt}], "tester")
        return re.sub(r'```python|```', '', raw_test_code).strip()

    def _debug_code(self, code_content: str, test_output: str, test_file: str) -> str:
        print("  -> [CodingAgentV2] Debugging failed code...")
        prompt = f"""
You are a senior software engineer. The following code snippet failed to pass its unit tests.
Your task is to analyze the code and the test failure output, identify the bug, and provide a corrected version of the code.

== Original Code ==
```python
{code_content}
```

== Test Failure Output (from {test_file}) ==
```
{test_output}
```

== Instructions ==
1. Carefully examine the code and the test output to find the root cause of the error.
2. Provide a corrected version of the ENTIRE code snippet.
3. Return ONLY the corrected Python code, enclosed in a single markdown code block.
"""
        messages = [{'role': 'user', 'content': prompt}]
        raw_fixed_code = self._call_ollama_api(messages, "debugger")
        return re.sub(r'```python|```', '', raw_fixed_code).strip()
    
    def _analyze_test_failure(self, code_content: str, test_output: str) -> str:
        print("  -> [CodingAgentV2] Analyzing test failure with analyzer model...")
        prompt = f"""
You are a quality assurance expert. Analyze the provided Python code and the output from a failed test run.
Your task is to determine if the failure is due to a bug in the code or a flaw in the generated tests.

== Code ==
```python
{code_content}
```

== Test Failure Output ==
```
{test_output}
```

Based on your analysis, state whether the failure is a result of a bug in the code or a flaw in the test.
Respond with ONLY one of the following keywords: 'code_bug', 'test_bug', or 'cannot_determine'.
"""
        messages = [{'role': 'user', 'content': prompt}]
        analysis_result = self._call_ollama_api(messages, "analyzer").strip().lower()
        return analysis_result if analysis_result in ['code_bug', 'test_bug'] else 'cannot_determine'

    def execute_coding_agent_v2(self, language: str, code_file: str, prompt: str, test_plan: str, mode: str = 'generate', initial_code: Optional[str] = None) -> str:
        final_answer = "An error occurred during the coding process."
        test_passed = False
        
        try:
            self.project_manager.create_project()
            
            if initial_code and mode in ['refactor', 'debug']:
                generated_code = self._generate_code(language, prompt, initial_code, mode)
            else:
                generated_code = self._generate_code(language, prompt)
            
            self.project_manager.write_file(code_file, generated_code)
            
            test_file = f"test_{code_file}"
            test_output = ""
            analysis_result = 'code_bug'  # Default assumption
            
            for attempt in range(MAX_DEBUG_ATTEMPTS + MAX_TEST_REGEN_ATTEMPTS):
                print(f"  -> [CodingAgentV2] Starting test attempt {attempt + 1}...")
                generated_tests = self._generate_unit_tests(code_file, generated_code, test_plan)
                self.project_manager.write_file(test_file, generated_tests)
                
                stdout, stderr, returncode = self.project_manager.run_command(['pytest', '-q', '--tb=no', test_file])
                
                if returncode == 0:
                    print(f"  -> [CodingAgentV2] Tests passed successfully on attempt {attempt + 1}.")
                    test_output = stdout
                    test_passed = True
                    break
                else:
                    print(f"  -> [CodingAgentV2] Tests failed on attempt {attempt + 1}. Analyzing failure...")
                    test_output = stdout + stderr
                    
                    analysis_result = self._analyze_test_failure(generated_code, test_output)
                    print(f"  -> [CodingAgentV2] Analysis result: '{analysis_result}'")
                    
                    if analysis_result == 'code_bug' and attempt < MAX_DEBUG_ATTEMPTS:
                        print("  -> [CodingAgentV2] Identified as a code bug. Attempting to debug...")
                        generated_code = self._debug_code(generated_code, test_output, test_file)
                        self.project_manager.write_file(code_file, generated_code)
                    elif analysis_result == 'test_bug' and attempt < MAX_TEST_REGEN_ATTEMPTS:
                        print("  -> [CodingAgentV2] Identified as a test bug. Regenerating tests...")
                        # Loop will try again with new unit tests
                        continue
                    else:
                        print("  -> [CodingAgentV2] Cannot determine cause or max attempts reached. Stopping.")
                        break

            final_file_path = os.path.join(CODING_AGENT_CONFIG["OUTPUT_DIR"], code_file)
            print(f"\n  -> [CodingAgentV2] Saving final code to '{final_file_path}'...")
            shutil.copy(os.path.join(self.project_manager.current_dir, code_file), final_file_path)

            if test_passed:
                final_answer = (f"I have successfully generated and tested the code. All tests passed.\n"
                                f"The final code has been saved to `{final_file_path}`.\n\n"
                                f"**Code:**\n```python\n{generated_code}\n```\n\n"
                                f"**Test Results:**\n```\n{test_output}\n```")
            else:
                analysis_message = ("I was unable to fix a bug in the code within the allowed attempts."
                                   if analysis_result == 'code_bug'
                                   else "The analysis suggests the failure may be due to a flaw in the generated tests.")
                final_answer = (f"I was unable to produce a working solution that passes all tests.\n"
                                f"The last code version has been saved to `{final_file_path}`.\n\n"
                                f"{analysis_message}\n\n"
                                f"**Last Code Attempt:**\n```python\n{generated_code}\n```\n\n"
                                f"**Final Test Output:**\n```\n{test_output}\n```")
        except Exception as e:
            final_answer = f"An unexpected error occurred during coding agent execution: {e}\n{traceback.format_exc()}"
        finally:
            self.project_manager.cleanup()
        
        return final_answer

# -----------------------------------------------------------------------------
# Helper function to get multi-line input from the user.
# -----------------------------------------------------------------------------
def _get_multiline_input(prompt_message: str) -> str:
    print(f"\n{prompt_message}")
    print(" (Enter your text. Press Ctrl-D on Linux/macOS or Ctrl-Z+Enter on Windows when done)")
    lines = sys.stdin.readlines()
    return "".join(lines).strip()

# -----------------------------------------------------------------------------
# Main interactive function.
# -----------------------------------------------------------------------------
def main():
    print("--- Coding Agent V2: Interactive Mode ---")
    print("Please provide the following details for your coding task.")
    
    try:
        language = input("\n▶ Enter the programming language (e.g., python): ")
        code_file = input("▶ Enter the target filename (e.g., my_module.py): ")
        prompt = _get_multiline_input("▶ Enter the main prompt describing the code:")

        # Auto or manual test plan generation
        test_plan = ""
        while not test_plan:
            plan_choice = input("\n▶ Test Plan: [M]anual entry or [A]uto-generate? (M/a): ").lower().strip() or 'm'
            if plan_choice == 'a':
                # Create a temporary CodingAgentV2 instance to get the proposed plan
                generated_plan = CodingAgentV2(ProjectManager())._generate_test_plan(language, prompt)
                print("\n--- Proposed Test Plan ---")
                print(generated_plan)
                print("--------------------------")
                confirm = input("▶ Use this plan? [Y/n] (or 'm' to enter manually): ").lower().strip() or 'y'
                if confirm == 'y':
                    test_plan = generated_plan
                elif confirm == 'n':
                    continue
                else:
                    test_plan = _get_multiline_input("▶ Enter your manual test plan:")
            else:
                test_plan = _get_multiline_input("▶ Enter your manual test plan:")

        mode = input("\n▶ Enter mode [generate, refactor, debug] (default: generate): ").lower().strip() or 'generate'
        if mode not in ['generate', 'refactor', 'debug']:
            print(f"  (Invalid mode '{mode}', defaulting to 'generate'.)")
            mode = 'generate'
        
        initial_code = None
        if mode in ['refactor', 'debug']:
            use_initial_file = input(f"▶ Do you want to provide an initial code file for '{mode}' mode? [y/N]: ").lower().strip()
            if use_initial_file == 'y':
                initial_code_file = input("  ▶ Enter the path to the initial code file: ")
                try:
                    with open(initial_code_file, 'r') as f:
                        initial_code = f.read()
                    print(f"--- Loaded initial code from '{initial_code_file}' ---")
                except FileNotFoundError:
                    print(f"FATAL: The initial code file '{initial_code_file}' was not found.")
                    return
        
        pm = ProjectManager()  # Create a new project manager instance.
        coding_agent = CodingAgentV2(pm)
        
        print("\n--- Initializing Agent and Starting Task ---")
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