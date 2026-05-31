const { app, BrowserWindow, ipcMain, screen } = require('electron')
const path = require('path')
const { execFile } = require('child_process')

let mainWindow

const ICON_PATH = path.join(__dirname, 'dist', 'icons', 'icon128.png')

// Default overlay dimensions — compact floating panel
const DEFAULT_WIDTH = 400
const DEFAULT_HEIGHT = 520

function createWindow() {
  const { width: screenWidth, height: screenHeight } = screen.getPrimaryDisplay().workAreaSize

  mainWindow = new BrowserWindow({
    width: DEFAULT_WIDTH,
    height: DEFAULT_HEIGHT,
    minWidth: 340,
    minHeight: 200,
    // Overlay behavior
    frame: false,
    transparent: true,
    alwaysOnTop: true,
    resizable: true,
    hasShadow: false,
    // Position: top-right corner, with some padding
    x: screenWidth - DEFAULT_WIDTH - 24,
    y: 40,
    title: 'Nectar',
    icon: ICON_PATH,
    skipTaskbar: false,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  })

  // macOS: exclude from screen capture (invisible to screen sharing like Zoom/Meet)
  if (process.platform === 'darwin') {
    mainWindow.setContentProtection(true)
    mainWindow.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true })
    mainWindow.setAlwaysOnTop(true, 'floating')
  }

  // Windows: keep on top across virtual desktops
  if (process.platform === 'win32') {
    mainWindow.setAlwaysOnTop(true, 'normal')
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

// ── IPC: Resize overlay ───────────────────────────────────────────────────
ipcMain.handle('resize-window', async (_event, { height, width }) => {
  if (!mainWindow) return
  const { width: screenWidth } = screen.getPrimaryDisplay().workAreaSize
  const targetWidth = width || DEFAULT_WIDTH
  const targetHeight = height || DEFAULT_HEIGHT
  mainWindow.setSize(targetWidth, targetHeight, true)
  // Re-pin to right edge
  const [, y] = mainWindow.getPosition()
  mainWindow.setPosition(screenWidth - targetWidth - 24, y, true)
})

// ── IPC: Move window (drag) ───────────────────────────────────────────────
ipcMain.handle('move-window', async (_event, { deltaX, deltaY }) => {
  if (!mainWindow) return
  const [x, y] = mainWindow.getPosition()
  mainWindow.setPosition(x + deltaX, y + deltaY)
})

// ── IPC: Toggle opacity ───────────────────────────────────────────────────
ipcMain.handle('set-opacity', async (_event, { opacity }) => {
  if (!mainWindow) return
  mainWindow.setOpacity(Math.max(0.1, Math.min(1.0, opacity)))
})

// ── IPC: Active browser tab URL detection via PowerShell UI Automation ───
ipcMain.handle('get-active-tab-url', async () => {
  return new Promise((resolve) => {
    const isDev = process.argv.includes('--dev')
    const psScriptPath = isDev
      ? path.join(__dirname, 'get_active_url.ps1')
      : path.join(__dirname, 'get_active_url.ps1')

    execFile(
      'powershell.exe',
      ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', psScriptPath],
      (error, stdout) => {
        if (error) {
          console.error('Error running active URL script:', error)
          resolve(null)
          return
        }
        const detectedUrl = stdout.trim()
        if (detectedUrl) {
          let formattedUrl = detectedUrl
          if (!/^https?:\/\//i.test(formattedUrl)) {
            formattedUrl = 'https://' + formattedUrl
          }
          resolve(formattedUrl)
        } else {
          resolve(null)
        }
      }
    )
  })
})