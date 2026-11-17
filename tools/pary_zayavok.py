"""Пары заявок: заявка с клиентом + заявка ВЛ перевозчику на одну перевозку — в одну папку, остальное — в отчёт.

    python tools/pary_zayavok.py              собрать пары, разложить копии, написать отчёт
    python tools/pary_zayavok.py --no-copy    только отчёт (папки не трогать)

Берёт заявки из картотеки (%USERPROFILE%\\vl_find_files\\kartoteka.json — её готовит tools/build_kartoteka.py) и их тексты
(те же, что видит картотека: свой PDF-слой, распознанные сканы и фото, Word/Excel). В каждой заявке ищет номера машин,
фамилию водителя, дату погрузки и города. Пара «уверенная» — совпал номер машины или фамилия водителя И даты погрузки
не дальше 2 дней. Файлы таких пар ИЗ ПОЧТЫ переносятся (tools/razbor_pochty.py) в C:\\РАБОТА\\Перевозки\\<Клиент>\\<ГГГГ-ММ-ДД> <Откуда>–<Куда>, <Фамилия>\\.
Всё, в чём программа не уверена, в папки не идёт — только в отчёт C:\\РАБОТА\\Перевозки\\Отчёт ГГГГ-ММ-ДД.xlsx.
Старый архив не трогается. Папка перевозки узнаётся по тому, где уже лежат её заявки.
"""
import argparse, json, os, re, sys
from datetime import date, datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import find_files as ff
import build_kartoteka as bk
import kart_fields as kf

BASE = os.path.dirname(ff.CACHE)
KARTOTEKA = os.path.join(BASE, 'kartoteka.json')
STATE = os.path.join(BASE, 'pary_state.json')
MAIL_STATUS = os.path.join(BASE, 'mail_status.json')  # итог вечернего скачивания почты (mail-downloader/nightly_mail.py)
OUT = os.path.join(ff.WORK, 'Перевозки')

SURE_DAYS = 2    # уверенная пара: даты погрузки расходятся не больше чем на столько дней
DOUBT_DAYS = 7   # сомнительная: водитель/машина совпали, но даты дальше или неизвестны

# Номера: тягач А123ВС38 (буквы — только те, что есть и в латинице), прицеп АВ1234 38. Латиницу OCR → кириллица.
LAT = str.maketrans('ABEKMHOPCTYX', 'АВЕКМНОРСТУХ')
PL = 'АВЕКМНОРСТУХ'
PLATE = re.compile(rf'(?<![А-ЯA-Z0-9])([{PL}])\s?(\d{{3}})\s?([{PL}]{{2}})\s?(\d{{2,3}})(?!\d)')
TRAILER = re.compile(rf'(?<![А-ЯA-Z0-9])([{PL}]{{2}})\s?(\d{{4}})\s?(\d{{2,3}})(?!\d)')

