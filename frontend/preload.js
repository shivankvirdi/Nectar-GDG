const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('electronAPI', {
  getActiveTabUrl: () => ipcRenderer.invoke('get-active-tab-url'),
  resizeWindow: (opts) => ipcRenderer.invoke('resize-window', opts),
})
