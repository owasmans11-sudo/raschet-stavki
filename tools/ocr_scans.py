"""Распознаёт текст в сканах PDF (без текстового слоя), чтобы поиск файлов видел их содержимое.

    python tools/ocr_scans.py               все сканы из папок поиска (проект и C:\\РАБОТА)
    python tools/ocr_scans.py --limit 3     только 3 скана — для проверки

Берёт до 2 страниц на файл: сначала первые страницы всех сканов, потом вторые — так поиск
начинает видеть основное (стороны, маршрут, суммы) уже на середине работы.
Результат — %USERPROFILE%\\vl_find_files\\ocr.json (сохраняется каждые 20 страниц).
Можно прервать и запустить снова — продолжит с места остановки, готовое не пересчитывает.
Ход работы — в консоли и в ocr_log.txt рядом с ocr.json.
"""
import argparse, multiprocessing as mp, os, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import find_files as ff  # noqa: E402

LOG = os.path.join(os.path.dirname(ff.OCR_CACHE), 'ocr_log.txt')
MAX_PAGES = 2
DPI = 150
SAVE_EVERY = 20
# OCR путает похожие буквы: «ИHH», «Py6» — в словах, где есть кириллица, латиницу меняем на кириллицу
HOMOGLYPHS = str.maketrans('ABCEHKMOPTXaceopxyb', 'АВСЕНКМОРТХасеорхуЬ')

_engine = None


def _init():
    global _engine
    from rapidocr import RapidOCR
    from rapidocr.utils.typings import LangRec, OCRVersion, ModelType
    # onnxruntime на этом компьютере почти не ускоряется от потоков — выгоднее несколько процессов по 2 потока
    _engine = RapidOCR(params={
        'Rec.lang_type': LangRec.ESLAV, 'Rec.ocr_version': OCRVersion.PPOCRV5, 'Rec.model_type': ModelType.MOBILE,
        'Det.ocr_version': OCRVersion.PPOCRV5, 'Det.model_type': ModelType.MOBILE,
        'Global.use_cls': False, 'Global.log_level': 'error',
        'EngineConfig.onnxruntime.intra_op_num_threads': 2,
        'EngineConfig.onnxruntime.inter_op_num_threads': 1})


def _ocr_page(task):
    key, path, page = task
    try:
        import pymupdf
        with pymupdf.open(path) as doc:
            img = doc[page].get_pixmap(dpi=DPI).tobytes('png')
        return key, page, ' '.join(_engine(img).txts or ()), ''
    except Exception as e:
        return key, page, '', str(e)[:200]


def fix_letters(text):
    out = []
    for w in text.split():
        if any('а' <= c <= 'я' or 'А' <= c <= 'Я' for c in w):
            w = w.translate(HOMOGLYPHS)
        out.append(w)
    return ' '.join(out)


def log(msg):
    line = time.strftime('%H:%M:%S ') + msg
    print(line, flush=True)
    with open(LOG, 'a', encoding='utf-8') as f:
        f.write(line + '\n')


def find_scans():
    """PDF без текстового слоя: [(ключ, путь, stamp, страниц)]."""
    import pymupdf
    cache = ff.load_cache()
    scans = []
    for path in ff.iter_files(ff.DEFAULT_ROOTS):
        if not path.lower().endswith('.pdf'):
            continue
        key = os.path.normcase(path)
        try:
            st = os.stat(path)
            stamp = f'{st.st_size}:{int(st.st_mtime)}'
            entry = cache.get(key)
            if entry and entry[0] == stamp:
                if len(entry[1]) >= ff.SCAN_MIN_TEXT:
                    continue
                with pymupdf.open(path) as doc:
                    pages = len(doc)
            else:
                with pymupdf.open(path) as doc:
                    pages = len(doc)
                    if len(''.join(p.get_text() for p in doc)) >= ff.SCAN_MIN_TEXT:
                        continue
        except Exception:
            continue
        if pages:
            scans.append((key, path, stamp, min(pages, MAX_PAGES)))
    return scans


def main():
    ap = argparse.ArgumentParser(description='Распознавание сканов PDF для поиска файлов')
    ap.add_argument('--limit', type=int, help='сколько сканов взять (для проверки)')
    ap.add_argument('--workers', type=int, default=max(1, min(6, (os.cpu_count() or 2) // 2)))
    a = ap.parse_args()
    os.makedirs(os.path.dirname(ff.OCR_CACHE), exist_ok=True)

    log('Ищу сканы без текста…')
    scans = find_scans()
    if a.limit:
        scans = scans[:a.limit]
    ocr = ff.load_cache(ff.OCR_CACHE)
    # запись: [stamp, нормализованный текст, сколько страниц уже распознано]
    for key, path, stamp, pages in scans:
        e = ocr.get(key)
        if not e or e[0] != stamp or len(e) < 3:
            ocr[key] = [stamp, '', 0]
    tasks = [(key, path, p) for p in range(MAX_PAGES)
             for key, path, stamp, pages in scans if p < pages and ocr[key][2] <= p]
    total = len(tasks)
    log(f'Сканов: {len(scans)}, страниц распознать: {total}, процессов: {a.workers}')
    if not total:
        log('Всё уже распознано.')
        return

    t0, done, errors = time.time(), 0, 0
    pending = {}  # вторая страница может прийти раньше первой — складываем по порядку
    with mp.Pool(a.workers, initializer=_init) as pool:
        for key, page, raw, err in pool.imap_unordered(_ocr_page, tasks):
            done += 1
            if err:
                errors += 1
                log(f'  не получилось: {os.path.basename(key)} стр. {page + 1}: {err}')
            pending.setdefault(key, {})[page] = ' '.join(ff.words(fix_letters(raw)))
            e = ocr[key]
            while e[2] in pending[key]:
                e[1] = (e[1] + ' ' + pending[key].pop(e[2])).strip()[:ff.MAX_TEXT]
                e[2] += 1
            if done % SAVE_EVERY == 0 or done == total:
                ff.save_cache(ocr, ff.OCR_CACHE)
                left = (time.time() - t0) / done * (total - done) / 60
                log(f'{done} из {total} страниц, осталось ~{left:.0f} мин')
    ff.save_cache(ocr, ff.OCR_CACHE)
    log(f'Готово: {done} страниц за {(time.time() - t0) / 60:.0f} мин, ошибок: {errors}. '
        'Перезапусти окно поиска — сканы будут искаться по тексту.')


if __name__ == '__main__':
    mp.freeze_support()
    main()
