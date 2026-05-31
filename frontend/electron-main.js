const { app, BrowserWindow, ipcMain } = require('electron')
const path = require('path')
const { execFile } = require('child_process')

let mainWindow

// Icon path — always points at the 128px Nectar logo in public/icons
const ICON_PATH = path.join(__dirname, 'dist', 'icons', 'icon128.png')

// The compact height covering just header + product analysis card + history header
// Frame chrome on Windows is ~30px title bar, so subtract from target visual height
const COMPACT_HEIGHT = 380
const COMPACT_WIDTH = 400

function createWindow() {
  mainWindow = new BrowserWindow({
    width: COMPACT_WIDTH,
    height: COMPACT_HEIGHT,
    minWidth: COMPACT_WIDTH,
    minHeight: COMPACT_HEIGHT,
    resizable: true,
    title: 'Nectar',
    icon: ICON_PATH,
    autoHideMenuBar: true,
    frame: true,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  })

  // Set Windows taskbar app ID so the correct icon shows in taskbar
  if (process.platform === 'win32') {
    app.setAppUserModelId('com.nectar.app')
  }

  // If --dev flag is passed, load Vite dev server. Otherwise load built index.html.
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
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow()
    }
  })
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit()
  }
})

// ── IPC: Renderer tells main to resize the window ────────────────────────
// Called with { height } to expand (during scan) or { height: COMPACT_HEIGHT } to shrink back.
ipcMain.handle('resize-window', async (_event, { height, width }) => {
  if (!mainWindow) return
  const targetWidth = width || COMPACT_WIDTH
  const targetHeight = height || COMPACT_HEIGHT
  mainWindow.setSize(targetWidth, targetHeight, true /* animate */)
})

// ── IPC: Active browser tab URL detection via PowerShell UI Automation ───
ipcMain.handle('get-active-tab-url', async () => {
  return new Promise((resolve) => {
    // In dev mode the script lives next to this file; in prod it's in dist/
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
