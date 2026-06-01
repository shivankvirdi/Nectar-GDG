const { spawn } = require('child_process');
const path = require('path');

function getActiveUrl() {
  return new Promise((resolve) => {
    const platform = process.platform;
    if (platform === 'win32') {
      // Windows: invoke the existing PowerShell script via PowerShell
      const psScriptPath = path.resolve(__dirname, 'get_active_url.ps1');
      const ps = spawn('powershell', [
        '-NoProfile',
        '-ExecutionPolicy',
        'Bypass',
        '-File',
        psScriptPath,
      ]);
      let output = '';
      ps.stdout.on('data', (data) => (output += data));
      ps.stderr.on('data', (data) => (output += data));
      ps.on('close', (code) => {
        resolve(output.trim() || '');
      });
    } else if (platform === 'darwin') {
      // macOS: use AppleScript to retrieve the URL from the active Chrome tab
      const script = `tell application "Google Chrome" to get URL of active tab of window 1`;
      const appleScript = spawn('osascript', ['-e', script]);
      let output = '';
      appleScript.stdout.on('data', (data) => (output += data));
      appleScript.stderr.on('data', (data) => (output += data));
      appleScript.on('close', (code) => {
        resolve(output.trim() || '');
      });
    } else {
      // Linux or other platforms – placeholder (currently returns empty string)
      resolve('');
    }
  });
}

// Allow direct execution: `node getActiveUrl.js`
if (require.main === module) {
  getActiveUrl().then((url) => console.log(url));
}

const EventEmitter = require('events');
const emitter = new EventEmitter();

/**
 * Starts polling for the active URL.
 * @param {function(string):void} callback - Called with the new URL whenever it changes.
 * @param {number} intervalMs - Polling interval in milliseconds (default 2000ms).
 * @returns {function} A function to stop the polling.
 */
function startUrlPolling(callback, intervalMs = 2000) {
  let lastUrl = '';
  const timer = setInterval(async () => {
    try {
      const url = await getActiveUrl();
      if (url && url !== lastUrl) {
        lastUrl = url;
        callback(url);
        emitter.emit('urlChanged', url);
      }
    } catch (e) {
      // ignore errors during polling
    }
  }, intervalMs);
  return () => clearInterval(timer);
}

module.exports = { getActiveUrl, startUrlPolling, emitter };
