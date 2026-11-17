"""Вечернее скачивание почты без окна — со всех ящиков из настроек (окно настройки — nightly_settings.py).

    python nightly_mail.py              скачать и обработать (так запускает планировщик)
    python nightly_mail.py --only-mail  только скачать, без распознавания и пар

Для каждого ящика скачивает письма из «Входящих» с дня прошлого успешного скачивания (этот день — ещё раз: письма,
пришедшие после прошлого запуска, не потеряются, а дублей не будет — уже скачанное пропускается)
в C:\\РАБОТА\\Почта\\<ящик>\\ГГГГ-ММ\\. Потом tools/nightly_update.py (распознавание новых сканов → картотека) и
tools/pary_zayavok.py (пары заявок и отчёт C:\\РАБОТА\\Перевозки\\Отчёт ГГГГ-ММ-ДД.xlsx).
Журнал: %USERPROFILE%\\vl_find_files\\mail_log.txt; итог по ящикам — mail_status.json рядом (его берёт отчёт).
Ошибка одного ящика (нет интернета, пароль отозван) не мешает другому.
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mail_core import download_attachments

SETTINGS_FILE = os.path.join(os.path.expanduser("~"), ".mail_downloader_nightly.json")
BASE = os.path.join(os.path.expanduser("~"), "vl_find_files")  # как у tools/find_files.py
LOG = os.path.join(BASE, "mail_log.txt")
STATUS = os.path.join(BASE, "mail_status.json")
DEFAULT_DIR = r"C:\РАБОТА\Почта"
PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NIGHTLY = os.path.join(PROJECT, "tools", "nightly_update.py")
PARY = os.path.join(PROJECT, "tools", "pary_zayavok.py")
RAZBOR = os.path.join(PROJECT, "tools", "razbor_pochty.py")
JUNK = "ПОМОЙКА"  # тексты писем и логотипы: <Почта>\ПОМОЙКА\<ящик>\ГГГГ-ММ\ (решение владельца 05.11.2026)


def load_settings():
    try:
        with open(SETTINGS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"boxes": [], "out_dir": DEFAULT_DIR}


def save_settings(data):
    tmp = SETTINGS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, SETTINGS_FILE)


def log(msg):
    os.makedirs(BASE, exist_ok=True)
    lines = []
    if os.path.exists(LOG):
        with open(LOG, encoding="utf-8", errors="ignore") as f:
            lines = f.read().splitlines()[-600:]
    lines.append(time.strftime("%d.%m.%Y %H:%M  ") + msg)
    with open(LOG, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def box_dir(out_dir, login):
    return os.path.join(out_dir, login.split("@")[0] if login else "ящик")


def explain(e):
    text = str(e)
    if "AUTHENTICATIONFAILED" in text or "Invalid credentials" in text or "authentication failed" in text.lower():
        return "почта не пустила: пароль приложения неверный или отозван — введите новый в «Настройка почты»"
    if isinstance(e, OSError) and not text.startswith("b'"):
        return "нет связи с почтой (интернет?): " + text[:120]
    return "ошибка: " + text[:200]


def check_login(host, login, password):
    """Пробный вход (для кнопки «Проверить вход»). Возвращает текст ошибки или ''."""
    import imaplib
    try:
        conn = imaplib.IMAP4_SSL(host, 993, timeout=30)
        try:
            conn.login(login, password)
            conn.select("INBOX", readonly=True)
        finally:
            try:
                conn.logout()
            except Exception:
                pass
        return ""
    except Exception as e:
        return explain(e)


def download_all(log=log):
    s = load_settings()
    out_dir = s.get("out_dir") or DEFAULT_DIR
    today = date.today()
    status = {"run": datetime.now().strftime("%d.%m.%Y %H:%M"), "boxes": []}
    for box in s.get("boxes", []):
        login, host, pwd = box.get("login", ""), box.get("host") or "imap.mail.ru", box.get("password", "")
        if not (login and pwd):
            status["boxes"].append({"login": login or "?", "error": "нет адреса или пароля — откройте «Настройка почты»"})
            continue
        last = box.get("last_ok") or box.get("start") or f"{today - timedelta(days=7):%d.%m.%Y}"
        d_from = datetime.strptime(last, "%d.%m.%Y").date()
        period = f"{d_from:%d.%m}–{today:%d.%m.%Y}"
        log(f"{login}: скачиваю {period}")
        try:
            letters, files, texts = download_attachments(
                host, login, pwd, d_from, today, box_dir(out_dir, login), layout="По месяцам",
                save_text=True, log=lambda t: None, junk_dir=box_dir(os.path.join(out_dir, JUNK), login))
            box["last_ok"] = f"{today:%d.%m.%Y}"
            status["boxes"].append({"login": login, "letters": letters, "files": files, "texts": texts,
                                    "period": period})
            log(f"{login}: писем {letters}, новых файлов {files}, текстов {texts}")
        except Exception as e:
            status["boxes"].append({"login": login, "error": explain(e), "period": period})
            log(f"{login}: {explain(e)}")
    save_settings(s)  # дата успешного скачивания — у каждого ящика своя
    os.makedirs(BASE, exist_ok=True)
    with open(STATUS, "w", encoding="utf-8") as f:
        json.dump(status, f, ensure_ascii=False, indent=2)
    return status


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only-mail", action="store_true", help="только скачать, без распознавания и пар")
    a = ap.parse_args()
    log("почта: старт")
    try:
        download_all()
    except Exception as e:  # сломанные настройки и т.п. — распознавание всё равно запускаем
        log("почта: " + explain(e))
    if not a.only_mail:
        python = os.path.join(os.path.dirname(sys.executable), "python.exe")  # консольный — окно скрыто флагом
        flags = subprocess.CREATE_NO_WINDOW | subprocess.BELOW_NORMAL_PRIORITY_CLASS if os.name == "nt" else 0
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        # распознавание и картотека (если ночное обновление сейчас идёт — оно само пропустит повтор),
        # потом пары и отчёт — только здесь, чтобы отчёт был один в день
        for title, script in (("уборка в ПОМОЙКУ", RAZBOR), ("распознавание и картотека", NIGHTLY),
                              ("пары заявок, раскладка почты переносом и отчёт", PARY)):
            args = [script, "--pomoyka"] if script == RAZBOR else [script]
            r = subprocess.run([python] + args, cwd=PROJECT, creationflags=flags, stdin=subprocess.DEVNULL, env=env,
                               capture_output=True, text=True, encoding="utf-8", errors="ignore")
            tail = (r.stdout.strip().splitlines() or [""])[-1][:200]
            log(f"почта: {title} — {'готово' if r.returncode == 0 else 'ОШИБКА ' + str(r.returncode)} {tail}")
    log("почта: конец")


if __name__ == "__main__":
    main()
