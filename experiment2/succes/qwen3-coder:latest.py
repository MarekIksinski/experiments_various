#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sat Oct 25 23:50:12 2025

@author: marek
"""

import requests
import json
import re
import os
import shutil
import subprocess
import sys
from typing import Optional, Tuple

# --- Configuration ---
OLLAMA_API_URL = "http://192.168.1.127:11434/api/chat"
MODELS = {
    "coder": {"name": "qwen3-coder:latest", "options": {"temperature": 0.6, "num_ctx": 16000, "top_p": 0.95}},
    "tester": {"name": "qwen3-coder:latest", "options": {"temperature": 0.1, "num_ctx": 16000, "top_p": 0.8}},
    "debugger": {"name": "qwen3-coder:latest", "options": {"temperature": 0.1, "num_ctx": 16000, "top_p": 0.95}},
    "analyzer": {"name": "qwen3-coder:latest", "options": {"temperature": 0.0, "num_ctx": 16000}},
    "planner": {"name": "qwen3-coder:latest", "options": {"temperature": 0.2, "num_ctx": 16000, "top_p": 0.8}}
}
MAX_DEBUG_ATTEMPTS = 3
MAX_TEST_REGEN_ATTEMPTS = 2
OUTPUT_DIR = "generated_code"

# --- Helper functions ---
def call_ollama_api(messages: list, model_key: str) -> str:
    """Internal helper to send requests to the Ollama API."""
    model_config = MODELS.get(model_key)
    if not model_config:
        raise ValueError(f"Model key '{model_key}' not found in config.")

    try:
        payload = {
            "model": model_config["name"],
            "messages": messages,
            "options": model_config["options"],
            "stream": False
        }
        response = requests.post(OLLAMA_API_URL, json=payload, timeout=None)
        response.raise_for_status()
        return response.json().get("message", {}).get("content", "").strip()
    except requests.exceptions.RequestException as e:
        print(f"API Error: {e}")
        return f"Error: Failed to connect to '{model_config['name']}' API. Details: {e}"

def generate_test_plan(language: str, code_prompt: str) -> str:
    """Uses an LLM to generate a test plan based on the code prompt."""
    print("  -> Generating test plan from prompt...")
    prompt = f"""
    You are an expert Quality Assurance (QA) engineer. Your task is to create a detailed, step-by-step test plan for a piece of code that will be written in {language}.
    Analyze the following user request and break it down into a numbered list of specific test cases.

    == User Code Request ==
    {code_prompt}

    == Instructions ==
    1.  Identify the core functionalities described in the request.
    2.  For each functionality, define at least one "happy path" test case (i.e., it works with normal, expected inputs).
    3.  Identify and create test cases for edge conditions (e.g., empty inputs, zero, large numbers, empty strings).
    4.  Identify and create test cases for error conditions (e.g., invalid input types, division by zero).
    5.  Format your output as a clean, numbered list. Do not include any explanations, conversational text, or markdown.
    
    Example Output:
    1. Test the add function with two positive integers.
    2. Test the add function with a positive and a negative integer.
    3. Test the divide function with a non-zero denominator.
    4. Test that the divide function raises a ValueError when the denominator is zero.
    """
    messages = [{'role': 'user', 'content': prompt}]
    generated_plan = call_ollama_api(messages, "planner")
    return generated_plan

def generate_code(language: str, prompt: str, initial_code: Optional[str] = None, mode: str = 'generate') -> str:
    """Generates a code snippet based on a natural language prompt."""
    print(f"  -> Generating {language} code in {mode} mode...")
    system_prompt = f"""You are an expert {language} programmer. Your task is to write a single, clean, well-commented, and efficient code snippet that fulfills the user's request.
    Respond with ONLY the code snippet, enclosed in a single markdown code block. Do not include any explanations or conversational text outside the code block."""
    
    user_message = prompt
    if initial_code:
        if mode == 'refactor':
            user_message = f"Please improve this existing code based on the following prompt:\n\n== Existing Code ==\n```python\n{initial_code}\n```\n\n== Improvement Prompt ==\n{prompt}"
        elif mode == 'debug':
            user_message = f"Please debug and fix this existing code based on the following prompt and a test plan that will be provided:\n\n== Existing Code ==\n```python\n{initial_code}\n```\n\n== Debugging Prompt ==\n{prompt}"
    
    messages = [{'role': 'system', 'content': system_prompt}, {'role': 'user', 'content': user_message}]
    raw_code = call_ollama_api(messages, "coder")
    cleaned_code = re.sub(r'```python|```', '', raw_code).strip()
    return cleaned_code

def generate_unit_tests(file_name: str, code_content: str, test_plan_description: str) -> str:
    """Generates pytest unit tests based on the provided code content and test plan."""
    print("  -> Generating unit tests...")
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
    1.  Write valid `pytest` test functions. Name the test file `test_{file_name.replace('.py', '')}.py`.
    2.  Import the necessary classes/functions from the original file.
    3.  Implement test cases that cover all aspects mentioned in the `Test Plan`.
    4.  For negative test cases (e.g., expected errors), use `pytest.raises`.
    5.  Use assertions (`assert`) to verify expected behavior.
    6.  Return ONLY the Python code for the unit tests. Do NOT include any explanations or markdown fences.
    """
    raw_test_code = call_ollama_api([{'role': 'user', 'content': prompt}], "tester")
    cleaned_test_code = re.sub(r'```python|```', '', raw_test_code).strip()
    return cleaned_test_code