# Города маршрутов ВЛ (из заявок) — по основе слова, чтобы ловить падежи. Порядок в тексте: первый — откуда, последний — куда.
CITIES = {'москв': 'Москва', 'щербинк': 'Щербинка', 'щелков': 'Щёлково', 'подольск': 'Подольск', 'домодедов': 'Домодедово',
          'химк': 'Химки', 'балаших': 'Балашиха', 'люберц': 'Люберцы', 'видн': 'Видное', 'электросталь': 'Электросталь',
          'санкт-петербург': 'Санкт-Петербург', 'петербург': 'Санкт-Петербург', 'спб': 'Санкт-Петербург',
          'иркутск': 'Иркутск', 'ангарск': 'Ангарск', 'шелехов': 'Шелехов', 'усть-кут': 'Усть-Кут', 'братск': 'Братск',
          'усть-илимск': 'Усть-Илимск', 'тайшет': 'Тайшет', 'черемхов': 'Черемхово', 'саянск': 'Саянск', 'тулун': 'Тулун',
          'чит': 'Чита', 'улан-удэ': 'Улан-Удэ', 'улан-уде': 'Улан-Удэ', 'хабаровск': 'Хабаровск', 'владивосток': 'Владивосток',
          'уссурийск': 'Уссурийск', 'находк': 'Находка', 'благовещенск': 'Благовещенск', 'якутск': 'Якутск',
          'красноярск': 'Красноярск', 'ачинск': 'Ачинск', 'новосибирск': 'Новосибирск', 'кемерово': 'Кемерово',
          'новокузнецк': 'Новокузнецк', 'томск': 'Томск', 'омск': 'Омск', 'барнаул': 'Барнаул', 'тюмен': 'Тюмень',
          'екатеринбург': 'Екатеринбург', 'челябинск': 'Челябинск', 'пермь': 'Пермь', 'перми': 'Пермь', 'уф': 'Уфа',
          'казан': 'Казань', 'самар': 'Самара', 'тольятт': 'Тольятти', 'саранск': 'Саранск', 'нижн': 'Нижний Новгород',
          'новгород': 'Нижний Новгород', 'ярославл': 'Ярославль', 'владимир': 'Владимир', 'тул': 'Тула',
          'рязан': 'Рязань', 'калуг': 'Калуга', 'тверь': 'Тверь', 'твер': 'Тверь', 'воронеж': 'Воронеж',
          'краснодар': 'Краснодар', 'ростов': 'Ростов-на-Дону', 'волгоград': 'Волгоград', 'саратов': 'Саратов',
          'пенз': 'Пенза', 'ульяновск': 'Ульяновск', 'чебоксар': 'Чебоксары', 'кстов': 'Кстово', 'дзержинск': 'Дзержинск',
          'минск': 'Минск', 'нерюнгри': 'Нерюнгри', 'бодайб': 'Бодайбо', 'северобайкальск': 'Северобайкальск'}
# короткие основы — только целым словом с окончанием (иначе «чит» найдётся в «считать», «тул» в «стулья»)
SHORT = {k for k in CITIES if len(k) <= 4}
CITY_RX = re.compile(r'(?<![а-яё-])(' + '|'.join(sorted(map(re.escape, CITIES), key=len, reverse=True)) + r')([а-яё]*)')
CITY_END = {'', 'а', 'е', 'у', 'ы', 'ой', 'ою', 'и', 'ей', 'ью', 'ь'}


def to_date(s):
    try:
        return datetime.strptime(s, '%d.%m.%Y').date()
    except Exception:
        return None


def raw_text(card, known, raw_other, fixes):
    """Текст заявки — тем же путём, что берёт картотека (build_kartoteka.build)."""
    path, name = card['path'], card['file']
    ext = os.path.splitext(name)[1].lower()
    _, flat, scan = known.get(os.path.normcase(path), (path, '', False))
    raw = ''
    if ext == '.pdf' and not scan and len(flat) >= ff.SCAN_MIN_TEXT:
        raw = bk.pdf_lines(path)
    raw = raw or raw_other.get(name.lower(), '')
    if not raw and ext in ('.docx', '.xlsx', '.xlsm'):
        raw = bk.office_lines(path, ext)
    raw = raw or flat or ''
    if card.get('source') in ('скан', 'фото') and fixes:
        raw = re.sub(r'[^\W\d_]+', lambda m: fixes.get(m.group().lower().replace('ё', 'е'), m.group()), raw)
    return raw


def cities(text):
    out = []
    for m in CITY_RX.finditer(text.lower().replace('ё', 'е')):
        stem, end = m.group(1), m.group(2)
        if stem in SHORT and end not in CITY_END:
            continue
        c = CITIES[stem]
        if c not in out:
            out.append(c)
    return out


UNLOAD_LABEL = re.compile(r'(адрес|место|пункт)[^\n]{0,25}(выгрузк|разгрузк|доставк)|^(выгрузка|разгрузка)\b|грузополучател', re.I)


def place_city(lines, label):
    """Город из строки «погрузка»/«выгрузка» или 3 строк под ней (в реквизитах ВЛ всегда есть Иркутск — их не берём)."""
    for i, l in enumerate(lines):
        if label.search(l):
            for s in lines[i:i + 4]:
                found = cities(s)
                if found:
                    return found[0]
    return ''


