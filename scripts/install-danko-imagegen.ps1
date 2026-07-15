$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$pythonCommand = $null
$pythonPrefix = @()
$candidates = @(
    [pscustomobject]@{ Command = "py"; Prefix = @("-3") },
    [pscustomobject]@{ Command = "python"; Prefix = @() },
    [pscustomobject]@{ Command = "python3"; Prefix = @() }
)

foreach ($candidate in $candidates) {
    $resolved = Get-Command $candidate.Command -ErrorAction SilentlyContinue
    if ($null -eq $resolved) {
        continue
    }

    & $candidate.Command @($candidate.Prefix + @("-c", "import sys; raise SystemExit(sys.version_info < (3, 10))"))
    if ($LASTEXITCODE -eq 0) {
        $pythonCommand = $candidate.Command
        $pythonPrefix = $candidate.Prefix
        break
    }
}

if ($null -eq $pythonCommand) {
    throw "Python 3.10+ is required. Install Python, then rerun this installer."
}

$venvDir = Join-Path $repoRoot ".venv"
& $pythonCommand @($pythonPrefix + @("-m", "venv", $venvDir))
$venvPython = Join-Path $venvDir "Scripts\python.exe"
& $venvPython -m pip install -r (Join-Path $repoRoot "requirements.txt")

$codexHome = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $HOME ".codex" }
& $venvPython (Join-Path $repoRoot "scripts\write_mcp_config.py") `
    --config (Join-Path $codexHome "config.toml") `
    --python $venvPython `
    --server (Join-Path $repoRoot "skills\third-party-imagegen\mcp_server\danko_imagegen_server.py") `
    --cwd $repoRoot

Write-Output "Danko ImageGen MCP installed. Restart Codex to load the updated configuration."
