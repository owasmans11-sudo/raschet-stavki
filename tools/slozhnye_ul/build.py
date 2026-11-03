# Все сложные перевозки из «Умной логистики» → Excel. Собрано 2026-11-02.
# Вход — «Отчёт по Сложным перевозкам», сохранённый из УЛ как .mxl (Сохранить как → Табличный документ).
# Запуск: python tools/slozhnye_ul/build.py "<отчёт.mxl>" "<выход.xlsx>"
import re
import sys
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

import mxl

SRC, OUT = sys.argv[1], sys.argv[2]
cells = mxl.read(SRC)


def lines(v):
    return [x.strip() for x in (v or '').replace('\r', '').split('\n') if x.strip()]


def num(v):
    v = (v or '').replace('\xa0', '').replace(' ', '').replace('т', '').replace('м3', '').replace(',', '.')
    try:
        f = float(v)
        return int(f) if f == int(f) else f
    except ValueError:
        return None


def first_num(v):
    nums = [num(x) for x in lines(v)]
    return next((x for x in nums if x), nums[0] if nums else None)


slozh, zayav = [], []
cur = None
for r in sorted({r for r, _ in cells}):
    g = lambda k: cells.get((r, k), '')
    a = lines(g(0))
    if not a:
        continue
    if re.match(r'№\s*\d', a[0]):
        d = lines(g(3))
        cur = {'n': num(a[0][1:]), 'ot': a[1].replace('от', '').strip() if len(a) > 1 else '',
               'marshrut': g(2), 'nach': d[0] if d else '', 'kon': d[-1] if d else '',
               'ves': num(g(4)), 'obem': num(g(5)),
               'kol': [num(g(k)) for k in (6, 7, 8, 9, 13, 14)],
               'klient': num(g(10)), 'perev': num(g(11)), 'marzha': num(g(12)), 'zayavok': 0, 'sum_k': 0, 'sum_p': 0}
        slozh.append(cur)
    elif a[0].startswith('Заявка') and cur:
        vid, mesta, daty = lines(g(1)), lines(g(2)), lines(g(3))
        tochki = []
        for i, m in enumerate(mesta):
            v = ('погр.' if vid[i].lower().startswith('погр') else 'разгр.') if i < len(vid) else ''
            dt = daty[i][:5] if i < len(daty) else ''
            tochki.append(f'{m} ({v} {dt})'.replace('( ', '(').replace(' )', ')'))
        kl, pr = num(g(10)), num(g(11))
        zayav.append([cur['n'], a[0].replace('Заявка', '').strip(), a[1].replace('от', '').strip() if len(a) > 1 else '',
                      mesta[0] if mesta else '', mesta[-1] if mesta else '',
                      daty[0] if daty else '', daty[-1] if daty else '', ' → '.join(tochki),
                      first_num(g(4)), first_num(g(5)), g(6), g(7), g(8), g(9),
                      kl, pr, num(g(12)), g(13), g(14)])
        cur['zayavok'] += 1
        cur['sum_k'] += kl or 0
        cur['sum_p'] += pr or 0

HEAD = Font(bold=True, color='FFFFFF')
FILL = PatternFill('solid', fgColor='305496')
WARN = PatternFill('solid', fgColor='FFF2CC')
MONEY = '#,##0'


def sheet(ws, head, rows, widths, money_cols):
    ws.append(head)
    for c in ws[1]:
        c.font, c.fill = HEAD, FILL
        c.alignment = Alignment(wrap_text=True, vertical='center')
    for row in rows:
        ws.append(row)
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    for col in money_cols:
        for c in ws[get_column_letter(col)][1:]:
            c.number_format = MONEY
    ws.freeze_panes = 'A2'
    ws.auto_filter.ref = ws.dimensions


wb = Workbook()
ws = wb.active
ws.title = 'Сложные'
sheet(ws, ['№ сложной', 'Дата', 'Маршрут', 'Начало', 'Конец', 'Вес, т', 'Объём, м3', 'Заявок',
           'Грузов', 'Заказчиков', 'Перевозчиков', 'Транспорт', 'Организаций', 'Менеджеров',
           'Ставка заказчику', 'Ставка перевозчику', 'Маржа', 'Сверка с заявками'],
      [[s['n'], s['ot'], s['marshrut'], s['nach'], s['kon'], s['ves'], s['obem'], s['zayavok'], *s['kol'],
        s['klient'], s['perev'], s['marzha'],
        'сходится' if (s['klient'] or 0) == s['sum_k'] and (s['perev'] or 0) == s['sum_p']
        else f"не сходится: по заявкам {s['sum_k']:,} / {s['sum_p']:,}".replace(',', ' ')]
       for s in slozh],
      [10, 11, 34, 11, 11, 8, 9, 8, 8, 10, 11, 10, 11, 11, 13, 13, 12, 22], [15, 16, 17])
r = ws.max_row + 1
ws.cell(r, 1, 'Итого').font = Font(bold=True)
for col in (6, 7, 8, 15, 16, 17):
    L = get_column_letter(col)
    c = ws.cell(r, col, f'=SUM({L}2:{L}{r - 1})')
    c.font = Font(bold=True)
    c.number_format = MONEY
for row in ws.iter_rows(min_row=2, max_row=r - 1):
    if row[17].value != 'сходится':
        row[17].fill = WARN

ws = wb.create_sheet('Заявки')
sheet(ws, ['№ сложной', '№ заявки', 'Дата заявки', 'Откуда', 'Куда', 'Дата погрузки', 'Дата разгрузки',
           'Все точки', 'Вес, т', 'Объём, м3', 'Груз', 'Заказчик', 'Перевозчик', 'Транспорт',
           'Ставка заказчику', 'Ставка перевозчику', 'Маржа', 'Организация', 'Менеджер'],
      zayav, [10, 13, 11, 18, 18, 11, 11, 50, 8, 9, 26, 30, 30, 24, 13, 13, 12, 24, 26], [15, 16, 17])
r = ws.max_row + 1
ws.cell(r, 1, 'Итого').font = Font(bold=True)
for col in (15, 16, 17):
    L = get_column_letter(col)
    c = ws.cell(r, col, f'=SUM({L}2:{L}{r - 1})')
    c.font = Font(bold=True)
    c.number_format = MONEY

ws = wb.create_sheet('Пояснения')
for t in ['Источник: «Умная логистика» → «Отчёт по Сложным перевозкам», выгрузка ' + re.sub(r'.*[\\/]', '', SRC) + '.',
          'Лист «Сложные» — одна строка на сложную перевозку (итоги из отчёта УЛ).',
          'Лист «Заявки» — одна строка на заявку внутри сложной. Фильтры в заголовках.',
          '«Откуда» — первая точка, «Куда» — последняя; все точки с датами — в «Все точки».',
          'Вес и объём — по первой точке (погрузке). В УЛ они часто нулевые.',
          'Колонки «Грузов… Менеджеров» на листе «Сложные» — числа из отчёта УЛ, как там стоят.',
          '«Сверка с заявками»: сумма ставок по заявкам сравнивается с итогом сложной. Жёлтым — расхождение.',
          'Адреса в отчёте УЛ — только города; полные адреса есть лишь в карточке заявки.']:
    ws.append([t])
ws.column_dimensions['A'].width = 110

wb.save(OUT)
print(f'сложных {len(slozh)}, заявок {len(zayav)}, не сходится: '
      f'{sum(1 for s in slozh if (s["klient"] or 0) != s["sum_k"] or (s["perev"] or 0) != s["sum_p"])}')