def features(card, raw):
    lines = kf.norm_lines(raw)
    up = raw.upper().translate(LAT)
    plates = {''.join(m.groups()[:3]) for m in PLATE.finditer(up)}  # без региона: OCR часто съедает его
    trailers = {''.join(m.groups()[:2]) for m in TRAILER.finditer(up)}
    drv = kf.driver(lines) or card.get('driver') or ''
    surname = drv.split()[0].lower().replace('ё', 'е') if drv else ''
    ld, _ = kf.loading(lines)
    m = re.match(r'(\d\d\.\d\d\.20\d\d)', card.get('load_place') or '')  # картотека пишет дату погрузки в начало «Погрузки»
    load = to_date(ld) or to_date(m.group(1) if m else '')
    doc = to_date(card.get('date') or '')
    return {'plates': plates, 'trailers': trailers, 'driver': drv, 'surname': surname,
            'load': load, 'doc': doc, 'cities': cities(raw[:6000]),
            'from': place_city(lines, kf.LOAD_LABEL), 'to': place_city(lines, UNLOAD_LABEL)}


def same_surname(a, b):
    if not a or not b:
        return False
    if a == b:
        return True
    return len(a) >= 5 and len(b) >= 5 and a[:-1] == b[:-1]  # падеж: Петров / Петрова


def compare(c, p):
    """(уровень, причина): 'sure' / 'doubt' / None."""
    fc, fp = c['f'], p['f']
    car = bool(fc['plates'] & fp['plates'])
    drv = same_surname(fc['surname'], fp['surname'])
    dc, dp = fc['load'] or fc['doc'], fp['load'] or fp['doc']
    days = abs((dc - dp).days) if dc and dp else None
    route = len(set(fc['cities']) & set(fp['cities']))
    why = []
    if car:
        why.append('машина ' + ', '.join(sorted(fc['plates'] & fp['plates'])))
    if drv:
        why.append('водитель')
    if days is not None:
        why.append(f'даты ±{days} дн.' + ('' if fc['load'] and fp['load'] else ' (по дате заявки)'))
    if route:
        why.append(f'городов общих: {route}')
    if (car or drv) and days is not None and days <= SURE_DAYS and (fc['load'] and fp['load'] or days == 0):
        return 'sure', ', '.join(why)
    if (car or drv) and (days is None or days <= DOUBT_DAYS):
        return 'doubt', ', '.join(why)
    if days is not None and days <= 1 and route >= 2 and not (fc['surname'] and fp['surname']):
        return 'doubt', ', '.join(why) + ' — водителя в одной из заявок нет'
    return None, ''


def load_state():
    return ff.load_cache(STATE) or {'folders': {}}


def clean(s, limit=60):
    s = re.sub(r'[\\/:*?"<>|\r\n\t]+', ' ', s or '')
    s = re.sub(r'\s+', ' ', s).strip(' .')
    return s[:limit].strip(' .') or 'без названия'


def client_name(card):
    n = card.get('counterparty') or ''
    n = re.sub(r'^(ООО|ОАО|ЗАО|АО|ПАО|ИП|ТК)(\s+|(?=[А-ЯЁA-Z][а-яё]))', '',
               n.replace('«', '').replace('»', '').replace('"', '').strip())
    return clean(n, 50) if n else 'Клиент не определён'


MAX_CLIENTS = 3  # больше разных клиентов в одной перевозке — скорее ошибка склейки, такое — в «Проверить»


def norm_org(s):
    s = (s or '').lower().replace('ё', 'е')
    s = re.sub(r'\b(ооо|оао|зао|ао|пао|ип|тк|компания|транспортная)\b|[«»"“”„()]', ' ', s)
    return re.sub(r'\s+', ' ', s).strip()


def doc_key(c):
    """Один и тот же документ, пришедший несколько раз (подписанный, «новая», (1)) — один ключ."""
    f = c['f']
    num = (c.get('num') or '').lower() if re.search(r'\d', c.get('num') or '') else ''  # «б/н» — не номер
    d = f['load'] or f['doc']
    if c['kind'] == 'Заявка с клиентом':
        if num and len(num) >= 2 and norm_org(c.get('counterparty')):
            return ('c', num, norm_org(c['counterparty']))
    else:
        if f['plates'] and d:
            return ('p', min(f['plates']), d.isoformat())
        if num and d:
            return ('p', num, d.isoformat())
    return ('f', c['path'])


