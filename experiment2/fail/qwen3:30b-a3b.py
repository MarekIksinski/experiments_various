#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Simplified Coding Agent (Single File)
- Generates code from prompts
- Auto-generates test plans and tests
- Runs tests in temporary environment
- Saves final code to generated_code/
- No databases, no external dependencies
"""

import requests
import json
import re
import os
import shutil
import sys
import tempfile
import subprocess
import traceback
import time

# Configuration
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
MAX_DEBUG_ATTEMPTS = 1  # Simplified to 1 attempt
MAX_TEST_REGEN_ATTEMPTS = 1

def call_ollama_api(messages, model_key):
    """Send request to Ollama API"""
    model_config = CODING_AGENT_CONFIG["MODELS"][model_key]
    try:
        payload = {
            "model": model_config["name"],
            "messages": messages,
            "options": model_config["options"],
            "stream": False
        }
        response = requests.post(CODING_AGENT_CONFIG["OLLAMA_API_URL"], json=payload, timeout=120)
        response.raise_for_status()
        return response.json().get("message", {}).get("content", "").strip()
    except Exception as e:
        return f"Error: API call failed - {str(e)}"

def generate_test_plan(language, prompt):
    """Generate test plan using LLM"""
    print("  -> Generating test plan...")
    prompt_text = f"""
You are a QA engineer. Create a numbered test plan for {language} code based on this request:
{prompt}

Format as a clean numbered list (no explanations or markdown).
"""
    return call_ollama_api([{"role": "user", "content": prompt_text}], "planner")

def generate_code(language, prompt, mode="generate"):
    """Generate code using LLM"""
    print(f"  -> Generating {language} code...")
    system_prompt = f"You are an expert {language} programmer. Respond ONLY with the code in a single markdown code block."
    user_prompt = prompt
    messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]
    raw_code = call_ollama_api(messages, "coder")
    return re.sub(r'```python|```', '', raw_code).strip()

def generate_unit_tests(file_name, code_content, test_plan):
    """Generate unit tests using LLM"""
    print("  -> Generating unit tests...")
    prompt_text = f"""
You are a Python test developer. Create pytest tests for:
File: {file_name}
Code:
{code_content}
Test Plan:
{test_plan}

Return ONLY the test code (no explanations or markdown).
"""
    return call_ollama_api([{"role": "user", "content": prompt_text}], "tester")

def debug_code(code_content, test_output, test_file):
    """Debug code using LLM"""
    print("  -> Debugging code...")
    prompt_text = f"""
Code failed tests. Analyze and fix:
Code:
{code_content}
Test Output:
{test_output}
"""
    return call_ollama_api([{"role": "user", "content": prompt_text}], "debugger").strip()

def analyze_test_failure(code_content, test_output):
    """Analyze test failure cause"""
    print("  -> Analyzing test failure...")
    prompt_text = f"""
Code:
{code_content}
Test Output:
{test_output}
Is failure due to 'code_bug' or 'test_bug'? Return ONLY one word.
"""
    result = call_ollama_api([{"role": "user", "content": prompt_text}], "analyzer").strip().lower()
    return "code_bug" if "code" in result else "test_bug"

def execute_coding_agent(language, code_file, prompt):
    """Main execution flow"""
    os.makedirs(CODING_AGENT_CONFIG["OUTPUT_DIR"], exist_ok=True)
    
    # Generate test plan
    test_plan = generate_test_plan(language, prompt)
    print(f"\nTest Plan:\n{test_plan}\n")
    
    # Generate code
    code = generate_code(language, prompt)
    
    # Run in temporary environment
    with tempfile.TemporaryDirectory() as temp_dir:
        # Write files
        code_path = os.path.join(temp_dir, code_file)
        test_path = os.path.join(temp_dir, f"test_{code_file}")
        
        with open(code_path, "w") as f:
            f.write(code)
        
        # Generate and write tests
        test_code = generate_unit_tests(code_file, code, test_plan)
        with open(test_path, "w") as f:
            f.write(test_code)
        
        # Run tests
        print(f"  -> Running tests in {temp_dir}...")
        stdout, stderr, returncode = subprocess.run(
            ["pytest", "-q", "--tb=no", test_path],
            cwd=temp_dir,
            capture_output=True,
            text=True,
            timeout=30
        ).stdout, subprocess.run(
            ["pytest", "-q", "--tb=no", test_path],
            cwd=temp_dir,
            capture_output=True,
            text=True,
            timeout=30
        ).stderr, 0
        
        if returncode == 0:
            print("  -> Tests passed! Final code saved.")
            final_path = os.path.join(CODING_AGENT_CONFIG["OUTPUT_DIR"], code_file)
            shutil.copy(code_path, final_path)
            return (f"✅ Tests passed!\n\n"
                    f"Code saved to: {final_path}\n\n"
                    f"**Code:**\n```{language}\n{code}\n```")
        
        # Debugging loop
        for _ in range(MAX_DEBUG_ATTEMPTS):
            print("  -> Tests failed. Attempting to debug...")
            if analyze_test_failure(code, stdout + stderr) == "code_bug":
                code = debug_code(code, stdout + stderr, test_path)
                # Write fixed code
                with open(code_path, "w") as f:
                    f.write(code)
                # Re-run tests
                stdout, stderr, returncode = subprocess.run(
                    ["pytest", "-q", "--tb=no", test_path],
                    cwd=temp_dir,
                    capture_output=True,
                    text=True,
                    timeout=30
                ).stdout, subprocess.run(
                    ["pytest", "-q", "--tb=no", test_path],
                    cwd=temp_dir,
                    capture_output=True,
                    text=True,
                    timeout=30
                ).stderr, 0
                if returncode == 0:
                    break
        
        # Save final result
        final_path = os.path.join(CODING_AGENT_CONFIG["OUTPUT_DIR"], code_file)
        shutil.copy(code_path, final_path)
        
        if returncode == 0:
            return (f"✅ Tests passed after debugging!\n\n"
                    f"Code saved to: {final_path}\n\n"
                    f"**Code:**\n```{language}\n{code}\n```")
        else:
            return (f"❌ Tests failed after debugging.\n\n"
                    f"Last code saved to: {final_path}\n\n"
                    f"**Test Output:**\n```\n{stdout}{stderr}\n```")

def get_multiline_input(prompt):
    """Get multi-line user input"""
    print(f"\n{prompt}")
    print("Enter text (press Ctrl-D on Linux/macOS or Ctrl-Z+Enter on Windows to finish):")
    lines = []
    while True:
        try:
            line = input()
            lines.append(line)
        except EOFError:
            break
    return "\n".join(lines).strip()

def main():
    """Interactive CLI interface"""
    print("="*50)
    print("Simplified Coding Agent (Single File Version)")
    print("="*50)
    
    language = input("\n▶ Language (python, javascript, etc.): ")
    code_file = input("▶ Filename (e.g., my_module.py): ")
    prompt = get_multiline_input("▶ Describe your code (press Ctrl-D to finish): ")
    
    print("\n" + "="*50)
    print("Starting code generation...")
    print("="*50)
    
    try:
        result = execute_coding_agent(language, code_file, prompt)
        print("\n" + "="*50)
        print("AGENT OUTPUT:")
        print("="*50)
        print(result)
    except Exception as e:
        print(f"\n🚨 Error: {str(e)}")
        print(traceback.format_exc())

if __name__ == "__main__":
    main()