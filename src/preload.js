const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
  openFolder: () => ipcRenderer.invoke('open-folder'),
  sortByPrompt: (args) => ipcRenderer.invoke('sort-by-prompt', args),
});