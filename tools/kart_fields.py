# Взято из чата «Excel заявки с клиентами + УПД» (24.10.2026) для картотеки документов — tools/build_kartoteka.py
"""Черновое извлечение полей заявки (номер, дата, сумма, заказчик, водитель, погрузка) + ключевые строки для ручной проверки."""
import re
from datetime import date

MONTHS = {'январ': 1, 'феврал': 2, 'март': 3, 'апрел': 4, 'мая': 5, 'май': 5, 'июн': 6, 'июл': 7, 'август': 8, 'сентябр': 9, 'октябр': 10, 'ноябр': 11, 'декабр': 12}
VL = re.compile(r'восточн\S{0,3}\s*логист|vostok|3812166710|шерстов', re.I)

def norm_lines(text):
    lines = [re.sub(r'[ \t ]+', ' ', l).strip() for l in text.splitlines()]
    return [l for l in lines if l]

def month_num(s):
    s = s.lower()
    if s.isdigit():
        return int(s)
    for k, v in MONTHS.items():
        if s.startswith(k):
            return v
    return None

DATE = r'[«"]?\s*(\d{1,2})\s*[»"]?[\s.,/-]*(\d{1,2}|[а-яё]{3,9})[\s.,/-]*(20\d\d|2[56])(?!\d)'

def find_date(s):
    for m in re.finditer(DATE, s, re.I):
        d, mo, y = int(m.group(1)), month_num(m.group(2)), m.group(3)
        if not mo or not (1 <= d <= 31 and 1 <= mo <= 12):
            continue
        y = int(y) if len(y) == 4 else 2000 + int(y)
        if 2025 <= y <= date.today().year + 1:  # было «≤ 2026» — с 2027 года даты перестали бы находиться
            return f'{d:02d}.{mo:02d}.{y}'
    return ''

TITLE = re.compile(r'(заявк|заказ[\s-]*наряд|поручени|договор)', re.I)
NUM = re.compile(r'(?:№|\bN[°ºo]?|номер)\s*[:.]?\s*([A-Za-zА-Яа-я]{0,4}[\s-]?\d[\w/\\.\-]*|б/н)', re.I)

def title_info(lines):
    for i, l in enumerate(lines[:80]):
        if TITLE.search(l) and not re.search(r'^\s*\d+\.\s|в соответствии|согласно|по договору', l, re.I):
            chunk = ' '.join(lines[i:i + 3])
            m = NUM.search(chunk)
            if not m and not re.search(r'\bот\b', chunk):
                continue
            num = m.group(1).strip(' .,') if m else ''
            after = chunk[m.end():] if m else chunk
            return num, find_date(after) or find_date(chunk), l[:160]
    return '', '', ''

MONEY = re.compile(r'(?<![\d.,])(\d{1,3}(?:[  .]\d{3})+|\d{4,7})([.,]\d{1,2})?(?![\d])(\s*(?:руб|р\.|₽|rub|т\.?р))?', re.I)
MONEY_KEY = re.compile(r'ставк|стоимост|сумм|фрахт|цена|оплат|итого|руб|₽|без ндс|с ндс|ндс|вознагражден', re.I)
BAD_LINE = re.compile(r'\bинн\b|\bкпп\b|огрн|\bбик\b|р/с\s*№?\s*\d|к/с\s*№?\s*\d|сч[её]т\s*№\s*\d{10}|\bтел\b|телефон|паспорт|расч[её]тный сч[её]т\s*№?\s*\d|корр\S* сч|штраф|неустойк|простой|сверхнорматив|за кажд|в сутки|/сут|\bчас|опоздан|\bкг\b|тонн|объявленн|код участника|код в ати|\bати\b', re.I)
GOOD_LINE = re.compile(r'ставк|стоимост|фрахт|сумма|итого|цена|вознагражден|к оплате', re.I)

STRONG = re.compile(r'(?<![а-яё])ставк|стоимост\S* (перевозк|услуг|фрахт|рейс)|стоимост\S*,? сроки|стоимость и форма|сумм\S* фрахт|фрахт|стоимость:|провозная плата|цена перевозк|к оплате|оплата\s*:', re.I)
CLAUSE = re.compile(r'^\s*\d{1,2}\.\d{1,2}\.')

