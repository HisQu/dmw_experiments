$ErrorActionPreference = "Stop"
$RunRoot = $PSScriptRoot
$Action = if ($args.Count -gt 0) { $args[0] } else { "help" }
$Allowed = @("validate", "start", "status", "pause", "resume", "analyze", "prepare-promotion")

if ($Action -in @("help", "-h", "--help")) {
    Write-Output "Usage: .\run.ps1 <validate|start|status|pause|resume|analyze|prepare-promotion> [options]"
    exit 0
}
if ($Action -notin $Allowed) {
    Write-Error "Unknown action: $Action"
    exit 2
}

$Remaining = if ($args.Count -gt 1) { $args[1..($args.Count - 1)] } else { @() }
python -m dmw_experiments `
    --storage $RunRoot `
    --skip-dotenv-layers `
    $Action --run-dir $RunRoot @Remaining
exit $LASTEXITCODE