def debug_code(code_content: str, test_output: str, test_file: str) -> str:
    """Uses an LLM to debug and fix code based on test output."""
    print("  -> Debugging failed code...")
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
    1.  Carefully examine the code and the test output to find the root cause of the error.
    2.  Provide a corrected version of the ENTIRE code snippet.
    3.  Return ONLY the corrected Python code, enclosed in a single markdown code block.
    """
    messages = [{'role': 'user', 'content': prompt}]
    raw_fixed_code = call_ollama_api(messages, "debugger")
    cleaned_fixed_code = re.sub(r'```python|```', '', raw_fixed_code).strip()
    return cleaned_fixed_code

def analyze_test_failure(code_content: str, test_output: str) -> str:
    """Analyzes a test failure to determine if the bug is in the code or the test."""
    print("  -> Analyzing test failure...")
    prompt = f"""
    You are a quality assurance expert. Analyze the provided Python code and the output from a failed test run.
    Your task is to determine the most likely cause of the failure.

    == Code ==
    ```python
    {code_content}
    ```

    == Test Failure Output ==
    ```
    {test_output}
    ```

    Based on your analysis, state whether the failure is a result of a bug in the code or a flaw in the unit test itself.
    Respond with ONLY one of the following keywords: 'code_bug', 'test_bug', or 'cannot_determine'.
    """
    messages = [{'role': 'user', 'content': prompt}]
    analysis_result = call_ollama_api(messages, "analyzer").strip().lower()
    if analysis_result not in ['code_bug', 'test_bug']:
        return 'cannot_determine'
    return analysis_result

# --- Project Manager ---
class ProjectManager:
    """
    Manages a temporary project directory for writing and executing code.
    Ensures a clean, isolated environment for each task.
    """

    def __init__(self, base_dir: str = "temp_project"):
        self.base_dir = base_dir
        self.current_dir = None

    def create_project(self):
        """
        Creates a new, unique temporary directory for the project.
        Deletes any existing directory with the same name first.
        """
        print(f"Creating new project directory at '{self.base_dir}'.")
        if os.path.exists(self.base_dir):
            shutil.rmtree(self.base_dir)
            print(f"Removed old directory.")
        
        os.makedirs(self.base_dir)
        self.current_dir = self.base_dir
        print(f"Directory created.")

    def write_file(self, file_name: str, content: str):
        """
        Writes content to a file within the current project directory.
        """
        if not self.current_dir:
            raise RuntimeError("No project directory exists. Call create_project() first.")
        
        file_path = os.path.join(self.current_dir, file_name)
        print(f"Writing file '{file_name}'.")
        with open(file_path, "w") as f:
            f.write(content)

    def read_file(self, file_name: str) -> str:
        """
        Reads and returns the content of a file from the project directory.
        """
        if not self.current_dir:
            raise RuntimeError("No project directory exists. Call create_project() first.")
        
        file_path = os.path.join(self.current_dir, file_name)
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_name}")

        with open(file_path, "r") as f:
            return f.read()

    def run_command(self, command: list[str], timeout: int = 60) -> Tuple[str, str, int]:
        """
        Runs a shell command within the project directory and captures its output.
        
        Args:
            command (list[str]): The command and its arguments.
            timeout (int): The maximum time to wait for the command to finish.

        Returns:
            A tuple containing (stdout, stderr, returncode).
        """
        if not self.current_dir:
            raise RuntimeError("No project directory exists. Call create_project() first.")

        print(f"Executing command: {' '.join(command)}")
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
        """
        Removes the entire project directory.
        """
        if self.base_dir and os.path.exists(self.base_dir):
            print(f"Cleaning up project directory '{self.base_dir}'.")
            shutil.rmtree(self.base_dir)
            self.current_dir = None
            print("Cleanup complete.")

# --- Main Generation Function ---
def generate_code_and_tests(prompt: str, language: str = "python", test_plan: Optional[str] = None) -> Tuple[str, str]:
    """
    Generates code and unit tests based on a prompt.
    
    Args:
        prompt (str): The natural language description of what the code should do.
        language (str): The programming language (default: "python").
        test_plan (str): The test plan description (if None, auto-generates).
        
    Returns:
        Tuple[str, str]: The generated code and test code.
    """
    print(f"Starting code generation for: {prompt}")
    
    # Setup
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    project_manager = ProjectManager(base_dir="temp_coding_project")
    code_file = "generated_module.py"
    test_file = f"test_{code_file}"
    
    try:
        project_manager.create_project()
        
        # Generate code
        generated_code = generate_code(language, prompt)
        project_manager.write_file(code_file, generated_code)
        
        # Generate test plan if not provided
        if not test_plan:
            test_plan = generate_test_plan(language, prompt)
            print("\n--- Auto-generated Test Plan ---")
            print(test_plan)
            print("-----------------------------")
        
        # Generate tests and run them
        test_passed = False
        test_output = ""
        analysis_result = 'code_bug'  # Default assumption
        
        for attempt in range(MAX_DEBUG_ATTEMPTS + MAX_TEST_REGEN_ATTEMPTS):
            print(f"\n--- Attempt {attempt + 1} ---")
            generated_tests = generate_unit_tests(code_file, generated_code, test_plan)
            project_manager.write_file(test_file, generated_tests)
            
            stdout, stderr, returncode = project_manager.run_command(['python', '-m', 'pytest', '-q', '--tb=no', test_file])
            
            if returncode == 0:
                print("Tests passed successfully!")
                test_output = stdout
                test_passed = True
                break
            else:
                print("Tests failed. Analyzing failure...")
                test_output = stdout + stderr
                
                analysis_result = analyze_test_failure(generated_code, test_output)
                print(f"Analysis result: '{analysis_result}'")
                
                if analysis_result == 'code_bug' and attempt < MAX_DEBUG_ATTEMPTS:
                    print("Identified as a code bug. Attempting to debug...")
                    generated_code = debug_code(generated_code, test_output, test_file)
                    project_manager.write_file(code_file, generated_code)
                elif analysis_result == 'test_bug' and attempt < MAX_TEST_REGEN_ATTEMPTS:
                    print("Identified as a test bug. Regenerating tests...")
                    pass  # Loop will regenerate tests
                else:
                    print("Cannot determine cause or max attempts reached. Stopping.")
                    break

        # Save final files
        final_code_path = os.path.join(OUTPUT_DIR, code_file)
        final_test_path = os.path.join(OUTPUT_DIR, test_file)
        shutil.copy(os.path.join(project_manager.current_dir, code_file), final_code_path)
        shutil.copy(os.path.join(project_manager.current_dir, test_file), final_test_path)
        
        print("\n" + "="*50)
        print("          GENERATION COMPLETE")
        print("="*50)
        
        if test_passed:
            print("SUCCESS: All tests passed!")
            print(f"Code saved to: {final_code_path}")
            print(f"Tests saved to: {final_test_path}")
        else:
            analysis_message = "I was unable to fix a bug in the code within the allowed attempts." if analysis_result == 'code_bug' else "My analysis suggests the failure may be due to a flaw in the generated tests, not the code itself."
            print("FAILURE: Unable to produce a working solution.")
            print(f"Code saved to: {final_code_path}")
            print(f"Tests saved to: {final_test_path}")
            print(f"\n{analysis_message}")
        
        print("\n--- Generated Code ---")
        print(generated_code)
        print("\n--- Generated Tests ---")
        print(generated_tests)
        
        return generated_code, generated_tests
        
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        raise
    finally:
        project_manager.cleanup()

# --- Example Usage ---
if __name__ == "__main__":
    # Example usage
    code, test = generate_code_and_tests(
        prompt="Write a function that adds two numbers",
        language="python",
        test_plan="Test with positive numbers, negative numbers, and zero"
    )