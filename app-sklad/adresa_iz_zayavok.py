# Полные адреса погрузки/выгрузки для грузов из УЛ — из распознанных сканов заявок клиентов
# (сводная таблица «Заявки ВЛ и УПД — вариант 7.xlsx»). Собрано 2026-11-02.
# Пара: похожий заказчик + та же ставка и/или дата погрузки ±7 дней. Адрес берём, только если он похож на адрес
# и в нём тот же город, что в УЛ (выгрузку на склад МО заменяем адресом клиента — это его конечная точка).
# Повтор не задваивает: метка «[адрес из заявки …]» в примечании.
# Запуск: python app-sklad/adresa_iz_zayavok.py ["<вариант 7.xlsx>"]
import datetime as D
import difflib
import re
import sys
from pathlib import Path

from openpyxl import load_workbook

sys.path.insert(0, str(Path(__file__).resolve().parent))
import server  # noqa: E402

SRC = sys.argv[1] if len(sys.argv) > 1 else r'C:\РАБОТА\Заявки ВЛ и УПД — вариант 7.xlsx'
SKLAD_MO = ('щербинка', 'щёлково', 'щелково')
MUSOR = ('адрес', 'ответствен', 'ставка', 'контакт', 'дата', 'груз')


def norm(s):
    return ' '.join(re.sub(r'\b(ооо|ип|оао|ао|тк|пао|зао)\b|[«»"\'.,()]', ' ', (s or '').lower()).split())


def data(x):
    if isinstance(x, D.datetime):
        return x.date()
    try:
        return D.datetime.strptime(str(x)[:10], '%d.%m.%Y').date()
    except ValueError:
        return None


def pohozh_adres(s):
    s = (s or '').strip()
    return len(s) > 10 and re.search(r'\d', s) and not s.lower().startswith(MUSOR) and s


def gorod_v(adr, gorod):
    g = (gorod or '').lower().replace('ё', 'е')[:5]
    return g and g in adr.lower().replace('ё', 'е')


def main():
    rows = [r for r in load_workbook(SRC, read_only=True)['Заявки ВЛ и УПД'].iter_rows(min_row=2, values_only=True) if r[1]]
    con = server.connect()
    gruzy = con.execute("SELECT id, client, rate_client, created, from_addr, to_addr, note FROM gruz "
                        "WHERE note LIKE '%[УЛ %' AND note NOT LIKE '%[адрес из заявки%'").fetchall()
    n_from = n_to = n_para = 0
    for g in gruzy:
        gn, gd = norm(g['client']), D.date.fromisoformat(g['created']) if g['created'] else None
        best, bs = None, 0
        for r in rows:
            s = difflib.SequenceMatcher(None, gn, norm(r[1])).ratio()
            if s < 0.7:
                continue
            if g['rate_client'] and isinstance(r[4], (int, float)) and abs(r[4] - g['rate_client']) < 1:
                s += 1
            rd = data(r[7]) or data(r[3])
            if gd and rd and abs((rd - gd).days) <= 7:
                s += 0.5
            if s > bs:
                best, bs = r, s
        if not best or bs < 1.5:
            continue
        n_para += 1
        new_from, new_to = g['from_addr'], g['to_addr']
        a = pohozh_adres(best[8])
        if a and gorod_v(a, g['from_addr']):
            new_from, n_from = a, n_from + 1
        b = pohozh_adres(best[9])
        if b and (gorod_v(b, g['to_addr']) or (g['to_addr'] or '').lower() in SKLAD_MO):
            new_to, n_to = b, n_to + 1
        if (new_from, new_to) != (g['from_addr'], g['to_addr']):
            con.execute('UPDATE gruz SET from_addr=?, to_addr=?, note=note||? WHERE id=?',
                        (new_from, new_to, f" [адрес из заявки {best[2]} от {str(best[3])[:10]}, было: "
                                           f"{g['from_addr']} → {g['to_addr']}]", g['id']))
    con.commit()
    print(f'Пара со сканом: {n_para} из {len(gruzy)}; адрес погрузки уточнён {n_from}, выгрузки {n_to}.')


if __name__ == '__main__':
    main()
