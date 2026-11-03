"""Ночное обновление поиска файлов и картотеки — без окон, низкий приоритет, 2 процесса (ноутбук не перегревается).

Запускает планировщик Windows (задача «ВЛ — обновление поиска и картотеки», каждую ночь в 03:00; если ноутбук был
выключен или спал — при следующем включении; от батареи не стартует). То же самое, что «Распознать сканы.bat»:
старые Excel → сканы PDF → фото → словарь исправлений → картотека. Готовое не пересчитывает — только новые файлы.
Журнал: %USERPROFILE%\\vl_find_files\\nightly_log.txt
"""
import os, subprocess, sys, time

TOOLS = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.join(os.path.expanduser('~'), 'vl_find_files')  # как в find_files.py
LOG = os.path.join(BASE, 'nightly_log.txt')
LOCK = os.path.join(BASE, 'nightly.lock')
PYTHON = os.path.join(os.path.dirname(sys.executable), 'python.exe')  # консольный — окно скрыто флагом ниже
STEPS = [('старые Excel', ['read_xls.py']), ('сканы PDF', ['ocr_scans.py', '--workers', '2']),
         ('фото', ['ocr_photos.py', '--workers', '2']), ('словарь исправлений', ['build_fixes.py']),
         ('картотека', ['build_kartoteka.py']),
         ('резервная копия склада', [os.path.join('..', 'app-sklad', 'backup.py')])]  # база и документы приложения «Склад»
FLAGS = subprocess.CREATE_NO_WINDOW | subprocess.BELOW_NORMAL_PRIORITY_CLASS  # дочерние процессы наследуют


def log(msg):
    os.makedirs(BASE, exist_ok=True)
    lines = []
    if os.path.exists(LOG):
        with open(LOG, encoding='utf-8', errors='ignore') as f:
            lines = f.read().splitlines()[-400:]
    lines.append(time.strftime('%d.%m.%Y %H:%M  ') + msg)
    with open(LOG, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')


def main():
    if os.path.exists(LOCK) and time.time() - os.path.getmtime(LOCK) < 12 * 3600:
        log('пропуск: обновление уже идёт')
        return
    open(LOCK, 'w').close()
    try:
        log('старт')
        env = dict(os.environ, PYTHONIOENCODING='utf-8')
        for title, args in STEPS:
            t = time.time()
            r = subprocess.run([PYTHON, os.path.join(TOOLS, args[0])] + args[1:], cwd=os.path.dirname(TOOLS), env=env,
                               creationflags=FLAGS, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                               encoding='utf-8', errors='ignore')
            tail = (r.stdout.strip().splitlines() or [''])[-1][:200]
            log(f'{title}: {"готово" if r.returncode == 0 else "ОШИБКА " + str(r.returncode)} за {round((time.time() - t) / 60, 1)} мин. {tail}')
        log('конец')
    finally:
        os.remove(LOCK)


if __name__ == '__main__':
    main()
