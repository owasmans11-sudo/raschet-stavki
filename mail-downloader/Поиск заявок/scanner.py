"""Обход папки: извлечение текста (с кэшем), классификация, отчёт и копирование."""

import hashlib
import os
import shutil
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from classify import classify
from extract import ARCHIVE_EXT, archive_members, extract_bytes, find_tesseract

CACHE_FILE = os.path.join(os.path.expanduser("~"), ".zayavki", "cache.sqlite")
VERDICT_DIRS = {"Заявка": "Заявки", "Проверить": "Проверить вручную",
                "Мы заказчик": "Мы заказчик"}


class Cache:
    """Текст файла по его хэшу: повторный запуск не распознаёт всё заново."""

    def __init__(self):
        os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
        self.db = sqlite3.connect(CACHE_FILE, check_same_thread=False)
        self.db.execute("CREATE TABLE IF NOT EXISTS t (h TEXT PRIMARY KEY, how TEXT, text TEXT)")
        self.lock = threading.Lock()

    def get(self, h):
        with self.lock:
            r = self.db.execute("SELECT how, text FROM t WHERE h=?", (h,)).fetchone()
        return r

    def put(self, h, how, text):
        with self.lock:
            self.db.execute("INSERT OR REPLACE INTO t VALUES (?,?,?)", (h, how, text))
            self.db.commit()


def list_files(src, skip_dir):
    out = []
    for root, dirs, files in os.walk(src):
        if skip_dir and os.path.abspath(root).startswith(os.path.abspath(skip_dir)):
            dirs[:] = []
            continue
        for f in files:
            out.append(os.path.join(root, f))
    return out


def scan(src, out_dir, company_names, log, progress, stop_flag, workers=None):
    t0 = time.time()
    cache = Cache()
    if not find_tesseract():
        log("⚠ Tesseract (распознавание картинок) не найден: картинки и сканы будут пропущены.")
    files = list_files(src, out_dir)
    total = len(files)
    log(f"Файлов в папке: {total}")
    seen = {}
    rows = []
    lock = threading.Lock()
    done = [0]

    def handle_one(path):
        if stop_flag():
            return []
        if os.path.getsize(path) > 150_000_000:
            return [{"path": path, "inner": "", "verdict": "Не заявка", "score": "",
                     "role": "", "found": "", "other": "", "how": "слишком большой",
                     "snippet": ""}]
        with open(path, "rb") as fh:
            data = fh.read()
        h = hashlib.sha1(data).hexdigest()
        with lock:
            dup_of = seen.get(h)
            if dup_of is None:
                seen[h] = path
        if dup_of:
            return [{"path": path, "inner": "", "verdict": "Дубликат", "score": "",
                     "role": "", "found": "", "other": "", "how": "",
                     "snippet": f"Такой же файл: {os.path.basename(dup_of)}"}]
        ext = os.path.splitext(path)[1].lower()
        if ext in ARCHIVE_EXT:
            return handle_archive(path, h)
        return [check(path, "", os.path.basename(path), data, h)]

    def check(path, inner, name, data, h):
        c = cache.get(h)
        if c:
            how, text = c
        else:
            try:
                text, how = extract_bytes(name, data)
            except Exception as e:
                text, how = "", f"ошибка: {type(e).__name__}"
            cache.put(h, how, text)
        r = classify(text, name, company_names)
        r.update(path=path, inner=inner, how=how)
        return r

    def handle_archive(path, h):
        res = []
        try:
            for inner, data in archive_members(path):
                if stop_flag():
                    break
                ih = hashlib.sha1(data).hexdigest()
                if os.path.splitext(inner)[1].lower() in ARCHIVE_EXT:
                    continue    # архив в архиве встречается редко, пропускаем
                res.append(check(path, inner, os.path.basename(inner), data, ih))
        except Exception as e:
            res.append({"path": path, "inner": "", "verdict": "Не заявка", "score": "",
                        "role": "", "found": "", "other": "", "snippet": "",
                        "how": f"архив не открылся: {type(e).__name__}"})
        return res

    workers = workers or max(2, min(8, (os.cpu_count() or 4)))
    with ThreadPoolExecutor(workers) as pool:
        futs = [pool.submit(handle_one, p) for p in files]
        for f in as_completed(futs):
            try:
                got = f.result()
            except Exception as e:
                got = []
                log(f"Ошибка: {e}")
            with lock:
                rows.extend(got)
                done[0] += 1
                for r in got:
                    if r["verdict"] == "Заявка":
                        log(f"✔ {os.path.basename(r['path'])}" + (f" → {r['inner']}" if r["inner"] else ""))
            progress(done[0], total)

    if stop_flag():
        log("Остановлено. Отчёт по уже просмотренным файлам.")
    copied = copy_found(rows, out_dir)
    report = write_report(rows, out_dir)
    counts = {}
    for r in rows:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
    mins = (time.time() - t0) / 60
    log(f"Время: {mins:.0f} мин.")
    return counts, copied, report


