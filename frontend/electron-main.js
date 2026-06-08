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
const MIN_WINDOW_HEIGHT = DEFAULT_HEIGHT
const MAX_WINDOW_HEIGHT = DEFAULT_HEIGHT * 2
const AUTO_RESIZE_FRAME_MS = 16
const AUTO_RESIZE_EASE = 0.28

let autoResizeTimer = null
let autoResizeTargetHeight = DEFAULT_HEIGHT

function clampWindowHeight(height) {
  return Math.min(MAX_WINDOW_HEIGHT, Math.max(MIN_WINDOW_HEIGHT, Math.ceil(height)))
}

function stopAutoResizeAnimation() {
  if (autoResizeTimer) clearTimeout(autoResizeTimer)
  autoResizeTimer = null
}

function setPinnedWindowHeight(height) {
  if (!mainWindow) return
  const { width: screenWidth } = screen.getPrimaryDisplay().workAreaSize
  const [, y] = mainWindow.getPosition()
  mainWindow.setBounds({
    x: screenWidth - DEFAULT_WIDTH - 24,
    y,
    width: DEFAULT_WIDTH,
    height,
  })
}

function animateWindowToContentHeight(contentHeight) {
  if (!mainWindow) return

  const targetHeight = clampWindowHeight(contentHeight)
  const [curW, curH] = mainWindow.getSize()

  autoResizeTargetHeight = targetHeight

  if (Math.abs(curH - targetHeight) <= 2 && curW === DEFAULT_WIDTH) {
    setPinnedWindowHeight(targetHeight)
    return
  }

  if (autoResizeTimer) return

  const tick = () => {
    if (!mainWindow) {
      stopAutoResizeAnimation()
      return
    }

    const [, currentHeight] = mainWindow.getSize()
    const diff = autoResizeTargetHeight - currentHeight
    const nextHeight = Math.round(currentHeight + diff * AUTO_RESIZE_EASE)

    setPinnedWindowHeight(nextHeight)

    if (Math.abs(diff) > 1) {
      autoResizeTimer = setTimeout(tick, AUTO_RESIZE_FRAME_MS)
      return
    }

    setPinnedWindowHeight(autoResizeTargetHeight)
    autoResizeTimer = null
  }

  tick()
}

function createWindow() {
  const { width: screenWidth } = screen.getPrimaryDisplay().workAreaSize
  const isMac = process.platform === 'darwin'
  const isWin = process.platform === 'win32'

  mainWindow = new BrowserWindow({
    width:  DEFAULT_WIDTH,
    height: DEFAULT_HEIGHT,
    minWidth:  DEFAULT_WIDTH,
    maxWidth:  DEFAULT_WIDTH,
    minHeight: MIN_WINDOW_HEIGHT,
    maxHeight: MAX_WINDOW_HEIGHT,
    frame: false,
    transparent: process.platform==='darwin',        
    alwaysOnTop: true,
    resizable:   true,
    maximizable: false,
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

  mainWindow.on('closed', () => {
    stopAutoResizeAnimation()
    mainWindow = null
  })
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
ipcMain.handle('fit-to-content', async (_event, { contentHeight }) => {
  if (!mainWindow) return
  animateWindowToContentHeight(contentHeight)

})

// ── Manual resize (e.g. when content area scrolls) ────────────────────────────
ipcMain.handle('resize-window', async (_event, { height }) => {
  if (!mainWindow) return
  stopAutoResizeAnimation()
  const { width: screenWidth } = screen.getPrimaryDisplay().workAreaSize
  const targetWidth  = DEFAULT_WIDTH
  const targetHeight = clampWindowHeight(height || DEFAULT_HEIGHT)
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
