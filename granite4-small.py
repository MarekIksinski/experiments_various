
# ... (imports and previous code remains unchanged) ...

class MultiFunctionApp(QWidget):
    def __init__(self):
        super().__init__()
        self.logger = Logger()
        self.chat_history = []
        self.attached_files = []
        self.init_ui()

    # ... (other methods like init_ui, update_ui, select_image_files, attach_text_files remain unchanged) ...

    def init_ui(self):
        # ... (initialization code remains unchanged) ...

        self.reset_button = QPushButton("Reset Conversation")
        self.reset_button.clicked.connect(self.reset_conversation)

        # Add reset button to the UI
        self.left_layout.addWidget(self.reset_button)
        
        # ... (rest of the initialization code remains unchanged) ...

    def reset_conversation(self):
        """Clears the chat history and updates the log."""
        self.chat_history = []  # Reset conversation context
        self.chat_history_display.clear()  # Clear display in UI
        # Optionally, you might want to indicate this action in your logs:
        print("Conversation has been reset.")

    def submit(self):
        mode = self.mode_combo.currentText()
        prompt = self.prompt_entry.toPlainText()
        model = self.model_combo.currentText()

        if not self.chat_history and mode == "Chat":
            self.logger.log_header(model)  # Log header only at the beginning of a new chat

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
        
        # ... (rest of the submit method remains unchanged) ...

# ... (rest of the script remains unchanged) ...