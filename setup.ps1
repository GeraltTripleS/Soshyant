# Soshyant — quick-start setup (Windows)
# Usage:
#   powershell -ExecutionPolicy Bypass -File setup.ps1                  # default: Bonsai-2-27B
#   powershell -ExecutionPolicy Bypass -File setup.ps1 -Models bonsai,huihui4b
# Optional models: bonsai (default), huihui4b, ornith, gemma4
param(
    [string]$Models = "bonsai",
    [string]$Python = "3.11"
)
$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot

function Info($m)  { Write-Host "==> $m" -ForegroundColor Cyan }
function Ok($m)    { Write-Host "    [OK] $m" -ForegroundColor Green }
function Warn($m)  { Write-Host "    [!] $m" -ForegroundColor Yellow }

# ---------- 1. Python venv + dependencies ----------
Info "Setting up Python $Python environment (.venv)"
if (-not (Test-Path "$Root\.venv\Scripts\python.exe")) {
    try { py "-$Python" -m venv "$Root\.venv" }
    catch { python -m venv "$Root\.venv" }
    if (-not (Test-Path "$Root\.venv\Scripts\python.exe")) {
        Write-Host "ERROR: could not create a Python $Python venv. Install Python $Python from python.org" -ForegroundColor Red
        exit 1
    }
}
$Py = "$Root\.venv\Scripts\python.exe"
& $Py -m pip install --disable-pip-version-check --quiet --upgrade pip
Info "Installing Python dependencies"
& $Py -m pip install --disable-pip-version-check --quiet -r "$Root\requirements.txt"
Ok "dependencies installed"

# ---------- download helpers ----------
# Hugging Face files via huggingface_hub (resumable, no auth needed for these repos)
function Get-HFFile($repo, $file, $dest) {
    $destPath = Join-Path $Root $dest
    if (Test-Path $destPath) { Ok "already present: $dest"; return }
    New-Item -ItemType Directory -Force -Path (Split-Path $destPath) | Out-Null
    Info "downloading $repo/$file"
    & $Py -c "from huggingface_hub import hf_hub_download; hf_hub_download('$repo', '$file', local_dir=r'$Root', local_dir_use_symlinks=False)" | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "download failed: $repo/$file" }
    # hf_hub_download keeps the repo subpath; move into place if needed
    $dl = Join-Path $Root $file
    if ((Split-Path $dl) -ne (Split-Path $destPath)) {
        Move-Item $dl $destPath -Force
    } elseif ($dl -ne $destPath) {
        Move-Item $dl $destPath -Force
    }
    Ok "downloaded: $dest"
}

# GitHub release assets via curl.exe (ships with Windows; -C - resumes)
function Get-URL($url, $dest) {
    $destPath = Join-Path $Root $dest
    if (Test-Path $destPath) { Ok "already present: $dest"; return }
    New-Item -ItemType Directory -Force -Path (Split-Path $destPath) | Out-Null
    Info "downloading $url"
    curl.exe -L --fail --retry 3 -C - -o "$destPath.downloading" $url
    if ($LASTEXITCODE -ne 0) { throw "download failed: $url" }
    Move-Item "$destPath.downloading" $destPath -Force
    Ok "downloaded: $dest"
}

# ---------- 2. llama.cpp runtime (Prism build, CUDA) ----------
Info "Fetching llama.cpp runtime (Prism build, CUDA)"
$Tag = "prism-b10709-9a9394a"
$Base = "https://github.com/PrismML-Eng/llama.cpp/releases/download/$Tag"
if (-not (Test-Path "$Root\bin\cuda\llama-server.exe")) {
    Get-URL "$Base/llama-$Tag-bin-win-cuda-13.3-x64.zip" "dl\runtime.zip"
    Get-URL "$Base/cudart-llama-bin-win-cuda-13.3-x64.zip" "dl\cudart.zip"
    Info "extracting runtime"
    Expand-Archive -Path "$Root\dl\runtime.zip" -DestinationPath "$Root\bin\cuda" -Force
    Expand-Archive -Path "$Root\dl\cudart.zip" -DestinationPath "$Root\bin\cuda" -Force
    Remove-Item "$Root\dl" -Recurse -Force
}
Ok "llama-server ready"

