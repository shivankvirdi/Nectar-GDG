const { app, BrowserWindow, ipcMain, screen } = require('electron')
const path = require('path')
const { shell } = require('electron')
const {
  getActiveUrl,
  startUrlPolling
} = require('./getActiveUrl')

let mainWindow

const ICON_PATH = path.join(__dirname, 'dist', 'icons', 'icon128.png')
const DEFAULT_WIDTH = 420
const DEFAULT_HEIGHT = 390
const WINDOW_PADDING = 14

function createWindow() {
  const { width: screenWidth, height: screenHeight } = screen.getPrimaryDisplay().workAreaSize
  const isMac = process.platform === 'darwin'
  const isWin = process.platform === 'win32'

  mainWindow = new BrowserWindow({
    width:  DEFAULT_WIDTH,
    height: DEFAULT_HEIGHT,
    minWidth:  340,
    minHeight: 100,
    frame: false,
    transparent: process.platform==='darwin',        
    alwaysOnTop: true,
    resizable:   false,
    hasShadow:   false,         // we draw our own shadow via CSS box-shadow
    x: screenWidth - DEFAULT_WIDTH - 24,
    y: 40,
    title: 'Nectar',
    icon: ICON_PATH,
    skipTaskbar: false,
    backgroundColor: process.platform==='darwin'?undefined:'#1e1e1e',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  })

  if (isMac) {
    mainWindow.setContentProtection(true)
    mainWindow.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true })
    mainWindow.setAlwaysOnTop(true, 'floating')
    // 'under-window' vibrancy gives native macOS frosted-glass
    mainWindow.setVibrancy('popover')
  }

  if (isWin) {
    mainWindow.setAlwaysOnTop(true, 'normal')
    try { mainWindow.setBackgroundMaterial('acrylic') } catch (_) {}
    app.setAppUserModelId('com.nectar.app')
  }

  const isDev = process.argv.includes('--dev')
  if (isDev) {
    mainWindow.loadURL('http://localhost:5173')
    mainWindow.webContents.openDevTools({ mode: 'detach' })
  } else {
    mainWindow.loadFile(path.join(__dirname, 'dist', 'index.html'))
  }

  mainWindow.on('closed', () => { mainWindow = null })
}

app.whenReady().then(() => {
  createWindow()
  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
  })
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit()
})

ipcMain.handle('close-window',    () => { if (mainWindow) mainWindow.close() })
ipcMain.handle('minimize-window', () => { if (mainWindow) mainWindow.minimize() })

// ── Auto-fit: renderer reports content height, we resize the window ──────────
// Called from App.tsx after every render that might change height.
ipcMain.handle('fit-to-content', async (_event, { contentHeight, contentWidth }) => {
  if (!mainWindow) return
  const { width: screenWidth, height: screenHeight } = screen.getPrimaryDisplay().workAreaSize

  // Clamp: never smaller than 200px, never bigger than 90% of screen height
  const maxH   = Math.floor(screenHeight * 0.90)
  const newH   = Math.min(maxH, Math.max(200, Math.ceil(contentHeight) + WINDOW_PADDING))
  const newW = Math.ceil(contentWidth)
  const [curW, curH] = mainWindow.getSize()

  if (Math.abs(curH - newH) > 2) {           // skip trivial sub-pixel changes
    mainWindow.setSize(newW, newH, false)     // no animation — instant snap
    // Re-pin to right edge in case width changed
    const [, y] = mainWindow.getPosition()
    mainWindow.setPosition(screenWidth - newW - 24, y)
  }
})

// ── Manual resize (e.g. when content area scrolls) ────────────────────────────
ipcMain.handle('resize-window', async (_event, { height, width }) => {
  if (!mainWindow) return
  const { width: screenWidth } = screen.getPrimaryDisplay().workAreaSize
  const targetWidth  = width  || DEFAULT_WIDTH
  const targetHeight = height || DEFAULT_HEIGHT
  mainWindow.setSize(targetWidth, targetHeight, true)
  const [, y] = mainWindow.getPosition()
  mainWindow.setPosition(screenWidth - targetWidth - 24, y, true)
})

ipcMain.handle('move-window', async (_event, { deltaX, deltaY }) => {
  if (!mainWindow) return
  const [x, y] = mainWindow.getPosition()
  mainWindow.setPosition(x + deltaX, y + deltaY)
})

ipcMain.handle('set-opacity', async (_event, { opacity }) => {
  if (!mainWindow) return
  mainWindow.setOpacity(Math.max(0.1, Math.min(1.0, opacity)))
})

ipcMain.handle('get-active-tab-url', async () => {
  try {
    const url = await getActiveUrl()

    if (!url) return null

    return /^https?:\/\//i.test(url)
      ? url
      : `https://${url}`
  } catch {
    return null
  }
})

ipcMain.handle('open-external', (_event, url) => {
  if (url && /^https?:\/\//i.test(url)) {
    shell.openExternal(url)
  }
})