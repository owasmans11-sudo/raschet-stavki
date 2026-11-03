# Полные адреса для грузов из УЛ, которым не хватило сводной таблицы (adresa_iz_zayavok.py), —
# из «Картотеки документов» (заявки с клиентами из почты и папок): пара по заказчику, ставке и дате,
# адреса — разбором самого файла заявки (zayavka.parse). Собрано 2026-11-02.
# Запуск: python app-sklad/adresa_iz_kartoteki.py ["<Картотека документов.xlsx>"]
import datetime as D
import difflib
import os
import sys
from pathlib import Path

from openpyxl import load_workbook

sys.path.insert(0, str(Path(__file__).resolve().parent))
import server  # noqa: E402
import firma as F  # noqa: E402
import zayavka as Z  # noqa: E402
from adresa_iz_zayavok import norm, data, pohozh_adres, gorod_v, SKLAD_MO  # noqa: E402

SRC = sys.argv[1] if len(sys.argv) > 1 else r'C:\РАБОТА\Картотека документов.xlsx'


def main():
    kart = [r for r in load_workbook(SRC, read_only=True)['Все документы'].iter_rows(min_row=2, values_only=True)
            if r[1] == 'Заявка с клиентом' and r[4] and r[12]]
    con = server.connect()
    gruzy = con.execute("SELECT id, client, rate_client, created, from_addr, to_addr FROM gruz "
                        "WHERE note LIKE '%[УЛ %' AND note NOT LIKE '%[адрес из заявки%'").fetchall()
    n_para = n_from = n_to = 0
    for g in gruzy:
        gn, gd = norm(g['client']), D.date.fromisoformat(g['created']) if g['created'] else None
        best, bs = None, 0
        for r in kart:
            s = difflib.SequenceMatcher(None, gn, norm(r[4])).ratio()
            if s < 0.7:
                continue
            if g['rate_client'] and isinstance(r[7], (int, float)) and abs(r[7] - g['rate_client']) < 1:
                s += 1
            rd = data(r[5]) or data(r[3])
            if gd and rd and abs((rd - gd).days) <= 7:
                s += 0.5
            if s > bs:
                best, bs = r, s
        if not best or bs < 1.5:
            continue
        path = os.path.join(str(best[13] or ''), str(best[12]))
        if not os.path.exists(path):
            continue
        n_para += 1
        (_, text, _), = F.read_all([(best[12], open(path, 'rb').read())])
        if not text:
            continue
        f, _ = Z.parse(text)
        new_from, new_to = g['from_addr'], g['to_addr']
        a = pohozh_adres(f.get('from_addr'))
        if a and gorod_v(a, g['from_addr']):
            new_from, n_from = a, n_from + 1
        b = pohozh_adres(f.get('to_addr'))
        if b and (gorod_v(b, g['to_addr']) or (g['to_addr'] or '').lower() in SKLAD_MO):
            new_to, n_to = b, n_to + 1
        if (new_from, new_to) != (g['from_addr'], g['to_addr']):
            con.execute('UPDATE gruz SET from_addr=?, to_addr=?, note=note||? WHERE id=?',
                        (new_from, new_to, f" [адрес из заявки {best[2] or 'б/н'} от {best[3] or '?'}, файл {best[12]}, "
                                           f"было: {g['from_addr']} → {g['to_addr']}]", g['id']))
    con.commit()
    print(f'Пара с картотекой: {n_para} из {len(gruzy)}; адрес погрузки уточнён {n_from}, выгрузки {n_to}.')


if __name__ == '__main__':
    main()
