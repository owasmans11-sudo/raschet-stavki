import openpyxl, re, datetime as dt
from difflib import SequenceMatcher
from openpyxl.styles import PatternFill, Font, Alignment
from openpyxl.utils import get_column_letter
B = "C:/Users/user/Yandex.Disk/Восточная Логистика/1. Илья Satdinov/Папка Satdinova/Клиенты - Машины- бух-док.xlsx"
D = "C:/Users/user/Desktop/ДОЛГОВЫЕ.xlsx"
OUT = "C:/Users/user/Desktop/ДОЛГОВЫЕ и бух-док — общие клиенты.xlsx"
LAT = str.maketrans({'a':'а','b':'б','c':'с','d':'д','e':'е','f':'ф','g':'г','h':'х','i':'и','k':'к','l':'л','m':'м',
                     'n':'н','o':'о','p':'п','r':'р','s':'с','t':'т','u':'у','v':'в','x':'кс','y':'у','z':'з'})
FORMS = {'ооо','ип','тлк','тк','тэк','пто','ао','зао','оао'}

def norm(s):
    s = str(s or '').lower().replace('ё','е').replace('\n',' ')
    s = re.sub(r'\(.*?\)', ' ', s)
    s = s.translate(LAT)
    s = re.sub(r'[^0-9а-я ]', ' ', s)
    return [w for w in s.split() if w not in FORMS]

def surname_like(t):
    return len(t) >= 2 and all(len(w) <= 2 for w in t[1:])

def name_score(a, b):
    ta, tb = norm(a), norm(b)
    if not ta or not tb: return 0
    ka, kb = ''.join(ta), ''.join(tb)
    if ka == kb: return 1
    GEN = {'логистика','логистик','транс','групп','экспресс','груз','карго','мск'}
    if set(ta) <= GEN or set(tb) <= GEN: return 0
    if len(min(ka, kb, key=len)) >= 3 and (ka.startswith(kb) or kb.startswith(ka)): return .95
    if surname_like(ta) or surname_like(tb) or len(ta) == 1 or len(tb) == 1 or len(ta) == 3 or len(tb) == 3:
        r = SequenceMatcher(None, ta[0], tb[0]).ratio()
        if len(ta[0]) >= 5 and r >= .85 and (surname_like(ta) or surname_like(tb) or len(ta) == 3 or len(tb) == 3 or len(ta) == 1 or len(tb) == 1):
            return .9
    return SequenceMatcher(None, ka, kb).ratio()

def num(v):
    if isinstance(v, (int, float)): return float(v)
    m = re.search(r'\d[\d .]*', str(v or ''))
    if not m: return None
    s = m.group().replace(' ', '').rstrip('.')
    if re.fullmatch(r'\d{1,3}\.\d{3}', s): s = s.replace('.', '')
    try: return float(s)
    except ValueError: return None

def dat(v):
    if isinstance(v, dt.datetime): return v.date()
    m = re.search(r'(\d{2})\.(\d{2})\.(\d{4})', str(v or ''))
    if m: return dt.date(int(m[3]), int(m[2]), int(m[1]))
    m = re.search(r'(\d{2})[–-]\d{2}\.(\d{2})\.(\d{4})', str(v or ''))
    if m: return dt.date(int(m[3]), int(m[2]), int(m[1]))
    return None

wb = openpyxl.load_workbook(B, data_only=True); ws = wb["Вложения в компанию"]
buh = []
for r in range(2, ws.max_row + 1):
    row = [ws.cell(r, c).value for c in range(1, 13)]
    if row[0] and str(row[0]).strip():
        buh.append(dict(r=r, row=row, name=str(row[0]).strip(), sum=num(row[2]), date=dat(row[1])))
wd = openpyxl.load_workbook(D, data_only=True).active
dolg = []
for r in range(1, wd.max_row + 1):
    row = [wd.cell(r, c).value for c in range(1, 23)]
    if row[1]:
        dolg.append(dict(r=r, row=row, name=str(row[1]).strip(), sum=num(row[4]), date=dat(row[7]) or dat(row[3])))

used = set(); res = []
for d in dolg:
    cands = []
    for b in buh:
        s = name_score(d['name'], b['name'])
        same_sum = bool(d['sum'] and b['sum'] and abs(d['sum'] - b['sum']) < 1)
        dd = abs((d['date'] - b['date']).days) if d['date'] and b['date'] else 99
        if s >= .88 or (s >= .55 and same_sum and dd <= 10):
            cands.append((s, same_sum, dd, b))
    free = sorted([c for c in cands if c[3]['r'] not in used],
                  key=lambda c: (-(c[1] and c[2] <= 10), -c[1], c[2], -c[0]))
    trip = None; how = ''
    if free:
        s, ss, dd, b = free[0]
        if ss and dd <= 10: trip, how = b, 'клиент + сумма + дата'
        elif ss: trip, how = b, 'клиент + сумма (даты расходятся)'
        elif dd <= 5: trip, how = b, 'клиент + дата (суммы разные)'
    if trip: used.add(trip['r'])
    res.append(dict(d=d, client_ok=bool(cands), client_names=sorted({c[3]['name'] for c in cands}), trip=trip, how=how))

