# Резервная копия приложения «Склад»: база (грузы, водители, контрагенты, оплаты) + папка документов.
# Раз в день: при запуске приложения (если сегодняшней копии нет) и ночью из tools/nightly_update.py.
#   C:\РАБОТА\Резервные копии\Склад ВЛ\ГГГГ-ММ-ДД\sklad.db   — копия базы за день, храним 30 последних
#   C:\РАБОТА\Резервные копии\Склад ВЛ\Ежемесячные\ГГГГ-ММ\ — первая копия каждого месяца, хранится бессрочно
#   C:\РАБОТА\Резервные копии\Склад ВЛ\files\               — документы: только добавляются, ничего не удаляется
# Запуск вручную: python app-sklad/backup.py  (--force — сделать ещё раз сегодня)
import shutil
import sqlite3
import sys
from datetime import date, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
DB = HERE / 'sklad.db'
FILES = HERE / 'files'
DEST = Path(r'C:\РАБОТА\Резервные копии\Склад ВЛ')
KEEP_DAYS = 30

README = """Резервные копии приложения «Склад ВЛ» (делаются сами: при запуске приложения и ночью в 03:00).

Вся работа хранится в самой базе приложения бессрочно; здесь — её снимки на случай поломки или ошибочного удаления.
Каждый снимок содержит ВСЕ данные на свой день.

Папки ГГГГ-ММ-ДД — снимок базы за этот день (sklad.db). Хранятся 30 последних.
Папка «Ежемесячные» — снимок на начало каждого месяца (ГГГГ-ММ), хранится бессрочно.
Папка files — документы водителей и контрагентов (оттуда ничего не удаляется).

Как восстановить:
1. Закройте приложение (чёрное окно «Склад ВЛ»).
2. Скопируйте sklad.db из папки нужного дня в папку проекта: РАСЧЕТ СТАВКИ\\app-sklad\\ (заменить).
3. Если пропали документы — скопируйте папку files в РАСЧЕТ СТАВКИ\\app-sklad\\.
4. Запустите приложение ярлыком «Склад ВЛ».
"""


def make_backup(force=False):
    """Сделать копию за сегодня. Возвращает текст для журнала."""
    if not DB.exists():
        return 'копия: базы ещё нет'
    day = DEST / date.today().isoformat()
    if (day / 'sklad.db').exists() and not force:
        return f'копия: за сегодня уже есть ({day})'
    day.mkdir(parents=True, exist_ok=True)
    # копия базы средствами SQLite — целая и согласованная, даже если приложение сейчас работает
    src, dst = sqlite3.connect(DB), sqlite3.connect(day / 'sklad.db.tmp')
    with dst:
        src.backup(dst)
    src.close()
    dst.close()
    (day / 'sklad.db.tmp').replace(day / 'sklad.db')
    # снимок месяца — первая копия в месяце, никогда не удаляется
    month = DEST / 'Ежемесячные' / date.today().strftime('%Y-%m')
    new_month = not (month / 'sklad.db').exists()
    if new_month:
        month.mkdir(parents=True, exist_ok=True)
        shutil.copy2(day / 'sklad.db', month / 'sklad.db')
    # документы: новые и изменённые файлы
    copied = 0
    if FILES.exists():
        for f in FILES.rglob('*'):
            if f.is_file():
                to = DEST / 'files' / f.relative_to(FILES)
                if not to.exists() or to.stat().st_size != f.stat().st_size or to.stat().st_mtime < f.stat().st_mtime:
                    to.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(f, to)
                    copied += 1
    # старые копии базы — оставляем 30 последних дней
    days = sorted(p for p in DEST.iterdir() if p.is_dir() and len(p.name) == 10 and p.name[4] == '-')
    removed = 0
    for old in days[:-KEEP_DAYS]:
        shutil.rmtree(old)
        removed += 1
    (DEST / 'Как восстановить.txt').write_text(README, encoding='utf-8')
    return (f'копия: {day} — база {round((day / "sklad.db").stat().st_size / 1024)} КБ, документов скопировано {copied}'
            + (f', снимок месяца {month.name} сохранён бессрочно' if new_month else '')
            + (f', удалено старых ежедневных копий {removed}' if removed else ''))


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    print(datetime.now().strftime('%H:%M:%S'), make_backup(force='--force' in sys.argv))
