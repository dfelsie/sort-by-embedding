const { app, BrowserWindow, ipcMain, dialog } = require('electron');
const path = require('path');
const fs = require('fs');
const { spawn } = require('child_process');

let mainWindow;
let splashWindow;
let apiProcess;

// --- Window Creation ---

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1000,
    height: 700,
    show: false, // Start hidden
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    }
  });
  mainWindow.loadFile(path.join(__dirname, 'index.html'));
  mainWindow.on('closed', () => { mainWindow = null; });
}

function createSplashWindow() {
  splashWindow = new BrowserWindow({
    width: 400,
    height: 200,
    frame: false,
    alwaysOnTop: true,
  });
  splashWindow.loadFile(path.join(__dirname, 'splash.html'));
}

// --- Python Server Management ---

function startApi() {
  const serverExe = process.platform === 'win32' ? 'api_server.exe' : 'api_server';

  const apiPath = app.isPackaged
    ? path.join(process.resourcesPath, 'api', serverExe)
    : path.join(__dirname, 'dist', serverExe);

  console.log(`[Electron] Starting Python server at: ${apiPath}`);
  apiProcess = spawn(apiPath);

  // Helper to prevent showing the window multiple times
  const showMainWindow = () => {
    if (mainWindow && !mainWindow.isVisible()) {
      console.log('[Electron] Server is ready. Showing main window.');
      if (splashWindow) {
        splashWindow.close();
        splashWindow = null;
      }
      mainWindow.show();
    }
  };

  // Listen to STDOUT (for custom print statements, just in case)
  apiProcess.stdout.on('data', (data) => {
    const output = data.toString();
    console.log(`[Python stdout]: ${output}`);
    if (output.includes("PYTHON_SERVER_READY")) {
      showMainWindow();
    }
  });

  // Listen to STDERR (where Uvicorn logs by default)
  apiProcess.stderr.on('data', (data) => {
    const output = data.toString();
    console.error(`[Python stderr]: ${output}`);
    // Use the reliable Uvicorn message as our primary trigger
    if (output.includes("Uvicorn running on")) {
      showMainWindow();
    }
  });
}

// --- App Lifecycle ---

app.on('ready', () => {
  createSplashWindow();
  createWindow();
  startApi();
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('will-quit', () => {
  if (apiProcess) {
    console.log('[Electron] Killing Python server process.');
    apiProcess.kill();
    apiProcess = null;
  }
});

app.on('activate', () => {
  if (mainWindow === null) {
    createWindow();
  }
});

// ---------------- IPC Handlers (Unchanged) ----------------

ipcMain.handle('open-folder', async () => {
  const res = await dialog.showOpenDialog(mainWindow, { properties:['openDirectory'] });
  if (res.canceled) return { canceled: true };
  const folderPath = res.filePaths[0];
  const files = fs.readdirSync(folderPath).filter(f=>{
    const e = path.extname(f).toLowerCase();
    return ['.png','.jpg','.jpeg','.bmp','.gif','.webp'].includes(e);
  });
  return {
    canceled: false,
    folderPath,
    imagePaths: files.map(f=> path.join(folderPath,f))
  };
});

ipcMain.handle('sort-by-prompt', async (event, { imagePaths, prompt }) => {
  try {
    const response = await fetch("http://127.0.0.1:8000/sort-by-clip", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ imagePaths, prompt }),
    });

    if (!response.ok) {
      const text = await response.text();
      throw new Error(`Server error ${response.status}: ${text}`);
    }
    return (await response.json()).sortedPaths;
  } catch (err) {
    console.error("[main] Error calling sort API:", err);
    throw err;
  }
});

ipcMain.handle('apply-renames', async (event, { sortedPaths }) => {
  try {
    const MAX_NAME_LEN = 100;
    for (let i = 0; i < sortedPaths.length; i++) {
      const oldFullPath = sortedPaths[i];
      const dir = path.dirname(oldFullPath);
      let base = path.basename(oldFullPath);
      const prefixMatch = /^(\d+)_/.exec(base);
      if (prefixMatch) {
        base = base.substring(prefixMatch[0].length);
      }
      const ext = path.extname(base);
      const nameOnly = base.slice(0, -ext.length);
      let truncatedName = nameOnly.length > MAX_NAME_LEN ? nameOnly.slice(0, MAX_NAME_LEN) : nameOnly;
      const prefix = String(i + 1).padStart(2, '0');
      const newBase = `${prefix}_${truncatedName}${ext}`;
      const newFullPath = path.join(dir, newBase);

      if (oldFullPath !== newFullPath) {
        if (!fs.existsSync(newFullPath)) {
          fs.renameSync(oldFullPath, newFullPath);
        }
        sortedPaths[i] = newFullPath;
      }
    }
    return true;
  } catch (err)
 {
    console.error('[main] Error during file renaming:', err);
    throw err;
  }
});