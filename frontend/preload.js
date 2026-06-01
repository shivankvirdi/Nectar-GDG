const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('electronAPI', {
  getActiveTabUrl: () => ipcRenderer.invoke('get-active-tab-url'),
  resizeWindow: (opts) => ipcRenderer.invoke('resize-window', opts),
  moveWindow: (opts) => ipcRenderer.invoke('move-window', opts),
  setOpacity: (opts) => ipcRenderer.invoke('set-opacity', opts),
  closeWindow: () => ipcRenderer.invoke('close-window'),
  minimizeWindow: () => ipcRenderer.invoke('minimize-window'),
})