class Groups:
    """Объединение заявок в перевозки (union-find)."""

    def __init__(self, items):
        self.up = {id(x): id(x) for x in items}

    def top(self, i):
        while self.up[i] != i:
            self.up[i] = self.up[self.up[i]]
            i = self.up[i]
        return i

    def join(self, a, b):
        self.up[self.top(id(a))] = self.top(id(b))


def build():
    cards = ff.load_cache(KARTOTEKA) or []
    z = [c for c in cards if c.get('type') == 'Заявка' and os.path.exists(c.get('path', ''))]
    known = bk.entry_texts()
    raw_other = bk.other_texts()
    fixes = ff.load_cache(ff.FIXES)
    for c in z:
        c['f'] = features(c, raw_text(c, known, raw_other, fixes))
        c['key'] = doc_key(c)
    clients = [c for c in z if c['kind'] == 'Заявка с клиентом']
    carriers = [c for c in z if c['kind'] == 'Заявка перевозчику']
    unclear = [c for c in z if c['kind'] not in ('Заявка с клиентом', 'Заявка перевозчику', 'Заявка без ВЛ')]

    g = Groups(clients + carriers)
    first = {}
    for c in clients + carriers:  # экземпляры одного документа
        if c['key'][0] != 'f':
            g.join(c, first.setdefault(c['key'], c))
    links = {}  # пара клиент-перевозчик → (уровень, почему)
    for p in carriers:
        for c in clients:
            lvl, why = compare(c, p)
            if lvl:
                links[(id(c), id(p))] = (lvl, why, c, p)
    for lvl, why, c, p in links.values():
        if lvl == 'sure':
            g.join(c, p)

    trips = {}
    for x in clients + carriers:
        trips.setdefault(g.top(id(x)), []).append(x)
    sure, doubt_trips = [], []
    for members in trips.values():
        cl = [x for x in members if x['kind'] == 'Заявка с клиентом']
        pr = [x for x in members if x['kind'] == 'Заявка перевозчику']
        if not cl or not pr:
            continue
        why = sorted({links[(id(c), id(p))][1] for c in cl for p in pr if links.get((id(c), id(p)), ('',))[0] == 'sure'})
        trip = {'clients': cl, 'carriers': pr, 'why': why[0] if why else 'тот же документ'}
        (doubt_trips if len({c['key'] for c in cl}) > MAX_CLIENTS else sure).append(trip)
    in_sure = {id(x) for t in sure for x in t['clients'] + t['carriers']}

    # сомнительные: у каждой заявки без пары — лучший кандидат (если есть)
    doubt, seen = [], set()
    rank = lambda why: ('машина' in why) * 4 + ('водитель' in why) * 2 + ('±0' in why)
    for lvl, why, c, p in sorted(links.values(), key=lambda v: -rank(v[1])):
        if id(c) in in_sure and id(p) in in_sure:
            continue
        a, b = g.top(id(c)), g.top(id(p))
        if a in seen and b in seen:
            continue
        seen |= {a, b}
        doubt.append({'clients': trips[a] if a in trips else [c], 'carriers': trips[b] if b in trips else [p],
                      'why': why + ('' if lvl == 'doubt' else ' (одна из заявок уже в другой паре)'),
                      'client': c, 'carrier': p})
    for t in doubt_trips:
        doubt.append({**t, 'client': t['clients'][0], 'carrier': t['carriers'][0],
                      'why': f'в одной машине {len({c["key"] for c in t["clients"]})} разных клиентов — проверь склейку'})
    in_doubt = {id(d['client']) for d in doubt} | {id(d['carrier']) for d in doubt}

    def lone(items):  # по одному экземпляру на документ
        out, keys = [], set()
        for x in items:
            k = g.top(id(x))
            if id(x) in in_sure or k in keys or any(g.top(i) == k for i in in_doubt):
                continue
            keys.add(k)
            out.append(x)
        return out

    return {'sure': sure, 'doubt': doubt, 'lone_c': lone(clients), 'lone_p': lone(carriers), 'unclear': unclear,
            'total': len(z), 'clients': len(clients), 'carriers': len(carriers), 'cards': cards}


# ---------- отчёт ----------
MAIL_DIR = os.path.join(ff.WORK, 'Почта')  # сюда кладёт вечернее скачивание (mail-downloader/nightly_mail.py)


