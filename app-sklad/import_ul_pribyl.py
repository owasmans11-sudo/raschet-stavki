# Обычные (не сложные) перевозки из «Умной логистики» → грузы приложения. Собрано 2026-11-02.
# Вход — «Отчёт по Прибыли», вариант «По Организациям», сохранённый как .mxl (Дирекция → Финансовые отчёты):
# фирма → заказчик → «Заявка (для Экспедитора) N от дата» со суммами заказчику и перевозчику.
# Берём заявки со ставкой заказчику, которых ещё нет в приложении (номер УЛ ищем в примечаниях грузов и фур, в отрезках).
# В отчёте нет маршрута, груза и перевозчика — только деньги; дата — дата заявки в УЛ (часто внесена позже перевозки).
# Повтор не задваивает: метка «[УЛ заявка N]». Запуск: python app-sklad/import_ul_pribyl.py "<отчёт.mxl>"
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / 'tools' / 'slozhnye_ul'))
import server  # noqa: E402
import mxl  # noqa: E402
from import_ul import NASHI, num, iso  # noqa: E402

ORG = {'ООО "Восточная Логистика"': 'ООО ВЛ', 'Шерстов Андрей Витальевич': 'ИП Шерстов', 'ТК МВЛ ООО': 'ТК МВЛ ООО'}
ZAYAVKA = re.compile(r'Заявка \(для Экспедитора\)\s+(\d+)\s+от\s+(\d{2}\.\d{2}\.\d{4})')


def read_report(path):
    cells = mxl.read(path)
    org = client = None
    for r in sorted({r for r, _ in cells}):
        name = cells.get((r, 0), '').strip()
        m = ZAYAVKA.match(name)
        if m:
            yield {'nomer': m.group(1), 'dt': m.group(2), 'org': org, 'client': client,
                   'st_k': num(cells.get((r, 3), '').replace(',00', '')), 'st_p': num(cells.get((r, 5), '').replace(',00', ''))}
        elif name in ORG:
            org, client = ORG[name], None
        elif name and not name.startswith(('Заказчик', 'Итого')):
            client = name


def main():
    con = server.connect()
    est = set()
    for (t,) in con.execute("SELECT note FROM gruz UNION ALL SELECT note FROM fura UNION ALL SELECT zayavka FROM leg "
                            "UNION ALL SELECT zayavka FROM fura"):
        est |= {int(x) for x in re.findall(r'(?:УЛ [^/\]]*/|УЛ заявка )?(\d{6,10})', t or '')}
    novye = propusk = nashi = 0
    sum_k = 0.0
    for z in read_report(sys.argv[1]):
        if int(z['nomer']) in est:
            propusk += 1
            continue
        if not z['st_k'] or any(k in (z['client'] or '').upper() for k in NASHI):
            nashi += 1  # наша заявка перевозчику без клиента — грузом не делаем
            continue
        note = (f"[УЛ заявка {z['nomer']}] Обычная перевозка из УЛ: заявка {z['nomer']} от {z['dt']} "
                f"(дата оформления в УЛ). Маршрута и груза в отчёте УЛ нет.")
        gid = con.execute('INSERT INTO gruz(created, client, company, rate_client, status, note) VALUES (?,?,?,?,?,?)',
                          (iso(z['dt']), z['client'], z['org'] or 'ООО ВЛ', z['st_k'], 'доставлен', note)).lastrowid
        con.execute('UPDATE gruz SET nomer=? WHERE id=?', (f'Г-{gid:04d}', gid))
        con.execute("INSERT INTO leg(gruz_id, kind, zayavka, dt, rate) VALUES (?,?,?,?,?)",
                    (gid, 'zabor', z['nomer'], iso(z['dt']), z['st_p']))
        est.add(int(z['nomer']))
        novye += 1
        sum_k += z['st_k']
    con.commit()
    print(f'Новых грузов {novye} (ставки клиентам {sum_k:,.0f} ₽), уже были в приложении {propusk}, '
          f'наших заявок без клиента пропущено {nashi}.'.replace(',', ' '))


if __name__ == '__main__':
    main()