# ---------- 3. TTS + STT models ----------
Info "Fetching Kokoro TTS (English, CPU)"
Get-URL "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1/kokoro-v1.0.onnx" "tts\kokoro-fp32.onnx"
Get-URL "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1/voices-v1.0.bin" "tts\voices-v1.0.bin"

Info "Fetching Whisper speech-to-text (English)"
if (-not (Test-Path "$Root\tts\whisper-base-en\model.bin")) {
    & $Py -c "from huggingface_hub import snapshot_download; snapshot_download('Systran/faster-whisper-base.en', local_dir=r'$Root\tts\whisper-base-en')" | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "whisper download failed" }
}
Ok "whisper ready"

# ---------- 4. LLM model(s) ----------
$ModelList = $Models -split "," | ForEach-Object { $_.Trim().ToLowerInvariant() }
foreach ($m in $ModelList) {
    switch ($m) {
        "bonsai" {
            Info "Fetching LLM: Bonsai-2-27B (5.6 GB — this is the default model)"
            Get-HFFile "BoldingBuilds/Ternary-Bonsai-2-27B-Abliterated-PTQ1_0-GGUF" "Ternary-Bonsai-2-27B-Abliterated-PTQ1_0.gguf" "models\Ternary-Bonsai-2-27B-Abliterated-PTQ1_0.gguf"
        }
        "huihui4b" {
            Info "Fetching LLM: Huihui-4B light (2.5 GB)"
            Get-HFFile "mradermacher/Huihui-Qwen3.5-4B-abliterated-GGUF" "Huihui-Qwen3.5-4B-abliterated.Q4_K_M.gguf" "models\Huihui-Qwen3.5-4B-abliterated.Q4_K_M.gguf"
        }
        "ornith" {
            Info "Fetching LLM: Ornith-1.5-9B with vision (5.4 GB)"
            Get-HFFile "ornith-ai/Ornith-1.5-9B-GGUF" "Ornith-1.5-9B-Q4_K_M.gguf" "models\Ornith-1.5-9B-Q4_K_M.gguf"
            Get-HFFile "ornith-ai/Ornith-1.5-9B-GGUF" "mmproj-Ornith-1.5-9B-BF16.gguf" "models\mmproj-Ornith-1.5-9B-BF16.gguf"
        }
        "gemma4" {
            Info "Fetching LLM: Gemma4-26B MoE with vision (15.6 GB)"
            Get-HFFile "HauhauCS/Gemma4-26B-A4B-Uncensored-HauhauCS-Balanced" "Gemma4-26B-A4B-Uncensored-HauhauCS-Balanced-Q4_K_M.gguf" "models\Gemma4-26B-A4B-Uncensored-HauhauCS-Balanced-Q4_K_M.gguf"
            Get-HFFile "HauhauCS/Gemma4-26B-A4B-Uncensored-HauhauCS-Balanced" "mmproj-Gemma4-26B-A4B-Uncensored-HauhauCS-Balanced-f16.gguf" "models\mmproj-Gemma4-26B-A4B-Uncensored-HauhauCS-Balanced-f16.gguf"
        }
        default { Warn "unknown model '$m' (supported: bonsai, huihui4b, ornith, gemma4)" }
    }
}

Write-Host ""
Write-Host "=============================" -ForegroundColor Green
Write-Host " Setup complete!" -ForegroundColor Green
Write-Host " Start the app:  start-soshyant.bat" -ForegroundColor Green
Write-Host " Then open:      http://127.0.0.1:8091" -ForegroundColor Green
Write-Host "=============================" -ForegroundColor Green
Write-Host ""
Write-Host " More models later:  powershell -File setup.ps1 -Models huihui4b,ornith,gemma4"
Write-Host " (each model ~2.5-16 GB; only one fits in an 8 GB GPU at a time —"
Write-Host "  the app switches them automatically)"