out = openpyxl.Workbook()
H = Font(bold=True, color='FFFFFF'); HF = PatternFill('solid', fgColor='305496')
G = PatternFill('solid', fgColor='E2EFDA'); Y = PatternFill('solid', fgColor='FFF2CC'); R = PatternFill('solid', fgColor='FCE4D6')
def fmt(v): return v.date() if isinstance(v, dt.datetime) else v
def head(w, cols, widths):
    w.append(cols)
    for i, c in enumerate(cols, 1):
        x = w.cell(1, i); x.font = H; x.fill = HF; x.alignment = Alignment(wrap_text=True, vertical='center')
        w.column_dimensions[get_column_letter(i)].width = widths[i - 1] if i <= len(widths) else 14
    w.freeze_panes = 'C2'; w.row_dimensions[1].height = 45
DCOLS = [('№ (долговые)',0),('Клиент (долговые)',1),('№ заявки',2),('Дата заявки',3),('Сумма заявки',4),('НДС',5),
         ('Дата погрузки',7),('Дата выгрузки',10),('Оплачено',16),('Долг',18),('Статус',19),('Пометки',17),('Пояснение',21)]
BCOLS = [('Клиент (бух-док)',0),('Дата загрузки',1),('Оплата',2),('Вид опл',3),('За 1 перевозку',4),('За 2 перевозку',5),
         ('Транспорт',6),('Дата выгрузки',7),('Контакт клиента',8),('Бух-док-ТТН-фото',10),('Срок оплаты',11)]
w1 = out.active; w1.title = 'Общие клиенты'
head(w1, [c for c, _ in DCOLS] + ['Как совпало', 'Строка в бух-док'] + [c for c, _ in BCOLS],
     [7,30,12,11,12,9,11,12,11,11,16,30,40,24,9,26,11,11,11,13,13,11,12,35,14,11])
n_cli = n_trip = 0
for x in res:
    if not x['client_ok']: continue
    d = x['d']; b = x['trip']
    how = x['how'] or 'клиент есть, эту перевозку в бух-док не нашёл'
    tail = [fmt(b['row'][i]) for _, i in BCOLS] if b else [' / '.join(x['client_names'])] + [None] * (len(BCOLS) - 1)
    line = [fmt(d['row'][i]) for _, i in DCOLS] + [how, b['r'] if b else None] + tail
    w1.append(line); rr = w1.max_row
    fill = G if how == 'клиент + сумма + дата' else (Y if b else R)
    for c in range(1, len(line) + 1):
        w1.cell(rr, c).fill = fill; w1.cell(rr, c).alignment = Alignment(wrap_text=True, vertical='top')
    n_cli += 1; n_trip += bool(b)
w2 = out.create_sheet('Нет в бух-док')
head(w2, [c for c, _ in DCOLS], [7,30,12,11,12,9,11,12,11,11,16,30,40])
for x in res:
    if not x['client_ok']: w2.append([fmt(x['d']['row'][i]) for _, i in DCOLS])
w3 = out.create_sheet('Есть только в бух-док')
head(w3, ['Строка'] + [c for c, _ in BCOLS], [8,30,12,11,9,14,14,11,12,35,14,11])
matched = {n for x in res for n in x['client_names']}
for b in buh:
    if b['name'] not in matched: w3.append([b['r']] + [fmt(b['row'][i]) for _, i in BCOLS])
for w in (w1, w2, w3):
    for row in w.iter_rows(min_row=2):
        for c in row:
            if isinstance(c.value, dt.date): c.number_format = 'DD.MM.YYYY'
            elif isinstance(c.value, (int, float)) and c.column > 1: c.number_format = '# ##0'
    w.auto_filter.ref = w.dimensions
out.save(OUT)
print('долговых', len(dolg), '| общий клиент', n_cli, '| перевозка найдена', n_trip, '| нет в бух-док', len(dolg) - n_cli, '| только в бух-док', w3.max_row - 1)
for x in res:
    print('OK ' if x['client_ok'] else '-- ', x['d']['name'].replace('\n', ' '), '->', x['client_names'], '|', x['how'], x['trip']['r'] if x['trip'] else '')
