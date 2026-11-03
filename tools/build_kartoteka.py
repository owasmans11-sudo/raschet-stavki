"""Картотека документов — одна таблица по всем заявкам, УПД, счетам, актам, ТН, договорам, документам водителей.

    python tools/build_kartoteka.py

Пишет C:\\РАБОТА\\Картотека документов.xlsx (листы «Все документы» и «Сводка») и копию для программ
%USERPROFILE%\\vl_find_files\\kartoteka.json. Ничего не распознаёт заново — берёт тексты, которые уже собрал поиск файлов
(tools/find_files.py, OCR сканов и фото), и готовые данные чата «Excel заявки с клиентами + УПД» (from_other_chat:
раскладка PDF по типам classes.json, поля заявок rows.json с ручными поправками). Новые файлы попадают при каждом запуске;
«Распознать сканы.bat» запускает её в конце сам. Сомнительные суммы и пустые поля — с пометкой «проверить», ничего не выдумывается.
"""
import json, os, re, sys, zipfile, html

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import find_files as ff
import kart_classify as kc
import kart_fields as kf
import kart_roles as kr

BASE = os.path.dirname(ff.CACHE)
OTHER = os.path.join(BASE, 'from_other_chat')
OUT_XLSX = os.path.join(ff.WORK, 'Картотека документов.xlsx')
OUT_JSON = os.path.join(BASE, 'kartoteka.json')
DOC_EXT = {'.pdf', '.docx', '.doc', '.rtf', '.xlsx', '.xls', '.xlsm', '.txt'} | ff.IMG_EXT
VL_INN = '3812166710'
ILLEGAL = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f]')  # Excel не принимает управляющие символы

# категории другого чата → короткий тип в таблице
TYPE = {kc.ZAYAVKA: 'Заявка', kc.BUH: 'Бухгалтерия', kc.TRANSPORT: 'ТН / ТТН / накладная', kc.DRIVER: 'Водитель / машина',
        kc.COMPANY: 'Реквизиты компании', kc.DOGOVOR: 'Договор', kc.POST: 'Почта', kc.OTHER: 'Прочее', kc.UNREAD: 'Не распознано'}
ROLE = {'client': 'с клиентом', 'carrier': 'перевозчику', 'none': 'без ВЛ', '?': ''}
COLUMNS = [('type', 'Тип', 20), ('kind', 'Вид', 22), ('num', 'Номер', 12), ('date', 'Дата документа', 13),
           ('counterparty', 'Контрагент', 34), ('load_place', 'Погрузка', 34), ('driver', 'Водитель', 24),
           ('amount', 'Сумма, ₽', 13), ('vat', 'НДС', 10), ('check', 'Проверить', 22), ('received', 'Получен', 11),
           ('source', 'Откуда текст', 13), ('file', 'Файл', 46), ('folder', 'Папка', 40), ('copies', 'Копии', 7)]


def load(path):
    return ff.load_cache(path)


def other_texts():
    """Сырые тексты другого чата (со строками и заглавными буквами) — по имени файла."""
    out = {}
    for name in ('ocr.json', 'ocr_inc.json', 'zay_full2.json', 'zay_full_b.json', 'zay_full.json',
                 'office_text2.json', 'office_text.json', 'img_ocr_1.json', 'img_ocr_0.json', 'photo_full.json'):
        for k, v in load(os.path.join(OTHER, name)).items():
            v = v.get('text', '') if isinstance(v, dict) else v
            if isinstance(v, str) and v and not v.startswith('ERR'):
                out[k.lower()] = v  # файлы ниже по списку полнее — перезаписывают шапки
    for k, v in load(os.path.join(OTHER, 'dog_ocr.json')).items():
        if v.get('text'):
            out[k.lower()] = v['text']
    return out


def office_lines(path, ext):
    """Текст docx/xlsx по строкам (поиск хранит его одной строкой без знаков)."""
    try:
        with zipfile.ZipFile(path) as z:
            names = [n for n in z.namelist() if re.match(r'word/document\.xml$|xl/sharedStrings\.xml$|xl/worksheets/sheet\d+\.xml$', n)]
            parts = []
            for n in names:
                d = z.read(n).decode('utf-8', 'ignore')
                d = re.sub(r'</w:p>|</si>|</row>', '\n', d)
                d = re.sub(r'<w:tab/>|</c>', ' ', d)
                parts.append(html.unescape(re.sub(r'<[^>]+>', '', d)))
            return '\n'.join(parts)
    except Exception:
        return ''


