@echo off
chcp 65001 >nul
title Склад ВЛ
cd /d "%~dp0"
python app-sklad\server.py || pause
