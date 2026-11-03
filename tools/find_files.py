"""Нечёткий поиск файлов по похожим словам — в именах и внутри файлов.

    python tools/find_files.py "Лукин А. В."
    python tools/find_files.py "климат комплект" --only-names
    python tools/find_files.py                      (без слов — спросит запрос, удобно двойным щелчком)

Где ищет: папка проекта и C:\\РАБОТА (другие — через --root, можно несколько).
Что сравнивает: слова запроса с похожими словами (опечатки, падежи: Лукин ~ Лукина ~ Лукину ~ лукин1),
инициалы «А. В.» — по первой букве слов рядом с фамилией.
Внутри смотрит: docx, xlsx, pdf, md, txt, csv. Сканы PDF без текста — по распознанному тексту из ocr.json
(его готовит tools/ocr_scans.py, запуск — «Распознать сканы.bat»); старые .xls — по xls.json (tools/read_xls.py).
Испорченные OCR-слова сверяются со словарём своих слов (fixes.json, tools/build_fixes.py): «шербинка» → «щербинка»,
в выдаче пометка «испр.».
Тексты кешируются в %USERPROFILE%\\vl_find_files\\cache.json — повторный поиск быстрый.
"""
import argparse, difflib, html, json, os, re, sys, zipfile

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = r'C:\РАБОТА'
DEFAULT_ROOTS = [PROJECT, WORK]
# не в AppData: приложение Claude прячет туда записанное в свою папку, и планировщик и окна, открытые
# двойным щелчком, этих данных не видят (24.10.2026)
CACHE = os.path.join(os.path.expanduser('~'), 'vl_find_files', 'cache.json')
OCR_CACHE = os.path.join(os.path.dirname(CACHE), 'ocr.json')
XLS_CACHE = os.path.join(os.path.dirname(CACHE), 'xls.json')  # старые .xls — готовит tools/read_xls.py
IMPORTED_CACHE = os.path.join(os.path.dirname(CACHE), 'imported.json')  # фото, .doc, .rtf — tools/import_ocr.py --extra
PHOTO_CACHE = os.path.join(os.path.dirname(CACHE), 'photo_ocr.json')  # нижняя часть фото — tools/ocr_photos.py
FIXES = os.path.join(os.path.dirname(CACHE), 'fixes.json')  # испорченное OCR-слово → слово словаря — tools/build_fixes.py
FIX_WEIGHT = 0.9  # найдено через исправление — чуть ниже точного совпадения
IMG_EXT = {'.jpg', '.jpeg', '.png', '.webp', '.gif', '.jfif', '.heic', '.bmp', '.tif', '.tiff'}
SCAN_MIN_TEXT = 80  # у PDF меньше символов — считаем сканом без текстового слоя
TEXT_EXT = {'.docx', '.xlsx', '.pdf', '.md', '.txt', '.csv'}
SKIP_DIRS = {'.git', '__pycache__', 'node_modules', '.claude'}
# служебные папки проекта (память агента, планы, скрипты) — владельцу в поиске не нужны
SKIP_PROJECT = {os.path.join(PROJECT, d).lower() for d in
                ('context', 'retros', 'plans', 'prompts', 'rules', 'tools', 'mail-downloader')}
SKIP_PROJECT_FILES = {'claude.md', 'onboarding.md', 'readme.md', 'поиск файлов.bat', 'распознать сканы.bat'}
MAX_TEXT = 300_000
ENDINGS = {'а', 'у', 'е', 'ы', 'ом', 'ым', 'ой', 'ой', 'ою', 'ым', 'ов', 'ой', 'ах', 'ам', 'ами', 'ую', 'ая', 'ого', 'ому'}
LAT2CYR =dict(zip('abvgdezijklmnoprstufhcy', 'абвгдезийклмнопрстуфхцы'))

for s in (sys.stdout, sys.stderr):
    try:
        s.reconfigure(encoding='utf-8')
    except Exception:
        pass


def words(text):
    """Слова в нижнем регистре, ё→е; буквы и цифры разделяются (лукин1 → лукин, 1)."""
    text = text.lower().replace('ё', 'е')
    return re.findall(r'[^\W\d_]+|\d+', text)


def translit(w):
    if w.isascii() and w.isalpha():
        w = w.replace('sh', 'ш').replace('ch', 'ч').replace('zh', 'ж').replace('kh', 'х').replace('ya', 'я').replace('yu', 'ю')
        return ''.join(LAT2CYR.get(c, c) for c in w)
    return w