def copy_found(rows, out_dir):
    copied = 0
    archives = {}
    for r in rows:
        sub = VERDICT_DIRS.get(r["verdict"])
        if not sub:
            continue
        d = os.path.join(out_dir, sub)
        os.makedirs(d, exist_ok=True)
        if r["inner"]:
            archives.setdefault((r["path"], d), []).append(r)
            continue
        r["copy"] = _copy(r["path"], d)
        copied += 1
    # Из архивов достаём только сами заявки
    for (path, d), items in archives.items():
        want = {i["inner"] for i in items}
        prefix = os.path.splitext(os.path.basename(path))[0]
        try:
            for inner, data in archive_members(path):
                if inner in want:
                    name = f"{prefix} - {os.path.basename(inner)}"
                    dst = _unique(os.path.join(d, name))
                    with open(dst, "wb") as fh:
                        fh.write(data)
                    for i in items:
                        if i["inner"] == inner:
                            i["copy"] = dst
                    copied += 1
        except Exception:
            pass
    return copied


def _unique(dst):
    base, ext = os.path.splitext(dst)
    n = 1
    while os.path.exists(dst):
        dst = f"{base} ({n}){ext}"
        n += 1
    return dst


def _copy(src, d):
    dst = _unique(os.path.join(d, os.path.basename(src)))
    shutil.copy2(src, dst)
    return dst


def write_report(rows, out_dir):
    import openpyxl
    from openpyxl.styles import Font, PatternFill
    order = {"Заявка": 0, "Проверить": 1, "Мы заказчик": 2, "Не заявка": 3, "Дубликат": 4}
    rows = sorted(rows, key=lambda r: (order.get(r["verdict"], 9), -float(r["score"] or 0),
                                       os.path.basename(r["path"])))
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Файлы"
    head = ["Итог", "Файл", "Внутри архива", "Дата письма", "Балл", "Роль нашей компании",
            "Найдено", "Похоже на", "Как прочитан", "Начало текста", "Где лежит", "Копия"]
    ws.append(head)
    for c in ws[1]:
        c.font = Font(bold=True)
    fills = {"Заявка": "C6EFCE", "Проверить": "FFEB9C", "Мы заказчик": "DDEBF7"}
    for r in rows:
        name = os.path.basename(r["path"])
        date = name[:10] if len(name) > 10 and name[4] == "-" and name[7] == "-" else ""
        ws.append([r["verdict"], name, r["inner"], date, r["score"], r["role"], r["found"],
                   r["other"], r["how"], r["snippet"], r["path"], r.get("copy", "")])
        if r["verdict"] in fills:
            for c in ws[ws.max_row]:
                c.fill = PatternFill("solid", fgColor=fills[r["verdict"]])
        cell = ws.cell(ws.max_row, 2)
        target = r.get("copy") or r["path"]
        cell.hyperlink = "file:///" + target.replace("\\", "/")
    widths = [13, 45, 30, 12, 7, 18, 45, 20, 16, 70, 50, 50]
    for i, w in enumerate(widths):
        ws.column_dimensions[chr(65 + i)].width = w
    ws.auto_filter.ref = ws.dimensions
    ws.freeze_panes = "A2"
    os.makedirs(out_dir, exist_ok=True)
    path = _unique(os.path.join(out_dir, f"Отчёт {time.strftime('%Y-%m-%d %H-%M')}.xlsx"))
    wb.save(path)
    return path
