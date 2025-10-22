Local LLM Coding Showdown: Who Can Actually Refactor a Python App?
We hear a lot about the coding prowess of large language models. But when you move away from cloud-hosted APIs and onto your own hardware, how do the top local models stack up in a real-world, practical coding task?

I decided to find out. I ran an experiment to test a simple, common development request: refactoring an existing script to add a new feature. This isn't about generating a complex algorithm from scratch, but about a task that's arguably more common: reading, understanding, and modifying existing code.

The Testbed: Hardware and Software
For this experiment, the setup was crucial.

Hardware: A trusty NVIDIA Tesla P40 with 24GB of VRAM. This is a solid "prosumer" or small-lab card, and its 24GB capacity is a realistic constraint for running larger models.

Software: All models were run using Ollama and pulled directly from the official Ollama repository.

The Task: The base script was a PyQt5 application (server_acces.py) that acts as a simple frontend for the Ollama API. The app maintains a chat history in memory. The task was to add a "Reset Conversation" button to clear this history.

The Models: We tested a range of models from 14B to 32B parameters. To ensure the 14B models could compete with larger ones and fit comfortably within the VRAM, they were run at q8 quantization.

The Prompt
To ensure a fair test, every model was given the exact same, clear prompt:

hello, i need a button to reset the conversation, can you provide full refactored script, please

The "full refactored script" part is key. A common failure point for LLMs is providing only a snippet, which is useless for this kind of task.

The Results: A Three-Tiered-System
After running the experiment, the results were surprisingly clear and fell into three distinct categories.

Category 1: Flawless Victory (Full Success)
These models performed the task perfectly. They provided the complete, runnable Python script, correctly added the new QPushButton, connected it to a new reset_conversation method, and that method correctly cleared the chat history. No fuss, no errors.

The Winners:

deepseek-r1

devstral

mistral-small

phi4-reasoning-14b-q8

qwen3-coder

qwen2-5-coder

Desired Code Example: They correctly added the button to the init_ui method and created the new handler method, like this example from devstral.py:

Python

    def init_ui(self):
        # ... (all previous UI code) ...

        self.submit_button = QPushButton("Submit")
        self.submit_button.clicked.connect(self.submit)

        # Reset Conversation Button
        self.reset_button = QPushButton("Reset Conversation") #
        self.reset_button.clicked.connect(self.reset_conversation) #

        # ... (layout code) ...

        self.left_layout.addWidget(self.submit_button)
        self.left_layout.addWidget(self.reset_button) #

        # ... (rest of UI code) ...

    def reset_conversation(self): #
        """Resets the conversation by clearing chat history and updating UI."""
        self.chat_history = [] #
        self.attached_files = [] #
        self.prompt_entry.clear() #
        self.output_entry.clear() #
        self.chat_history_display.clear() #
        self.logger.log_header(self.model_combo.currentText()) #
Category 2: Success... With a Catch (Unrequested Layout Changes)
This group also functionally completed the task. The reset button was added, and it worked.

However, these models took it upon themselves to also refactor the app's layout. While not a "failure," this is a classic example of an LLM "hallucinating" a requirement. In a professional setting, this is the kind of "helpful" change that can drive a senior dev crazy by creating unnecessary diffs and visual inconsistencies.

The "Creative" Coders:

gpt-oss

magistral

qwen3-a3b

Code Variation Example: The simple, desired change was to just add the new button to the existing vertical layout.

Instead, models like gpt-oss.py and magistral.py decided to create a new horizontal layout for the buttons and move them elsewhere in the UI.

For example, magistral.py created a whole new QHBoxLayout and placed it above the prompt entry field, whereas the original script had the submit button below it.

Python

# ... (in init_ui) ...
        # Action buttons (submit and reset)
        self.submit_button = QPushButton("Submit")
        self.submit_button.clicked.connect(self.submit)

        self.reset_button = QPushButton("Reset Conversation") #
        self.reset_button.setToolTip("Clear current conversation context")
        self.reset_button.clicked.connect(self.reset_conversation) #

        # ... (file selection layout) ...

        # Layout for action buttons (submit and reset)
        button_layout = QHBoxLayout() # <-- Unrequested new layout
        button_layout.addWidget(self.submit_button) #
        button_layout.addWidget(self.reset_button) #
        
        # ... (main layout structure) ...

        # Add file selection and action buttons
        self.left_layout.addLayout(file_selection_layout)
        self.left_layout.addLayout(button_layout) # <-- Added in a new location

        # Add prompt input at the bottom
        self.left_layout.addWidget(self.prompt_label)
        self.left_layout.addWidget(self.prompt_entry) # <-- Button is no longer at the bottom
Category 3: The Spectacular Fail (Total Fail)
This category includes models that failed to produce a working, complete script for different reasons.

Sub-Failure 1: Broken Code

gemma3-27b: This model produced code that, even after some manual fixes, simply did not work. The script would launch, but the core functionality was broken. Worse, it introduced a buggy, unrequested QThread and ApiWorker class, completely breaking the app's chat history logic.

Sub-Failure 2: Did Not Follow Instructions (The Snippet Fail) This was a more fundamental failure. Two models completely ignored the key instruction: "provide full refactored script."

phi3-medium-14b-q8

granite4-small

Instead of providing the complete file, they returned only snippets of the changes. This is a total failure. It puts the burden back on the developer to manually find where the code goes, and it's useless for an automated "fix-it" task. This is arguably worse than broken code, as it's an incomplete answer.

Analysis & Takeaways
"Coder" Models Shine: It's no surprise, but models specifically fine-tuned for coding (qwen3-coder, qwen2-5-coder, deepseek-r1) excelled. They understood the task's constraints and didn't add fluff.

Size Isn't Everything (Quality Is): This is the biggest takeaway. The phi4-reasoning-14b-q8 model, a 14B model running at Q8, performed flawlessly. In stark contrast, the phi3-medium-14b-q8 (also 14B Q8) and the much larger gemma3-27b failed spectacularly. This proves that a high-quality, well-quantized smaller model can be far more useful than a larger or poorly-instruct-tuned one.

The "Snippet" Problem is a Real Failure: Models that provide snippets instead of full code for a refactoring task are not useful. This failure to follow a clear, primary instruction ("provide full refactored script") is a major mark against them.

The "Tinkerer" Problem: The models in Category 2 highlight a real-world friction point. They "solved" the problem but also created a new one by making unrequested changes. This suggests that for refactoring, models with a stronger adherence to instructions are preferable.
