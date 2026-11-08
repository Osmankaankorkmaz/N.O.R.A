# Nora Windows setup. Run from any directory; no admin rights or model downloads.
# Example: powershell -ExecutionPolicy Bypass -File .\tools\setup_windows.ps1 -Feature piper
[CmdletBinding()]
param(
    [ValidateSet("base", "local", "embeddings", "chat", "piper", "all")]
    [string]$Feature = "base"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
Push-Location $Root
try {
    if (-not (Test-Path -LiteralPath $VenvPython)) {
        Write-Host "Python 3.10-3.12 sanal ortami olusturuluyor..."
        if (Get-Command py -ErrorAction SilentlyContinue) {
            & py -3 -m venv .venv
        }
        elseif (Get-Command python -ErrorAction SilentlyContinue) {
            & python -m venv .venv
        }
        else {
            throw "Python bulunamadi. python.org'dan Python 3.11 kurup tekrar deneyin."
        }
        if ($LASTEXITCODE -ne 0) { throw "Sanal ortam olusturulamadi." }
    }

    & $VenvPython -c "import sys; raise SystemExit(0 if (3, 10) <= sys.version_info[:2] <= (3, 12) else 1)"
    if ($LASTEXITCODE -ne 0) {
        throw "Bu kurulum Python 3.10-3.12 ister. Mevcut .venv silinmeden yeni bir Python 3.11 ile yeniden olusturun."
    }

    & $VenvPython -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) { throw "pip guncellenemedi. Internet/proxy ayarini kontrol edin." }

    $Requirements = switch ($Feature) {
        "base" { "requirements.txt" }
        "local" { "requirements-local.txt" }
        "embeddings" { "requirements-embeddings.txt" }
        "chat" { "requirements-chat.txt" }
        "piper" { "requirements-piper.txt" }
        "all" { "requirements-ai.txt" }
    }
    Write-Host "Kuruluyor: $Requirements (model dosyalari indirilmez)"
    & $VenvPython -m pip install -r $Requirements
    if ($LASTEXITCODE -ne 0) {
        throw "Paket kurulumu basarisiz. Hata satirini kontrol edin; diger ozellikleri ayri requirements dosyalariyla kurabilirsiniz."
    }

    $DoctorArgs = @("main.py", "--doctor")
    if ($Feature -eq "all") {
        $DoctorArgs += @("--check", "local", "--check", "embeddings", "--check", "chat", "--check", "piper")
    }
    elseif ($Feature -ne "base") {
        $DoctorArgs += @("--check", $Feature)
    }
    & $VenvPython @DoctorArgs
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    Write-Host ""
    Write-Host "Kurulum tamamlandi. Baslatmak icin: .venv\Scripts\python.exe main.py"
    Write-Host "Model/Spotify adimlari README.md'de; hicbir model veya hesap izni otomatik verilmedi."
}
finally {
    Pop-Location
}