def pdf_lines(path):
    try:
        import pymupdf
        with pymupdf.open(path) as doc:
            return '\n'.join(doc[i].get_text() for i in range(min(3, doc.page_count)))
    except Exception:
        return ''


def money_value(s):
    m = re.fullmatch(r'\s*(\d{1,3}(?:[\s\u00a0.]\d{3})+|\d+)(?:[.,](\d{1,2}))?\s*', s or '')
    if not m:
        return None
    return float(re.sub(r'\D', '', m.group(1)) + '.' + (m.group(2) or '0'))


# ---------- бухгалтерия: УПД, счета, акты ----------
BUH_KIND = [(r'универсальн\S* передаточн|\bупд\b', 'УПД'), (r'сч[её]т[\s-]*фактур', 'Счёт-фактура'),
            (r'акт\S* сверк', 'Акт сверки'), (r'платежн\S* поручени|\bп/п\b', 'Платёжка'),
            (r'сч[её]т (на оплату|№)|^сч[её]т\b', 'Счёт'), (r'\bакт\b', 'Акт')]
TOTAL = re.compile(r'всего к оплате|итого к оплате|всего по сч[её]ту|итого с ндс|всего с ндс|итого|всего|сумма к оплате|на сумму', re.I)
SELLER = re.compile(r'(продав\S*|поставщик\S*|исполнител\S*|получатель)\W{0,20}', re.I)


def buh_fields(name, text):
    t = re.sub(r'[ \t\u00a0]+', ' ', text)
    low = t.lower()
    head = re.sub(r'\s+', ' ', low[:1200])
    fn = name.lower()[11:]
    kind, at = '', None
    if re.search(r'упд|передаточн', fn):  # имя файла про УПД надёжнее шапки (в УПД есть и слова «счёт-фактура»)
        kind = 'УПД'
    for rx, k in BUH_KIND:
        m = re.search(rx, head)
        if m and (not kind or k == kind):
            kind, at = k, m.start()
            break
    kind = kind or next((k for rx, k in BUH_KIND if re.search(rx, fn)), 'Бухгалтерия')
    num = date = ''
    # номер — рядом с названием документа, а не «№ счёта» из банковских реквизитов
    seg = head[at:at + 160] if at is not None else head[:300]
    for m in re.finditer(r'(?:№|\bn[°o]?\b)\s*([\w/\\-]{1,12})', seg):
        x = m.group(1).strip(' .,-')
        if re.search(r'\d', x) and not re.fullmatch(r'\d{11,}', x):
            num = x
            date = kf.find_date(seg[m.end():m.end() + 40])
            break
    date = date or kf.find_date(seg) or kf.find_date(head)
    if not num:  # «Платежное_поручение_№552», «сч0241», «УПД № 2948»
        m = re.search(r'(?:№|\bn|сч|упд|акт|пп)\s*_?\s*0*(\d{1,7})(?!\d)', fn)
        num = m.group(1) if m else ''
    amount = None
    for m in TOTAL.finditer(t):
        cands = [money_value(x.group(1) + (x.group(2) or '')) for x in kf.MONEY.finditer(t[m.end():m.end() + 120])]
        cands = [c for c in cands if c and c >= 100]
        if cands:
            amount = max(cands)
            break
    vat = 'без НДС' if re.search(r'без\s*(налога\s*)?\(?ндс', low) else ('с НДС' if re.search(r'ндс\s*\d{1,2}\s*%|в т\.?\s*ч\.?\s*ндс|сумма ндс', low) else '')
    direction = ''
    for m in SELLER.finditer(low[:1500]):
        seg = low[m.end():m.end() + 150]
        if kr.VL.search(seg):
            direction = 'ВЛ — продавец'
            break
        if re.search(r'\w{3,}', seg):
            direction = 'ВЛ — покупатель' if kr.VL.search(low[:2500]) else ''
            break
    return {'kind': kind + (f' ({direction})' if direction else ''), 'num': num, 'date': date, 'amount': amount, 'vat': vat}


# ---------- сборка ----------

def entry_texts():
    """Тексты, уже собранные поиском (без чтения файлов), плюс тексты .xls/фото из их отдельных кешей."""
    files = ff.collect(ff.DEFAULT_ROOTS, True, progress=lambda name: None)
    return {os.path.normcase(p): (p, t, scan) for p, t, scan in files}


