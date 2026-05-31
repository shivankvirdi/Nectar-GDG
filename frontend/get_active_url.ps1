Add-Type -AssemblyName UIAutomationClient
function Get-BrowserUrl {
    param (
        [IntPtr]$hwnd,
        [string]$processName
    )
    try {
        $el = [System.Windows.Automation.AutomationElement]::FromHandle($hwnd)
        if (-not $el) { return $null }
        # In Chrome and Edge, the address bar is an Edit control
        # ClassName is usually 'OmniboxViewViews'
        $condEdit = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty, [System.Windows.Automation.ControlType]::Edit)
        $edits = $el.FindAll([System.Windows.Automation.TreeScope]::Descendants, $condEdit)
        
        foreach ($edit in $edits) {
            # Check name or class name to find the address bar
            $name = $edit.Current.Name
            $className = $edit.Current.ClassName
            if ($name -match "address" -or $className -eq "OmniboxViewViews" -or $name -eq "Address and search bar") {
                $valPattern = $edit.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern)
                if ($valPattern -and $valPattern.Current.Value) {
                    return $valPattern.Current.Value
                }
            }
        }
        
        # Fallback: if no match by name/classname, try any Edit control that has a ValuePattern and looks like a URL/domain
        foreach ($edit in $edits) {
            $valPattern = $edit.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern)
            if ($valPattern -and $valPattern.Current.Value) {
                $val = $valPattern.Current.Value
                if ($val -match "^(https?://)?([a-zA-Z0-9\-]+\.)+[a-zA-Z]{2,}(/.*)?$") {
                    return $val
                }
            }
        }
    }
    catch {
        # Silently ignore errors
    }
    return $null
}
# 1. Get the foreground window
$signature = @'
[DllImport("user32.dll")]
public static extern IntPtr GetForegroundWindow();
'@
$type = Add-Type -MemberDefinition $signature -Name "Win32ActiveWindow" -Namespace "Win32" -PassThru
$foregroundHwnd = $type::GetForegroundWindow()
if ($foregroundHwnd -ne [IntPtr]::Zero) {
    $proc = Get-Process -Id ([System.Windows.Automation.AutomationElement]::FromHandle($foregroundHwnd).Current.ProcessId) -ErrorAction SilentlyContinue
    if ($proc -and ($proc.ProcessName -match "chrome|msedge|firefox|opera|browser")) {
        $url = Get-BrowserUrl -hwnd $foregroundHwnd -processName $proc.ProcessName
        if ($url) {
            Write-Output $url
            exit
        }
    }
}
# 2. Fallback: Search all running browser processes with a window
$browsers = Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -match "chrome|msedge|firefox|opera|browser" }
foreach ($b in $browsers) {
    if ($b.MainWindowHandle -ne [IntPtr]::Zero) {
        $url = Get-BrowserUrl -hwnd $b.MainWindowHandle -processName $b.ProcessName
        if ($url) {
            # Make sure it's a valid website or Amazon URL if possible
            Write-Output $url
            exit
        }
    }
}
Write-Output ""