import subprocess
import sys
import os
import time
import shutil

# --- Configuration ---
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
VENV_DIR = os.path.join(PROJECT_DIR, ".venv311") # Using your specific venv name
NODE_MODULES_DIR = os.path.join(PROJECT_DIR, "node_modules")
REQUIREMENTS_FILE = os.path.join(PROJECT_DIR, "requirements.txt")
PYTHON_SERVER_SCRIPT = os.path.join(PROJECT_DIR, "unified_sorter_server.py") # Use full path

# --- Platform-specific Executable Names ---
# This makes the script cross-platform (Windows/macOS/Linux)
if sys.platform == "win32":
    VENV_PYTHON = os.path.join(VENV_DIR, "Scripts", "python.exe")
    NPM_CMD = "npm.cmd"
else: # macOS / Linux
    VENV_PYTHON = os.path.join(VENV_DIR, "bin", "python")
    NPM_CMD = "npm"

# --- Helper Functions ---

def print_header(message):
    """Prints a formatted header."""
    print("\n" + "="*60)
    print(f" {message}")
    print("="*60)

def check_and_install_python_deps():
    """Checks for a venv and dependencies, creates/installs if missing."""
    print_header("Checking Python Environment...")
    if os.path.exists(VENV_PYTHON):
        print("Virtual environment found.")
        # A more robust check would be to verify all packages are installed,
        # but for simplicity, we assume if venv exists, it's okay.
        return True

    print("Virtual environment not found. Creating and installing dependencies...")

    # Ensure the system's python is used to create the venv
    try:
        # Create the virtual environment
        subprocess.run([sys.executable, "-m", "venv", VENV_DIR], check=True)
        print(f"Virtual environment created at: {VENV_DIR}")

        # Install dependencies from requirements.txt using the new venv's pip
        pip_path = os.path.join(VENV_DIR, "Scripts" if sys.platform == "win32" else "bin", "pip")
        subprocess.run([pip_path, "install", "-r", REQUIREMENTS_FILE], check=True)

        print("Python dependencies installed successfully.")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"\nERROR: Failed to set up Python environment. {e}")
        print("Please ensure Python 3 is installed and in your PATH.")
        print(f"Also, make sure '{REQUIREMENTS_FILE}' exists.")
        return False

def check_and_install_npm_deps():
    """Checks for node_modules, runs 'npm install' if missing."""
    print_header("Checking Node.js Environment...")
    if os.path.exists(NODE_MODULES_DIR):
        print("node_modules folder found. Skipping 'npm install'.")
        return True

    print("node_modules folder not found. Running 'npm install'...")
    try:
        # On Windows, shell=True is often needed to find npm.cmd in the PATH
        subprocess.run([NPM_CMD, "install"], check=True, shell=(sys.platform == "win32"))
        print("Node.js dependencies installed successfully.")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"\nERROR: 'npm install' failed. {e}")
        print("Please ensure Node.js and npm are installed and in your PATH.")
        return False

# --- Main Execution ---

if __name__ == "__main__":
    # 1. Setup Python Environment
    if not check_and_install_python_deps():
        sys.exit(1) # Exit if setup fails

    # 2. Setup Node.js Environment
    if not check_and_install_npm_deps():
        sys.exit(1) # Exit if setup fails

    # 3. Define commands with correct, absolute paths to executables
    python_server_cmd = [VENV_PYTHON, PYTHON_SERVER_SCRIPT]
    electron_app_cmd = [os.path.join(PROJECT_DIR, "node_modules", ".bin", NPM_CMD), "start"]

    # 4. Start processes
    python_proc = None
    electron_proc = None

    try:
        print_header("Starting Development Servers...")

        # Start Python server
        print(f"-> Launching Python server: {' '.join(python_server_cmd)}")
        python_proc = subprocess.Popen(python_server_cmd, cwd=PROJECT_DIR)

        # Wait a moment to let the server initialize
        print("   (Waiting 2 seconds for server to spin up...)")
        time.sleep(2)

        # Start Electron app
        print(f"-> Launching Electron app: {' '.join(electron_app_cmd)}")
        # Use shell=True for npm on Windows
        electron_proc = subprocess.Popen(electron_app_cmd, cwd=PROJECT_DIR, shell=(sys.platform == "win32"))

        print("\nBoth processes are running. Press Ctrl+C in this window to stop everything.")

        # Wait for either process to exit
        while python_proc.poll() is None and electron_proc.poll() is None:
            time.sleep(1)

    except KeyboardInterrupt:
        print("\nCtrl+C detected. Shutting down...")
    except Exception as e:
        print(f"\nAn unexpected error occurred: {e}")
    finally:
        print_header("Cleaning up processes...")
        if electron_proc and electron_proc.poll() is None:
            print("Terminating Electron process...")
            electron_proc.terminate()
            electron_proc.wait() # Wait for it to actually close
        if python_proc and python_proc.poll() is None:
            print("Terminating Python process...")
            python_proc.terminate()
            python_proc.wait()
        print("All processes stopped. Exiting.")