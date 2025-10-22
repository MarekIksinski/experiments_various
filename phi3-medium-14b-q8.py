#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue Jan  7 20:52:13 2025
Refactored on Oct 7 2025

@author: marek

frontend for ollama, support simple image to text and chat
chat preserves conversation context between models - it's a feature, not a bug
can't preserve context between sessions, result of the above - use main-v0.3.x instead
to do:
    *custom system prompt
    *basic parameters of the model, temp, repeat penalty, etc...
    *button to clear conversation context (reset)
"""
import os
import sys
import base64
import json
from datetime import datetime
from PyQt5.QtWidgets import QApplication, QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout, QTextEdit, QComboBox

# --- Configuration for Ollama API ---
OLLAMA_BASE_URL = "http://192.168.1.127:11434" # Change if your ollama server is on a different IP/port

class Logger:
    """Logger class to handle logging of conversations."""
    
    def __init__(self, log_dir=".logs"):
        self.log_dir = log_dir
        os.makedirs(self.log_dir, exist_ok=True)
    
    def get_log_filename(self, model):
        """Generates a filename for the logs."""
        sanitized_model_name = model.replace('/', '_').replace(':', '_') # Replace slashes/colons for valid filenames
        return os.path.join(self.log_dir, f"{sanitized_model_name}_conversations.txt")
    
    def log_header(self, model):
        """Logs a new conversation header."""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(self.get_log_filename(model), 'a') as file:
            file.write(f"\n\n--- New Conversation ---\nTimestamp: {now}\nModel: {model}\n")
    
    def log_user(self, model, user_input):
        """Logs the user's input."""
        with open(self.get_log_filename(model), 'a') as file:
            file.write(f"User: {user_input}\n")
    
    def log_model(self, model, response):
        """Logs the model's response."""
        with open(self.get_log_filename(model), 'a') as file:
            file.write(f"Model: {response}\n")

class MultiFunctionApp(QWidget):
    """Main application class for managing interactions."""
    
    def __init__(self, base_url=OLLAMA_BASE_URL):
        super().__init__()
        self.logger = Logger()
        # ... rest of the initialization code ...
        
        self.reset_button = QPushButton("Reset Conversation")
        self.reset_button.clicked.connect(self.clear_conversation)
    
    def init_ui(self):
        # Initialize UI components and layouts as before, but add the reset button
        
        reset_layout = QVBoxLayout()
        reset_layout.addWidget(self.reset_button)
        
        self.main_layout.addLayout(self.right_layout, 2)
        self.left_layout.addLayout(reset_layout) # Add the reset layout to left sidebar or right panel
    
    def clear_conversation(self):
        """Clears the conversation history."""
        for chat_entry in self.chat_history:
            if chat_entry['role'] == "assistant":
                self.logger.log_model(self.model_combo.currentText(), "") # Log an empty line to indicate reset
        
        # Clear the UI elements related to conversation history, such as QTextEdit or other components displaying it
        self.chat_history = []  # Reset the in-memory chat log list
    
    def submit(self):
        """Processes submission for image to text or chat mode."""
        if self.reset_button.isChecked():
            return
        
        # ... rest of the submit logic ...
        
# The remainder of your code remains unchanged, except where you initialize MultiFunctionApp and set up signals/slots

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MultiFunctionApp()
    window.show()
    sys.exit(app.exec_())