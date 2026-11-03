# Водитель из файлов: распознать фото / PDF / Word (паспорт, права, СТС, карточка водителя) и разобрать поля.
# Движок — тот же, что в «Распознать сканы» (tools/ocr_scans.py): RapidOCR, кириллица. Держим его загруженным.
# Разбор работает и на «плоском» тексте из кеша поиска (без строк, в нижнем регистре), и на свежем OCR.
import io
import re
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))

IMAGE_EXT = {'.jpg', '.jpeg', '.jfif', '.png', '.bmp', '.tif', '.tiff', '.webp'}
_engine = None
_lock = threading.Lock()  # один движок на сервер — запросы распознаём по очереди


def engine():
    global _engine
    if _engine is None:
        from rapidocr import RapidOCR
        from rapidocr.utils.typings import LangRec, ModelType, OCRVersion
        _engine = RapidOCR(params={
            'Rec.lang_type': LangRec.ESLAV, 'Rec.ocr_version': OCRVersion.PPOCRV5, 'Rec.model_type': ModelType.MOBILE,
            'Det.ocr_version': OCRVersion.PPOCRV5, 'Det.model_type': ModelType.MOBILE,
            'Global.use_cls': False, 'Global.log_level': 'error'})
    return _engine


# ---------- распознавание ----------

def _lines(res, width):
    """Блоки текста OCR → строки сверху вниз (блоки с близкой высотой — в одну строку).
    Блоки из правой половины листа отделяются табуляцией: «левое\tправое» — так разбор реквизитов
    различает две колонки (наши | клиента), которые OCR иначе склеивает в одну строку."""
    if not res.txts:
        return ''
    items = []
    for box, t in zip(res.boxes, res.txts):
        ys = [p[1] for p in box]
        items.append(((min(ys) + max(ys)) / 2, min(p[0] for p in box), max(ys) - min(ys), t))
    items.sort()
    mid = width * 0.48

    def join(cur):
        cur = sorted(cur)
        left = ' '.join(t for x, t in cur if x < mid)
        right = ' '.join(t for x, t in cur if x >= mid)
        return f'{left}\t{right}' if right else left

    lines, cur, cur_y = [], [], None
    for y, x, h, t in items:
        if cur and abs(y - cur_y) > max(h, 8) * 0.6:
            lines.append(join(cur))
            cur = []
        cur.append((x, t))
        cur_y = y if len(cur) == 1 else cur_y
    lines.append(join(cur))
    return '\n'.join(lines)


def _ocr_img(img):
    import numpy as np
    with _lock:
        return _lines(engine()(np.array(img.convert('RGB'))), img.width)


def _score(text):
    """Насколько текст похож на русский документ: сколько слов из 3+ кириллических букв."""
    return len(re.findall(r'[А-Яа-яЁё]{3,}', text))


def ocr_image(img):
    """Фото: уменьшаем, распознаём; если текста мало — пробуем повернуть (фото боком или вверх ногами).
    Номер паспорта напечатан вертикально — для него отдельно читаем повёрнутую на 90° картинку."""
    from PIL import ImageOps
    img = ImageOps.exif_transpose(img)
    img.thumbnail((1800, 1800))
    best = _ocr_img(img)
    if _score(best) < 12:
        for angle in (90, 270, 180):
            t = _ocr_img(img.rotate(angle, expand=True))
            if _score(t) > _score(best) * 1.5 + 3:
                best = t
    if re.search(r'паспорт|выдан|отчество|рождени|уфмс|мвд|подразделени|\bмуж\b|\bжен\b', best, re.I) \
            and not re.search(r'P[NН<]RUS|водительск|свидетельств', best, re.I) and not PASSPORT_NUM.search(best):
        best += '\n' + _ocr_img(img.rotate(90, expand=True)) + '\n' + _ocr_img(img.rotate(270, expand=True))
    return best