def money_candidates(lines):
    """(сумма, вес, строка): вес 3 — рядом со «ставка/стоимость перевозки/фрахт», 1 — просто «руб»."""
    out = []
    for i, l in enumerate(lines):
        if CLAUSE.match(l) or BAD_LINE.search(l):
            continue
        prev = ' '.join(lines[max(0, i - 2):i])
        strong = bool(STRONG.search(l)) or (bool(STRONG.search(prev)) and not CLAUSE.match(lines[i - 1] if i else ''))
        if not (strong or MONEY_KEY.search(l)):
            continue
        for m in MONEY.finditer(l):
            raw = m.group(1)
            v = int(re.sub(r'\D', '', raw))
            if not (3000 <= v <= 3000000) or 2020 <= v <= 2030:
                continue
            if raw.isdigit() and len(raw) == 6 and not (m.group(2) or m.group(3)) and not re.search(r'руб|(?<![а-яё])ставк|стоим|ндс|₽|фрахт', l, re.I):
                continue  # похоже на почтовый индекс
            if re.search(r'ндс\D{0,12}$', l[:m.start()].lower()[-20:]):
                continue  # это сумма НДС, а не ставка
            if re.search(r'предоплат|аванс|50\s*%|30\s*%|из них', l[max(0, m.start() - 40):m.start()].lower()):
                continue
            out.append((v, 3 if strong else 1, l[:150]))
    return out

def amount_ctx(c, lines):
    """Строка выбранной суммы и следующая за ней — для определения НДС."""
    a = pick_amount(c)
    for v, w, l in c:
        if v == a:
            i = next((k for k, s in enumerate(lines) if s[:150] == l), None)
            return ' '.join(lines[i:i + 2]) if i is not None else l
    return ''

def pick_amount(c):
    if not c:
        return None
    top = max(w for _, w, _ in c)
    return next(v for v, w, _ in c if w == top)

def amount_doubt(c):
    """Сомнение: нет сильного кандидата или есть другая сильная сумма, сравнимая с выбранной (не НДС и не аванс)."""
    top = [v for v, w, _ in c if w == 3]
    if not top:
        return True
    a = top[0]
    return any(v != a and v > a * 0.4 for v in top[1:])

VAT_NO = re.compile(r'без\s*ндс|ндс не облага|без учета ндс|ндс\s*-?\s*нет|без\s*нщс|без\s*ндc', re.I)
VAT_YES = re.compile(r'(в т\.?\s*ч\.?|в том числе|включая|с|вкл\.?)\s*ндс|ндс\s*\(?\d{1,2}\s*%', re.I)

def vat(text, amount_line=''):
    for s in (amount_line, text):
        no, yes = VAT_NO.search(s), VAT_YES.search(s)
        if no and (not yes or no.start() < yes.start()):
            return 'без НДС'
        if yes:
            return 'с НДС'
    return ''

FIO = r'([А-ЯЁ][а-яё]+(?:-[А-ЯЁ][а-яё]+)?\s+(?:[А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+(?:вич|вна|ич|кызы|оглы|угли)\b|[А-ЯЁ]\.\s?[А-ЯЁ]\.?))'
NOT_DRIVER = re.compile(r'в лице|руководител|директор|менеджер|логист|диспетчер|контактн|бухгалтер|ответственн', re.I)

def driver(lines):
    for i, l in enumerate(lines):
        if re.search(r'водител', l, re.I) and not re.search(r'водитель (должен|обязан|не)|водителю|водителем', l, re.I):
            for j in range(i, min(i + 4, len(lines))):
                s = lines[j]
                if j > i and NOT_DRIVER.search(s):
                    continue
                part = s.split('водител', 1)[-1] if j == i and 'водител' in s.lower() else s
                m = re.search(FIO, part)
                if m and not NOT_DRIVER.search(part[:m.start()]):
                    return m.group(1)
    return ''

LOAD_LABEL = re.compile(r'(адрес|место|пункт)[^\n]{0,25}(погрузк|загрузк)|^(погрузка|загрузка)\b|грузоотправитель и место погрузки', re.I)
UNLOAD = re.compile(r'выгрузк|разгрузк|грузополучател', re.I)

