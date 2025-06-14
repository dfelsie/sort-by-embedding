# Definitive Build Instructions for Unified Sorter

This guide provides the complete, end-to-end process for building the Unified Sorter application. Follow these steps methodically to ensure a clean and successful build.

---

## Section 1: Prerequisites

Ensure the following files are correct and in your project root (`sort-by-embedding/`):

1. **`package.json`**: The final version that correctly lists the application files.
2. **`main.js`**: The final version that manages the splash screen and listens for the "Uvicorn running on" signal.
3. **`run_server.py`**: The final version that corrects the Python `sys.path`.
4. **`requirements.txt`**: The version that includes the `--extra-index-url` for PyTorch.

---

## Section 2: The "Total Reset" (Pre-Build Cleanup)

> **⚠️ This is the most critical phase.** Do this every time you want to create a guaranteed clean build.

### Step 1: Uninstall Previous Version
- Go to Windows "Add or Remove Programs" and uninstall "Unified Sorter" if it exists
- Manually delete its installation folder if it remains:
  - `C:\Users\DLF\AppData\Local\Programs\Unified Sorter`
  - `C:\Program Files\Unified Sorter`

### Step 2: Close All Programs
Close VS Code, all terminals, and any File Explorer windows pointing to your project directory.

### Step 3: Clean Project Artifacts
Open a new Command Prompt and navigate to your project root. Run these commands:

```cmd
rmdir /s /q dist
rmdir /s /q build
rmdir /s /q node_modules
del api_server.spec
del package-lock.json
```

*Note: It is okay if some commands fail with "File Not Found"*

### Step 4: Clean System Caches

```cmd
npm cache clean --force
rmdir /s /q C:\Users\DLF\AppData\Local\electron-builder\Cache
```

### Step 5: Reboot Your Computer
**This is not optional.** It releases any stubborn file locks held by the operating system or hung processes.

---

## Section 3: Phase 1 - Build the Python Backend

### Step 1: Open Terminal as Administrator
After rebooting, find Command Prompt or PowerShell, right-click, and "Run as administrator".

### Step 2: Navigate to Project and Activate Virtual Environment

```cmd
cd C:\Users\DLF\Documents\newCode\jobs2\sort-by-embedding
.\.venv311\Scripts\activate
```

### Step 3: Run PyInstaller
Copy and paste the entire one-line command below. This includes the data files (`.txt.gz` and the `model_configs` directory) required by `open_clip`.

```cmd
pyinstaller --name "api_server" --onefile --noconsole --add-data ".venv311/Lib/site-packages/open_clip/bpe_simple_vocab_16e6.txt.gz;open_clip" --add-data ".venv311/Lib/site-packages/open_clip/model_configs;open_clip/model_configs" --hidden-import="sklearn.utils._cython_blas" --hidden-import="PIL._tkinter_finder" --copy-metadata "torch" --copy-metadata "tqdm" --copy-metadata "regex" --copy-metadata "requests" --copy-metadata "packaging" --copy-metadata "filelock" --copy-metadata "numpy" --copy-metadata "huggingface-hub" --copy-metadata "safetensors" --copy-metadata "pyyaml" --copy-metadata "open-clip-torch" run_server.py
```

### Step 4: Test the Executable
After the build completes, run the server directly to confirm it works:

```cmd
.\dist\api_server.exe
```

You should see the `INFO: uvicorn.error: Uvicorn running...` message without any errors beforehand. Press `Ctrl+C` to stop it. If this step works, the Python part is perfect.

---

## Section 4: Phase 2 - Build the Final Application

### Step 1: Install Node Dependencies

```cmd
npm install
```

### Step 2: Set Antivirus Exclusion (CRITICAL for NSIS error)
- Open **Windows Security** → **Virus & threat protection**
- Click **Manage settings** → **Add or remove exclusions**
- Add a **Folder** exclusion for your project directory: `C:\Users\DLF\Documents\newCode\jobs2\sort-by-embedding`

### Step 3: Run the Electron Build

```cmd
npm run build
```

---

## Section 5: Advanced Troubleshooting (If NSIS Still Fails)

If the build fails again with the `mmap` or `makensis.exe` error, the problem is 100% with the NSIS installer tool's interaction with your machine. Try these modifications in your `package.json`.

### Option A: Disable NSIS Compression

This makes the installer larger but is much less likely to hit a memory or file-locking issue.

Modify the `nsis` block in `package.json`:

```json
"nsis": {
  "oneClick": false,
  "allowToChangeInstallationDirectory": true,
  "compression": "store"
}
```

Then, re-run `npm run build` (after cleaning the `dist` folder).

### Option B: Build a "Portable" App (Bypass the Installer)

This creates a single `.exe` that runs without installation. This is a great alternative if the installer is the only thing failing.

Modify the `win` block in `package.json`:

```json
"win": {
  "target": "portable",
  "icon": "build/icon.ico"
}
```

Then, re-run `npm run build`. This will produce a single `.exe` in your `dist` folder that you can distribute.