def read_file(name, data):
    """Текст файла: фото и сканы — OCR; PDF с текстом и Word — как есть."""
    ext = Path(name).suffix.lower()
    if ext in IMAGE_EXT:
        from PIL import Image
        return ocr_image(Image.open(io.BytesIO(data)))
    if ext == '.pdf':
        import pymupdf
        from PIL import Image
        out = []
        with pymupdf.open(stream=data, filetype='pdf') as doc:
            for page in list(doc)[:4]:
                t = page.get_text()
                if len(t.strip()) < 40:  # скан — распознаём картинку страницы
                    pix = page.get_pixmap(dpi=200)
                    t = ocr_image(Image.open(io.BytesIO(pix.tobytes('png'))))
                out.append(t)
        return '\n'.join(out)
    if ext == '.docx':
        import zipfile
        import html
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            x = z.read('word/document.xml').decode('utf-8', 'ignore')
        x = re.sub(r'</w:p>|<w:br/>', '\n', x)
        x = re.sub(r'<w:tab/>|</w:tc>', ' ', x)
        return html.unescape(re.sub(r'<[^>]+>', '', x))
    if ext == '.heic':
        raise ValueError('Фото HEIC (iPhone) не открывается — сохраните как JPG или скопируйте картинку и вставьте Ctrl+V')
    if ext in ('.txt', '.csv'):
        return data.decode('utf-8', 'ignore')
    raise ValueError(f'Не умею читать файлы {ext} — нужны фото, PDF или Word (.docx)')


# ---------- разбор полей ----------

CYR = 'АВЕКМНОРСТУХ'
LAT2CYR = str.maketrans('ABEKMHOPCTYXabekmhopctyx', 'АВЕКМНОРСТУХавекмнорстух')
HOMO = str.maketrans('ABCEHKMOPTXYaceopxyb', 'АВСЕНКМОРТХУасеорхуЬ')
# машиночитаемая строка паспорта РФ: латиница/цифры → русские буквы (приказ ФМС)
MRZ_TR = dict(zip('ABVGDE2JZIQKLMNOPRSTUFHC34WXY9678', 'АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ'))
ISSUER = re.compile(r'\b(УФМС|ОУФМС|МВД|ОВД|УВД|ГУ|ТП|ОТДЕЛ\w*|ОТДЕЛЕНИ\w*|МИГРАЦИ\w*)\b', re.I)
DATE = r'(\d{2})[.\s,/-]{1,2}(\d{2})[.\s,/-]{1,2}((?:19|20)\d{2})'
PASSPORT_NUM = re.compile(r'(?<![\d.])(\d{2})\s?(\d{2})\s?(\d{6})(?![\d.])')
PATRON = r'(?:вич|вна|ична|оглы|кызы|улы)'
WORD = r'[А-ЯЁа-яё][А-ЯЁа-яё-]+'
NOT_NAME = re.compile(r'^(паспорт|россия|российская|федерация|выдан|отделом|отделением|уфмс|мвд|гу|по|области|область|края|край|'
                      r'республики|района|району|города|гор|код|дата|место|рождения|пол|муж|жен|фамилия|имя|отчество|подпись|'
                      r'личный|водитель|водителя|данные|фио|тел|телефон|на|имя|серия|номер|г|обл|в|и)$', re.I)
CATS = {'A', 'A1', 'B', 'B1', 'BE', 'C', 'C1', 'C1E', 'CE', 'D', 'D1', 'D1E', 'DE', 'M', 'TM', 'TB'}


DIGITLIKE = str.maketrans('оОoOзЗ', '000033')


def fix(text):
    """Латиница-двойник в русских словах → кириллица (OCR путает «ИHH», «Py6»);
    в числах буквы-двойники → цифры («180 о00» → «180 000»)."""
    out = []
    for w in re.split(r'(\s+)', text):
        core = w.strip('.,:;()₽')
        if re.search(r'\d', core) and re.fullmatch(r'[\dоОoOзЗ]+', core):
            w = w.translate(DIGITLIKE)
        elif re.search(r'[А-Яа-яЁё]', w):
            w = w.translate(HOMO)
        out.append(w)
    return ''.join(out)


