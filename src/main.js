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
        console.log(sortedPaths,"sorPa ", stdoutData)
        resolve(sortedPaths);
      } catch (err) {
        console.error('[main] Failed to parse JSON from Python:', err, stdoutData);
        reject(err);
      }
    });
  });
});
;

