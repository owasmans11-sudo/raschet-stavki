# Выгрузка заявок в Excel (по кнопке в приложении).
# Строки считает страница тем же расчётом, что вкладка «Зарплата» (app.js → calc), поэтому цифры совпадают до рубля;
# здесь — только запись файла: шапка в цветах ВЛ, фильтры, итоги (SUBTOTAL — считают и при фильтре), лист итогов по менеджерам.
import re
from datetime import date
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

OUT_DIR = Path(__file__).resolve().parent.parent / 'Заявки из приложения' / 'Excel'
BLUE, DARK, LIGHT = '1E6FE0', '0B4AA8', 'EAF2FE'
RUB = '#,##0 ₽;[Red]-#,##0 ₽'
THIN = Side(style='thin', color='A9C8F5')

# (ключ строки, заголовок, ширина, формат, итог)
COLS = [
    ('nomer', '№', 10, None, False), ('dt', 'Дата погрузки', 12, 'DD.MM.YYYY', False), ('manager', 'Менеджер', 13, None, False),
    ('client', 'Заказчик', 28, None, False), ('inn', 'ИНН заказчика', 13, '@', False), ('from', 'Откуда', 28, None, False),
    ('to', 'Куда', 28, None, False), ('sklady', 'Склады', 20, None, False), ('cargo', 'Груз', 20, None, False),
    ('kg', 'Вес, кг', 10, '#,##0', True), ('m3', 'Объём, м³', 9, '#,##0.0#', True), ('places', 'Мест', 7, '#,##0', True),
    ('status', 'Статус груза', 12, None, False), ('fury', 'Фура(ы)', 14, None, False),
    ('rate', 'Ставка клиента', 13, RUB, True), ('pay_form', 'Форма оплаты', 11, None, False), ('company', 'Наша компания', 13, None, False),
    ('z_carrier', 'Забор: перевозчик', 22, None, False), ('z_rate', 'Забор, ₽', 11, RUB, True),
    ('r_carrier', 'Развоз: перевозчик', 22, None, False), ('r_rate', 'Развоз, ₽', 11, RUB, True),
    ('other', 'Прочие, ₽', 10, RUB, True), ('share', 'Доля фур, ₽', 12, RUB, True), ('nalog', 'Налог с выручки, ₽', 13, RUB, True),
    ('vat', 'НДС к вычету, ₽', 12, RUB, True), ('np', 'Налог на прибыль, ₽', 13, RUB, True),
    ('profit', 'ОСТАТОК ПРИБЫЛИ, ₽', 14, RUB, True), ('zp', 'Зп 20%, ₽', 11, RUB, True),
    ('paid', 'Клиент оплатил, ₽', 13, RUB, True), ('paid_date', 'Дата оплаты', 12, 'DD.MM.YYYY', False),
    ('pay_status', 'Оплата', 12, None, False), ('debt', 'Долг клиента, ₽', 13, RUB, True),
    ('zp_nach', 'Зп начислено, ₽', 13, RUB, True), ('zp_wait', 'Зп ждёт оплаты, ₽', 13, RUB, True),
]
KEY = {k: i + 1 for i, (k, *_) in enumerate(COLS)}


def _date(s):
    try:
        y, m, d = map(int, s[:10].split('-'))
        return date(y, m, d)
    except Exception:
        return None


def _header(ws, row, titles, widths=None):
    for j, t in enumerate(titles, 1):
        c = ws.cell(row, j, t)
        c.font = Font(bold=True, color='FFFFFF')
        c.fill = PatternFill('solid', fgColor=BLUE)
        c.alignment = Alignment(wrap_text=True, vertical='center', horizontal='center')
        c.border = Border(top=THIN, bottom=THIN, left=THIN, right=THIN)
        if widths:
            ws.column_dimensions[get_column_letter(j)].width = widths[j - 1]
    ws.row_dimensions[row].height = 32