def dates(text):
    res = []
    for m in re.finditer(DATE, text):
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 1 <= d <= 31 and 1 <= mo <= 12:
            res.append((m.start(), f'{d:02d}.{mo:02d}.{y}', m))
    return res


def doc_type(t):
    tl = t.lower()
    if re.search(r'водительск\w*\s+удостовер|driving|permis de conduire|\b4[аa]\)', tl):
        return 'ВУ'
    if re.search(r'свидетельств\w* о регистрац|регистрационн\w* (знак|номер)|идентификационн\w* номер|\bvin\b', tl):
        return 'СТС'
    if re.search(r'паспорт\s+выдан|отчество|место\s+рождени|личный\s+код|\bуфмс\b|оуфмс|мвд\s+по|гу\s+мвд|\bмвд\b|p[nн<]rus', tl):
        return 'паспорт'
    if re.search(r'паспорт', tl):
        return 'карточка'
    return 'другое'


def find_fio(t):
    tl = t
    # 1) подписи «Фамилия … Имя … Отчество …» (паспорт)
    f = re.search(r'фамилия\s+(' + WORD + ')', tl, re.I)
    i = re.search(r'\bимя\s+(' + WORD + ')', tl, re.I)
    o = re.search(r'отчество\s+(' + WORD + ')', tl, re.I)
    if f and i and o and not any(NOT_NAME.match(x.group(1)) for x in (f, i, o)):
        return ' '.join(x.group(1) for x in (f, i, o))
    # 2) права: «1. ФАМИЛИЯ 2. ИМЯ ОТЧЕСТВО»
    m = re.search(r'(?:^|\s)1[.,]?\s+(' + WORD + r')\s+(?:[A-Z]+\s+)?2[.,]?\s+(' + WORD + r')\s+(' + WORD + PATRON + r')\b', tl, re.I)
    if m:
        return ' '.join(m.groups())
    # 3) три слова подряд, третье — отчество
    for m in re.finditer(r'(' + WORD + r')\s+(' + WORD + r')\s+(' + WORD + PATRON + r')\b', tl, re.I):
        if not NOT_NAME.match(m.group(1)) and not NOT_NAME.match(m.group(2)):
            return ' '.join(m.groups())
    return ''


def title(s):
    return ' '.join(w[:1].upper() + w[1:].lower() for w in s.split()) if s else ''


def phone(t):
    m = re.search(r'(?:\+7|\b8)[\s(-]*(\d{3})[\s)-]*(\d{3})[\s-]*(\d{2})[\s-]*(\d{2})\b', t)
    return f'+7 ({m[1]}) {m[2]}-{m[3]}-{m[4]}' if m else ''


D = '[0-9ОЗБ]'                                    # цифра; OCR путает 0→О, 3→З, 6→Б
DIG = str.maketrans('ОЗБ', '036')


def plates(t):
    """Госномера: авто А123ВС38 и прицеп АВ1234 38 (латиница-двойник → кириллица, «з» в цифрах → 3)."""
    u = t.upper().translate(LAT2CYR)
    auto = [f'{m[1]}{m[2].translate(DIG)}{m[3]}{m[4].translate(DIG)}'
            for m in re.finditer(rf'(?<![А-Я0-9])([{CYR}])\s?(\d{D}{{2}})\s?([{CYR}]{{2}})\s?({D}{{2,3}})(?![0-9А-Я])', u)]
    trailer = [f'{m[1]}{m[2].translate(DIG)}{m[3].translate(DIG)}'
               for m in re.finditer(rf'(?<![А-Я0-9])([{CYR}]{{2}})\s?(\d{D}{{3}})\s?({D}{{2,3}})(?![0-9А-Я])', u)]
    return auto, trailer


