// src/main.js

const { app, BrowserWindow, ipcMain, dialog } = require('electron');
const path = require('path');
const fs = require('fs');
// We no longer need child_process.spawn for sorting
// const { spawn } = require('child_process');
//const fetchPkg = require('node-fetch'); // if you installed node-fetch
// (If using Node 18’s built-in fetch, you can omit `require('node-fetch')`)

let mainWindow;

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1000,
    height: 700,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    }
  });
  mainWindow.loadFile(path.join(__dirname, 'index.html'));
  mainWindow.on('closed', () => { mainWindow = null; });
}

app.on('ready', createWindow);
app.on('window-all-closed', () => { if (process.platform !== 'darwin') app.quit(); });
app.on('activate', () => { if (mainWindow === null) createWindow(); });

// ---------------- IPC ----------------

ipcMain.handle('open-folder', async () => {
  const result = await dialog.showOpenDialog(mainWindow, {
    properties: ['openDirectory']
  });
  if (result.canceled) {
    return { canceled: true };
  }
  const folderPath = result.filePaths[0];
  const allFiles = fs.readdirSync(folderPath).filter(fname => {
    const ext = path.extname(fname).toLowerCase();
    return ['.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp'].includes(ext);
  });
  const imagePaths = allFiles.map(fname => path.join(folderPath, fname));
  return { canceled: false, folderPath, imagePaths };
});

ipcMain.handle('sort-by-prompt', async (event, { folderPath, imagePaths, prompt }) => {
  try {
    // 1) Build the payload
    const payload = { folderPath, imagePaths, prompt };

    // 2) POST to our local FastAPI server
    const response = await fetch("http://127.0.0.1:8000/sort", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      const text = await response.text();
      throw new Error(`Server error ${response.status}: ${text}`);
    }

    const json = await response.json();
    // The server returns { sortedPaths: [ … ] }
    return json.sortedPaths;
  } catch (err) {
    console.error("[main] Error calling sort API:", err);
    throw err;
  }
});

ipcMain.handle('apply-renames', async (event, { folderPath, sortedPaths }) => {
  /**
   * (Leave your existing rename logic here—unchanged.)
   */
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
      let truncatedName = nameOnly;
      if (nameOnly.length > MAX_NAME_LEN) {
        truncatedName = nameOnly.slice(0, MAX_NAME_LEN);
      }
      const prefix = String(i + 1).padStart(2, '0');
      const newBase = `${prefix}_${truncatedName}${ext}`;
      const newFullPath = path.join(dir, newBase);

      if (oldFullPath !== newFullPath) {
        if (fs.existsSync(newFullPath)) {
          sortedPaths[i] = newFullPath;
        } else {
          fs.renameSync(oldFullPath, newFullPath);
          sortedPaths[i] = newFullPath;
        }
      } else {
        sortedPaths[i] = newFullPath;
      }
    }
    return true;
  } catch (err) {
    console.error('[main] Error during file renaming:', err);
    throw err;
  }
});
