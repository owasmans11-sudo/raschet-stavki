"""Логика: подключение к почте по IMAP и скачивание вложений из «Входящих»."""

import csv
import email
from email import policy
import html
import imaplib
import os
import re
from datetime import date, datetime, timedelta
from email.header import decode_header, make_header
from email.utils import parseaddr, parsedate_to_datetime
from urllib.parse import quote

PROVIDERS = {
    "Gmail": "imap.gmail.com",
    "Яндекс": "imap.yandex.ru",
    "Mail.ru": "imap.mail.ru",
    "Outlook / Hotmail": "outlook.office365.com",
    "Другой": "",
}

# быстрые кнопки: только заполняют поля «с … по …»
QUICK_PERIODS = ["Вчера", "Месяц", "Прошлый квартал", "Полгода", "Год"]

LAYOUTS = ["По месяцам", "По отправителю", "Месяц → отправитель", "Одной папкой"]

MONTHS_EN = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
             "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

BATCH = 50

OPIS_CSV = "Опись.csv"
OPIS_HTML = "Опись.html"
OPIS_COLUMNS = ["Дата", "Ящик", "От кого", "Адрес отправителя", "Кому", "Тема",
                "Файл", "Путь к файлу", "Текст письма", "Ссылка на письмо", "Message-ID"]