def similarity(q, w):
    if q == w:
        return 1.0
    w = translit(w)
    if q == w:
        return 0.97
    if len(q) >= 4 and w.startswith(q) and len(w) - len(q) <= 3:
        return 0.92  # падежи и окончания: лукин / лукина / лукину
    if len(w) >= 4 and q.startswith(w) and q[len(w):] in ENDINGS:
        return 0.88  # запрос в падеже: лукину → лукин (но не лукин → луки)
    if abs(len(q) - len(w)) > 2 or len(w) < 3:
        return 0.0
    if q[0] != w[0]:
        return 0.0  # иначе «комтранс» ~ «sotrans» (марка прицепа) только из-за общего «-транс»
    m = difflib.SequenceMatcher(None, q, w)
    return 0.9 * m.ratio() if m.real_quick_ratio() >= 0.6 else 0.0  # опечатка всегда ниже точного


# ---------- чтение текста из файлов ----------

def _xml_text(z, name):
    data = z.read(name).decode('utf-8', 'ignore')
    data = re.sub(r'</w:p>|<w:tab/>|<w:br/>|</si>|</c>', ' ', data)
    return html.unescape(re.sub(r'<[^>]+>', '', data))


def read_text(path, ext):
    try:
        if ext == '.docx':
            with zipfile.ZipFile(path) as z:
                return ' '.join(_xml_text(z, n) for n in z.namelist()
                                if re.match(r'word/(document|header\d*|footer\d*)\.xml$', n))
        if ext == '.xlsx':
            with zipfile.ZipFile(path) as z:
                return ' '.join(_xml_text(z, n) for n in z.namelist()
                                if n == 'xl/sharedStrings.xml' or re.match(r'xl/worksheets/sheet\d+\.xml$', n))
        if ext == '.pdf':
            import pymupdf
            with pymupdf.open(path) as doc:
                out = []
                for page in doc:
                    out.append(page.get_text())
                    if sum(map(len, out)) > MAX_TEXT:
                        break
                return ' '.join(out)
        with open(path, encoding='utf-8', errors='ignore') as f:
            return f.read(MAX_TEXT)
    except Exception:
        return ''


def load_cache(path=CACHE):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def save_cache(cache, path=CACHE):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False)
    os.replace(tmp, path)


def iter_files(roots):
    for root in roots:
        if not os.path.isdir(root):
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS
                           and os.path.join(dirpath, d).lower() not in SKIP_PROJECT]
            in_project_root = os.path.normcase(dirpath) == os.path.normcase(PROJECT)
            for fn in filenames:
                if in_project_root and fn.lower() in SKIP_PROJECT_FILES:
                    continue
                if not fn.startswith('~$'):
                    yield os.path.join(dirpath, fn)


# ---------- два блока выдачи ----------
DOCS, TABLES = 0, 1
GROUP_TITLES = {DOCS: 'ДОКУМЕНТЫ', TABLES: 'СВОДНЫЕ ТАБЛИЦЫ И ОПИСИ'}
EXCEL_EXT = {'.xlsx', '.xls', '.xlsm'}


def group_of(path):
    """ДОКУМЕНТЫ — заявки, УПД, сканы, фото, файлы из почты; ТАБЛИЦЫ — то, что собирали мы сами."""
    name = os.path.basename(path)
    ext = os.path.splitext(name)[1].lower()
    folder = os.path.normcase(os.path.dirname(path))
    if ext in ('.csv', '.md') or name.startswith('ИТОГ_'):
        return TABLES
    if (folder + os.sep).startswith(os.path.normcase(os.path.join(WORK, 'Claude outputs')) + os.sep):
        return TABLES
    if ext in EXCEL_EXT and folder in (os.path.normcase(WORK), os.path.normcase(PROJECT)):
        return TABLES
    return DOCS