def loading(lines):
    date = place = ''
    for i, l in enumerate(lines):
        low = l.lower()
        if not date and re.search(r'(дата|время|срок)[^\n]{0,25}(погрузк|загрузк|подач)|(погрузк|загрузк)[^\n]{0,15}(дата|:)', low) and not UNLOAD.search(low[:15]):
            date = find_date(' '.join(lines[i:i + 3]))
        if not place and LOAD_LABEL.search(l) and not UNLOAD.search(low.split('погруз')[0].split('загруз')[0]):
            rest = re.split(r'(?:погрузк|загрузк)\S*', l, maxsplit=1, flags=re.I)[-1]
            rest = re.sub(r'^[\s:.\-1)]+', '', rest).rstrip(' :-')  # было strip(' :.-1)') — съедало «д. 1» в конце адреса
            cand = rest if len(re.findall(r'[А-Яа-яЁё]{3,}', rest)) >= 2 else ''
            k = i + 1
            while not cand and k < min(i + 4, len(lines)):
                s = lines[k]
                if not re.search(r'дата|время|контакт|способ|тип|выгруз|разгруз', s, re.I) and len(re.findall(r'[А-Яа-яЁё]{3,}', s)) >= 2:
                    cand = s
                k += 1
            place = cand[:120]
    return date, place

ORG = re.compile(r'(?<![А-Яа-яЁёA-Za-z])((?:ООО|ОАО|ЗАО|АО|ПАО|ИП)\s+[«"“„]*\s*[^«"”»,\n]{2,45}?[»"”]*|(?:ООО|ОАО|ЗАО|АО|ПАО)\s*[«"“„]+[^«"”»\n]{2,45}[»"”]+)(?=[,\n(]|\s+(?:ИНН|в лице|именуем|$)|$)')
ORG_JUNK = re.compile(r'кузов|прицеп|загрузк|подвижн|автотранспорт|транспортного средства|\bтс\b|ипальн|наименован|контактн|адрес|телефон|банк|\bпао\)|нужное', re.I)

def _short(t):
    t = re.sub(r'общество\s+с\s+ограниченной\s+ответственностью', 'ООО', t, flags=re.I)
    t = re.sub(r'индивидуальный\s+предприниматель', 'ИП', t, flags=re.I)
    t = re.sub(r'(открытое|публичное|закрытое)?\s*акционерное\s+общество', 'АО', t, flags=re.I)
    return t

def client(text):
    t = _short(re.sub(r'[ \t ]+', ' ', text))
    c = _client(t)
    return '' if (not c or ORG_JUNK.search(c)) else re.sub(r'\s+', ' ', c).strip(' ,.')

def _client(t):
    # явная метка «Заказчик: ...»
    for m in re.finditer(r'заказчик\W{0,5}\s*(?:наименование\s*)?[:\-–]?\s*', t, re.I):
        seg = t[m.end():m.end() + 120]
        o = ORG.search(seg)
        if o and not VL.search(o.group(1)) and o.start() < 25:
            return o.group(1).strip()
    # «…, именуемое в дальнейшем Заказчик»
    for m in re.finditer(r'именуем\S*\s*(?:в дальнейшем|далее)?\s*\W{0,3}\s*заказчик', t, re.I):
        seg = t[max(0, m.start() - 200):m.start()]
        orgs = [o.group(1) for o in ORG.finditer(seg) if not VL.search(o.group(1))]
        if orgs:
            return orgs[-1].strip()
    for o in ORG.finditer(t[:2500]):
        if not VL.search(o.group(1)):
            return o.group(1).strip()
    return ''

def key_lines(lines, limit=12):
    keys = re.compile(r'заявк|№|ставк|стоимост|сумм|фрахт|руб|водител|погрузк|загрузк|маршрут|заказчик|перевозчик|исполнител|экспедитор', re.I)
    return [l[:170] for l in lines if keys.search(l) and len(l) > 3][:limit]

NOT_ZAYAVKA = re.compile(r'^\s*(акт\b|сч[её]т\b|счет-фактура|универсальный передаточный|накладная|print-order|требования по оформлению)', re.I)

def extract(text):
    lines = norm_lines(text)
    num, date, tline = title_info(lines)
    money = money_candidates(lines)
    ld, lp = loading(lines)
    head = ' '.join(lines[:6])
    return {'num': num, 'date': date, 'title': tline, 'money': [m[0] for m in money if m[1] == 3][:5], 'amount': pick_amount(money),
            'doubt': amount_doubt(money),
            'vat': vat(text, amount_ctx(money, lines)), 'client': client(text), 'driver': driver(lines), 'load_date': ld, 'load_place': lp,
            'not_zayavka': bool(NOT_ZAYAVKA.search(head)) and not re.search(r'заявк', ' '.join(lines[:3]), re.I),
            'keys': key_lines(lines)}
