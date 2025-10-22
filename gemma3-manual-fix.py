#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue Jan  7 20:52:13 2025
Refactored on Oct 7 2025

@author: marek

frontend for ollama, support simple image to text, and chat
chat preserves conversation context between models - it's a feature, not a bug
can't preserve context between sessions, result of the above - use main-v0.3.x instead
to do:
    *custom system prompt
    *basic parameters of the model, temp, repeat penalty, etc...
    *button to clear conversation context
"""
import os
import sys
import base64
import json
import requests
from datetime import datetime
from PyQt5.QtWidgets import QApplication, QWidget, QLabel, QFileDialog, QPushButton, QVBoxLayout, QHBoxLayout, QTextEdit, QComboBox, QMessageBox
from PyQt5.QtCore import QThread, pyqtSignal

# --- Configuration for Ollama API ---
OLLAMA_BASE_URL = "http://192.168.1.127:11434"  # Change if your ollama server is on a different IP/port


# --- New Functions for Direct API Calls ---

def get_ollama_models(base_url):
    """Fetches the list of available models from the Ollama API."""
    try:
        response = requests.get(f"{base_url}/api/tags")
        response.raise_for_status()  # Raise an exception for bad status codes (4xx or 5xx)
        models_data = response.json()
        return [model['name'] for model in models_data.get('models', [])]
    except requests.exceptions.RequestException as e:
        print(f"Error connecting to Ollama: {e}")
        # Return an empty list or handle the error as appropriate for your UI
        return ["Error: Could not connect to Ollama server"]

model_names = get_ollama_models(OLLAMA_BASE_URL)  #manual fix
vision_models = [m for m in model_names if 'vision' in m or 'llava' in m] #manual fix
chat_models   = [m for m in model_names if not ('vision' in m or 'llava' in m)] #manual fix

def encode_image_to_base64(filepath):
    """Reads an image file and returns its Base64 encoded string."""
    try:
        with open(filepath, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')
    except Exception as e:
        print(f"Error encoding image {filepath}: {e}")
        return None


# Logger Class (Unchanged)
class Logger:
    def __init__(self, log_dir=".logs"):
        """Initializes the logger with a directory for log files."""
        self.log_dir = log_dir
        if not os.path.exists(self.log_dir):
            os.makedirs(self.log_dir)

    def get_log_filename(self, model):
        """Generates a log filename based on the model."""
        model_name = model.replace('/', '_').replace(':', '_')  # Replace slashes/colons for valid filenames
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


# --- Thread for API Calls to prevent UI freezing ---
class ApiWorker(QThread):
    response_signal = pyqtSignal(str)
    error_signal = pyqtSignal(str)

    def __init__(self, mode, model, prompt, attached_files, parent=None):
        super().__init__(parent)
        self.mode = mode
        self.model = model
        self.prompt = prompt
        self.attached_files = attached_files

    def run(self):
        try:
            if self.mode == "Chat":
                self.chat_history = []  # Initialize chat history
                self.logger = Logger()
                if not self.chat_history:
                    self.logger.log_header(self.model)

                self.chat_history.append({"role": "user", "content": self.prompt})

                payload = {
                    "model": self.model,
                    "messages": self.chat_history,
                    "stream": True  # Enable streaming
                }

                response_parts = []
                with requests.post(f"{OLLAMA_BASE_URL}/api/chat", json=payload, stream=True) as response:
                    response.raise_for_status()
                    for line in response.iter_lines():
                        if line:
                            part = json.loads(line.decode('utf-8'))
                            content_part = part['message']['content']
                            response_parts.append(content_part)
                            self.response_signal.emit("".join(response_parts))  # Emit parts for UI update
                            # No need for QApplication.processEvents() inside the thread

                response_content = "".join(response_parts)
                self.chat_history.append({"role": "assistant", "content": response_content})
                self.response_signal.emit(response_content)  # Emit final content
                self.logger.log_model(self.model, response_content)

            else:  # Image to Text mode
                filenames = self.prompt.splitlines()
                text_prompt = "Describe these images."  # Default prompt
                base64_images = [encode_image_to_base64(f) for f in filenames if os.path.exists(f)]

                if not base64_images:
                    raise ValueError("Could not find or encode any valid images.")

                payload = {
                    "model": self.model,
                    "messages": [{
                        "role": "user",
                        "content": text_prompt,
                        "images": base64_images
                    }],
                    "stream": False  # No streaming for this mode
                }

                response = requests.post(f"{OLLAMA_BASE_URL}/api/chat", json=payload)
                response.raise_for_status()
                response_data = response.json()
                response_content = response_data['message']['content']
                self.response_signal.emit(response_content)
                self.logger.log_model(self.model, response_content)

        except requests.exceptions.RequestException as e:
            self.error_signal.emit(f"API Error: {e}")
        except Exception as e:
            self.error_signal.emit(f"An unexpected error occurred: {e}")


# Main Application (UI is mostly unchanged, submit() method is refactored)
class MultiFunctionApp(QWidget):
    def __init__(self):
        super().__init__()
        self.chat_history = []
        self.attached_files = []
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("Multi-chat v0.2.7 (API Refactor)")
        self.setStyleSheet("background-color: #333333; \n color: #5feb3d;")
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

        self.attach_button = QPushButton("Attach Text...")
        self.attach_button.clicked.connect(self.attach_text_files)

        self.model_label = QLabel("Model:")
        self.model_combo = QComboBox()
        self.model_combo.addItems(model_names)

        self.submit_button = QPushButton("Submit")
        self.submit_button.clicked.connect(self.submit)

        self.clear_button = QPushButton("Clear Conversation")
        self.clear_button.clicked.connect(self.clear_conversation)

        self.right_layout = QVBoxLayout()
        self.right_layout.addWidget(self.chat_history_label)
        self.right_layout.addWidget(self.chat_history_display)

        self.left_layout = QVBoxLayout()
        self.left_layout.addWidget(self.mode_label)
        self.left_layout.addWidget(self.mode_combo)
        self.left_layout.addWidget(self.model_label)
        self.left_layout.addWidget(self.model_combo)
        self.left_layout.addWidget(self.output_label)
        self.left_layout.addWidget(self.output_entry)

        file_selection_layout = QHBoxLayout()
        file_selection_layout.addWidget(self.file_button)
        file_selection_layout.addWidget(self.attach_button)

        self.left_layout.addLayout(file_selection_layout)
        self.left_layout.addWidget(self.prompt_label)
        self.left_layout.addWidget(self.prompt_entry)
        self.left_layout.addWidget(self.submit_button)
        self.left_layout.addWidget(self.clear_button)

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
        self.prompt_entry.setText("\n".join(filenames))  # Put filenames in prompt for reference, not output

    def attach_text_files(self):
        filenames, _ = QFileDialog.getOpenFileNames(self, "Attach text files", "", "Text files (*.txt *.py *.ino *.csv *.cpp *.html)")
        if filenames:
            self.attached_files = filenames
            self.output_entry.append("Attached files for the current prompt:\n" + "\n".join(filenames))

    def submit(self):
        mode = self.mode_combo.currentText()
        prompt = self.prompt_entry.toPlainText()
        model = self.model_combo.currentText()

        self.output_entry.setText("Generating response...")
        QApplication.processEvents()  # Update the UI to show the message

        # Create a worker thread for the API call
        self.worker = ApiWorker(mode, model, prompt, self.attached_files)
        self.worker.response_signal.connect(self.update_output)
        self.worker.error_signal.connect(self.show_error)
        self.worker.start()

    def update_output(self, text):
        self.output_entry.append(text)
        QApplication.processEvents()

    def show_error(self, message):
        QMessageBox.critical(self, "Error", message)
        self.output_entry.setText(f"Error: {message}")

    def clear_conversation(self):
        self.chat_history = []
        self.output_entry.clear()
        self.chat_history_display.clear()
        QApplication.processEvents()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MultiFunctionApp()
    window.show()
    sys.exit(app.exec_())