def collect(roots, with_text, progress=None):
    """Список (путь, текст, скан?) — скан?=True, если текст взят из распознавания OCR."""
    cache = load_cache() if with_text else {}
    ocr = load_cache(OCR_CACHE) if with_text else {}
    xls = load_cache(XLS_CACHE) if with_text else {}
    imported = load_cache(IMPORTED_CACHE) if with_text else {}
    photo = load_cache(PHOTO_CACHE) if with_text else {}
    files, changed, seen = [], False, set()
    for path in iter_files(roots):
        key = os.path.normcase(path)
        if key in seen:
            continue
        seen.add(key)
        ext = os.path.splitext(path)[1].lower()
        text, scan = '', False
        if with_text and ext in TEXT_EXT:
            try:
                st = os.stat(path)
            except OSError:
                continue
            stamp = f'{st.st_size}:{int(st.st_mtime)}'
            entry = cache.get(key)
            if not entry or entry[0] != stamp:
                if progress:
                    progress(os.path.basename(path))
                else:
                    print(f'  читаю: {os.path.basename(path)}', file=sys.stderr, end='\r')
                entry = [stamp, ' '.join(words(read_text(path, ext)))[:MAX_TEXT]]
                cache[key] = entry
                changed = True
            text = entry[1]
            if ext == '.pdf' and len(text) < SCAN_MIN_TEXT:
                o = ocr.get(key)
                if o and o[0] == stamp and o[1]:
                    text, scan = o[1], True
        elif with_text and ext == '.xls':
            x = xls.get(key)
            if x:
                try:
                    st = os.stat(path)
                except OSError:
                    continue
                if x[0] == f'{st.st_size}:{int(st.st_mtime)}':
                    text = x[1]
        if with_text and not text:  # фото, .doc, .rtf — текст, готовый из других сессий (tools/import_ocr.py --extra)
            m = imported.get(key)
            if m:
                try:
                    st = os.stat(path)
                except OSError:
                    continue
                if m[0] == f'{st.st_size}:{int(st.st_mtime)}':
                    text, scan = m[1], ext in IMG_EXT
        if with_text and ext in IMG_EXT:  # нижняя часть фото — дописываем к верхней
            b = photo.get(key)
            if b and b[1]:
                try:
                    st = os.stat(path)
                except OSError:
                    continue
                if b[0] == f'{st.st_size}:{int(st.st_mtime)}':
                    text, scan = (text + ' ' + b[1]).strip(), True
        files.append((path, text, scan))
    if changed:
        if not progress:
            print(' ' * 100, file=sys.stderr, end='\r')
        save_cache(cache)
    return files


# ---------- оценка ----------

def parse_query(q):
    main, initials = [], []
    for w in words(q):
        if len(w) == 1 and not w.isdigit():
            initials.append(w)
        elif len(w) == 2 and w.isalpha() and q.replace(' ', '').lower().replace('ё', 'е').find(w[0] + '.' + w[1]) >= 0:
            initials.extend(w)  # «А.В.» слитно
        else:
            main.append(w)
    return main, initials


def score_window(window, main, initials, sims):
    """Оценка куска текста (или имени файла): 0..1 и найденные слова."""
    got, found = [], []
    for q in main:
        best, bw = 0.0, None
        for w in window:
            s = sims[q].get(w, 0.0)
            if s > best:
                best, bw = s, w
        got.append(best)
        if bw:
            found.append(bw)
    score = sum(got) / len(main) if main else 0.0
    if initials:  # инициалы только уточняют: точная фамилия без инициалов выше похожей с инициалами
        letters = [w[0] for w in window if w.isalpha() and w not in found]
        hit = sum(1 for i in initials if i in letters) / len(initials)
        score *= 0.85 + 0.15 * hit
    return score, found


def search(query, roots, only_names=False, limit=20, threshold=0.6, progress=None):
    main, initials = parse_query(query)
    if not main:
        main, initials = initials, []
    files = collect(roots, not only_names, progress)

    vocab = set()
    named = []
    for path, text, scan in files:
        nw = words(os.path.splitext(os.path.basename(path))[0])
        tw = text.split() if text else []
        named.append((path, nw, tw, scan))
        vocab.update(nw)
        vocab.update(tw)
    # «климат комплект» ищем и слитно — «климаткомплект»
    variants_q = [main, [''.join(main)]] if len(main) > 1 else [main]
    sims = {q: {} for v in variants_q for q in v}
    fixes = {} if only_names else load_cache(FIXES)
    via_fix = set()  # слова, засчитанные через исправление OCR (йербинка → щербинка)
    for w in vocab:
        g = fixes.get(w)
        for q in sims:
            s = similarity(q, w)
            if g:
                sf = FIX_WEIGHT * similarity(q, g)
                if sf > s:
                    s = sf
                    if s >= 0.7:
                        via_fix.add(w)
            if s >= 0.7:
                sims[q][w] = s

    def best(window):
        return max((score_window(window, v, initials, sims) for v in variants_q), key=lambda r: r[0])

    results, variants = [], {}
    for path, nw, tw, scan in named:
        s_name, f_name = best(nw)
        s_text, f_text, snippet = 0.0, [], ''
        if tw:
            for i, w in enumerate(tw):
                if any(w in sims[q] for q in sims):
                    win = tw[max(0, i - 4): i + 5]
                    s, f = best(win)
                    if s > s_text:
                        s_text, f_text, snippet = s, f, ' '.join(win)
        if max(s_name, s_text) < threshold:
            continue
        in_name = s_name >= s_text
        where = ('имя' if in_name else
                 ('фото' if os.path.splitext(path)[1].lower() in IMG_EXT else 'скан') if scan else 'текст')
        found = f_name if in_name else f_text
        if via_fix.intersection(found):
            where += ', испр.'
        for w in found:
            w = fixes[w] if w in via_fix else w  # в похожих словах — правильное слово, не мусор OCR
            variants[w] = variants.get(w, 0) + 1
        results.append((max(s_name, s_text), where, path, '' if in_name else snippet, group_of(path)))

    results.sort(key=lambda r: (-r[0], r[2]))
    total = len(results)
    results = results[:limit]
    results.sort(key=lambda r: r[4])  # сверху документы, снизу наши таблицы; внутри — по похожести
    # похожие слова: сначала самые похожие, потом самые частые
    variants = dict(sorted(variants.items(),
                           key=lambda kv: (-max(sims[q].get(kv[0], 0) or similarity(q, kv[0]) for q in sims), -kv[1])))
    return results, total, variants