def received(c):
    m = re.match(r'(\d\d)\.(\d\d)\.(20\d\d)', c.get('received') or '')
    return date(int(m[3]), int(m[2]), int(m[1])) if m else None


def fmt(d):
    return d.strftime('%d.%m.%Y') if d else ''


def write_report(res, made, since, docs=None):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
    blue, new_fill = '1E6FE0', PatternFill('solid', fgColor='FFF4D6')
    head = Font(name='Arial', bold=True, color='FFFFFF')
    font, bold = Font(name='Arial', size=9), Font(name='Arial', size=10, bold=True)
    link = Font(name='Arial', size=9, color='0B4AA8', underline='single')
    is_new = lambda items: any((received(x) or date.min) >= since for x in items)

    wb = Workbook()
    summary = wb.active
    summary.title = 'Сводка'

    def sheet(title, cols, rows, note):
        """rows: [(новое?, [значение | (текст, ссылка)])] — новое сверху и подсвечено. Возвращает (всего, новых)."""
        ws = wb.create_sheet(title)
        ws.cell(row=1, column=1, value=note).font = Font(name='Arial', size=9, italic=True, color='6B6B6B')
        for i, (name, w) in enumerate(cols, 1):
            c = ws.cell(row=2, column=i, value=name)
            c.font, c.fill = head, PatternFill('solid', fgColor=blue)
            c.alignment = Alignment(vertical='center', wrap_text=True)
            ws.column_dimensions[get_column_letter(i)].width = w
        rows = sorted(rows, key=lambda r: not r[0])
        for r, (new, vals) in enumerate(rows, 3):
            for i, v in enumerate(vals, 1):
                txt, href = v if isinstance(v, tuple) else (v, None)
                c = ws.cell(row=r, column=i, value=bk.ILLEGAL.sub(' ', txt) if isinstance(txt, str) else txt)
                c.font = link if href else font
                if href:
                    c.hyperlink = href
                if new:
                    c.fill = new_fill
        ws.freeze_panes = 'A3'
        ws.auto_filter.ref = f'A2:{get_column_letter(len(cols))}{len(rows) + 2}'
        return len(rows), sum(1 for r in rows if r[0])

    def doc(c):
        return (c['file'], c['path'])

    def when(c):
        return fmt(c['f']['load'] or c['f']['doc'])

    def route(c):
        return '–'.join(x for x in (c['f']['from'], c['f']['to']) if x)

    trips = []
    for t in res['sure']:
        c = sorted(t['clients'], key=lambda c: (not c.get('counterparty'), c['path']))[0]
        folders = t.get('folders') or ['']
        trips.append((is_new(t['clients'] + t['carriers']),
                      [c.get('counterparty') or '', when(c), route(c), c['f']['driver'],
                       len(t['clients']), len(t['carriers']), t['why'],
                       (os.path.basename(folders[0]), folders[0]) if folders[0] else '',
                       f'+ ещё клиентов: {len(folders) - 1}' if len(folders) > 1 else '']))
    n_trips = sheet('Перевозки', [('Клиент', 30), ('Погрузка', 11), ('Маршрут', 26), ('Водитель', 22), ('Заявок клиента', 9),
                                  ('Заявок перевозчику', 10), ('Почему вместе', 40), ('Папка', 44), ('', 16)], trips,
                    'Уверенные пары: совпала машина или водитель и дата погрузки (±2 дня). Файлы из почты перенесены в папку перевозки. Жёлтым — новое.')
    doubts = [(is_new([d['client'], d['carrier']]),
               [doc(d['client']), d['client'].get('counterparty') or '', when(d['client']),
                doc(d['carrier']), d['carrier'].get('counterparty') or '', when(d['carrier']), d['why']])
              for d in res['doubt']]
    n_doubt = sheet('Проверить', [('Заявка с клиентом', 40), ('Клиент', 26), ('Дата', 11), ('Заявка перевозчику', 40),
                                  ('Перевозчик', 26), ('Дата', 11), ('Почему похоже', 46)], doubts,
                    'Похоже на пару, но программа не уверена — в папки не положено. Проверь глазами.')

    def lone_rows(items):
        return [((received(c) or date.min) >= since,
                 [doc(c), c.get('counterparty') or '', c.get('num') or '', when(c), route(c), c['f']['driver'],
                  ', '.join(sorted(c['f']['plates'])), c.get('received') or '']) for c in items]
    lone_cols = [('Файл', 44), ('Контрагент', 28), ('№', 10), ('Дата', 11), ('Маршрут', 24), ('Водитель', 22),
                 ('Машина', 14), ('Получен', 11)]
    n_lc = sheet('Клиент без пары', lone_cols, lone_rows(res['lone_c']),
                 'Заявки с клиентом, к которым не нашлась заявка перевозчику (или в ней нет водителя и машины).')
    n_lp = sheet('Перевозчик без пары', lone_cols, lone_rows(res['lone_p']),
                 'Заявки ВЛ перевозчику, к которым не нашлась заявка с клиентом.')
    n_un = sheet('Чья заявка — не ясно', lone_cols, lone_rows(res['unclear']),
                 'Не понятно, кто здесь заказчик, а кто перевозчик — такие в пары не берутся.')
    mail_dir = os.path.normcase(MAIL_DIR) + os.sep
    unread = [((received(c) or date.min) >= since, [doc(c), c['type'], c.get('received') or '', c.get('check') or ''])
              for c in res['cards'] if os.path.normcase(c.get('path', '')).startswith(mail_dir)
              and (c.get('check') == 'не читается' or c['type'] in ('Не распознано', 'Фото без текста'))]
    n_ur = sheet('Не прочитано', [('Файл', 50), ('Тип', 20), ('Получен', 11), ('Почему', 20)], unread,
                 'Файлы из вечерней почты, текст которых не удалось прочитать (плохой скан, архив, видео).')

    docs = docs or {'tn': [], 'buh': [], 'drv': [], 'junk': []}
    fresh = lambda c: (received(c) or date.min) >= since
    place = lambda folder: (os.path.relpath(folder, OUT), folder) if folder else ''

    def linked_rows(items, with_kind):
        rows = []
        for x in items:
            t = x['target']
            res_txt = x.get('status') or {'sure': 'перенесён к перевозке', 'doubt': 'в Почте — проверь'}.get(
                x['level'], 'в Почте — перевозка не найдена')
            rows.append((fresh(x['card']), [doc(x['card']), x['card'].get('received') or '']
                         + ([x['card'].get('kind') or '', x['card'].get('amount'), x['cp']] if with_kind else [])
                         + [x['info'].get('subject', ''), res_txt,
                            place(x['folder']) if x['folder'] else (t['title'] if t else ''), x['why']]))
        return rows
    n_tn = sheet('ТН', [('ТН (где лежит сейчас)', 40), ('Получена', 11), ('Тема письма', 34), ('Итог', 22),
                       ('Перевозка / на что похожа', 44), ('Почему', 44)], linked_rows(docs['tn'], False),
                 'ТН из почты. Уверенные — перенесены в папку перевозки; остальные лежат в «Почте» — проверь сам.')
    n_buh = sheet('Счета и акты', [('Документ (где лежит сейчас)', 44), ('Получен', 11), ('Вид', 12), ('Сумма', 12),
                                   ('Контрагент', 24), ('Тема письма', 30), ('Итог', 22), ('Перевозка / на что похожа', 40),
                                   ('Почему', 40)], linked_rows(docs['buh'], True),
                  'Счета, акты, УПД из почты: к перевозке или к заявке перевозчика; не нашлась заявка — в «_Счета и акты» по контрагенту.')
    n_drv = sheet('Водители и машины', [('Документ', 44), ('Получен', 11), ('Папка', 40), ('Имя папки взято', 22),
                                        ('Тема письма', 34)],
                  [(fresh(x['card']), [doc(x['card']), x['card'].get('received') or '', place(x['folder']), x['how'],
                                       x['info'].get('subject', '')]) for x in docs['drv']],
                  'ВУ, паспорта, СТС, ПТС, аренда — перенесены в Перевозки\\_Водители и машины\\<Фамилия>\\.')

    # сводка
    for col, w in zip('ABCD', (46, 14, 14, 44)):
        summary.column_dimensions[col].width = w

    def head_row(row, titles):
        for i, t in enumerate(titles, 1):
            c = summary.cell(row=row, column=i, value=t)
            c.font, c.fill = head, PatternFill('solid', fgColor=blue)

    summary.cell(row=1, column=1, value=f'Отчёт за {date.today():%d.%m.%Y}').font = Font(name='Arial', size=14, bold=True)
    row = 3
    mail = ff.load_cache(MAIL_STATUS)
    if mail.get('boxes'):
        head_row(row, ('Почта', 'Писем', 'Новых файлов', 'Итог'))
        for b in mail['boxes']:
            row += 1
            vals = (b.get('login'), b.get('letters'), b.get('files'), b.get('error') or f'ок, {b.get("period", "")}')
            for i, v in enumerate(vals, 1):
                c = summary.cell(row=row, column=i, value=v)
                c.font = font
                if b.get('error'):
                    c.fill = PatternFill('solid', fgColor='FDE2E1')
        row += 1
        summary.cell(row=row, column=1, value=f'Скачано: {mail.get("run", "")}').font = font
        row += 2
    head_row(row, ('Заявки', 'Всего', 'Новых'))
    for title, (n, new) in (('Перевозки собраны (уверенно)', n_trips), ('Проверить — похоже на пару', n_doubt),
                            ('Заявка с клиентом без пары', n_lc), ('Заявка перевозчику без пары', n_lp),
                            ('Чья заявка — не ясно', n_un), ('Файлы из почты — не прочитаны', n_ur),
                            ('ТН из почты', n_tn), ('Счета и акты из почты', n_buh), ('Документы водителей и машин', n_drv)):
        row += 1
        for i, v in enumerate((title, n, new or None), 1):
            c = summary.cell(row=row, column=i, value=v)
            c.font = bold if i == 1 else font
            if new and i == 3:
                c.fill = new_fill
    row += 2
    for t in (f'«Новых» — пришли с {since:%d.%m.%Y} (день прошлого отчёта); на листах они сверху и жёлтым.',
              f'Перенесено файлов из почты: {sum(made.values())}. Папки — {OUT}\\<Клиент>\\. Старый архив не тронут; '
              'в «Почте» осталось то, что надо проверить. Вернуть всё назад: python tools/razbor_pochty.py --undo',
              'Номера машин, фамилии и даты программа читает из текста; в сканах бывают ошибки — сомнительное в «Проверить».',
              'Пересобрать вручную: python tools/pary_zayavok.py'):
        summary.cell(row=row, column=1, value=t).font = Font(name='Arial', size=9, color='6B6B6B')
        row += 1

    os.makedirs(OUT, exist_ok=True)
    out = os.path.join(OUT, f'Отчёт {date.today():%Y-%m-%d}.xlsx')
    tmp = out[:-5] + '.tmp.xlsx'
    wb.save(tmp)
    try:
        os.replace(tmp, out)
    except PermissionError:  # отчёт открыт в Excel — пишем рядом
        out = out[:-5] + f' {datetime.now():%H-%M}.xlsx'
        os.replace(tmp, out)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--no-copy', action='store_true', help='только отчёт, файлы не переносить')
    a = ap.parse_args()
    state = load_state()
    since = to_date(state.get('last_run', '')) or date.today()
    res = build()
    import razbor_pochty  # почта раскладывается ПЕРЕНОСОМ: перевозки, ТН, счета/акты, водители, ПОМОЙКА
    docs = razbor_pochty.razlozhit(res, state, dry=a.no_copy)
    out = write_report(res, {'перенесено': docs['moved']}, since, docs)
    if not a.no_copy:
        state['last_run'] = f'{date.today():%d.%m.%Y}'
        ff.save_cache(state, STATE)
    sure = lambda k: sum(1 for x in docs[k] if x['level'] == 'sure')
    print(f'Перевозок: {len(res["sure"])}, проверить: {len(res["doubt"])}, ТН к перевозкам: {sure("tn")} из {len(docs["tn"])}, '
          f'счета/акты к перевозкам: {sure("buh")} из {len(docs["buh"])}, док. водителей: {len(docs["drv"])}, '
          f'в ПОМОЙКУ: {len(docs["junk"])}, перенесено файлов: {docs["moved"]} → {out}')


if __name__ == '__main__':
    main()
