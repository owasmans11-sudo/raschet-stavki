@echo off
rem Окно настройки вечернего скачивания почты: ящики, пароли приложений, «Скачать сейчас»
start "" pythonw "%~dp0mail-downloader\nightly_settings.py"