def build():
    classes = {k.lower(): v[0] for k, v in load(os.path.join(OTHER, 'classes.json')).items()}
    rows = {r['file'].lower(): r for r in (json.load(open(os.path.join(OTHER, 'rows.json'), encoding='utf-8'))
                                           if os.path.exists(os.path.join(OTHER, 'rows.json')) else [])}
    raw_other = other_texts()
    fixes = load(ff.FIXES)
    known = entry_texts()

    cards, by_key = [], {}
    for key, (path, flat, scan) in sorted(known.items()):
        name = os.path.basename(path)
        ext = os.path.splitext(name)[1].lower()
        if ext not in DOC_EXT or ff.group_of(path) != ff.DOCS:
            continue
        try:
            size = os.path.getsize(path)
        except OSError:
            continue
        dup = (name.lower(), size)
        if dup in by_key:  # тот же файл в другой папке (PDF по категориям и Заявки на перевозку)
            by_key[dup]['copies'] += 1
            by_key[dup]['other_paths'].append(path)
            continue
        low = name.lower()
        # сырой текст со строками: свой PDF-слой → другой чат → свой docx/xlsx → плоский текст поиска
        raw, source = '', ''
        if ext == '.pdf' and not scan and len(flat) >= ff.SCAN_MIN_TEXT:
            raw, source = pdf_lines(path), 'текст PDF'
        if not raw and low in raw_other:
            raw, source = raw_other[low], ('фото' if ext in ff.IMG_EXT else 'скан' if ext == '.pdf' else 'текст')
        if not raw and ext in ('.docx', '.xlsx', '.xlsm'):
            raw, source = office_lines(path, ext), 'текст'
        if not raw and flat:
            raw, source = flat, ('фото' if ext in ff.IMG_EXT else 'скан' if scan else 'текст')
        if not raw:
            source = 'нет текста'
        # исправленные OCR-слова (шербинка → щербинка) — только для разбора, сам файл не трогаем
        if source in ('скан', 'фото') and fixes:
            raw = re.sub(r'[^\W\d_]+', lambda m: fixes.get(m.group().lower().replace('ё', 'е'), m.group()), raw)

        cat = classes.get(low) or (kc.classify(name, raw)[0] if raw else (kc.UNREAD if ext != '.pdf' else kc.UNREAD))
        if not raw and ext in ff.IMG_EXT:
            cat = None
        card = {'type': TYPE.get(cat, 'Фото без текста'), 'kind': '', 'num': '', 'date': '', 'counterparty': '',
                'load_place': '', 'driver': '', 'amount': None, 'vat': '', 'check': '',
                'received': (lambda m: f'{m[3]}.{m[2]}.{m[1]}' if m else '')(re.match(r'(20\d\d)-(\d\d)-(\d\d)_', name)),
                'source': source, 'file': name, 'folder': os.path.dirname(path), 'path': path, 'copies': 1, 'other_paths': []}
        checks = []
        if cat == kc.ZAYAVKA:
            r = rows.get(low)
            if r:  # готовые поля другого чата, уже с его ручными поправками
                f = r
                role = r.get('role') or '?'
            else:
                f = kf.extract(raw) if raw else {}
                role = kr.role(raw)[0] if raw else '?'
            card['kind'] = 'Заявка ' + ROLE.get(role, '') if ROLE.get(role) else 'Заявка (чья — не ясно)'
            for k in ('num', 'date', 'driver', 'load_place', 'vat'):
                card[k] = str(f.get(k) or '')
            card['counterparty'] = str(f.get('client') or '')
            card['amount'] = f.get('amount') if isinstance(f.get('amount'), (int, float)) else money_value(str(f.get('amount') or ''))
            if f.get('doubt'):
                checks.append('сумма')
            if f.get('load_date'):
                card['load_place'] = (str(f['load_date']) + ' ' + card['load_place']).strip()
        elif cat == kc.BUH and raw:
            card.update(buh_fields(name, raw))
            card['counterparty'] = kf.client(raw)
            if card['amount'] is None:
                checks.append('сумма')
            elif source in ('скан', 'фото'):
                checks.append('сумма (скан)')
        elif raw:
            card['date'] = kf.find_date(raw[:1500])
            card['counterparty'] = kf.client(raw) if cat in (kc.DOGOVOR, kc.COMPANY, kc.TRANSPORT, kc.OTHER) else ''
            if cat == kc.DOGOVOR:
                m = re.search(r'договор\S*\s*(?:№|n)\s*([\w/-]{1,15})', raw[:600], re.I)
                card['num'] = m.group(1) if m else ''
        if cat in (kc.ZAYAVKA, kc.BUH):
            if not card['num']:
                checks.append('номер')
            if not card['date']:
                checks.append('дата')
        if source == 'нет текста':
            checks = ['не читается']
        card['check'] = ', '.join(checks)
        cards.append(card)
        by_key[dup] = card
    cards.sort(key=lambda c: (c['type'], c['received'][6:] + c['received'][3:5] + c['received'][:2], c['file']))
    return cards


