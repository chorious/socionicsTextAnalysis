param(
    [int]$Port = 8787
)

$ErrorActionPreference = "Stop"
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
chcp 65001 | Out-Null

Set-Location -LiteralPath $PSScriptRoot
python -m uvicorn kernel1.app:app --host 127.0.0.1 --port $Port
