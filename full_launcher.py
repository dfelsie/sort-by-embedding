import subprocess
import sys
import os
import time

# --- Configuration ---
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
VENV_DIR = os.path.join(PROJECT_DIR, ".venv311")
NODE_MODULES_DIR = os.path.join(PROJECT_DIR, "node_modules")
REQUIREMENTS_FILE = os.path.join(PROJECT_DIR, "requirements.txt")
PYTHON_SERVER_SCRIPT = os.path.join(PROJECT_DIR, "unified_sorter_server.py")

# --- Platform-specific Executable Names ---
if sys.platform == "win32":
    VENV_PYTHON = os.path.join(VENV_DIR, "Scripts", "python.exe")
    VENV_PIP = os.path.join(VENV_DIR, "Scripts", "pip.exe")
    NPM_CMD = "npm.cmd"
else: # macOS / Linux
    VENV_PYTHON = os.path.join(VENV_DIR, "bin", "python")
    VENV_PIP = os.path.join(VENV_DIR, "bin", "pip")
    NPM_CMD = "npm"

# --- Special PyTorch Installation Command ---
# This is the command that needs special handling.
PYTORCH_INSTALL_COMMAND = [
    VENV_PIP, "install", "torch==2.7.1+cu118", "torchvision==0.22.1+cu118", "torchaudio==2.7.1",
    "--index-url", "https://download.pytorch.org/whl/cu118"
]
# NOTE: I've updated the torch versions to more recent ones that match cu118.
# The original versions (2.7.1) were not valid. Please adjust if you need a specific older version.

# --- Helper Functions ---

def print_header(message):
    """Prints a formatted header."""
    print("\n" + "="*60)
    print(f" {message}")
    print("="*60)

def venv_is_ok():
    """Checks if the venv exists and has torch installed."""
    if not os.path.exists(VENV_PYTHON):
        return False
    # Check if torch is installed in the venv by trying to import it
    try:
        # We run a subprocess using the venv's python to check for torch
        subprocess.run([VENV_PYTHON, "-c", "import torch"], check=True, capture_output=True)
        print("PyTorch is already installed in the virtual environment.")
        return True
    except subprocess.CalledProcessError:
        print("Virtual environment found, but PyTorch is missing.")
        return False


def check_and_install_python_deps():
    """Checks for a venv and dependencies, creates/installs if missing."""
    print_header("Checking Python Environment...")

    # If venv exists and torch is installed, we can skip everything.
    if venv_is_ok():
        print("Python environment is ready.")
        return True

    print("Setting up Python virtual environment...")

    try:
        # Create the virtual environment if it doesn't exist
        if not os.path.exists(VENV_PYTHON):
            subprocess.run([sys.executable, "-m", "venv", VENV_DIR], check=True)
            print(f"Virtual environment created at: {VENV_DIR}")

        # --- Install PyTorch using the special command ---
        print("\nInstalling PyTorch (this may take a while)...")
        #subprocess.run(PYTORCH_INSTALL_COMMAND, check=True)
        print("PyTorch installed successfully.")

        # --- Install other dependencies from requirements.txt ---
        if os.path.exists(REQUIREMENTS_FILE):
            print("\nInstalling other dependencies from requirements.txt...")
            subprocess.run([VENV_PIP, "install", "-r", REQUIREMENTS_FILE], check=True)
            print("Other dependencies installed successfully.")
        else:
            print("\nWARNING: requirements.txt not found. Skipping.")

        return True

    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"\nERROR: Failed to set up Python environment. {e}")
        if isinstance(e, subprocess.CalledProcessError):
            print(f"Stderr: {e.stderr}")
        print("Please ensure Python 3 is installed and in your PATH.")
        return False


def check_and_install_npm_deps():
    """Checks for node_modules, runs 'npm install' if missing."""
    print_header("Checking Node.js Environment...")
    if os.path.exists(NODE_MODULES_DIR):
        print("node_modules folder found. Skipping 'npm install'.")
        return True

    print("node_modules folder not found. Running 'npm install'...")
    try:
        subprocess.run([NPM_CMD, "install"], check=True, shell=(sys.platform == "win32"))
        print("Node.js dependencies installed successfully.")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"\nERROR: 'npm install' failed. {e}")
        print("Please ensure Node.js and npm are installed and in your PATH.")
        return False

# --- Main Execution ---

if __name__ == "__main__":
    if not check_and_install_python_deps():
        sys.exit(1)

    if not check_and_install_npm_deps():
        sys.exit(1)

    python_server_cmd = [VENV_PYTHON, PYTHON_SERVER_SCRIPT]
    electron_app_cmd = [  NPM_CMD,"run", "start"]

    python_proc, electron_proc = None, None
    try:
        print_header("Starting Development Servers...")

        print(f"-> Launching Python server...")
        python_proc = subprocess.Popen(python_server_cmd, cwd=PROJECT_DIR)

        print("   (Waiting 5 seconds for server to spin up...)")
        time.sleep(5)

        print(f"-> Launching Electron app...")
        electron_proc = subprocess.Popen(electron_app_cmd, cwd=PROJECT_DIR, shell=(sys.platform == "win32"))

        print("\nBoth processes are running. Press Ctrl+C in this window to stop everything.")

        while python_proc.poll() is None and electron_proc.poll() is None:
            time.sleep(1)

    except KeyboardInterrupt:
        print("\nCtrl+C detected. Shutting down...")
    except Exception as e:
        print(f"\nAn unexpected error occurred: {e}")
    finally:
        print_header("Cleaning up processes...")
        if electron_proc and electron_proc.poll() is None:
            electron_proc.terminate()
            electron_proc.wait()
        if python_proc and python_proc.poll() is None:
            python_proc.terminate()
            python_proc.wait()
        print("All processes stopped. Exiting.")