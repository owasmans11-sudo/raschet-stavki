"""Словарь своих слов → исправления OCR для поиска файлов.

    python tools/build_fixes.py            собрать %USERPROFILE%\\vl_find_files\\fixes.json
    python tools/build_fixes.py щербинка   ещё и показать, какие искажения нашлись для этих слов

Словарь — слова из справочников: Клиенты_заявки.xlsx, «Клиенты - Машины- бух-док.xlsx», сводки ИТОГ_*,
rows.json другого чата (заказчик, водитель, место погрузки). Распознанные слова (сканы, фото), которых нет
в обычных текстах, сверяются со словарём: латиница внутри русского слова (щербuнка), одна-две ошибки,
ошибка в первой букве (йербинка) — только одна ошибка на всё слово и только если вариант один.
"""
import glob, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import find_files as ff

BASE = os.path.dirname(ff.CACHE)
FIXES = os.path.join(BASE, 'fixes.json')
SOURCES = [os.path.join(ff.WORK, 'Клиенты_заявки.xlsx'), os.path.join(ff.PROJECT, 'Клиенты - Машины- бух-док.xlsx')]
SOURCES += glob.glob(os.path.join(ff.PROJECT, '**', 'ИТОГ_*.xlsx'), recursive=True)
ROWS = os.path.join(BASE, 'from_other_chat', 'rows.json')
# похожие латинские буквы в русском слове: щербuнка → щербинка
HOMO = dict(zip('aeopcxyukmhtbnr', 'аеорсхуикмнтвпг'))
MIN_LEN = 5


def dictionary():
    out = set()
    for p in SOURCES:
        out.update(ff.words(ff.read_text(p, '.xlsx')))
    try:
        with open(ROWS, encoding='utf-8') as f:
            for r in json.load(f):
                for k in ('client', 'driver', 'load_place'):
                    out.update(ff.words(str(r.get(k) or '')))
    except Exception:
        pass
    return {w for w in out if len(w) >= MIN_LEN and w.isalpha() and not w.isascii()}


def ocr_and_clean():
    """Слова распознанных текстов (с частотой) и слова обычных текстов (их не трогаем)."""
    ocr = {}
    for name in ('ocr.json', 'photo_ocr.json', 'imported.json'):
        for e in ff.load_cache(os.path.join(BASE, name)).values():
            for w in set((e[1] or '').split()):
                ocr[w] = ocr.get(w, 0) + 1
    clean = set()
    for key, e in ff.load_cache().items():
        if key.endswith('.pdf'):  # текст в PDF часто распознал сканер — те же ошибки, что и у нас
            for w in set(e[1].split()):
                ocr[w] = ocr.get(w, 0) + 1
        elif ff.group_of(key) == ff.DOCS:  # наши сводки могут повторять мусор OCR — не в счёт
            clean.update(e[1].split())
    return ocr, clean


def norm(w):
    if not w.isascii() and any(c.isascii() for c in w):
        return ''.join(HOMO.get(c, c) for c in w)
    return w


def deletes(w, n):
    out, level = {w}, {w}
    for _ in range(n):
        level = {x[:i] + x[i + 1:] for x in level for i in range(len(x))}
        out |= level
    return out


def lev(a, b):
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def build():
    dic = dictionary()
    ocr, clean = ocr_and_clean()

    def freq(w):
        return ocr.get(w, 0) + (5 if w in clean else 0)

    def make_index(words):
        index = {}
        for d in words:
            for k in deletes(d, 2 if len(d) >= 8 else 1):
                index.setdefault(k, set()).add(d)
        return index

    def match(n, index, dist2_ok):
        """Слово словаря для искажённого n: самое близкое, при равенстве — заметно более частое."""
        found = {}
        for k in deletes(n, 2 if len(n) >= 8 else 1):
            for d in index.get(k, ()):
                if d == n or d.startswith(n) or n.startswith(d):
                    continue  # окончания поиск и так понимает
                x = lev(n, d)
                limit = 1
                # две ошибки — только редкое слово той же длины с тем же окончанием (иначе «применение» → «примечание»)
                if dist2_ok and len(n) == len(d) >= 8 and n[-2:] == d[-2:]:
                    limit = 2
                if n[0] != d[0]:
                    limit = 1 if len(d) >= 6 else 0  # ошибка в первой букве — только одна на слово
                if x <= limit:
                    found[d] = x
        if not found:
            return None
        top = min(found.values())
        best = sorted((d for d, x in found.items() if x == top), key=freq, reverse=True)
        if len(best) > 1 and freq(best[0]) < 3 * max(freq(best[1]), 1):
            return None  # два равных варианта (Лукин / Букин) — не угадываем
        return best[0]

    fixes = {}
    # мусор в самом словаре (rows.json тоже из распознавания): «пербинка» при частой «щербинке»
    index = make_index(dic)
    for d in sorted(dic, key=freq):
        g = match(d, index, False)
        if g and freq(g) >= 5 * max(freq(d), 1) and d not in clean:
            fixes[d] = g
    dic -= set(fixes)
    index = make_index(dic)
    for w, c in ocr.items():
        if w in dic or w in fixes or w in clean or len(w) < MIN_LEN or not w.isalpha():
            continue
        n = norm(w)
        if n in dic:
            fixes[w] = n
        elif not n.isascii():
            g = match(n, index, c <= 3)  # настоящие слова повторяются, мусор OCR с двумя ошибками — редкость
            if g:
                fixes[w] = g
    # исправление ведёт только в живое слово словаря
    fixes = {w: fixes.get(g, g) for w, g in fixes.items()}
    return dic, ocr, fixes


def main():
    dic, ocr, fixes = build()
    ff.save_cache(fixes, FIXES)
    print(f'Словарь: {len(dic)} слов. Распознанных слов: {len(ocr)}. Исправлений: {len(fixes)} → {FIXES}')
    for q in sys.argv[1:]:
        q = ff.words(q)[0]
        bad = sorted((w for w, g in fixes.items() if g == q), key=lambda w: -ocr[w])
        print(f'  {q}: ' + (', '.join(f'{w} ({ocr[w]})' for w in bad) or '—'))


if __name__ == '__main__':
    main()
