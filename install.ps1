# LangGraph Evaluation Harness - One-Line Installer for Windows
# Usage: irm https://raw.githubusercontent.com/tyraakj/eval-harness-pipeline/main/install.ps1 | iex

param(
    [string]$InstallPath = "$env:USERPROFILE\personal-evaluation-harness"
)

Write-Host "Installing Glyph..." -ForegroundColor Cyan

# Check if uv is installed
$uvInstalled = Get-Command uv -ErrorAction SilentlyContinue
if (-not $uvInstalled) {
    Write-Host "Installing uv (Python package manager)..." -ForegroundColor Yellow
    irm https://astral.sh/uv/install.ps1 | iex
    $env:PATH += ";$env:USERPROFILE\.local\bin"
    [Environment]::SetEnvironmentVariable("Path", $env:PATH, [EnvironmentVariableTarget]::User)
}

# Clone or update the repository
if (Test-Path $InstallPath) {
    Write-Host "Updating existing installation..." -ForegroundColor Yellow
    Set-Location $InstallPath
    git pull
} else {
    Write-Host "Cloning repository to $InstallPath..." -ForegroundColor Yellow
    git clone https://github.com/tyraakj/eval-harness-pipeline.git $InstallPath
    Set-Location $InstallPath
}

# Install dependencies
Write-Host "Installing dependencies..." -ForegroundColor Yellow
uv sync --all-extras

# Install the glyph launcher globally. uv manages a small isolated tool
# environment and exposes its executable through the user's tool-bin folder.
$toolBin = uv tool dir --bin
if (($env:Path -split ';') -notcontains $toolBin) {
    $env:Path = "$toolBin;$env:Path"
    $userPath = [Environment]::GetEnvironmentVariable("Path", [EnvironmentVariableTarget]::User)
    if (($userPath -split ';') -notcontains $toolBin) {
        [Environment]::SetEnvironmentVariable(
            "Path",
            "$toolBin;$userPath",
            [EnvironmentVariableTarget]::User
        )
    }
}
uv tool install --editable $InstallPath --force

Write-Host "Installation complete!" -ForegroundColor Green
Write-Host "Open a new terminal, then run:" -ForegroundColor Cyan
Write-Host "   glyph guide" -ForegroundColor White
Write-Host "   glyph run --factory examples.simple_graph:create_evaluation --dataset datasets/example.jsonl --output artifacts/example.jsonl" -ForegroundColor White
