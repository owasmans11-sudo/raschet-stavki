"""Логика: подключение к почте по IMAP и скачивание вложений из «Входящих»."""

import email
from email import policy
import imaplib
import os
import re
from datetime import date, timedelta
from email.header import decode_header, make_header
from email.utils import parsedate_to_datetime

PROVIDERS = {
    "Gmail": "imap.gmail.com",
    "Яндекс": "imap.yandex.ru",
    "Mail.ru": "imap.mail.ru",
    "Outlook / Hotmail": "outlook.office365.com",
    "Другой": "",
}

PERIODS = {
    "Месяц": 30,
    "Полгода": 182,
    "Год": 365,
}

MONTHS_EN = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
             "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

BATCH = 50


def imap_date(d):
    # IMAP требует английские названия месяцев, не зависим от локали системы
    return f"{d.day:02d}-{MONTHS_EN[d.month - 1]}-{d.year}"


def decode_str(value):
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return str(value)


def safe_name(name, limit=150):
    name = re.sub(r'[\\/:*?"<>|\r\n\t]+', "_", name).strip(" .")
    if len(name) > limit:
        root, ext = os.path.splitext(name)
        name = root[: limit - len(ext)] + ext
    return name or "file"


def unique_path(folder, name):
    path = os.path.join(folder, name)
    root, ext = os.path.splitext(path)
    n = 1
    while os.path.exists(path):
        path = f"{root} ({n}){ext}"
        n += 1
    return path


def already_saved(folder, name, payload):
    """Есть ли уже такой же файл (то же имя или «имя (N)» и то же содержимое)."""
    root, ext = os.path.splitext(name)
    candidates = [name] + [f"{root} ({n}){ext}" for n in range(1, 50)]
    for cand in candidates:
        path = os.path.join(folder, cand)
        if not os.path.exists(path):
            return False
        if os.path.getsize(path) == len(payload):
            with open(path, "rb") as f:
                if f.read() == payload:
                    return True
    return False


def iter_attachments(msg):
    for part in msg.walk():
        if part.is_multipart():
            continue
        filename = part.get_filename()
        # заголовок может прийти объектом Header (кривые/нелатинские письма)
        disposition = str(part.get("Content-Disposition") or "").lower()
        if not filename and "attachment" not in disposition:
            continue
        payload = part.get_payload(decode=True)
        if not payload:
            continue
        filename = decode_str(filename) if filename else "attachment"
        yield filename, payload


def save_message_attachments(raw, out_dir, log):
    msg = email.message_from_bytes(raw, policy=policy.default)
    try:
        msg_date = parsedate_to_datetime(str(msg["Date"])).strftime("%Y-%m-%d")
    except Exception:
        msg_date = "без-даты"
    count = 0
    for filename, payload in iter_attachments(msg):
        name = safe_name(f"{msg_date}_{filename}")
        if already_saved(out_dir, name, payload):
            continue  # скачан при прошлом запуске
        path = unique_path(out_dir, name)
        with open(path, "wb") as f:
            f.write(payload)
        count += 1
        log(f"  ✓ {os.path.basename(path)}")
    return count


def download_attachments(host, login, password, days, out_dir,
                         log=print, progress=None, stop_flag=None, port=993):
    """Скачивает вложения из INBOX за последние `days` дней в `out_dir`.

    Возвращает (писем_просмотрено, файлов_сохранено).
    """
    since = date.today() - timedelta(days=days)
    os.makedirs(out_dir, exist_ok=True)

    log(f"Подключаюсь к {host}…")
    conn = imaplib.IMAP4_SSL(host, port)
    try:
        conn.login(login, password)
        conn.select("INBOX", readonly=True)  # письма не помечаются прочитанными

        status, data = conn.search(None, "SINCE", imap_date(since))
        if status != "OK":
            raise RuntimeError("Сервер не выполнил поиск писем")
        ids = data[0].split()
        total = len(ids)
        log(f"Писем с {since:%d.%m.%Y}: {total}")

        saved = 0
        done = 0
        for i in range(0, total, BATCH):
            if stop_flag and stop_flag():
                log("Остановлено пользователем.")
                break
            chunk = b",".join(ids[i:i + BATCH])
            status, parts = conn.fetch(chunk, "(BODY.PEEK[])")
            if status != "OK":
                log("Не удалось получить часть писем, пропускаю")
                continue
            for item in parts:
                if not isinstance(item, tuple):
                    continue
                done += 1
                try:
                    saved += save_message_attachments(item[1], out_dir, log)
                except Exception as e:
                    # одно «кривое» письмо не должно останавливать всё скачивание
                    log(f"  ! письмо пропущено: {e}")
                if progress:
                    progress(done, total)
        return done, saved
    finally:
        try:
            conn.logout()
        except Exception:
            pass
