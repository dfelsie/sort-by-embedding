// src/main.js (edited)

const { app, BrowserWindow, ipcMain, dialog } = require('electron');
const path = require('path');
const fs = require('fs');
const { spawn } = require('child_process');

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
  return new Promise((resolve, reject) => {
    // Build the JSON argument to pass to Python
    const payload = { folderPath, imagePaths, prompt };
    const jsonArg = JSON.stringify(payload);

    // Spawn Python process
    const scriptPath = path.join(__dirname, '..', 'embed_sorter.py');
    const pyProcess = spawn('python', [scriptPath, jsonArg]);

    let stdoutData = '';
    let stderrData = '';

    pyProcess.stdout.on('data', (chunk) => {
      stdoutData += chunk.toString();
    });
    pyProcess.stderr.on('data', (chunk) => {
      stderrData += chunk.toString();
    });
    pyProcess.on('close', (code) => {
      if (code !== 0) {
        console.error(`[main] embed_sorter.py exited with code ${code}`);
        console.error(stderrData);
        reject(new Error(`embed_sorter.py failed: ${stderrData}`));
        return;
      }
      try {
        // → Parse the JSON array directly from stdoutData
        const sortedPaths = JSON.parse(stdoutData);
        resolve(sortedPaths);
      } catch (err) {
        console.error('[main] Failed to parse JSON from Python:', err, stdoutData);
        reject(err);
      }
    });
  });
});
ipcMain.handle('apply-renames', async (event, { folderPath, sortedPaths }) => {
  /**
   * We assume:
   *   - folderPath is the directory containing all images.
   *   - sortedPaths is an array of absolute paths in desired order.
   * We will rename each file to "NN_originalName.ext", where NN is 01, 02, … (one-based).
   * If the "name" part (without extension) is extremely long, we truncate it to at most 100 characters.
   *
   * If the target name already exists, we do NOT append "_dup"—we simply skip renaming that file.
   */
  try {
    const MAX_NAME_LEN = 100; // maximum length for “name only” portion

    for (let i = 0; i < sortedPaths.length; i++) {
      const oldFullPath = sortedPaths[i];
      const dir = path.dirname(oldFullPath);
      let base = path.basename(oldFullPath); // e.g. "05_ReallyLongName...jpg"

      // 1) Strip any existing numeric prefix "NN_"
      const prefixMatch = /^(\d+)_/.exec(base);
      if (prefixMatch) {
        base = base.substring(prefixMatch[0].length);
        // e.g. from "05_LongFilename.jpg" → "LongFilename.jpg"
      }

      // 2) Split off extension
      const ext = path.extname(base);                // e.g. ".jpg"
      const nameOnly = base.slice(0, -ext.length);   // e.g. "VeryLongFilename…"

      // 3) Truncate nameOnly if it exceeds MAX_NAME_LEN
      let truncatedName = nameOnly;
      if (nameOnly.length > MAX_NAME_LEN) {
        truncatedName = nameOnly.slice(0, MAX_NAME_LEN);
      }

      // 4) Build the new base: zero-padded prefix + "_" + truncatedName + ext
      const prefix = String(i + 1).padStart(2, '0');   // "01", "02", …
      const newBase = `${prefix}_${truncatedName}${ext}`;
      const newFullPath = path.join(dir, newBase);

      // 5) Only attempt rename if oldFullPath differs from newFullPath
      if (oldFullPath !== newFullPath) {
        if (fs.existsSync(newFullPath)) {
          // — Skip renaming entirely if target already exists.
          //   We leave sortedPaths[i] pointing to newFullPath (the existing file).
          sortedPaths[i] = newFullPath;
        } else {
          // — Safe to rename
          fs.renameSync(oldFullPath, newFullPath);
          sortedPaths[i] = newFullPath;
        }
      } else {
        // oldFullPath === newFullPath, no change needed
        sortedPaths[i] = newFullPath;
      }
    }

    return true;
  } catch (err) {
    console.error('[main] Error during file renaming:', err);
    throw err;
  }
});