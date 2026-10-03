# Builds build\dist\ChessVision\ChessVision.exe and build\installer\ChessVision-Setup-<version>.exe
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
Push-Location $root
try {
    python installer\make_icon.py
    $ico = Join-Path $root "chess_vision.ico"
    python -m PyInstaller --noconfirm --clean --windowed --onedir --name ChessVision `
        --icon $ico --add-data "$ico;." `
        --distpath build\dist --workpath build\work --specpath build chess_vision.py
    if ($LASTEXITCODE) { throw "PyInstaller failed" }

    $iscc = @("${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe", "$env:ProgramFiles\Inno Setup 6\ISCC.exe") |
        Where-Object { Test-Path $_ } | Select-Object -First 1
    if (-not $iscc) { throw "Inno Setup 6 not found - install it from https://jrsoftware.org/isdl.php" }
    & $iscc /Q installer\ChessVision.iss
    if ($LASTEXITCODE) { throw "Inno Setup failed" }
    Get-ChildItem build\installer\*.exe | Select-Object Name, @{n = "MB"; e = { [math]::Round($_.Length / 1MB, 1) } }
}
finally { Pop-Location }
