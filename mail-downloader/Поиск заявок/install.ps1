# Установка «Поиска заявок» на новый компьютер. Запускается из Установить.bat.
$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = 'Tls12'
$app = Split-Path -Parent $MyInvocation.MyCommand.Path

function Find-Python {
    $cands = @(
        "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
        "C:\Program Files\Python312\python.exe",
        "C:\Program Files\Python313\python.exe"
    )
    foreach ($c in $cands) { if (Test-Path $c) { return $c } }
    $cmd = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($cmd -and $cmd.Source -notlike '*WindowsApps*') { return $cmd.Source }
    return $null
}

Write-Host "1/5 Python..." -ForegroundColor Cyan
$py = Find-Python
if (-not $py) {
    winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements --silent
    $py = Find-Python
    if (-not $py) { throw "Python не установился. Поставьте Python 3.12 с python.org и запустите установку ещё раз." }
}
Write-Host "   $py"

Write-Host "2/5 Библиотеки Python..." -ForegroundColor Cyan
& $py -m pip install --disable-pip-version-check -r "$app\requirements.txt"
if ($LASTEXITCODE -ne 0) { throw "pip install завершился с ошибкой" }

Write-Host "3/5 Tesseract OCR (распознавание сканов)..." -ForegroundColor Cyan
$tess = @("C:\Program Files\Tesseract-OCR\tesseract.exe", "$env:LOCALAPPDATA\Programs\Tesseract-OCR\tesseract.exe") | Where-Object { Test-Path $_ }
if (-not $tess) {
    winget install -e --id UB-Mannheim.TesseractOCR --accept-package-agreements --accept-source-agreements --silent
}
$td = "$env:USERPROFILE\.zayavki\tessdata"
New-Item -ItemType Directory -Force $td | Out-Null
foreach ($l in 'rus', 'eng') {
    if (-not (Test-Path "$td\$l.traineddata")) {
        Invoke-WebRequest "https://github.com/tesseract-ocr/tessdata_fast/raw/main/$l.traineddata" -OutFile "$td\$l.traineddata" -UseBasicParsing
    }
}

Write-Host "4/5 Архиватор для .rar..." -ForegroundColor Cyan
if (-not ((Test-Path "C:\Program Files\7-Zip\7z.exe") -or (Test-Path "C:\Program Files\WinRAR\UnRAR.exe"))) {
    winget install -e --id 7zip.7zip --accept-package-agreements --accept-source-agreements --silent
}

Write-Host "5/5 Ярлык на рабочем столе..." -ForegroundColor Cyan
$pyw = Join-Path (Split-Path $py) 'pythonw.exe'
$desk = [Environment]::GetFolderPath('Desktop')
$lnk = (New-Object -ComObject WScript.Shell).CreateShortcut("$desk\Поиск заявок.lnk")
$lnk.TargetPath = $pyw
$lnk.Arguments = '"' + "$app\app.py" + '"'
$lnk.WorkingDirectory = $app
$lnk.Save()

Write-Host ""
Write-Host "Готово. Запускайте ярлык «Поиск заявок» на рабочем столе." -ForegroundColor Green
