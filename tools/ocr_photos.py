"""Распознаёт НИЖНЮЮ часть фото (от 45% высоты до низа), чтобы поиск находил и подписи, и суммы внизу снимка.
Верхнюю половину уже распознал другой чат (imported.json, tools/import_ocr.py --extra); вместе — фото целиком.
Фото, распознанные целиком (photo_full.json другого чата), пропускаются.

    python tools/ocr_photos.py                      все фото из папок поиска
    python tools/ocr_photos.py --wait-for-pdf       сначала дождаться конца ocr_scans.py (чтобы не греть ноутбук вдвоём)
    python tools/ocr_photos.py --limit 3            проверка на 3 фото

Результат — %USERPROFILE%\\vl_find_files\\photo_ocr.json, сохраняется каждые 20 фото; можно прервать и запустить снова.
"""
import argparse, json, multiprocessing as mp, os, subprocess, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import find_files as ff  # noqa: E402
import ocr_scans as oc  # noqa: E402

TOP = 0.45  # верх до 50% уже распознан — берём с запасом, чтобы не разрезать строку на стыке
FULL_DONE = os.path.join(os.path.dirname(ff.CACHE), 'from_other_chat', 'photo_full.json')


def _ocr_bottom(task):
    key, path = task
    try:
        import numpy as np
        import pymupdf
        with pymupdf.open(path) as d:
            p = d[0]
            r = p.rect
            z = min(1.0, 1400 / max(r.width, 1))
            clip = pymupdf.Rect(r.x0, r.y0 + r.height * TOP, r.x1, r.y1)
            pix = p.get_pixmap(matrix=pymupdf.Matrix(z, z), clip=clip)
            img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n)[:, :, :3]
        return key, ' '.join(oc._engine(img).txts or ()), ''
    except Exception as e:
        return key, '', str(e)[:200]


def pdf_ocr_running():
    out = subprocess.run(['powershell', '-NoProfile', '-Command',
                          "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
                          "? { $_.CommandLine -like '*ocr_scans.py*' } | select -First 1 -Expand ProcessId"],
                         capture_output=True, text=True)
    return bool(out.stdout.strip())


def main():
    ap = argparse.ArgumentParser(description='Распознавание нижней части фото для поиска файлов')
    ap.add_argument('--limit', type=int)
    ap.add_argument('--workers', type=int, default=2)
    ap.add_argument('--wait-for-pdf', action='store_true')
    a = ap.parse_args()

    if a.wait_for_pdf:
        oc.log('Фото: жду, пока закончится распознавание сканов PDF…')
        while pdf_ocr_running():
            time.sleep(60)

    full = set()
    try:
        with open(FULL_DONE, encoding='utf-8') as f:
            full = {n.lower() for n in json.load(f)}
    except Exception:
        pass
    cache = ff.load_cache(ff.PHOTO_CACHE)
    tasks, stamps = [], {}
    for path in ff.iter_files(ff.DEFAULT_ROOTS):
        ext = os.path.splitext(path)[1].lower()
        if ext not in ff.IMG_EXT or os.path.basename(path).lower() in full:
            continue
        key = os.path.normcase(path)
        st = os.stat(path)
        stamps[key] = f'{st.st_size}:{int(st.st_mtime)}'
        e = cache.get(key)
        if not e or e[0] != stamps[key]:
            tasks.append((key, path))
    if a.limit:
        tasks = tasks[:a.limit]
    total = len(tasks)
    oc.log(f'Фото: распознать нижнюю часть у {total}, процессов: {a.workers}')
    if not total:
        oc.log('Фото: всё уже распознано.')
        return

    t0, done, errors = time.time(), 0, 0
    with mp.Pool(a.workers, initializer=oc._init) as pool:
        for key, raw, err in pool.imap_unordered(_ocr_bottom, tasks):
            done += 1
            if err:
                errors += 1  # heic и битые файлы pymupdf не открывает — просто пропускаем
            cache[key] = [stamps[key], ' '.join(ff.words(oc.fix_letters(raw)))[:ff.MAX_TEXT]]
            if done % 20 == 0 or done == total:
                ff.save_cache(cache, ff.PHOTO_CACHE)
                left = (time.time() - t0) / done * (total - done) / 60
                oc.log(f'Фото: {done} из {total}, осталось ~{left:.0f} мин')
    ff.save_cache(cache, ff.PHOTO_CACHE)
    oc.log(f'Фото: готово {done} за {(time.time() - t0) / 60:.0f} мин, не открылось: {errors}. '
           'Перезапусти окно поиска.')


if __name__ == '__main__':
    mp.freeze_support()
    main()
