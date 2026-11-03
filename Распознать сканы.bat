@echo off
chcp 65001 >nul
rem Достаёт текст для поиска файлов: старые Excel (.xls), сканы PDF, нижняя часть фото. Готовое не пересчитывает — только новые файлы.
rem 2 процесса и низкий приоритет — чтобы ноутбук не перегревался (решение владельца 23.10.2026)
title Распознавание сканов и фото
start /belownormal /wait /b python "%~dp0tools\read_xls.py"
start /belownormal /wait /b python "%~dp0tools\ocr_scans.py" --workers 2
start /belownormal /wait /b python "%~dp0tools\ocr_photos.py" --workers 2
start /belownormal /wait /b python "%~dp0tools\build_fixes.py"
start /belownormal /wait /b python "%~dp0tools\build_kartoteka.py"
pause
