$ErrorActionPreference = "Stop"
$RunRoot = $PSScriptRoot
$Action = if ($args.Count -gt 0) { $args[0] } else { "help" }
$Allowed = @("validate", "start", "status", "pause", "resume", "migrate-artifacts", "refresh-artifacts", "adopt-runtime-transition", "analyze", "prepare-promotion")

if ($Action -in @("help", "-h", "--help")) {
    Write-Output "Usage: .\run.ps1 <validate|start|status|pause|resume|migrate-artifacts|refresh-artifacts|adopt-runtime-transition|analyze|prepare-promotion> [options]"
    exit 0
}
if ($Action -notin $Allowed) {
    Write-Error "Unknown action: $Action"
    exit 2
}

$Remaining = if ($args.Count -gt 1) { $args[1..($args.Count - 1)] } else { @() }
$RepositoryRoot = (& git -C $RunRoot rev-parse --show-toplevel 2>$null)
$PythonExecutable = $null
$EnvironmentRoots = @()
if ($env:VIRTUAL_ENV) {
    $EnvironmentRoots += $env:VIRTUAL_ENV
}
if ($RepositoryRoot) {
    $EnvironmentRoots += (Join-Path $RepositoryRoot ".venv")
}
foreach ($EnvironmentRoot in $EnvironmentRoots) {
    foreach ($RelativePython in @("Scripts\python.exe", "bin/python")) {
        $Candidate = Join-Path $EnvironmentRoot $RelativePython
        if (Test-Path $Candidate) {
            $PythonExecutable = $Candidate
            break
        }
    }
    if ($PythonExecutable) { break }
}
if (-not $PythonExecutable) {
    $PythonExecutable = "python"
}

& $PythonExecutable -m dmw_experiments `
    --storage $RunRoot `
    --skip-dotenv-layers `
    $Action --run-dir $RunRoot @Remaining
exit $LASTEXITCODE
