' Launches the ingest PowerShell script with NO visible console window.
' Used by the Windows Scheduled Task so it doesn't flash a black window
' every run. The "0" argument to .Run means "hidden"; False = don't wait.
Dim shell, repo, cmd
repo = "C:\Users\lucas.falkenstein\Desktop\project_on_rails"
cmd  = "powershell -NoProfile -ExecutionPolicy Bypass -File """ & repo & "\scripts\run_ingest.ps1"""
Set shell = CreateObject("WScript.Shell")
shell.Run cmd, 0, False