TO_LAT = str.maketrans('АВЕКМНОРСТХУІ', 'ABEKMHOPCTXYI')


def to_lat(s):
    """Слово с латиницей, где OCR подмешал русские буквы-двойники (SСАNІА) → чистая латиница."""
    return ' '.join(w.translate(TO_LAT) if re.search(r'[A-Za-z]', w) else w for w in s.split(' '))


def inn_ok(inn):
    d = [int(c) for c in inn]
    k = lambda w: sum(a * b for a, b in zip(w, d)) % 11 % 10
    if len(d) == 10:
        return k([2, 4, 10, 3, 5, 9, 4, 6, 8]) == d[9]
    if len(d) == 12:
        return k([7, 2, 4, 10, 3, 5, 9, 4, 6, 8]) == d[10] and k([3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8]) == d[11]
    return False


def _mrz_check(s):
    vals = [int(c) if c.isdigit() else (ord(c) - 55 if c.isalpha() else 0) for c in s]
    return sum(v * w for v, w in zip(vals, [7, 3, 1] * 20)) % 10


def _yymmdd(s, future_ok=False):
    from datetime import date
    yy, mm, dd = int(s[:2]), int(s[2:4]), int(s[4:6])
    if not (1 <= mm <= 12 and 1 <= dd <= 31):
        return ''
    cur = date.today().year % 100
    y = 2000 + yy if yy <= cur or future_ok else 1900 + yy
    return f'{dd:02d}.{mm:02d}.{y}'


def parse_mrz(t, r):
    """Машиночитаемая строка внизу паспорта: ФИО, серия-номер, даты, код — с контрольными цифрами."""
    u = re.sub(r'\s+', '', t.upper()).replace('«', '<').replace('‹', '<')
    l1 = re.search(r'P[NН<]RUS([A-Z0-9]{2,})<<([A-Z0-9]{2,})<([A-Z0-9]{2,})', u)
    if l1:
        r['fio'] = title(' '.join(''.join(MRZ_TR.get(c, '') for c in part) for part in l1.groups()))
        r['fio_mrz'] = True
    l2 = re.search(r'(\d{9})(\d)RUS(\d{6})\d([MF<])[<0-9]{6}[<0-9]?(\d)(\d{6})(\d{6})', u)
    if l2:
        doc, chk, birth, _, last, issued, code = l2.groups()
        r['passport'] = f'{doc[:2]} {doc[2]}{last} {doc[3:]}'
        r['passport_mrz_ok'] = _mrz_check(doc) == int(chk)
        r['birth_date'] = _yymmdd(birth) or r.get('birth_date', '')
        r['passport_date'] = _yymmdd(issued) or r.get('passport_date', '')
        r['passport_code'] = f'{code[:3]}-{code[3:]}'


def caps_lines(t):
    return [l.strip(' .,') for l in t.split('\n')]