def write_xlsx(cards):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
    blue, light = '1E6FE0', 'EAF2FE'
    wb = Workbook()
    ws = wb.active
    ws.title = 'Все документы'
    head = Font(name='Arial', bold=True, color='FFFFFF')
    for i, (k, title, w) in enumerate(COLUMNS, 1):
        c = ws.cell(row=1, column=i, value=title)
        c.font, c.fill = head, PatternFill('solid', fgColor=blue)
        c.alignment = Alignment(vertical='center', wrap_text=True)
        ws.column_dimensions[get_column_letter(i)].width = w
    font, link = Font(name='Arial', size=9), Font(name='Arial', size=9, color='0B4AA8', underline='single')
    warn = PatternFill('solid', fgColor='FFF4D6')
    for r, card in enumerate(cards, 2):
        for i, (k, _, _) in enumerate(COLUMNS, 1):
            v = card[k]
            if isinstance(v, str):
                v = ILLEGAL.sub(' ', v)
            c = ws.cell(row=r, column=i, value=v if v not in ('', None) else None)
            c.font = font
            if k == 'file':
                c.hyperlink, c.font = card['path'], link
            elif k == 'amount' and v is not None:
                c.number_format = '# ##0.00'
            elif k == 'copies' and v == 1:
                c.value = None
            elif k == 'check' and v:
                c.fill = warn
    ws.freeze_panes = 'A2'
    ws.auto_filter.ref = f'A1:{get_column_letter(len(COLUMNS))}{len(cards) + 1}'

    s = wb.create_sheet('Сводка')
    s.column_dimensions['A'].width, s.column_dimensions['B'].width, s.column_dimensions['C'].width = 34, 12, 16
    for i, t in enumerate(('Тип / вид', 'Документов', 'Проверить'), 1):
        c = s.cell(row=1, column=i, value=t)
        c.font, c.fill = head, PatternFill('solid', fgColor=blue)
    stats = {}
    for c in cards:
        for k in (c['type'], '   ' + c['kind'] if c['kind'] else None):
            if k:
                n = stats.setdefault((c['type'], k), [0, 0])
                n[0] += 1
                n[1] += bool(c['check'])
    for r, ((_, k), (n, chk)) in enumerate(sorted(stats.items()), 2):
        for i, v in enumerate((k, n, chk), 1):
            c = s.cell(row=r, column=i, value=v)
            c.font = Font(name='Arial', size=10, bold=not k.startswith(' '))
            if not k.startswith(' '):
                c.fill = PatternFill('solid', fgColor=light)
    s.cell(row=len(stats) + 3, column=1, value=f'Всего документов: {len(cards)}').font = Font(name='Arial', bold=True)
    s.cell(row=len(stats) + 4, column=1, value='Пересобрать: python tools/build_kartoteka.py (или «Распознать сканы.bat» — в конце сам)').font = Font(name='Arial', size=9, color='6B6B6B')
    tmp = OUT_XLSX[:-5] + '.tmp.xlsx'
    wb.save(tmp)
    try:
        os.replace(tmp, OUT_XLSX)
    except PermissionError:  # таблица открыта в Excel — кладём рядом
        alt = OUT_XLSX[:-5] + ' (новая).xlsx'
        os.replace(tmp, alt)
        return alt
    return OUT_XLSX


def main():
    cards = build()
    ff.save_cache(cards, OUT_JSON)
    out = write_xlsx(cards)
    print(f'Картотека: {len(cards)} документов → {out}')


if __name__ == '__main__':
    main()