def word_counts(roots, progress=None):
    """Сколько файлов содержит каждое слово (в имени или тексте) — для подсказок при наборе."""
    counts = {}
    fixes = load_cache(FIXES)
    for path, text, scan in collect(roots, True, progress):
        ws = set(words(os.path.splitext(os.path.basename(path))[0]))
        ws.update(text.split())
        ws.update([fixes[w] for w in ws if w in fixes])  # «шербинка» в скане считается и за «щербинку»
        for w in ws:
            if len(w) >= 3 and not w.isdigit():
                counts[w] = counts.get(w, 0) + 1
    return counts


def suggest(typed, counts, n=12):
    """Похожие слова для того, что сейчас набрано: начало слова, опечатки, падежи."""
    ws = [w for w in words(typed) if len(w) >= 2]
    if not ws:
        return []
    q = max(ws, key=len)  # подсказываем по самому длинному слову (обычно фамилия или компания)
    out = []
    for w, c in counts.items():
        if w.startswith(q):
            s = 1.0 if w == q else 0.95
        elif len(q) >= 3:
            s = similarity(q, w)
            if s < 0.72:
                continue
        else:
            continue
        out.append((s, c, w))
    out.sort(key=lambda r: (-r[0], -r[1], r[2]))
    return [(w, c) for s, c, w in out[:n]]


def mask(text):
    return re.sub(r'\d{6,}', lambda m: m.group()[:2] + '…', text)


def show(query, roots, only_names, limit):
    results, total, variants = search(query, roots, only_names, limit)
    if not results:
        print(f'По запросу «{query}» ничего похожего не нашлось.')
        return
    if variants:
        top = list(variants.items())[:10]
        print('Похожие слова: ' + ', '.join(f'{w} ({n})' for w, n in top))
    print(f'Найдено: {total}, показаны лучшие {len(results)}\n')
    group = None
    for n, (score, where, path, snip, g) in enumerate(results, 1):
        if g != group:
            group = g
            print(f'——— {GROUP_TITLES[g]} ———')
        rel = os.path.relpath(path, PROJECT) if path.lower().startswith(PROJECT.lower()) else path
        print(f'{n:>2}. [{round(score * 100):>3}%  {where}]  {rel}')
        if snip:
            print(f'       … {mask(snip)} …')


def main():
    ap = argparse.ArgumentParser(description='Нечёткий поиск файлов по похожим словам')
    ap.add_argument('query', nargs='*')
    ap.add_argument('--root', action='append', help='папка поиска (можно несколько); по умолчанию проект и C:\\РАБОТА')
    ap.add_argument('--only-names', action='store_true', help='только по именам файлов (быстро)')
    ap.add_argument('-n', '--limit', type=int, default=20)
    a = ap.parse_args()
    roots = a.root or DEFAULT_ROOTS
    if a.query:
        show(' '.join(a.query), roots, a.only_names, a.limit)
        return
    while True:  # интерактивный режим
        try:
            q = input('\nЧто ищем? (пусто — выход): ').strip()
        except EOFError:
            break
        if not q:
            break
        show(q, roots, a.only_names, a.limit)


if __name__ == '__main__':
    main()