def parse_passport(t, r):
    parse_mrz(t, r)
    tl = t.lower()
    lines = caps_lines(t)
    if 'passport' not in r:
        nums = [m for m in PASSPORT_NUM.finditer(t) if not re.match(DATE, m.group(0))]
        near = [m for m in nums if re.search(r'паспорт|серия|№', t[max(0, m.start() - 25):m.start()], re.I)]
        m = (near or nums or [None])[0]
        if m:
            r['passport'] = f'{m[1]} {m[2]} {m[3]}'
    if 'passport_code' not in r:
        k = re.search(r'код\s+подразделени\w*\D{0,15}(\d{3})\s?[-–]?\s?(\d{3})', tl) or \
            re.search(r'(?<![\d-])(\d{3})\s?[-–]\s?(\d{3})(?![\d-])', t)
        if k:
            r['passport_code'] = f'{k[1]}-{k[2]}'
    v = re.search(r'выдан\w*[\s:]*(.{5,160}?)(?:\s+(?:дата\s+выдачи|от)\s*)?' + DATE, t, re.I | re.S)
    who, when = '', ''
    if v:
        who, when = v.group(1), f'{v[2]}.{v[3]}.{v[4]}'
    else:  # подпись «Паспорт выдан» не прочиталась: строки с УФМС/МВД/отделом — до первой даты
        start = next((i for i, l in enumerate(lines) if ISSUER.search(l)), None)
        if start is not None:
            part = []
            for l in lines[start:start + 6]:
                d = re.search(DATE, l)
                if d:
                    part.append(l[:d.start()])
                    when = f'{d[1]}.{d[2]}.{d[3]}'
                    break
                part.append(l)
            who = ' '.join(part) if when else ''
    who = re.sub(r'российская\s+федерация\s*', '', who, flags=re.I)
    who = re.sub(r'\s+', ' ', re.sub(r'^(паспорт\s+)?(выдан\w*\s+)?', '', who.strip(' ,.:'), flags=re.I))
    if len(re.findall(r'[А-Яа-яЁё]{3,}', who)) >= 2:
        r.setdefault('passport_issued_by', who.upper() if who.islower() else who)
    if when:
        r.setdefault('passport_date', when)
    b = re.search(r'рождени\w*\D{0,20}' + DATE, tl) or re.search(r'\b(?:муж|жен)\w*\.?\D{0,12}' + DATE, tl)
    if b:
        r.setdefault('birth_date', f'{b[1]}.{b[2]}.{b[3]}')
    if 'fio' not in r:  # ФИО в паспорте — три строки заглавными подряд, третья — отчество
        for i in range(len(lines) - 2):
            a, b_, c = lines[i:i + 3]
            if all(re.fullmatch(r'[А-ЯЁ][А-ЯЁ-]{1,}', x) and not NOT_NAME.match(x) for x in (a, b_, c)) and re.search(PATRON + '$', c, re.I):
                r['fio'] = title(f'{a} {b_} {c}')
                break


def parse_vu(t, r):
    tl = t.lower()
    m = re.search(r'(?:^|\s)5[.,]?\s*(\d{2})\s?(\d{2})\s?(\d{6})\b', t) or \
        next((x for x in PASSPORT_NUM.finditer(t) if not re.match(DATE, x.group(0))), None)
    if m:
        r['vu'] = f'{m[1]} {m[2]} {m[3]}'
    a = re.search(r'\b4\s?[аa]\)?[.,]?\s*' + DATE, tl)
    b = re.search(r'\b4\s?[bв6ь]\)?[.,]?\s*' + DATE, tl)
    if a:
        r['vu_date'] = f'{a[1]}.{a[2]}.{a[3]}'
    if b:
        r['vu_until'] = f'{b[1]}.{b[2]}.{b[3]}'
    if not a or not b:  # подписи 4a)/4b) потерялись: строка с двумя датами — выдано и действует до
        for l in t.split('\n'):
            ds = dates(l)
            if len(ds) == 2 and int(ds[1][1][-4:]) - int(ds[0][1][-4:]) in (10, 11):
                r.setdefault('vu_date', ds[0][1])
                r.setdefault('vu_until', ds[1][1])
                break
    lines = caps_lines(t)
    for i, l in enumerate(lines):  # «2. ИМЯ ОТЧЕСТВО», фамилия — ближайшая строка выше из одного русского слова
        m = re.fullmatch(r'(?:2[.,]?\s*)?([А-ЯЁ][А-ЯЁ-]+)\s+([А-ЯЁ][А-ЯЁ-]+' + PATRON + ')', l, re.I)
        if m and l.isupper():
            sur = next((x for x in reversed(lines[max(0, i - 3):i]) if re.fullmatch(r'(?:1[.,]?\s*)?[А-ЯЁ][А-ЯЁ-]{1,}', x)), '')
            sur = re.sub(r'^1[.,]?\s*', '', sur)
            r.setdefault('fio', title(f'{sur} {m[1]} {m[2]}'.strip()))
            break
    # категории: строка «9. B C C1 CE …» (или просто строка, где почти все слова — категории)
    lat = t.upper().translate(str.maketrans('АВЕСМТ', 'ABECMT'))
    for l in lat.split('\n'):
        toks = [x for x in re.split(r'[\s,.;]+', re.sub(r'^\s*9[.,)]?\s*', '', l)) if x]
        cats = [x for x in toks if x in CATS]
        if (re.match(r'\s*9[.,)]', l) and cats) or (len(cats) >= 2 and len(cats) >= len(toks) - 1):
            r['vu_cats'] = ', '.join(dict.fromkeys(cats))
            break
    if not r.get('birth_date'):
        d = re.search(r'(?:^|\s)3[.,]?\s+' + DATE, t)
        if d:
            r['birth_date'] = f'{d[1]}.{d[2]}.{d[3]}'
        elif r.get('vu_date'):  # подпись «3.» потерялась: дата, которая минимум на 16 лет раньше выдачи прав
            issued = int(r['vu_date'][-4:])
            old = [d for _, d, _ in dates(t) if int(d[-4:]) <= issued - 16]
            if old:
                r['birth_date'] = old[0]


