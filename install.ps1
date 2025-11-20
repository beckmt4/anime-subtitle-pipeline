# ============================================================================
# Anime Subtitle Pipeline - Installation Script for Windows
# ============================================================================
# This script automates the installation process.
# Run with: .\install.ps1
# ============================================================================

Write-Host "============================================================================"
Write-Host "Anime Subtitle Pipeline - Installation"
Write-Host "============================================================================`n"

# Check Python version
Write-Host "Checking Python version..."
$pythonVersion = python --version 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Python not found. Please install Python 3.9+ from python.org" -ForegroundColor Red
    exit 1
}
Write-Host "✓ $pythonVersion" -ForegroundColor Green

# Check ffmpeg
Write-Host "`nChecking ffmpeg..."
$ffmpegVersion = ffmpeg -version 2>&1 | Select-String "ffmpeg version" | Select-Object -First 1
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ ffmpeg not found" -ForegroundColor Red
    Write-Host "Please install ffmpeg:" -ForegroundColor Yellow
    Write-Host "  1. Download from: https://ffmpeg.org/download.html" -ForegroundColor Yellow
    Write-Host "  2. Extract and add to PATH" -ForegroundColor Yellow
    Write-Host "  3. Or install via Chocolatey: choco install ffmpeg" -ForegroundColor Yellow
    exit 1
}
Write-Host "✓ ffmpeg installed" -ForegroundColor Green

# Create virtual environment
Write-Host "`nCreating virtual environment..."
if (Test-Path "venv") {
    Write-Host "⊘ Virtual environment already exists" -ForegroundColor Yellow
} else {
    python -m venv venv
    if ($LASTEXITCODE -ne 0) {
        Write-Host "❌ Failed to create virtual environment" -ForegroundColor Red
        exit 1
    }
    Write-Host "✓ Virtual environment created" -ForegroundColor Green
}

# Activate virtual environment
Write-Host "`nActivating virtual environment..."
& .\venv\Scripts\Activate.ps1

# Check for CUDA
Write-Host "`nChecking for CUDA support..."
$cudaCheck = python -c "import torch; print(torch.cuda.is_available())" 2>&1
if ($cudaCheck -eq "True") {
    Write-Host "✓ CUDA available" -ForegroundColor Green
    $useCUDA = Read-Host "`nInstall PyTorch with CUDA support? (y/n)"
    if ($useCUDA -eq "y") {
        Write-Host "`nSelect CUDA version:"
        Write-Host "  1. CUDA 11.8 (recommended for most systems)"
        Write-Host "  2. CUDA 12.1 (for newer GPUs)"
        $cudaVersion = Read-Host "Enter choice (1 or 2)"
        
        if ($cudaVersion -eq "1") {
            Write-Host "`nInstalling PyTorch with CUDA 11.8..."
            pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
        } elseif ($cudaVersion -eq "2") {
            Write-Host "`nInstalling PyTorch with CUDA 12.1..."
            pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
        } else {
            Write-Host "Invalid choice, installing CPU version" -ForegroundColor Yellow
            pip install torch torchvision torchaudio
        }
    } else {
        Write-Host "Installing CPU version of PyTorch..." -ForegroundColor Yellow
        pip install torch torchvision torchaudio
    }
} else {
    Write-Host "⊘ CUDA not available, installing CPU version" -ForegroundColor Yellow
    pip install torch torchvision torchaudio
}

if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Failed to install PyTorch" -ForegroundColor Red
    exit 1
}

# Install other dependencies
Write-Host "`nInstalling other dependencies..."
pip install -r requirements.txt

if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Failed to install dependencies" -ForegroundColor Red
    exit 1
}
Write-Host "✓ Dependencies installed" -ForegroundColor Green

# Create directories
Write-Host "`nCreating directories..."
$dirs = @("inbox", "outbox", "logs", "temp")
foreach ($dir in $dirs) {
    if (!(Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir | Out-Null
        Write-Host "✓ Created $dir/" -ForegroundColor Green
    } else {
        Write-Host "⊘ $dir/ already exists" -ForegroundColor Yellow
    }
}

# Check Ollama (optional)
Write-Host "`nChecking for Ollama (optional for LLM polishing)..."
try {
    $ollamaCheck = Invoke-WebRequest -Uri "http://localhost:11434/api/tags" -TimeoutSec 2 -ErrorAction Stop
    Write-Host "✓ Ollama is running" -ForegroundColor Green
} catch {
    Write-Host "⊘ Ollama not running or not installed" -ForegroundColor Yellow
    Write-Host "  To use LLM polishing:" -ForegroundColor Yellow
    Write-Host "    1. Download from: https://ollama.ai/" -ForegroundColor Yellow
    Write-Host "    2. Run: ollama pull qwen2.5:7b" -ForegroundColor Yellow
    Write-Host "    3. Run: ollama serve" -ForegroundColor Yellow
    Write-Host "  Or set llm.enabled: false in config.yaml" -ForegroundColor Yellow
}

# Run tests
Write-Host "`n============================================================================"
$runTests = Read-Host "Run system tests? (y/n)"
if ($runTests -eq "y") {
    Write-Host "`nRunning tests..."
    python test_pipeline.py
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "`n✓ All tests passed!" -ForegroundColor Green
    } else {
        Write-Host "`n⚠ Some tests failed. Please check the output above." -ForegroundColor Yellow
    }
}

# Summary
Write-Host "`n============================================================================"
Write-Host "Installation Complete!" -ForegroundColor Green
Write-Host "============================================================================"
Write-Host "`nNext steps:"
Write-Host "  1. Review config.yaml and adjust settings for your hardware"
Write-Host "  2. If using LLM polishing, make sure Ollama is running"
Write-Host "  3. Place a test video in the current directory"
Write-Host "  4. Run: python main.py test_video.mkv"
Write-Host "`nFor more information:"
Write-Host "  - Quick Start: QUICKSTART.md"
Write-Host "  - Documentation: README.md"
Write-Host "  - Project Summary: PROJECT_SUMMARY.md"
Write-Host "`nTo activate the environment in future sessions:"
Write-Host "  .\venv\Scripts\Activate.ps1"
Write-Host "============================================================================`n"
