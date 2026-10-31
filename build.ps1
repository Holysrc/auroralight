# Builds app\AuroraLight\AuroraLight.exe, so that Windows lists it under its own name and icon rather than as Python.
#
#   powershell -ExecutionPolicy Bypass -File build.ps1
#
# Stop a running AuroraLight first. The first run downloads PyInstaller into .venv-build.
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if (-not (Test-Path .venv-build)) {
    python -m venv .venv-build
    & .venv-build\Scripts\python.exe -m pip install --quiet pyinstaller
}
$version = @'
VSVersionInfo(
  ffi=FixedFileInfo(filevers=(0,1,1,0), prodvers=(0,1,1,0), mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0,0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('FileDescription', 'AuroraLight'),
      StringStruct('FileVersion', '0.1.1'),
      StringStruct('ProductName', 'AuroraLight'),
      StringStruct('ProductVersion', '0.1.1'),
      StringStruct('OriginalFilename', 'AuroraLight.exe')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
'@
New-Item -ItemType Directory -Force build | Out-Null
Set-Content -Path build\version.txt -Value $version -Encoding Ascii
& .venv-build\Scripts\python.exe -m PyInstaller --noconfirm --clean --windowed --onedir --name AuroraLight `
    --icon "$PSScriptRoot\auroralight.ico" --version-file "$PSScriptRoot\build\version.txt" `
    --distpath "$PSScriptRoot\app" --workpath "$PSScriptRoot\build" --specpath "$PSScriptRoot\build" `
    --paths "$PSScriptRoot" --hidden-import fx_ui "$PSScriptRoot\fx_watch.pyw"
if ($LASTEXITCODE -ne 0) { throw 'build failed' }
Write-Host 'Built app\AuroraLight\AuroraLight.exe'
