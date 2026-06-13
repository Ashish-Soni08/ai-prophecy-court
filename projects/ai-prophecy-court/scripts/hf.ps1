$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$env:UV_CACHE_DIR = Join-Path $root ".uv-cache"
$env:UV_PYTHON_INSTALL_DIR = Join-Path $root ".uv-python"
$env:UV_TOOL_DIR = Join-Path $root ".uv-tools"
$env:UV_TOOL_BIN_DIR = Join-Path $root ".uv-tools\bin"
$python = Join-Path $root ".uv-python\cpython-3.11.12-windows-x86_64-none\python.exe"

& uv tool run --python $python hf @args
exit $LASTEXITCODE
