# Перевозки, которых нет в «Умной логистике» (в основном до сентября 2026), — из сводной таблицы заявок клиентов
# «Заявки ВЛ и УПД — вариант 7.xlsx» (сканы заявок): лист заявок ООО ВЛ + лист «Не вошли» (ИП Шерстов, ТК МВЛ). Собрано 2026-11-02.
# Пропускаем: повторные версии и дубли (по пометкам таблицы), заявки без суммы и те, что уже есть в приложении —
# тот же заказчик + та же сумма + дата ±10 дней, или заявка уже указана в примечании груза.
# Повтор не задваивает: метка «[В7 строка N]». Запуск: python app-sklad/import_variant7.py ["<вариант 7.xlsx>"]
import datetime as D
import difflib
import sys
from pathlib import Path

from openpyxl import load_workbook

sys.path.insert(0, str(Path(__file__).resolve().parent))
import server  # noqa: E402
from adresa_iz_zayavok import norm, data, pohozh_adres  # noqa: E402

SRC = sys.argv[1] if len(sys.argv) > 1 else r'C:\РАБОТА\Заявки ВЛ и УПД — вариант 7.xlsx'
ISP = {'ИП Шерстов': 'ИП Шерстов', 'ООО «ТК МВЛ»': 'ТК МВЛ ООО'}


def stroki():
    wb = load_workbook(SRC, read_only=True)
    for r in wb['Заявки ВЛ и УПД'].iter_rows(min_row=2, values_only=True):
        if not r[1]:
            continue
        skip = 'версия заявки' in str(r[17] or '') or 'дубл' in str(r[21] or '').lower()
        yield {'key': f'В7 строка {r[0]}', 'client': r[1], 'nomer': r[2], 'dt_z': data(r[3]), 'sum': r[4], 'nds': r[5],
               'dt_p': data(r[7]), 'from': r[8], 'to': r[9], 'company': 'ООО ВЛ', 'skip': skip}
    for r in wb['Не вошли (ИП Шерстов и др.)'].iter_rows(min_row=2, values_only=True):
        if not r[2] or r[1] not in ISP:
            continue
        yield {'key': f'В7 не вошли {r[0]}', 'client': r[2], 'nomer': r[3], 'dt_z': data(r[4]), 'sum': r[5], 'nds': '',
               'dt_p': None, 'from': '', 'to': '', 'company': ISP[r[1]], 'skip': False}


def main():
    con = server.connect()
    gruzy = [dict(g) for g in con.execute('SELECT id, client, rate_client, created, note FROM gruz')]
    stat = {'new': 0, 'dubl': 0, 'est': 0, 'pusto': 0}
    for z in stroki():
        if z['skip'] or not isinstance(z['sum'], (int, float)) or z['sum'] <= 0:
            stat['dubl' if z['skip'] else 'pusto'] += 1
            continue
        metka = f"[{z['key']}]"
        dt = z['dt_p'] or z['dt_z']
        zn = norm(z['client'])

        def tot_zhe(g):
            if metka in (g['note'] or ''):
                return True
            if z['nomer'] and z['dt_z'] and f"[адрес из заявки {z['nomer']} от {z['dt_z'].strftime('%d.%m.%Y')}" in (g['note'] or ''):
                return True
            if not g['rate_client'] or abs(g['rate_client'] - z['sum']) >= 1:
                return False
            if difflib.SequenceMatcher(None, norm(g['client']), zn).ratio() < 0.7:
                return False
            gd = D.date.fromisoformat(g['created']) if g['created'] else None
            return not (gd and dt) or abs((gd - dt).days) <= 10
        if any(tot_zhe(g) for g in gruzy):
            stat['est'] += 1
            continue
        note = (f"{metka} Из сводной таблицы заявок (вариант 7): заявка клиента {z['nomer'] or 'б/н'}"
                f"{' от ' + z['dt_z'].strftime('%d.%m.%Y') if z['dt_z'] else ''}.")
        frm, to = pohozh_adres(z['from']) or '', pohozh_adres(z['to']) or ''
        pay = {'с НДС': 'с НДС', 'без НДС': 'без НДС'}.get(str(z['nds'] or '').strip(), '')
        gid = con.execute('INSERT INTO gruz(created, client, company, pay_form, from_addr, to_addr, rate_client, status, note) '
                          'VALUES (?,?,?,?,?,?,?,?,?)',
                          (dt.isoformat() if dt else '', z['client'], z['company'], pay, frm, to, z['sum'], 'доставлен', note)).lastrowid
        con.execute('UPDATE gruz SET nomer=? WHERE id=?', (f'Г-{gid:04d}', gid))
        gruzy.append({'id': gid, 'client': z['client'], 'rate_client': z['sum'], 'created': dt.isoformat() if dt else '', 'note': note})
        stat['new'] += 1
    con.commit()
    print(f"Новых грузов {stat['new']}, уже были в приложении {stat['est']}, версии/дубли таблицы {stat['dubl']}, без суммы {stat['pusto']}.")


if __name__ == '__main__':
    main()
