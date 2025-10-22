#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue Jan  7 20:52:13 2025
Refactored on Oct 7 2025

Author: marek
Description: Front‑end for Ollama with image‑to‑text and chat capabilities.
             Adds a “Reset Conversation” button to clear chat context.
"""

import os
import sys
import base64
import json
import requests
from datetime import datetime
from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QFileDialog, QPushButton,
    QVBoxLayout, QHBoxLayout, QTextEdit, QComboBox
)

# ------------------------------------------------------------------
# Configuration
# ------------------------------------------------------------------
OLLAMA_BASE_URL = "http://192.168.1.127:11434"  # Change if your Ollama server is elsewhere

# ------------------------------------------------------------------
# Utility Functions
# ------------------------------------------------------------------
def get_ollama_models(base_url):
    """Fetch list of available models from the Ollama API."""
    try:
        response = requests.get(f"{base_url}/api/tags")
        response.raise_for_status()
        models_data = response.json()
        return [model['name'] for model in models_data.get('models', [])]
    except requests.exceptions.RequestException as e:
        print(f"Error connecting to Ollama: {e}")
        return ["Error: Could not connect to Ollama server"]

def encode_image_to_base64(filepath):
    """Read an image file and return its Base64 encoded string."""
    try:
        with open(filepath, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')
    except Exception as e:
        print(f"Error encoding image {filepath}: {e}")
        return None

# ------------------------------------------------------------------
# Model Lists
# ------------------------------------------------------------------
model_names = get_ollama_models(OLLAMA_BASE_URL)
vision_models = [m for m in model_names if 'vision' in m or 'llava' in m]
chat_models   = [m for m in model_names if not ('vision' in m or 'llava' in m)]

# ------------------------------------------------------------------
# Logger Class
# ------------------------------------------------------------------
class Logger:
    def __init__(self, log_dir=".logs"):
        self.log_dir = log_dir
        os.makedirs(self.log_dir, exist_ok=True)

    def get_log_filename(self, model):
        name = model.replace('/', '_').replace(':', '_')
        return os.path.join(self.log_dir, f"{name}_conversations.txt")

    def log_header(self, model):
        header = f"\n\n--- New Conversation ---\nTimestamp: {datetime.now():%Y-%m-%d %H:%M:%S}\nModel: {model}\n"
        with open(self.get_log_filename(model), "a") as f:
            f.write(header)

    def log_user(self, model, user_input):
        with open(self.get_log_filename(model), "a") as f:
            f.write(f"User: {user_input}\n")

    def log_model(self, model, model_response):
        with open(self.get_log_filename(model), "a") as f:
            f.write(f"Model: {model_response}\n")

# ------------------------------------------------------------------
# Main Application
# ------------------------------------------------------------------
class MultiFunctionApp(QWidget):
    def __init__(self):
        super().__init__()
        self.logger = Logger()
        self.chat_history = []        # List of message dicts for the current session
        self.attached_files = []      # Paths of files attached for a prompt
        self.init_ui()

    # --------------------- UI Construction -----------------------
    def init_ui(self):
        self.setWindowTitle("Multi-chat v0.2.7 (API Refactor)")
        self.setStyleSheet("background-color:#333333; color:#5feb3d;")
        self.resize(900, 600)

        # Widgets
        self.chat_history_label = QLabel("Chat History:")
        self.chat_history_display = QTextEdit()
        self.chat_history_display.setReadOnly(True)

        self.mode_label = QLabel("Mode:")
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["Chat", "Image to Text"])
        self.mode_combo.currentTextChanged.connect(self.update_ui)

        self.prompt_label = QLabel("Prompt:")
        self.prompt_entry = QTextEdit()

        self.output_label = QLabel("Output:")
        self.output_entry = QTextEdit()
        self.output_entry.setReadOnly(True)

        self.file_button = QPushButton("Attach Image…")
        self.file_button.clicked.connect(self.select_image_files)

        self.attach_button = QPushButton("Attach File…")
        self.attach_button.clicked.connect(self.attach_text_files)

        self.model_label = QLabel("Model:")
        self.model_combo = QComboBox()
        self.model_combo.addItems(model_names)

        self.submit_button = QPushButton("Submit")
        self.submit_button.clicked.connect(self.submit)

        self.reset_button = QPushButton("Reset Conversation")
        self.reset_button.clicked.connect(self.reset_conversation)

        # Layouts
        self.right_layout = QVBoxLayout()
        self.right_layout.addWidget(self.chat_history_label)
        self.right_layout.addWidget(self.chat_history_display)

        self.left_layout = QVBoxLayout()
        self.left_layout.addWidget(self.mode_label)
        self.left_layout.addWidget(self.mode_combo)
        self.left_layout.addWidget(self.model_label)
        self.left_layout.addWidget(self.model_combo)

        file_layout = QHBoxLayout()
        file_layout.addWidget(self.file_button)
        file_layout.addWidget(self.attach_button)
        self.left_layout.addLayout(file_layout)

        self.left_layout.addWidget(self.prompt_label)
        self.left_layout.addWidget(self.prompt_entry)
        self.left_layout.addWidget(self.output_label)
        self.left_layout.addWidget(self.output_entry)

        button_layout = QHBoxLayout()
        button_layout.addWidget(self.submit_button)
        button_layout.addWidget(self.reset_button)
        self.left_layout.addLayout(button_layout)

        self.main_layout = QHBoxLayout()
        self.main_layout.addLayout(self.left_layout, 2)
        self.main_layout.addLayout(self.right_layout, 1)

        self.setLayout(self.main_layout)
        self.update_ui()

    # --------------------- UI Updates -----------------------------
    def update_ui(self):
        """Show/hide controls based on the selected mode."""
        mode = self.mode_combo.currentText()
        if mode == "Image to Text":
            self.file_button.show()
            self.attach_button.hide()
            self.model_combo.clear()
            self.model_combo.addItems(vision_models)
        else:
            self.file_button.hide()
            self.attach_button.show()
            self.model_combo.clear()
            self.model_combo.addItems(chat_models)

    def select_image_files(self):
        filenames, _ = QFileDialog.getOpenFileNames(
            self, "Select image files",
            "", "Image files (*.png *.jpg *.jpeg *.bmp *.gif)"
        )
        if filenames:
            self.prompt_entry.setText("\n".join(filenames))

    def attach_text_files(self):
        filenames, _ = QFileDialog.getOpenFileNames(
            self, "Attach text files",
            "", "Text files (*.txt *.py *.ino *.csv *.cpp *.html)"
        )
        if filenames:
            self.attached_files = filenames
            self.output_entry.append("Attached files for the current prompt:\n" + "\n".join(filenames))

    # --------------------- Conversation Logic --------------------
    def submit(self):
        mode = self.mode_combo.currentText()
        prompt = self.prompt_entry.toPlainText().strip()
        model = self.model_combo.currentText()

        if not prompt:
            self.output_entry.setText("⚠️  Prompt is empty.")
            return

        # Start a new conversation if needed
        if not self.chat_history:
            self.logger.log_header(model)

        # Incorporate attached text files into the prompt
        if self.attached_files:
            for fp in self.attached_files:
                try:
                    with open(fp, 'r', encoding='utf-8') as f:
                        content = f.read()
                    prompt += f"\n\n--- Content of {fp} ---\n{content}"
                except Exception as e:
                    self.output_entry.append(f"⚠️  Error reading {fp}: {e}")
            self.attached_files.clear()

        self.logger.log_user(model, prompt)
        self.output_entry.setText("Generating response…")
        QApplication.processEvents()  # Update UI immediately

        try:
            if mode == "Chat":
                # Append user message
                self.chat_history.append({"role": "user", "content": prompt})
                payload = {"model": model, "messages": self.chat_history, "stream": True}

                response_parts = []
                with requests.post(f"{OLLAMA_BASE_URL}/api/chat", json=payload, stream=True) as resp:
                    resp.raise_for_status()
                    for line in resp.iter_lines():
                        if line:
                            part = json.loads(line.decode('utf-8'))
                            content_part = part["message"]["content"]
                            response_parts.append(content_part)
                            # Stream to UI
                            self.output_entry.setText("".join(response_parts))
                            QApplication.processEvents()

                response_text = "".join(response_parts)
                # Append assistant message
                self.chat_history.append({"role": "assistant", "content": response_text})

                # Update chat history display
                history_text = "\n\n".join(
                    f"{'User' if m['role']=='user' else 'Model'}: {m['content']}"
                    for m in self.chat_history
                )
                self.chat_history_display.setText(history_text)
                self.output_entry.setText(response_text)

            else:  # Image to Text
                image_paths = prompt.splitlines()
                if not image_paths:
                    raise ValueError("No image paths provided.")

                base64_imgs = [encode_image_to_base64(p) for p in image_paths if os.path.exists(p)]
                if not base64_imgs:
                    raise ValueError("Could not encode any provided images.")

                payload = {
                    "model": model,
                    "messages": [{
                        "role": "user",
                        "content": "Describe these images.",
                        "images": base64_imgs
                    }],
                    "stream": False
                }
                resp = requests.post(f"{OLLAMA_BASE_URL}/api/chat", json=payload)
                resp.raise_for_status()
                response_text = resp.json()["message"]["content"]
                self.output_entry.setText(response_text)

            self.logger.log_model(model, response_text)

        except requests.exceptions.RequestException as e:
            self.output_entry.setText(f"API Error: {e}")
        except Exception as e:
            self.output_entry.setText(f"Unexpected error: {e}")

    # --------------------- Reset Logic ----------------------------
    def reset_conversation(self):
        """Clear all conversation state and start a fresh session."""
        # Clear chat history
        self.chat_history.clear()
        self.chat_history_display.clear()

        # Clear output and prompt (optional – keeps the prompt)
        # self.output_entry.clear()
        # self.prompt_entry.clear()

        # Clear any attached files
        self.attached_files.clear()

        # Log a new conversation header (so future logs are isolated)
        model = self.model_combo.currentText()
        self.logger.log_header(model)

        # Inform the user
        self.output_entry.setText("✅  Conversation reset. You can start a new session now.")

# ------------------------------------------------------------------
# Run Application
# ------------------------------------------------------------------
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MultiFunctionApp()
    window.show()
    sys.exit(app.exec_())