def parse_sts(t, r):
    tl = t.lower()
    auto, trailer = plates(t)
    is_trailer = bool(trailer) and not auto or re.search(r'категория\s+тс\W{0,5}(о|o)\d|прицеп', tl) and not auto
    num = re.search(r'(?<![\d.])(\d{2})\s?([0-9' + CYR + r'A-Z]{2})\s?(\d{6})(?![\d.])', t.upper())
    # марка: первое слово ЗАГЛАВНЫМИ после «марка» (SCANIA, VOLVO, КАМАЗ…), не подпись поля
    brand = None
    for m in re.finditer(r'марка', t, re.I):
        for w in re.finditer(r'\b([A-ZА-ЯЁ][A-ZА-ЯЁ0-9\-]{2,}(?:\s+[A-Z0-9][A-Z0-9\-]{1,})?)', to_lat(t[m.end():m.end() + 80])):
            if w.group(1).split()[0].isupper() and not re.match(r'(МОДЕЛЬ|ТРАНСПОРТ|СРЕДСТВ|ТИП|КАТЕГОРИ|VIN)', w.group(1), re.I):
                brand = w
                break
        if brand:
            break
    side = 'trailer' if is_trailer else 'auto'
    if (trailer if is_trailer else auto):
        r.setdefault(f'{side}_plate', (trailer if is_trailer else auto)[0])
    if num and not re.match(DATE, num.group(0)):
        r.setdefault(f'{side}_sts', f'{num[1]} {num[2]} {num[3]}')
    if brand:
        b = brand.group(1).strip()
        if not re.match(r'(модель|тип|категория)', b, re.I):
            r.setdefault(f'{side}_brand', b.upper())


def parse_card(t, r):
    """Word-карточка / анкета: всё подряд — паспорт, в/у, машина, телефон, перевозчик."""
    parse_passport(t, r)
    v = re.search(r'(?:в\s*/?\s*у|водительск\w*\s+удостоверени\w*)[\s№:]*(\d{2})\s?(\d{2})\s?(\d{6})', t, re.I)
    if v:
        r['vu'] = f'{v[1]} {v[2]} {v[3]}'
    auto, trailer = plates(t)
    if auto:
        r.setdefault('auto_plate', auto[0])
    if trailer:
        r.setdefault('trailer_plate', trailer[0])
    am = re.search(r'(?:а\s*/\s*м|автомобил\w*|тягач)\s*(?:марка)?[\s:]*([A-ZА-ЯЁ][A-ZА-ЯЁa-zа-яё0-9\-]+(?:\s+[A-Z0-9\-]{2,})?)', t, re.I)
    if am and not NOT_NAME.match(am.group(1)):
        r.setdefault('auto_brand', am.group(1).upper())


