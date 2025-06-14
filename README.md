# Sort by Embedding: An AI-Powered Image Sorter

This desktop application uses the power of AI to sort your local image files using natural language. It offers two powerful ways to organize your photos:

1.  **Sort by Prompt (Local):** This primary mode runs entirely on your machine, no internet connection or API key needed. It uses a state-of-the-art CLIP model to find images that are most similar to a text description (e.g., "a sunny day at the beach").
2.  **Sort by Gemini (Cloud - Optional):** For more complex tasks, this mode uses Google's Gemini Pro Vision model to understand and execute sophisticated sorting commands (e.g., "from most cluttered to most minimalist" or "arrange by time of day"). This feature is optional and requires a free Google AI API key.

This project combines a Python/FastAPI backend for AI processing with an Electron frontend for a seamless user interface.

## Features

-   **Local-First Sorting:** The main "Sort by Prompt" feature works offline without any external services.
-   **Optional Cloud Power:** Enhance sorting capabilities with Google Gemini for complex commands.
-   **Natural Language Commands:** Describe how you want to sort using plain English.
-   **Privacy Focused:** Your images are only sent to an external API when you explicitly use the "Sort by Gemini" feature.
-   **One-Click Start:** A simple launch script starts the backend server and the Electron app simultaneously for easy development.

## Prerequisites

Before you begin, you will need the following installed on your system:

-   **Python** (version 3.9 or higher recommended)
-   **Node.js** and **npm** (LTS version recommended)

---

## 🛑 Optional: Getting a Gemini API Key

To enable the powerful **"Sort by Gemini"** feature, you need a personal API key from Google AI Studio. The "Sort by Prompt" feature works without this.

1.  Go to **[Google AI Studio](https://aistudio.google.com/app/apikey)**.
2.  Click **"Create API key in new project"**.
3.  Copy the generated API key. You will need it in the setup steps below.

---

## Setup and Installation

Follow these steps to get the application running on your local machine.

### 1. Clone the Repository

```bash
git clone https://github.com/dfelsie/sort-by-embedding.git
cd sort-by-embedding
```

### 2. Set Up the Python Backend

This step sets up the local AI models and the server.

```bash
# Create a Python virtual environment
python -m venv venv

# Activate the virtual environment
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate

# Install the required Python packages
# (Note: This may take some time as it includes PyTorch)
pip install -r requirements.txt
```
*(If a `requirements.txt` file doesn't exist, you can create one with `pip freeze > requirements.txt` after installing the necessary packages: `fastapi`, `uvicorn`, `torch`, `open_clip`, `google-generativeai`, `python-dotenv`)*

### 3. Configure Your Gemini API Key (Optional)

If you want to use the "Sort by Gemini" feature, you must provide the API key you generated.

-   In the root directory of the project, create a new file named `.env`.
-   Open the `.env` file and add the following line, pasting your secret key after the equals sign:

    ```env
    GEMINI_API_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
    ```
-   Save the file. If you leave this file out, only the local sorting will work.

**Warning:** Never commit your `.env` file or your API key to version control. The included `.gitignore` file should prevent this.

### 4. Set Up the Electron Frontend

This step installs the dependencies for the user interface.

```bash
npm install
```

## Running the Application

Once the setup is complete, a custom Python script handles starting both the backend server and the Electron app for you.

From the root directory of the project, run:

```bash
python launch.py
```

This will start both processes. To stop everything, press `Ctrl+C` in the terminal where you ran the launch script.

## How to Use the App

1.  **Select a Folder:** Click the "Select Folder" button to choose a directory of images.
2.  **Sort by Prompt (Local Model):** This feature works offline and does not require an API key. Enter a descriptive prompt (e.g., "a person smiling" or "winter snow") and click "Sort by Prompt". The images will reorder to show those most similar to the prompt first.
3.  **Sort by Gemini (Cloud Model):** If you have configured your API key, you can use this for advanced sorting. Enter a more complex command (e.g., "from oldest photo to newest" or "by how much blue color is in the picture") and click "Sort by Gemini".


list of models in the venv under open_clip model configs.