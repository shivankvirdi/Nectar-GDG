const { app, BrowserWindow, ipcMain, screen, shell } = require('electron')
const path = require('path')
const fs = require('fs')
const os = require('os')
const {
  getActiveUrl
} = require('./getActiveUrl')

let mainWindow

const ICON_PATH = path.join(__dirname, 'dist', 'Icons', 'icon128.png')
const DEFAULT_WIDTH = 375
const DEFAULT_HEIGHT = 358
const MIN_WINDOW_HEIGHT = DEFAULT_HEIGHT
const MAX_WINDOW_HEIGHT = 735
const AUTO_RESIZE_FRAME_MS = 8
const AUTO_RESIZE_EASE = 0.40

let autoResizeTimer = null
let autoResizeTargetHeight = DEFAULT_HEIGHT

const LEGACY_STORAGE_DIR = path.join(app.getPath('appData'), 'Electron')
const APP_STORAGE_DIR = path.join(app.getPath('appData'), 'Nectar')
const CACHE_DIR = path.join(os.tmpdir(), 'Nectar', 'ChromiumCache')
const HISTORY_MARKER = 'nectar_scan_history'

function ensureDir(dir) {
  try {
    fs.mkdirSync(dir, { recursive: true })
    return true
  } catch {
    return false
  }
}

function folderContainsText(dir, text) {
  try {
    if (!fs.existsSync(dir)) return false
    const entries = fs.readdirSync(dir, { withFileTypes: true })
    for (const entry of entries) {
      const fullPath = path.join(dir, entry.name)
      if (entry.isDirectory()) {
        if (folderContainsText(fullPath, text)) return true
        continue
      }
      if (!entry.isFile()) continue
      try {
        if (fs.readFileSync(fullPath).includes(text)) return true
      } catch {
        // Ignore locked cache/profile files; readable LevelDB files are enough for migration detection.
      }
    }
  } catch {
    return false
  }
  return false
}

function migrateLegacyStorage() {
  const legacyLocalStorage = path.join(LEGACY_STORAGE_DIR, 'Local Storage')
  const nextLocalStorage = path.join(APP_STORAGE_DIR, 'Local Storage')

  if (!folderContainsText(legacyLocalStorage, HISTORY_MARKER)) return
  if (folderContainsText(nextLocalStorage, HISTORY_MARKER)) return

  try {
    fs.rmSync(nextLocalStorage, { recursive: true, force: true })
    fs.cpSync(legacyLocalStorage, nextLocalStorage, { recursive: true })
  } catch {
    // If migration fails, keep startup non-fatal; the app can still create fresh storage.
  }
}

if (ensureDir(APP_STORAGE_DIR)) {
  migrateLegacyStorage()
  app.setPath('userData', APP_STORAGE_DIR)
}

if (ensureDir(CACHE_DIR)) {
  app.commandLine.appendSwitch('disk-cache-dir', CACHE_DIR)
  app.commandLine.appendSwitch('disable-gpu-shader-disk-cache')
}

// Chromium can spam stderr for transient remote image/API TLS resets. Keep app logs readable
// without relaxing certificate validation or suppressing renderer console errors.
app.commandLine.appendSwitch('log-level', '3')
app.commandLine.appendSwitch('disable-logging')

const gotSingleInstanceLock = app.requestSingleInstanceLock()

if (!gotSingleInstanceLock) {
  app.quit()
}

function clampWindowHeight(height) {
  return Math.min(MAX_WINDOW_HEIGHT, Math.max(MIN_WINDOW_HEIGHT, Math.ceil(height)))
}

function stopAutoResizeAnimation() {
  if (autoResizeTimer) clearTimeout(autoResizeTimer)
  autoResizeTimer = null
}

function setWindowHeight(height) {
  if (!mainWindow) return
  const [x, y] = mainWindow.getPosition()
  mainWindow.setBounds({
    x,
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

    setWindowHeight(nextHeight)

    if (Math.abs(diff) > 1) {
      autoResizeTimer = setTimeout(tick, AUTO_RESIZE_FRAME_MS)
      return
    }

    setWindowHeight(autoResizeTargetHeight)
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
    transparent: false,
    resizable:   false,
    hasShadow:   true,         // we draw our own shadow via CSS box-shadow
    x: screenWidth - DEFAULT_WIDTH - 24,
    y: 40,
    title: 'Nectar',
    icon: ICON_PATH,
    skipTaskbar: false,
    backgroundColor: process.platform === 'darwin' ? undefined : '#1e1e1e',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  })

  if (isMac) {
    mainWindow.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true })
    mainWindow.setAlwaysOnTop(true, 'floating')
    // 'under-window' vibrancy gives native macOS frosted-glass
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

if (gotSingleInstanceLock) {
  app.on('second-instance', () => {
    if (!mainWindow) return
    if (mainWindow.isMinimized()) mainWindow.restore()
    if (!mainWindow.isVisible()) mainWindow.show()
    mainWindow.focus()
  })

  app.whenReady().then(() => {
    createWindow()
    app.on('activate', () => {
      if (BrowserWindow.getAllWindows().length === 0) createWindow()
    })
  })
}

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit()
})

ipcMain.handle('close-window',    () => { if (mainWindow) mainWindow.close() })
ipcMain.handle('minimize-window', () => { if (mainWindow) mainWindow.minimize() })

ipcMain.handle('fit-to-content', async (_event, { contentHeight }) => {
  if (!mainWindow) return
  animateWindowToContentHeight(contentHeight)
})

// ── Manual resize (e.g. when content area scrolls) ────────────────────────────
ipcMain.handle('resize-window', async (_event, { height }) => {
  if (!mainWindow) return
  stopAutoResizeAnimation()
  const targetWidth  = DEFAULT_WIDTH
  const targetHeight = clampWindowHeight(height || DEFAULT_HEIGHT)
  mainWindow.setSize(targetWidth, targetHeight, true)
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

// ── Expand / Collapse (dashboard mode) ───────────────────────────────────────
let isExpanded = false

ipcMain.handle('toggle-expand', async () => {
  if (!mainWindow) return
  stopAutoResizeAnimation()

  if (!isExpanded) {
    isExpanded = true
    mainWindow.setResizable(true)
    mainWindow.setMaximizable(true)
    mainWindow.setAlwaysOnTop(false)
    mainWindow.setMinimumSize(800, 600)
    mainWindow.maximize()
  } else {
    isExpanded = false
    const { width: screenWidth } = screen.getPrimaryDisplay().workAreaSize
    mainWindow.unmaximize()
    mainWindow.setResizable(false)
    mainWindow.setMaximizable(false)
    mainWindow.setMinimumSize(DEFAULT_WIDTH, MIN_WINDOW_HEIGHT)
    if (process.platform === 'darwin') mainWindow.setAlwaysOnTop(true, 'floating')
    else if (process.platform === 'win32') mainWindow.setAlwaysOnTop(true, 'normal')
    else mainWindow.setAlwaysOnTop(true)
    mainWindow.setBounds(
      { x: screenWidth - DEFAULT_WIDTH - 24, y: 40, width: DEFAULT_WIDTH, height: DEFAULT_HEIGHT },
      true
    )
  }

  return isExpanded
})

ipcMain.handle('open-external', (_event, url) => {
  if (url && /^https?:\/\//i.test(url)) {
    shell.openExternal(url)
  }
})