def quick_period(name, today=None):
    """Даты (с, по) для быстрой кнопки, обе включительно."""
    today = today or date.today()
    if name == "Вчера":
        d = today - timedelta(days=1)
        return d, d
    if name == "Прошлый квартал":
        q_start = date(today.year, 3 * ((today.month - 1) // 3) + 1, 1)
        end = q_start - timedelta(days=1)
        return date(end.year, end.month - 2, 1), end
    days = {"Месяц": 30, "Полгода": 182, "Год": 365}[name]
    return today - timedelta(days=days), today


def parse_ru_date(text):
    return datetime.strptime(text.strip(), "%d.%m.%Y").date()


def imap_date(d):
    # IMAP требует английские названия месяцев, не зависим от локали системы
    return f"{d.day:02d}-{MONTHS_EN[d.month - 1]}-{d.year}"


def decode_str(value):
    if not value:
        return ""
    try:
        return str(make_header(decode_header(str(value))))
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
    """Путь к уже лежащему такому же файлу (то же имя или «имя (N)» и то же содержимое) или None."""
    root, ext = os.path.splitext(name)
    candidates = [name] + [f"{root} ({n}){ext}" for n in range(1, 50)]
    for cand in candidates:
        path = os.path.join(folder, cand)
        if not os.path.exists(path):
            return None
        if os.path.getsize(path) == len(payload):
            with open(path, "rb") as f:
                if f.read() == payload:
                    return path
    return None


def save_once(folder, name, payload):
    """Сохраняет файл, если такого ещё нет. Возвращает (путь, новый_ли)."""
    os.makedirs(folder, exist_ok=True)
    path = already_saved(folder, name, payload)
    if path:
        return path, False
    path = unique_path(folder, name)
    with open(path, "wb") as f:
        f.write(payload)
    return path, True


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


def html_to_text(text):
    text = re.sub(r"(?is)<(script|style|head)\b.*?</\1>", "", text)
    text = re.sub(r"(?i)<br\s*/?>|</(p|div|tr|li|h\d)>", "\n", text)
    text = re.sub(r"(?s)<[^>]+>", "", text)
    text = html.unescape(text).replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n\s*\n\s*\n+", "\n\n", text)


def body_text(msg):
    """Текст письма: обычный, а если есть только HTML — очищенный от разметки."""
    try:
        part = msg.get_body(preferencelist=("plain", "html"))
    except Exception:
        part = None
    if part is None:
        return ""
    try:
        text = part.get_content()
    except Exception:
        payload = part.get_payload(decode=True) or b""
        text = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
    if part.get_content_type() == "text/html":
        text = html_to_text(text)
    return text.strip()


def web_link(host, login, subject, msg_id, gm_msgid=None):
    """Ссылка на письмо в веб-почте. Точная — только у Gmail, у остальных — поиск по теме."""
    host = host.lower()
    if gm_msgid:
        return f"https://mail.google.com/mail/u/{quote(login)}/#all/{int(gm_msgid):x}"
    if "gmail" in host and msg_id:
        return (f"https://mail.google.com/mail/u/{quote(login)}/#search/"
                + quote(f"rfc822msgid:{msg_id.strip('<>')}"))
    if not subject:
        return ""
    if "mail.ru" in host:
        return "https://e.mail.ru/search/?q_query=" + quote(subject)
    if "yandex" in host:
        return "https://mail.yandex.ru/#search?request=" + quote(subject)
    return ""


def target_dir(out_dir, layout, msg_dt, sender):
    month = msg_dt.strftime("%Y-%m") if msg_dt else "без-даты"
    sender = safe_name(sender.lower() or "без-отправителя", 80)
    if layout == "По месяцам":
        return os.path.join(out_dir, month)
    if layout == "По отправителю":
        return os.path.join(out_dir, sender)
    if layout == "Месяц → отправитель":
        return os.path.join(out_dir, month, sender)
    return out_dir


class Opis:
    """Опись: какой файл из какого письма и с какого ящика. Копится между запусками."""

    def __init__(self, out_dir):
        self.out_dir = out_dir
        self.csv_path = os.path.join(out_dir, OPIS_CSV)
        self.keys = set()
        if os.path.exists(self.csv_path):
            with open(self.csv_path, encoding="utf-8-sig", newline="") as f:
                for row in csv.DictReader(f, delimiter=";"):
                    self.keys.add(self.key(row))

    @staticmethod
    def key(row):
        return (row.get("Ящик", ""), row.get("Message-ID", "") or row.get("Дата", "") + row.get("Тема", ""),
                row.get("Путь к файлу", ""))

    def rel(self, path):
        return os.path.relpath(path, self.out_dir) if path else ""

    def add(self, row):
        if self.key(row) in self.keys:
            return
        self.keys.add(self.key(row))
        new = not os.path.exists(self.csv_path)
        with open(self.csv_path, "a", encoding="utf-8-sig" if new else "utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=OPIS_COLUMNS, delimiter=";")
            if new:
                w.writeheader()
            w.writerow(row)

    def write_html(self):
        if not os.path.exists(self.csv_path):
            return
        with open(self.csv_path, encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f, delimiter=";"))
        rows.sort(key=lambda r: r.get("Дата", ""), reverse=True)

        def a(href, text, local=True):
            if not href:
                return ""
            if local:
                href = quote(href.replace(os.sep, "/"))
            return f'<a href="{html.escape(href)}" target="_blank">{html.escape(text)}</a>'

        lines = []
        for r in rows:
            e = {k: html.escape(r.get(k, "")) for k in OPIS_COLUMNS}
            lines.append(
                "<tr>"
                f"<td>{e['Дата']}</td><td>{e['Ящик']}</td>"
                f"<td>{e['От кого']}<br><small>{e['Адрес отправителя']}</small></td>"
                f"<td>{e['Тема']}</td>"
                f"<td>{a(r.get('Путь к файлу'), r.get('Файл') or '') or '<i>без вложений</i>'}</td>"
                f"<td>{a(r.get('Текст письма'), 'текст')}</td>"
                f"<td>{a(r.get('Ссылка на письмо'), 'в почте', local=False)}</td>"
                "</tr>")
        page = HTML_TEMPLATE.replace("{count}", str(len(rows))).replace("{rows}", "\n".join(lines))
        with open(os.path.join(self.out_dir, OPIS_HTML), "w", encoding="utf-8") as f:
            f.write(page)


HTML_TEMPLATE = """<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><title>Опись вложений из почты</title>
<style>
body{font:14px Segoe UI,Arial,sans-serif;margin:16px;color:#222}
input{font-size:16px;padding:6px 10px;width:100%;max-width:520px;margin-bottom:10px}
table{border-collapse:collapse;width:100%}
th{background:#2f5d8a;color:#fff;text-align:left;padding:6px;position:sticky;top:0}
td{padding:5px 6px;vertical-align:top;border-bottom:1px solid #e3e8ee}
tr:nth-child(even) td{background:#f4f7fa}
small{color:#667}
</style></head><body>
<h2>Опись вложений из почты</h2>
<input id="q" placeholder="Поиск: имя файла, отправитель, тема…" autofocus>
<p><small>Строк: {count}. «в почте» — у Gmail точная ссылка на письмо, у Mail.ru и Яндекса — поиск по теме.</small></p>
<table><thead><tr><th>Дата</th><th>Ящик</th><th>От кого</th><th>Тема</th><th>Файл</th><th>Письмо</th><th>Ссылка</th></tr></thead>
<tbody id="t">
{rows}
</tbody></table>
<script>
document.getElementById('q').addEventListener('input',function(){
  var q=this.value.toLowerCase();
  document.querySelectorAll('#t tr').forEach(function(tr){
    tr.style.display=tr.textContent.toLowerCase().indexOf(q)<0?'none':'';
  });
});
</script></body></html>
"""


def save_message(raw, ctx, gm_msgid=None):
    """Сохраняет вложения (и текст) одного письма. Возвращает (новых_файлов, новых_текстов)."""
    msg = email.message_from_bytes(raw, policy=policy.default)
    try:
        msg_dt = parsedate_to_datetime(str(msg["Date"]))
        msg_date = msg_dt.strftime("%Y-%m-%d")
    except Exception:
        msg_dt, msg_date = None, "без-даты"
    from_name, from_addr = parseaddr(decode_str(msg["From"]))
    subject = decode_str(msg["Subject"]).strip()
    msg_id = str(msg["Message-ID"] or "").strip()
    link = web_link(ctx["host"], ctx["login"], subject, msg_id, gm_msgid)
    folder = target_dir(ctx["out_dir"], ctx["layout"], msg_dt, from_addr)
    opis = ctx["opis"]

    files, saved = [], 0
    for filename, payload in iter_attachments(msg):
        path, new = save_once(folder, safe_name(f"{msg_date}_{filename}"), payload)
        files.append((filename, path))
        if new:
            saved += 1
            ctx["log"](f"  ✓ {opis.rel(path)}")

    text_path, text_new = "", 0
    if ctx["save_text"]:
        stamp = msg_dt.strftime("%Y-%m-%d %H-%M") if msg_dt else "без-даты"
        lines = [
            f"Ящик:       {ctx['login']}",
            f"От:         {decode_str(msg['From'])}",
            f"Кому:       {decode_str(msg['To'])}",
        ]
        if msg["Cc"]:
            lines.append(f"Копия:      {decode_str(msg['Cc'])}")
        lines += [
            f"Дата:       {msg_dt.strftime('%d.%m.%Y %H:%M') if msg_dt else '—'}",
            f"Тема:       {subject or '(без темы)'}",
            "Вложения:   " + ("; ".join(opis.rel(p) for _, p in files) or "нет"),
            f"В почте:    {link or '—'}",
            f"Message-ID: {msg_id or '—'}",
            "-" * 60,
            "",
            body_text(msg),
        ]
        payload = ("\n".join(lines) + "\n").encode("utf-8-sig")
        name = safe_name(f"{stamp}_ПИСЬМО_{subject or 'без темы'}", 120) + ".txt"
        text_path, created = save_once(folder, name, payload)
        text_new = int(created)

    base = {
        "Дата": msg_dt.strftime("%Y-%m-%d %H:%M") if msg_dt else "",
        "Ящик": ctx["login"], "От кого": from_name, "Адрес отправителя": from_addr,
        "Кому": decode_str(msg["To"]), "Тема": subject,
        "Текст письма": opis.rel(text_path), "Ссылка на письмо": link, "Message-ID": msg_id,
    }
    for filename, path in files:
        opis.add({**base, "Файл": filename, "Путь к файлу": opis.rel(path)})
    if not files and text_path:
        opis.add({**base, "Файл": "", "Путь к файлу": ""})
    return saved, text_new


def download_attachments(host, login, password, date_from, date_to, out_dir,
                         layout="Одной папкой", save_text=True,
                         log=print, progress=None, stop_flag=None, port=993):
    """Скачивает вложения из INBOX за дни с `date_from` по `date_to` включительно.

    Возвращает (писем_просмотрено, файлов_сохранено, текстов_сохранено).
    """
    os.makedirs(out_dir, exist_ok=True)
    opis = Opis(out_dir)
    ctx = {"host": host, "login": login, "out_dir": out_dir, "layout": layout,
           "save_text": save_text, "log": log, "opis": opis}
    gmail = "gmail" in host.lower()
    fetch_what = "(X-GM-MSGID BODY.PEEK[])" if gmail else "(BODY.PEEK[])"

    log(f"Подключаюсь к {host}…")
    conn = imaplib.IMAP4_SSL(host, port)
    try:
        conn.login(login, password)
        conn.select("INBOX", readonly=True)  # письма не помечаются прочитанными

        status, data = conn.search(None, "SINCE", imap_date(date_from),
                                   "BEFORE", imap_date(date_to + timedelta(days=1)))
        if status != "OK":
            raise RuntimeError("Сервер не выполнил поиск писем")
        ids = data[0].split()
        total = len(ids)
        log(f"Писем с {date_from:%d.%m.%Y} по {date_to:%d.%m.%Y}: {total}")

        saved = texts = done = 0
        for i in range(0, total, BATCH):
            if stop_flag and stop_flag():
                log("Остановлено пользователем.")
                break
            chunk = b",".join(ids[i:i + BATCH])
            status, parts = conn.fetch(chunk, fetch_what)
            if status != "OK":
                log("Не удалось получить часть писем, пропускаю")
                continue
            for item in parts:
                if not isinstance(item, tuple):
                    continue
                done += 1
                m = re.search(rb"X-GM-MSGID (\d+)", item[0])
                try:
                    s, t = save_message(item[1], ctx, m.group(1).decode() if m else None)
                    saved += s
                    texts += t
                except Exception as e:
                    # одно «кривое» письмо не должно останавливать всё скачивание
                    log(f"  ! письмо пропущено: {e}")
                if progress:
                    progress(done, total)
        return done, saved, texts
    finally:
        try:
            opis.write_html()
        except Exception as e:
            log(f"  ! опись HTML не обновлена: {e}")
        try:
            conn.logout()
        except Exception:
            pass
