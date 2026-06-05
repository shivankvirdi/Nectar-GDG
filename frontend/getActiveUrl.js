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
      // macOS: try Chrome, Arc, Brave, Edge, Firefox, Safari in order.
      // Returns the first URL that matches Amazon or eBay.
      // Falls back to whichever browser is frontmost if none match.
      const script = `
        set supportedDomains to {"amazon.", "ebay."}
        set browsers to {
          {"Google Chrome", "URL of active tab of front window"},
          {"Arc", "URL of active tab of window 1"},
          {"Brave Browser", "URL of active tab of front window"},
          {"Microsoft Edge", "URL of active tab of front window"},
          {"Firefox", "URL of active tab of front window"}
        }

        -- First pass: find a supported-marketplace URL in a running browser
        repeat with browserPair in browsers
          set bName to item 1 of browserPair
          set bCmd  to item 2 of browserPair
          try
            tell application bName
              set tabUrl to (do shell script "echo ''")
              try
                set tabUrl to (get ${"{bCmd}"})
              end try
              repeat with dom in supportedDomains
                if tabUrl contains dom then
                  return tabUrl
                end if
              end repeat
            end tell
          end try
        end repeat

        -- Second pass: return whatever the frontmost browser has open
        repeat with browserPair in browsers
          set bName to item 1 of browserPair
          set bCmd  to item 2 of browserPair
          try
            tell application bName
              if it is running then
                return (get ${"{bCmd}"})
              end if
            end tell
          end try
        end repeat

        -- Safari fallback
        try
          tell application "Safari"
            return URL of current tab of front window
          end tell
        end try

        return ""
      `;

      // Use a simpler, more reliable approach: try each browser directly
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

const EventEmitter = require('events');
const emitter = new EventEmitter();

/**
 * Starts polling for the active URL.
 * Calls `callback` whenever the URL changes to one that looks like
 * an Amazon or eBay product page.
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
      // ignore polling errors silently
    }
  }, intervalMs);
  return () => clearInterval(timer);
}

module.exports = { getActiveUrl, startUrlPolling, emitter };