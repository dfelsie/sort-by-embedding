# Sort by Embedding: An AI‑Powered Image Sorter
**100% Local · Offline · Privacy‑Focused**



Organize your photos and graphics using natural‑language prompts powered by a state‑of‑the‑art CLIP model. This desktop application runs entirely on your machine—no Internet connection or API keys required after setup.
🚀 Features

    100% Local & Offline
    All AI processing happens on your computer; your images never leave your system.

    No API Keys Required
    Completely free and self‑contained—no external services or subscriptions.

    Natural Language Commands

        Simple: “cats” or “a person smiling”

        Directional: “cats to dogs” or “close‑up to wide‑angle portraits”

    Privacy Focused
    Your files stay private and local—no cloud uploads.

    One‑Click Development Start
    A single launcher script sets up everything (Python + Node.js) and starts both backend and Electron frontend.

https://github.com/user-attachments/assets/5903ca4c-72c5-4d39-8db2-b8c910a25e7f


🎯 Prerequisites

    Python 3.10+

    Node.js & npm (LTS recommended)

    (Optional, for GPU Acceleration) NVIDIA CUDA‑compatible drivers

⚙️ Setup & Running the Application
1. Clone the Repository

git clone https://github.com/dfelsie/sort-by-embedding.git
cd sort-by-embedding

2. Run the Launcher

From the project root, launch the “one‑click” setup:

python full_launcher.py

    First Run:

        Dependency Check: Verifies Python & Node.js packages

        Initial Download (~15 minutes): Installs PyTorch (~2.5 GB) and CLIP models

        Disk Usage: ~7 GB in a local .venv311 folder

    Subsequent Runs:
    Skips installation and launches the Python server + Electron app immediately.

To stop the app, press <kbd>Ctrl</kbd>+<kbd>C</kbd> in the terminal.
📖 How to Use

    Choose Folder
    Click Choose Folder to select the directory containing your images.

    Sort by Prompt

        Enter a description (e.g., a snowy mountain or portrait to landscape)

        Click Sort by Prompt (CLIP)…

    (Optional) Rename Files
    After sorting, confirm if you’d like to rename files on disk to match the new order.

Enjoy a seamless, private, and intuitive way to sort your images—powered entirely by your local machine!

(Wrote about making this here: https://dfels.substack.com/p/writing-an-image-sorter-app-with)



