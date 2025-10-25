#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Fri Aug 8 10:00:00 2025

@author: marek (w/ Gemini)

This module provides a ProjectManager class that creates and manages an
isolated, temporary working directory. This is essential for safely
executing generated code and unit tests.
"""
import os
import shutil
import subprocess
from typing import Tuple, Any

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
        print(f"ProjectManager: Creating new project directory at '{self.base_dir}'...")
        if os.path.exists(self.base_dir):
            shutil.rmtree(self.base_dir)
            print(f"ProjectManager: Removed old directory.")
        
        os.makedirs(self.base_dir)
        self.current_dir = self.base_dir
        print(f"ProjectManager: Directory created.")

    def write_file(self, file_name: str, content: str):
        """
        Writes content to a file within the current project directory.
        """
        if not self.current_dir:
            raise RuntimeError("No project directory exists. Call create_project() first.")
        
        file_path = os.path.join(self.current_dir, file_name)
        print(f"ProjectManager: Writing file '{file_name}'...")
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
        """
        Removes the entire project directory.
        """
        if self.base_dir and os.path.exists(self.base_dir):
            print(f"ProjectManager: Cleaning up project directory '{self.base_dir}'...")
            shutil.rmtree(self.base_dir)
            self.current_dir = None
            print("ProjectManager: Cleanup complete.")


if __name__ == '__main__':
    # --- Demo of ProjectManager ---
    print("--- ProjectManager Demo ---")
    pm = ProjectManager(base_dir="my_test_project")
    pm.create_project()
    
    # Write a simple Python file
    code_content = "print('Hello, world!')"
    pm.write_file("hello.py", code_content)
    
    # Run the file and capture output
    stdout, stderr, _ = pm.run_command(['python', 'hello.py'])
    print("\n--- Command Output ---")
    print(f"STDOUT: {stdout}")
    print(f"STDERR: {stderr}")
    
    # Cleanup
    pm.cleanup()
    print("\n--- Demo Finished ---")
