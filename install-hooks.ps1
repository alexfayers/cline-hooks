param(
    [Parameter(Mandatory = $true)]
    [string]$TargetDir
)

$ErrorActionPreference = 'Stop'

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host "Installing cline-hooks as uv tool..."
uv tool install --editable "$ScriptDir" --force

Write-Host "Linking hooks to $TargetDir..."
cline-hook install "$TargetDir"
