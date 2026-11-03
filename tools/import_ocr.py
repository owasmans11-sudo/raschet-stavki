"""Переносит в кеш поиска текст сканов, уже распознанный другими сессиями, чтобы ocr_scans.py не делал работу дважды.

    python tools/import_ocr.py <папка с json>

Понимает файлы {имя файла: текст} или {имя файла: {"text": …, "pages": …}}.
Полный текст страницы засчитывается как 2 распознанные страницы, «шапка» (ocr.json — верх 1-й страницы) — как 1-я страница;
2-ю страницу тогда дораспознает ocr_scans.py. Запускать, когда ocr_scans.py НЕ работает (иначе он перезапишет кеш).
"""
import json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import find_files as ff  # noqa: E402
from ocr_scans import MAX_PAGES, find_scans, fix_letters  # noqa: E402

FULL = ['zay_full.json', 'zay_full2.json', 'zay_full_b.json', 'ocr_inc.json', 'dog_ocr.json']
HEAD = ['ocr.json']


def load(folder, names):
    out = {}
    for n in names:
        try:
            with open(os.path.join(folder, n), encoding='utf-8') as f:
                data = json.load(f)
        except Exception:
            continue
        for name, v in data.items():
            text = v.get('text', '') if isinstance(v, dict) else str(v)
            if len(text) >= ff.SCAN_MIN_TEXT and not text.startswith('ERR'):
                out[name.lower()] = text
    return out


def import_extra(folder):
    """Фото (img_ocr_*.json — верхняя половина снимка) и Word/RTF/XLS (office_text*.json) — в imported.json."""
    texts = load(folder, ['img_ocr_0.json', 'img_ocr_1.json', 'office_text.json', 'office_text2.json'])
    texts.update(load(folder, ['photo_full.json']))  # фото целиком — поверх верхних половин
    xls = ff.load_cache(ff.XLS_CACHE)
    imported, n = ff.load_cache(ff.IMPORTED_CACHE), {}
    for path in ff.iter_files(ff.DEFAULT_ROOTS):
        ext = os.path.splitext(path)[1].lower()
        name = os.path.basename(path).lower()
        if name not in texts or ext in ff.TEXT_EXT or ext == '.pdf':
            continue  # docx/xlsx/pdf поиск читает сам
        key = os.path.normcase(path)
        if ext == '.xls' and xls.get(key):
            continue  # уже прочитан read_xls.py
        st = os.stat(path)
        imported[key] = [f'{st.st_size}:{int(st.st_mtime)}', ' '.join(ff.words(fix_letters(texts[name])))[:ff.MAX_TEXT]]
        kind = 'фото' if ext in ff.IMG_EXT else ext
        n[kind] = n.get(kind, 0) + 1
    ff.save_cache(imported, ff.IMPORTED_CACHE)
    print(f'Добавлено в поиск: {n}')


def main():
    if sys.argv[1] == '--extra':
        return import_extra(sys.argv[2])
    folder = sys.argv[1]
    full, head = load(folder, FULL), load(folder, HEAD)
    ocr = ff.load_cache(ff.OCR_CACHE)
    added = {'полностью': 0, 'шапка 1-й стр.': 0}
    for key, path, stamp, pages in find_scans():
        e = ocr.get(key)
        if not e or e[0] != stamp or len(e) < 3:
            e = ocr[key] = [stamp, '', 0]
        name = os.path.basename(path).lower()
        if name in full and e[2] < pages:
            e[1], e[2] = ' '.join(ff.words(fix_letters(full[name])))[:ff.MAX_TEXT], MAX_PAGES
            added['полностью'] += 1
        elif name in head and e[2] == 0:
            e[1], e[2] = ' '.join(ff.words(fix_letters(head[name]))), 1
            added['шапка 1-й стр.'] += 1
    ff.save_cache(ocr, ff.OCR_CACHE)
    left = sum(max(0, min(p, MAX_PAGES) - ocr[k][2]) for k, _, _, p in find_scans())
    print(f'Перенесено: {added}. Осталось распознать страниц: {left}')


if __name__ == '__main__':
    main()
