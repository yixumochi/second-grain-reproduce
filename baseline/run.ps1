param([switch]$Test, [switch]$Changes)
$ErrorActionPreference = 'Stop'
[string[]]$taskArgs = if ($Test) {
    @('-m', 'unittest', 'discover', '-s', (Join-Path $PSScriptRoot 'tests'), '-v')
} elseif ($Changes) {
    @((Join-Path $PSScriptRoot 'run_changes.py'))
} else {
    @((Join-Path $PSScriptRoot 'run.py'))
}
uv run --no-project --python 3.12 python @taskArgs
exit $LASTEXITCODE
