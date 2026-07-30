[CmdletBinding()]
param(
    [string]$CodexHome,
    [switch]$Force
)

$ErrorActionPreference = 'Stop'

if ([string]::IsNullOrWhiteSpace($CodexHome)) {
    if (-not [string]::IsNullOrWhiteSpace($env:CODEX_HOME)) {
        $CodexHome = $env:CODEX_HOME
    } else {
        $CodexHome = Join-Path $env:USERPROFILE '.codex'
    }
}

$packageRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$sourceSkill = Join-Path $packageRoot 'rebuild-editable-ui-psd'
$skillsRoot = Join-Path $CodexHome 'skills'
$targetSkill = Join-Path $skillsRoot 'rebuild-editable-ui-psd'

if (-not (Test-Path -LiteralPath (Join-Path $sourceSkill 'SKILL.md') -PathType Leaf)) {
    throw "Invalid release package: rebuild-editable-ui-psd\SKILL.md is missing."
}

New-Item -ItemType Directory -Force -Path $skillsRoot | Out-Null

if (Test-Path -LiteralPath $targetSkill) {
    if (-not $Force) {
        throw "The skill is already installed at $targetSkill. Re-run with -Force to back it up and install this release."
    }
    $backupRoot = Join-Path $CodexHome 'skill-backups'
    New-Item -ItemType Directory -Force -Path $backupRoot | Out-Null
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $backupSkill = Join-Path $backupRoot "rebuild-editable-ui-psd-$stamp"
    Move-Item -LiteralPath $targetSkill -Destination $backupSkill
    Write-Host "Backed up the previous skill to $backupSkill"
}

Copy-Item -LiteralPath $sourceSkill -Destination $targetSkill -Recurse

function Test-CompatiblePython {
    param([string]$Executable)
    if ([string]::IsNullOrWhiteSpace($Executable) -or -not (Test-Path -LiteralPath $Executable -PathType Leaf)) {
        return $false
    }
    & $Executable -c "import sys; raise SystemExit(not ((3, 11) <= sys.version_info[:2] < (3, 14)))" 2>$null
    return $LASTEXITCODE -eq 0
}

$pythonCandidates = [System.Collections.Generic.List[string]]::new()
$bundledPython = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
$pythonCandidates.Add($bundledPython)

$pythonCommand = Get-Command python -ErrorAction SilentlyContinue
if ($pythonCommand) {
    $pythonCandidates.Add($pythonCommand.Source)
}

$pyLauncher = Get-Command py -ErrorAction SilentlyContinue
if ($pyLauncher) {
    $availablePythons = & $pyLauncher.Source -0p 2>$null
    if ($LASTEXITCODE -eq 0) {
        foreach ($line in $availablePythons) {
            if ($line -match '([A-Za-z]:\\.*python\.exe)\s*$') {
                $pythonCandidates.Add($Matches[1].Trim())
            }
        }
    }
}

$selectedPython = $null
foreach ($candidate in $pythonCandidates | Select-Object -Unique) {
    if (Test-CompatiblePython -Executable $candidate) {
        $selectedPython = $candidate
        break
    }
}

if (-not $selectedPython) {
    throw 'The skill was copied, but rembg installation requires Python 3.11, 3.12, or 3.13.'
}

$rembgInstaller = Join-Path $targetSkill 'scripts\install_rembg.py'
& $selectedPython $rembgInstaller --ensure
if ($LASTEXITCODE -ne 0) {
    throw 'The skill was copied, but its managed rembg installation failed. Review the error above and re-run this installer.'
}

$metadata = Get-Content -LiteralPath (Join-Path $targetSkill 'skill-metadata.json') -Raw | ConvertFrom-Json
Write-Host "Installed rebuild-editable-ui-psd $($metadata.version) at $targetSkill"
Write-Host 'rembg is installed in the skill-managed runtime.'