def parse(text):
    """Текст одного документа → (тип, поля)."""
    t = fix(text).replace('\t', ' ')  # колонки важны только для реквизитов компаний (firma.py)
    typ = doc_type(t)
    r = {}
    if typ == 'паспорт':
        parse_passport(t, r)
    elif typ == 'ВУ':
        parse_vu(t, r)
    elif typ == 'СТС':
        parse_sts(t, r)
    elif typ == 'карточка':
        parse_card(t, r)
    else:
        auto, trailer = plates(t)
        if auto:
            r['auto_plate'] = auto[0]
        if trailer:
            r['trailer_plate'] = trailer[0]
    if typ != 'СТС' and 'fio' not in r:  # в СТС ФИО — это собственник, а не водитель
        fio = find_fio(t)
        if fio:
            r['fio'] = title(fio)
    p = phone(t)
    if p:
        r['phone'] = p
    inn = next((m.group(1) for m in re.finditer(r'инн\D{0,6}(\d{10}|\d{12})\b', t, re.I) if inn_ok(m.group(1))), '')
    if inn:
        r['carrier_inn'] = inn
        ip = re.search(r'(ИП|индивидуальный предприниматель|ООО)\s+[«"]?([А-ЯЁA-Z][^\n,;«»"]{2,60})', t)
        if ip:
            r['carrier'] = (('ИП ' if ip[1] != 'ООО' else 'ООО ') + ip[2]).strip()
    return typ, r


# проверки — что подсветить жёлтым
def doubts(f):
    bad = {}
    if f.get('passport') and not re.fullmatch(r'\d{2} \d{2} \d{6}', f['passport']):
        bad['passport'] = 'номер паспорта — 10 цифр'
    if f.get('passport_mrz_ok') is False:
        bad['passport'] = 'контрольная цифра не сошлась — сверьте номер'
    if f.get('passport_code') and not re.fullmatch(r'\d{3}-\d{3}', f['passport_code']):
        bad['passport_code'] = 'код — 6 цифр'
    for k in ('auto_plate', 'trailer_plate'):
        if f.get(k):
            ok = re.fullmatch(rf'[{CYR}]\d{{3}}[{CYR}]{{2}}\d{{2,3}}' if k == 'auto_plate' else rf'[{CYR}]{{2}}\d{{4}}\d{{2,3}}', f[k].replace(' ', ''))
            if not ok:
                bad[k] = 'госномер не по шаблону'
    if f.get('fio') and len(f['fio'].split()) < 3:
        bad['fio'] = 'нет отчества?'
    if f.get('carrier_inn') and not inn_ok(f['carrier_inn']):
        bad['carrier_inn'] = 'ИНН не проходит проверку'
    return bad


def from_files(files):
    """[(имя, байты)] → общие поля водителя, разбор по каждому файлу и сомнительные поля."""
    parsed, docs = [], []
    for name, data in files:
        try:
            typ, f = parse(read_file(name, data))
            parsed.append((typ, f))
            docs.append({'name': name, 'type': typ, 'found': list(f)})
        except Exception as e:
            docs.append({'name': name, 'type': 'ошибка', 'error': str(e)[:200], 'found': []})
    # одно поле нашлось в нескольких файлах — верим паспорту и правам больше, чем карточке
    order = {'паспорт': 0, 'ВУ': 1, 'СТС': 2, 'карточка': 3, 'другое': 4}
    merged = {}
    for typ, f in sorted(parsed, key=lambda p: order.get(p[0], 9)):
        for k, v in f.items():
            merged.setdefault(k, v)
    bad = doubts(merged)
    for k in ('passport_mrz_ok', 'fio_mrz'):  # служебные пометки — не поля
        merged.pop(k, None)
    for d in docs:
        d['found'] = [k for k in d['found'] if k not in ('passport_mrz_ok', 'fio_mrz')]
    return {'fields': merged, 'docs': docs, 'doubts': bad}
