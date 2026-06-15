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
      ps.on('close', () => {
        resolve(output.trim() || '');
      });
    } else if (platform === 'darwin') {
      _tryBrowsersMac(resolve);
    } else {
      // Linux: xdotool fallback
      _tryLinux(resolve);
    }
  });
}

/**
 * macOS: sequentially try each browser using individual osascript calls.
 * Prefers Amazon/eBay URLs, falls back to whatever is open.
 */
function _tryBrowsersMac(resolve) {
  const browsers = [
    // [appName, scriptToGetUrl]
    ['Google Chrome', 'tell application "Google Chrome" to get URL of active tab of front window'],
    ['Arc',           'tell application "Arc" to get URL of active tab of window 1'],
    ['Brave Browser', 'tell application "Brave Browser" to get URL of active tab of front window'],
    ['Microsoft Edge','tell application "Microsoft Edge" to get URL of active tab of front window'],
    ['Firefox',       'tell application "Firefox" to get URL of active tab of front window'],
    ['Safari',        'tell application "Safari" to get URL of current tab of front window'],
  ];

  const SUPPORTED = ['amazon.', 'ebay.'];

  let fallbackUrl = '';
  let index = 0;

  function tryNext() {
    if (index >= browsers.length) {
      // No marketplace URL found — return the first non-empty URL we saw
      resolve(fallbackUrl);
      return;
    }

    const [, script] = browsers[index++];
    const proc = spawn('osascript', ['-e', script]);
    let out = '';
    proc.stdout.on('data', (d) => (out += d));
    proc.on('close', (code) => {
      const url = out.trim();
      if (url && !url.startsWith('osascript:') && !url.startsWith('execution error')) {
        // Save first valid URL as fallback
        if (!fallbackUrl) fallbackUrl = url;
        // Return immediately if it's a supported marketplace
        if (SUPPORTED.some((d) => url.includes(d))) {
          resolve(url);
          return;
        }
      }
      tryNext();
    });
    proc.stderr.on('data', () => {}); // silence errors for non-running apps
  }

  tryNext();
}

/**
 * Linux: use xdotool to get the active window title and try to extract
 * a URL. Very best-effort.
 */
function _tryLinux(resolve) {
  const proc = spawn('xdotool', ['getactivewindow', 'getwindowname']);
  let out = '';
  proc.stdout.on('data', (d) => (out += d));
  proc.on('close', () => {
    // Chrome/Firefox put "URL - Tab Title - Browser" in the window title
    const urlMatch = out.match(/https?:\/\/[^\s]+/);
    resolve(urlMatch ? urlMatch[0] : '');
  });
  proc.on('error', () => resolve(''));
}

// Allow direct execution: `node getActiveUrl.js`
if (require.main === module) {
  getActiveUrl().then((url) => console.log(url));
}

module.exports = { getActiveUrl };