def build(rows, manager, d_from, d_to):
    """rows — список словарей (ключи как в COLS). Возвращает путь к файлу."""
    wb = Workbook()
    ws = wb.active
    ws.title = 'Заявки'
    who = manager or 'все менеджеры'
    period = f'{_date(d_from):%d.%m.%Y} – {_date(d_to):%d.%m.%Y}' if _date(d_from) and _date(d_to) else 'весь период'
    ws['A1'] = f'Заявки — {who} — {period}'
    ws['A1'].font = Font(bold=True, size=14, color=DARK)
    ws['A2'] = ('Остаток прибыли и зп — как во вкладке «Зарплата»: выручка − налог с выручки − расходы + НДС к вычету '
                '− доля фур − налог на прибыль; зп 20% начисляется после полной оплаты клиента.')
    ws['A2'].font = Font(italic=True, color='6B6B6B', size=9)
    H = 4
    _header(ws, H, [c[1] for c in COLS], [c[2] for c in COLS])
    for i, r in enumerate(rows, H + 1):
        for j, (k, _, _, fmt, _) in enumerate(COLS, 1):
            v = r.get(k)
            if k in ('dt', 'paid_date'):
                v = _date(v or '')
            if v in ('', None):
                continue
            c = ws.cell(i, j, v)
            if fmt:
                c.number_format = fmt
        if (r.get('profit') or 0) < 0:
            ws.cell(i, KEY['profit']).font = Font(color='D64545', bold=True)
        if not r.get('manager'):
            ws.cell(i, KEY['manager']).fill = PatternFill('solid', fgColor='FFF6D6')
    last = H + len(rows)
    tot = last + 1
    ws.cell(tot, 1, 'ИТОГО').font = Font(bold=True)
    for j, (k, _, _, fmt, sumit) in enumerate(COLS, 1):
        c = ws.cell(tot, j)
        c.fill = PatternFill('solid', fgColor=LIGHT)
        if sumit and rows:
            L = get_column_letter(j)
            c.value = f'=SUBTOTAL(9,{L}{H + 1}:{L}{last})'  # SUBTOTAL — итог только по видимым строкам при фильтре
            c.number_format = fmt
            c.font = Font(bold=True)
    ws.freeze_panes = ws.cell(H + 1, 3)
    if rows:
        ws.auto_filter.ref = f'A{H}:{get_column_letter(len(COLS))}{last}'

    # итоги по менеджерам — формулами по листу «Заявки», пересчитываются, если поправить цифры
    s = wb.create_sheet('Итого по менеджерам')
    s['A1'] = f'Итого по менеджерам — {period}'
    s['A1'].font = Font(bold=True, size=14, color=DARK)
    _header(s, 3, ['Менеджер', 'Заявок', 'Выручка', 'Остаток прибыли', 'Зп начислено', 'Зп ждёт оплаты', 'Долг клиентов'],
            [20, 9, 15, 16, 15, 15, 15])
    rng = lambda k: f"Заявки!${get_column_letter(KEY[k])}${H + 1}:${get_column_letter(KEY[k])}${max(last, H + 1)}"
    names = sorted({r.get('manager') or '' for r in rows}, key=lambda m: (m == '', m))
    for i, m in enumerate(names, 4):
        s.cell(i, 1, m or '(без менеджера)')
        crit = f'"{m}"' if m else '""'
        s.cell(i, 2, f'=COUNTIFS({rng("manager")},{crit})')
        for j, k in enumerate(['rate', 'profit', 'zp_nach', 'zp_wait', 'debt'], 3):
            c = s.cell(i, j, f'=SUMIFS({rng(k)},{rng("manager")},{crit})')
            c.number_format = RUB
    t = 4 + len(names)
    s.cell(t, 1, 'ИТОГО').font = Font(bold=True)
    for j in range(2, 8):
        L = get_column_letter(j)
        c = s.cell(t, j, f'=SUM({L}4:{L}{t - 1})' if names else 0)
        c.font = Font(bold=True)
        c.fill = PatternFill('solid', fgColor=LIGHT)
        if j > 2:
            c.number_format = RUB

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stem = re.sub(r'[\\/:*?"<>|«»]+', '', f'{date.today():%Y-%m-%d} Заявки — {who} — {period.replace(" – ", "–")}')
    path, k = OUT_DIR / f'{stem}.xlsx', 2
    while True:
        try:
            wb.save(path)
            return path
        except PermissionError:  # такой файл открыт в Excel — сохраняем рядом
            path = OUT_DIR / f'{stem} ({k}).xlsx'
            k += 1
