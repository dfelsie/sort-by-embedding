const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
  openFolder: () => ipcRenderer.invoke('open-folder'),
  sortByPrompt: (args) => ipcRenderer.invoke('sort-by-prompt', args),
  applyRenames: (args) => ipcRenderer.invoke('apply-renames', args),
    conceptSort: args => ipcRenderer.invoke('concept-sort', args),
      openInExplorer:  p    => ipcRenderer.invoke('open-in-explorer', p),
      sortWithGemini: args => ipcRenderer.invoke('sort-with-gemini', args),
      oneShotSort: args => ipcRenderer.invoke('one-shot-sort', args),

});
