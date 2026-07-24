# LangGraph Evaluation Harness - One-Line Installer for Windows
# Usage: irm https://raw.githubusercontent.com/tyraakj/eval-harness-pipeline/main/install.ps1 | iex

param(
    [string]$InstallPath = "$env:USERPROFILE\personal-evaluation-harness"
)

Write-Host "🚀 Installing LangGraph Evaluation Harness..." -ForegroundColor Cyan

# Check if uv is installed
$uvInstalled = Get-Command uv -ErrorAction SilentlyContinue
if (-not $uvInstalled) {
    Write-Host "📦 Installing uv (Python package manager)..." -ForegroundColor Yellow
    irm https://astral.sh/uv/install.ps1 | iex
    $env:PATH += ";$env:USERPROFILE\.local\bin"
    [Environment]::SetEnvironmentVariable("Path", $env:PATH, [EnvironmentVariableTarget]::User)
}

# Clone or update the repository
if (Test-Path $InstallPath) {
    Write-Host "📁 Updating existing installation..." -ForegroundColor Yellow
    Set-Location $InstallPath
    git pull
} else {
    Write-Host "📁 Cloning repository to $InstallPath..." -ForegroundColor Yellow
    git clone https://github.com/tyraakj/eval-harness-pipeline.git $InstallPath
    Set-Location $InstallPath
}

# Install dependencies
Write-Host "🔧 Installing dependencies..." -ForegroundColor Yellow
uv sync --all-extras
uv lock

Write-Host "✅ Installation complete!" -ForegroundColor Green
Write-Host "🎯 You can now run the evaluation with:" -ForegroundColor Cyan
Write-Host "   cd $InstallPath" -ForegroundColor White
Write-Host "   uv run lg-eval run --factory examples.simple_graph:create_evaluation --dataset datasets/example.jsonl --output artifacts/example.jsonl --minimum-pass-rate 1.0" -ForegroundColor White
