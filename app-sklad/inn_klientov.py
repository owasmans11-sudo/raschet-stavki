# ИНН заказчиков для грузов без карточки клиента: чтобы платежи из выписки находили груз по ИНН, а не только по названию.
# Источники: «1233.xlsx» и «Клиенты_заявки.xlsx» (ИНН со сканов заявок) + сами платежи выписки (плательщик и его ИНН).
# Груз связывается с карточкой в «Контрагентах» (создаётся, если ИНН ещё нет), только если по названию подходит ровно один ИНН.
# Собрано 2026-11-02. Запуск: python app-sklad/inn_klientov.py
import re
import sys
from datetime import datetime
from pathlib import Path

from openpyxl import load_workbook

sys.path.insert(0, str(Path(__file__).resolve().parent))
import server  # noqa: E402
import vypiska as V  # noqa: E402

TABLES = [(r'C:\РАБОТА\1233.xlsx', 'Заявки ВЛ и УПД', 1, 2),
          (r'C:\РАБОТА\Клиенты_заявки.xlsx', 'Все заявки', 1, 2)]
NASHI = ('3812166710',)  # ООО ВЛ — свой ИНН в заявках не брать


def inn_ok(s):
    s = re.sub(r'\D', '', str(s or ''))
    return s if len(s) in (10, 12) and s not in NASHI else ''


def main():
    con = server.connect()
    pary = []  # (название, ИНН, откуда)
    for path, sheet, cn, ci in TABLES:
        try:
            ws = load_workbook(path, read_only=True)[sheet]
        except (FileNotFoundError, KeyError):
            print('нет таблицы:', path)
            continue
        for r in ws.iter_rows(min_row=2, values_only=True):
            if len(r) > ci and r[cn] and inn_ok(r[ci]):
                pary.append((str(r[cn]), inn_ok(r[ci]), Path(path).name))
    for p in con.execute('SELECT payer, inn FROM platezh WHERE ignored=0'):
        if inn_ok(p['inn']) and len(V.toks(p['payer'])) > 0:
            pary.append((p['payer'], inn_ok(p['inn']), 'выписка'))

    kart = {r['inn']: r['id'] for r in con.execute("SELECT id, inn FROM kontragent WHERE inn!=''")}
    svyazano = sozdano = spor = 0
    for g in con.execute("SELECT id, client FROM gruz WHERE client_id IS NULL AND client!=''").fetchall():
        inns = {inn: src for name, inn, src in pary if V.same_cust(g['client'], name)}
        if len(inns) != 1:
            spor += len(inns) > 1
            continue
        inn, src = next(iter(inns.items()))
        if inn not in kart:
            kart[inn] = con.execute('INSERT INTO kontragent(created, name, inn, note) VALUES (?,?,?,?)',
                                    (datetime.now().isoformat(timespec='seconds'), g['client'], inn,
                                     f'Создано автоматически по ИНН из «{src}» (для разнесения оплат).')).lastrowid
            sozdano += 1
        con.execute('UPDATE gruz SET client_id=? WHERE id=?', (kart[inn], g['id']))
        svyazano += 1
    con.commit()
    print(f'ИНН из таблиц и выписки: {len(pary)}; грузов связано с карточкой {svyazano}, новых карточек {sozdano}, '
          f'несколько ИНН на одно название (не трогал) {spor}.')


if __name__ == '__main__':
    main()
