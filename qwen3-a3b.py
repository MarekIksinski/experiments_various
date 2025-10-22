#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Refactored on Oct 7 2025 (Added Reset Conversation Button)
"""
import os
import sys
import base64
import json
import requests
from datetime import datetime
from PyQt5.QtWidgets import QApplication, QWidget, QLabel, QFileDialog, QPushButton, QVBoxLayout, QHBoxLayout, QTextEdit, QComboBox
from PyQt5.QtCore import Qt

# --- Configuration for Ollama API ---
OLLAMA_BASE_URL = "http://192.168.1.127:11434"  # Change if your ollama server is on a different IP/port

# --- New Functions for Direct API Calls ---
def get_ollama_models(base_url):
    """Fetches the list of available models from the Ollama API."""
    try:
        response = requests.get(f"{base_url}/api/tags")
        response.raise_for_status()
        models_data = response.json()
        return [model['name'] for model in models_data.get('models', [])]
    except requests.exceptions.RequestException as e:
        print(f"Error connecting to Ollama: {e}")
        return ["Error: Could not connect to Ollama server"]

def encode_image_to_base64(filepath):
    """Reads an image file and returns its Base64 encoded string."""
    try:
        with open(filepath, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')
    except Exception as e:
        print(f"Error encoding image {filepath}: {e}")
        return None

# --- Get Model Lists using the new API function ---
model_names = get_ollama_models(OLLAMA_BASE_URL)

# Filter models into two lists: vision and non-vision
vision_models = [model for model in model_names if 'vision' in model or 'llava' in model]
chat_models = [model for model in model_names if not 'vision' in model or 'llava' in model]

# Logger Class (Unchanged)
class Logger:
    def __init__(self, log_dir=".logs"):
        """Initializes the logger with a directory for log files."""
        self.log_dir = log_dir
        if not os.path.exists(self.log_dir):
            os.makedirs(self.log_dir)

    def get_log_filename(self, model):
        """Generates a log filename based on the model."""
        model_name = model.replace('/', '_').replace(':', '_')
        return os.path.join(self.log_dir, f"{model_name}_conversations.txt")

    def log_header(self, model):
        """Logs a new conversation header with timestamp and model."""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        header = f"\n\n--- New Conversation ---\nTimestamp: {now}\nModel: {model}\n"
        filename = self.get_log_filename(model)
        with open(filename, 'a') as file:
            file.write(header)

    def log_user(self, model, user_input):
        """Logs user input."""
        filename = self.get_log_filename(model)
        with open(filename, 'a') as file:
            file.write(f"User: {user_input}\n")

    def log_model(self, model, model_response):
        """Logs model response."""
        filename = self.get_log_filename(model)
        with open(filename, 'a') as file:
            file.write(f"Model: {model_response}\n")

# Main Application (UI with Reset Button)
class MultiFunctionApp(QWidget):
    def __init__(self):
        super().__init__()
        self.logger = Logger()
        self.chat_history = []
        self.attached_files = []
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("Multi-chat v0.2.8 (API Refactor + Reset Button)")
        self.setStyleSheet("""
            QWidget {
                background-color: #2d2d2d;
                color: #e0e0e0;
                font-family: 'Segoe UI', sans-serif;
            }
            QTextEdit {
                background-color: #1e1e1e;
                color: #e0e0e0;
                border: 1px solid #444;
                border-radius: 4px;
            }
            QPushButton {
                background-color: #4a86e8;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #3a76d8;
            }
            QPushButton:pressed {
                background-color: #2a66c8;
            }
        """)
        self.resize(900, 600)

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

        self.file_button = QPushButton("Attach Image...")
        self.file_button.clicked.connect(self.select_image_files)

        self.attach_button = QPushButton("Attach File...")
        self.attach_button.clicked.connect(self.attach_text_files)

        self.model_label = QLabel("Model:")
        self.model_combo = QComboBox()
        self.model_combo.addItems(model_names)

        # NEW: Reset Conversation Button
        self.reset_button = QPushButton("Reset Conversation")
        self.reset_button.setStyleSheet("""
            background-color: #e74c3c;
            color: white;
            font-weight: bold;
        """)
        self.reset_button.clicked.connect(self.reset_conversation)

        self.submit_button = QPushButton("Submit")
        self.submit_button.clicked.connect(self.submit)

        # UI Layout
        self.right_layout = QVBoxLayout()
        self.right_layout.addWidget(self.chat_history_label)
        self.right_layout.addWidget(self.chat_history_display)

        self.left_layout = QVBoxLayout()
        self.left_layout.addWidget(self.mode_label)
        self.left_layout.addWidget(self.mode_combo)
        self.left_layout.addWidget(self.model_label)
        self.left_layout.addWidget(self.model_combo)
        
        # Place reset button above submit button
        self.left_layout.addWidget(self.reset_button)
        self.left_layout.addWidget(self.output_label)
        self.left_layout.addWidget(self.output_entry)
        
        file_selection_layout = QHBoxLayout()
        file_selection_layout.addWidget(self.file_button)
        file_selection_layout.addWidget(self.attach_button)
        
        self.left_layout.addLayout(file_selection_layout)
        self.left_layout.addWidget(self.prompt_label)
        self.left_layout.addWidget(self.prompt_entry)
        self.left_layout.addWidget(self.submit_button)

        self.main_layout = QHBoxLayout()
        self.main_layout.addLayout(self.left_layout, 2)
        self.main_layout.addLayout(self.right_layout, 1)

        self.setLayout(self.main_layout)
        self.update_ui()

    def update_ui(self):
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
        filenames, _ = QFileDialog.getOpenFileNames(self, "Select image files", "", "Image files (*.png *.jpg *.jpeg *.bmp *.gif)")
        self.prompt_entry.setText("\n".join(filenames))

    def attach_text_files(self):
        filenames, _ = QFileDialog.getOpenFileNames(self, "Attach text files", "", "Text files (*.txt *.py *.ino *.csv *.cpp *.html)")
        if filenames:
            self.attached_files = filenames
            self.output_entry.append("Attached files for the current prompt:\n" + "\n".join(filenames))

    def reset_conversation(self):
        """Clears chat history and resets UI state."""
        self.chat_history = []
        self.chat_history_display.setText("")
        self.output_entry.setText("Conversation reset. Start new chat!")
        self.attached_files = []  # Clear attached files list
        self.logger.log_header("RESET")  # Log reset event

    def submit(self):
        mode = self.mode_combo.currentText()
        prompt = self.prompt_entry.toPlainText()
        model = self.model_combo.currentText()

        if not self.chat_history:
            self.logger.log_header(model)

        if self.attached_files:
            for filepath in self.attached_files:
                try:
                    with open(filepath, 'r') as file:
                        file_content = file.read()
                        prompt += f"\n\n--- Content of {filepath} ---\n{file_content}"
                except Exception as e:
                        self.output_entry.append(f"Error reading {filepath}: {e}")
            self.attached_files = []

        self.logger.log_user(model, prompt)
        
        self.output_entry.setText("Generating response...")
        QApplication.processEvents()

        # --- REFACTORED API CALL LOGIC ---
        try:
            if mode == "Chat":
                self.chat_history.append({"role": "user", "content": prompt})

                payload = {
                    "model": model,
                    "messages": self.chat_history,
                    "stream": True
                }
                
                response_parts = []
                with requests.post(f"{OLLAMA_BASE_URL}/api/chat", json=payload, stream=True) as response:
                    response.raise_for_status()
                    for line in response.iter_lines():
                        if line:
                            part = json.loads(line.decode('utf-8'))
                            content_part = part['message']['content']
                            response_parts.append(content_part)
                            self.output_entry.setText("".join(response_parts))
                            QApplication.processEvents()

                response_content = "".join(response_parts)
                self.chat_history.append({"role": "assistant", "content": response_content})
                
                self.chat_history_display.setText("\n\n".join(
                    [f"User: {msg['content']}" if msg['role'] == "user" else f"Model: {msg['content']}" for msg in self.chat_history]
                ))
                self.output_entry.setText(response_content)

            else:  # Image to Text mode
                filenames = prompt.splitlines()
                text_prompt = "Describe these images."
                
                base64_images = [encode_image_to_base64(f) for f in filenames if os.path.exists(f)]
                if not base64_images:
                    raise ValueError("Could not find or encode any valid images.")
                
                payload = {
                    "model": model,
                    "messages": [{
                        "role": "user",
                        "content": text_prompt,
                        "images": base64_images
                    }],
                    "stream": False
                }
                
                response = requests.post(f"{OLLAMA_BASE_URL}/api/chat", json=payload)
                response.raise_for_status()
                response_data = response.json()
                response_content = response_data['message']['content']
                self.output_entry.setText(response_content)

            self.logger.log_model(model, response_content)

        except requests.exceptions.RequestException as e:
            self.output_entry.setText(f"API Error: {e}")
        except Exception as e:
            self.output_entry.setText(f"Error: {e}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MultiFunctionApp()
    window.show()
    sys.exit(app.exec_())