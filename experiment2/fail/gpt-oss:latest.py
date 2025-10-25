#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sat Oct 25 21:28:26 2025

@author: marek
"""
import os
import sys
import json
import re
import shutil
import subprocess
import traceback
from typing import Tuple, Optional, Dict, List
import requests

# ----------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------
CODING_AGENT_CONFIG = {
    "OLLAMA_API_URL": "http://192.168.1.127:11434/api/chat",   # <-- change if your server is elsewhere
    "OUTPUT_DIR": "generated_code",
    "MODELS": {
        "coder": {"name": "qwen3-coder:latest", "options": {"temperature": 0.6, "num_ctx": 16000, "top_p": 0.95}},
        "tester": {"name": "qwen3-coder:latest", "options": {"temperature": 0.1, "num_ctx": 16000, "top_p": 0.8}},
        "debugger": {"name": "qwen3-coder:latest", "options": {"temperature": 0.1, "num_ctx": 16000, "top_p": 0.95}},
        "analyzer": {"name": "qwen3-coder:latest", "options": {"temperature": 0.0, "num_ctx": 16000}},
        "planner": {"name": "qwen3-coder:latest", "options": {"temperature": 0.2, "num_ctx": 16000, "top_p": 0.8}},
    }
}
MAX_DEBUG_ATTEMPTS = 3
MAX_TEST_REGEN_ATTEMPTS = 2

# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------
def _call_ollama(messages: List[Dict], model_key: str) -> str:
    """Send a request to Ollama and return the response string."""
    cfg = CODING_AGENT_CONFIG["MODELS"].get(model_key)
    if not cfg:
        raise ValueError(f"Model '{model_key}' not configured")

    payload = {
        "model": cfg["name"],
        "messages": messages,
        "options": cfg["options"],
        "stream": False,
    }

    try:
        r = requests.post(CODING_AGENT_CONFIG["OLLAMA_API_URL"], json=payload, timeout=None)
        r.raise_for_status()
        return r.json().get("message", {}).get("content", "").strip()
    except Exception as e:
        return f"Error calling Ollama: {e}"


def _clean_code(raw: str) -> str:
    """Strip out any accidental markdown fences."""
    return re.sub(r"```(?:python)?|```", "", raw).strip()


# ----------------------------------------------------------------------
# Project management – a lightweight temp dir
# ----------------------------------------------------------------------
class ProjectManager:
    def __init__(self, base_dir: str = "temp_coding_project"):
        self.base_dir = base_dir
        self.current_dir = None

    def create_project(self):
        if os.path.exists(self.base_dir):
            shutil.rmtree(self.base_dir)
        os.makedirs(self.base_dir, exist_ok=True)
        self.current_dir = self.base_dir

    def write_file(self, file_name: str, content: str):
        if not self.current_dir:
            raise RuntimeError("Project not created")
        path = os.path.join(self.current_dir, file_name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

    def run_command(self, cmd: List[str], timeout: int = 60) -> Tuple[str, str, int]:
        if not self.current_dir:
            raise RuntimeError("Project not created")
        try:
            res = subprocess.run(
                cmd,
                cwd=self.current_dir,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return res.stdout, res.stderr, res.returncode
        except Exception as e:
            return "", f"Command error: {e}", 1

    def cleanup(self):
        if self.base_dir and os.path.exists(self.base_dir):
            shutil.rmtree(self.base_dir)
            self.current_dir = None


# ----------------------------------------------------------------------
# Simplified conversation tracker – just keeps a list in memory
# ----------------------------------------------------------------------
class ConversationManager:
    def __init__(self):
        self.conversations: Dict[int, Dict] = {}
        self._next_id = 1

    def start_new_conversation(self, name: Optional[str] = None) -> int:
        cid = self._next_id
        self._next_id += 1
        self.conversations[cid] = {
            "name": name or f"Conversation {cid}",
            "turns": [],
            "solutions": [],
            "failures": [],
        }
        return cid

    def add_turn(self, cid: int, user: str, assistant: str):
        self.conversations[cid]["turns"].append((user, assistant))

    def save_successful_code(self, cid: int, file_name: str, prompt: str,
                              code: str, test_plan: str):
        self.conversations[cid]["solutions"].append(
            {"file": file_name, "prompt": prompt, "code": code,
             "test_plan": test_plan, "time": os.path.getmtime(file_name)}
        )

    def save_failed_code(self, cid: int, file_name: str, prompt: str,
                         code: str, test_plan: str, test_output: str):
        self.conversations[cid]["failures"].append(
            {"file": file_name, "prompt": prompt, "code": code,
             "test_plan": test_plan, "output": test_output,
             "time": os.path.getmtime(file_name)}
        )


# ----------------------------------------------------------------------
# The agent – core logic
# ----------------------------------------------------------------------
class CodingAgentV2:
    def __init__(self, conv_manager: ConversationManager):
        self.conv = conv_manager
        self.project = ProjectManager()
        os.makedirs(CODING_AGENT_CONFIG["OUTPUT_DIR"], exist_ok=True)

    # --- Code generation -------------------------------------------------
    def _generate_code(self, language: str, prompt: str,
                       initial_code: Optional[str] = None,
                       mode: str = "generate") -> str:
        system_prompt = (
            f"You are an expert {language} programmer. "
            "Write a single, clean, well‑commented snippet that fulfills the user's request.\n"
            "Respond with ONLY the code snippet, no explanations."
        )
        user_msg = prompt
        if initial_code:
            if mode == "refactor":
                user_msg = (
                    f"Refactor this code based on the following prompt:\n\n"
                    f"=== Existing code ===\n```python\n{initial_code}\n```\n\n"
                    f"=== Prompt ===\n{prompt}"
                )
            elif mode == "debug":
                user_msg = (
                    f"Debug this code based on the following prompt and a test plan that will be provided:\n\n"
                    f"=== Existing code ===\n```python\n{initial_code}\n```\n\n"
                    f"=== Prompt ===\n{prompt}"
                )

        resp = _call_ollama(
            [{"role": "system", "content": system_prompt},
             {"role": "user", "content": user_msg}],
            "coder",
        )
        return _clean_code(resp)

    # --- Test plan generation -------------------------------------------
    def _generate_test_plan(self, language: str, code_prompt: str) -> str:
        plan_prompt = (
            f"You are an expert QA engineer. Create a numbered list of test cases for code that will be written in {language}.\n"
            f"=== User Request ===\n{code_prompt}\n"
            "Provide ONLY a numbered list, no markdown or explanations.\n"
        )
        resp = _call_ollama([{"role": "user", "content": plan_prompt}], "planner")
        return resp.strip()

    # --- Unit test generation --------------------------------------------
    def _generate_unit_tests(self, file_name: str, code: str, test_plan: str) -> str:
        test_prompt = (
            f"Write pytest tests for the following code (strictly following the test plan):\n"
            f"=== Code ===\n```python\n{code}\n```\n"
            f"=== Test Plan ===\n{test_plan}\n"
            "Return only the test file content, no markdown."
        )
        resp = _call_ollama([{"role": "user", "content": test_prompt}], "tester")
        return _clean_code(resp)

    # --- Debugging -------------------------------------------------------
    def _debug_code(self, code: str, test_output: str, test_file: str) -> str:
        debug_prompt = (
            f"You are a senior software engineer. The following code failed its tests:\n"
            f"=== Code ===\n```python\n{code}\n```\n"
            f"=== Test Failure ===\n```\n{test_output}\n```\n"
            "Fix the code and return ONLY the corrected snippet, no markdown."
        )
        resp = _call_ollama([{"role": "user", "content": debug_prompt}], "debugger")
        return _clean_code(resp)

    # --- Test‑failure analysis ------------------------------------------
    def _analyze_test_failure(self, code: str, test_output: str) -> str:
        analysis_prompt = (
            f"You are a QA expert. Determine whether the failure is due to a code bug, a test bug, or cannot determine.\n"
            f"=== Code ===\n```python\n{code}\n```\n"
            f"=== Test Output ===\n```\n{test_output}\n```\n"
            "Respond with ONE of: 'code_bug', 'test_bug', 'cannot_determine'."
        )
        resp = _call_ollama([{"role": "user", "content": analysis_prompt}], "analyzer")
        ans = resp.strip().lower()
        return ans if ans in {"code_bug", "test_bug"} else "cannot_determine"

    # --- Main orchestration ---------------------------------------------
    def run(self, conv_id: int, language: str, file_name: str,
            prompt: str, test_plan: str, mode: str = "generate",
            initial_code: Optional[str] = None) -> str:
        try:
            self.project.create_project()

            # Generate (or refactor/debug) code
            code = self._generate_code(language, prompt, initial_code, mode)
            self.project.write_file(file_name, code)

            test_file = f"test_{file_name}"
            test_passed = False
            analysis = "code_bug"

            for attempt in range(MAX_DEBUG_ATTEMPTS + MAX_TEST_REGEN_ATTEMPTS):
                print(f"\n[Attempt {attempt+1}] Generating tests...")
                tests = self._generate_unit_tests(file_name, code, test_plan)
                self.project.write_file(test_file, tests)

                stdout, stderr, rc = self.project.run_command(
                    ["pytest", "-q", "--tb=no", test_file]
                )
                if rc == 0:
                    print("[Tests] Passed")
                    test_passed = True
                    self.conv.save_successful_code(conv_id, file_name, prompt, code, test_plan)
                    break
                else:
                    print("[Tests] Failed")
                    failure_output = stdout + stderr
                    analysis = self._analyze_test_failure(code, failure_output)
                    print(f"[Analysis] {analysis}")

                    if analysis == "code_bug" and attempt < MAX_DEBUG_ATTEMPTS:
                        code = self._debug_code(code, failure_output, test_file)
                        self.project.write_file(file_name, code)
                        continue
                    elif analysis == "test_bug" and attempt < MAX_TEST_REGEN_ATTEMPTS:
                        print("[Regenerate] Will regenerate tests")
                        continue
                    else:
                        print("[Stop] Max attempts or unknown issue")
                        break

            final_path = os.path.join(CODING_AGENT_CONFIG["OUTPUT_DIR"], file_name)
            shutil.copy(os.path.join(self.project.current_dir, file_name), final_path)

            if test_passed:
                result = (
                    f"✅ All tests passed.\n"
                    f"Code saved to: {final_path}\n\n"
                    f"--- CODE ---\n```python\n{code}\n```\n\n"
                    f"--- TESTS OUTPUT ---\n```\n{stdout}\n```\n"
                )
            else:
                self.conv.save_failed_code(conv_id, file_name, prompt, code,
                                          test_plan, failure_output)
                result = (
                    f"❌ Failed to produce working code after {attempt+1} attempts.\n"
                    f"Last code saved to: {final_path}\n\n"
                    f"Analysis: {analysis}\n\n"
                    f"--- LAST CODE ---\n```python\n{code}\n```\n\n"
                    f"--- FAILURE OUTPUT ---\n```\n{failure_output}\n```\n"
                )
            return result

        except Exception as exc:
            return f"Unexpected error: {exc}\n{traceback.format_exc()}"
        finally:
            self.project.cleanup()


# ----------------------------------------------------------------------
# Interactive CLI
# ----------------------------------------------------------------------
def _multiline_input(prompt: str) -> str:
    """Read a block of text terminated by EOF (Ctrl-D/Z)."""
    print(prompt)
    lines = sys.stdin.read()
    return lines.strip()


def main():
    print("=== Coding Agent v2 (single‑file) ===")
    language = input("\n▶ Programming language (default: python): ").strip() or "python"
    file_name = input("▶ Target file name (e.g., my_module.py): ").strip() or "my_module.py"
    prompt = _multiline_input("\n▶ Describe the code you want to generate:")

    # Test plan
    while True:
        choice = input("\n▶ Test Plan – (M)anual or (A)uto? [m/a] ").strip().lower() or "m"
        if choice == "a":
            conv = ConversationManager()
            agent = CodingAgentV2(conv)
            plan = agent._generate_test_plan(language, prompt)
            print("\n--- Generated Test Plan ---")
            print(plan)
            ok = input("▶ Use this plan? [y/n] ").strip().lower() or "y"
            if ok == "y":
                test_plan = plan
                break
            else:
                continue
        else:
            test_plan = _multiline_input("\n▶ Enter your test plan:")
            break

    mode = input("\n▶ Mode [generate/refactor/debug] (default: generate): ").strip().lower() or "generate"
    if mode not in {"generate", "refactor", "debug"}:
        print("Invalid mode – defaulting to generate.")
        mode = "generate"

    initial_code = None
    if mode in {"refactor", "debug"}:
        use = input("▶ Provide an existing code file? [y/N] ").strip().lower()
        if use == "y":
            path = input("▶ Path to file: ").strip()
            try:
                with open(path, "r", encoding="utf-8") as f:
                    initial_code = f.read()
                print(f"Loaded code from {path}")
            except FileNotFoundError:
                print("File not found – proceeding without initial code.")
                initial_code = None

    conv = ConversationManager()
    conv_id = conv.start_new_conversation(f"{language} code for {file_name}")

    agent = CodingAgentV2(conv)
    result = agent.run(conv_id, language, file_name, prompt, test_plan, mode, initial_code)

    print("\n" + "=" * 60)
    print("=== Agent Execution Completed ===")
    print("=" * 60)
    print(result)


if __name__ == "__main__":
    main()