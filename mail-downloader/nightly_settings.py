"""Окно «Настройка почты» для вечернего скачивания (nightly_mail.py): ящики, пароли приложений, папка.

Пароли вводит владелец сам; они хранятся только на этом компьютере — в %USERPROFILE%\\.mail_downloader_nightly.json.
Кнопки: «Проверить вход» (пробный вход в ящик, письма не трогаются), «Сохранить», «Скачать сейчас» (то же, что вечером),
«Журнал», «Папка отчётов».
"""

import os
import subprocess
import sys
import threading
import tkinter as tk
from datetime import date, datetime, timedelta
from tkinter import messagebox, ttk

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from nightly_mail import DEFAULT_DIR, LOG, check_login, load_settings, save_settings

BOXES = ["", ""]  # адреса задаются при первой настройке
HOST = "imap.mail.ru"  # list.ru, mail.ru, bk.ru, inbox.ru — один сервер Mail.ru
REPORTS = r"C:\РАБОТА\Перевозки"


class Settings(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Настройка почты — 2 ящика, каждый вечер")
        s = load_settings()
        saved = {b.get("login", "").lower(): b for b in s.get("boxes", [])}
        logins = [b.get("login") for b in s.get("boxes", [])] or BOXES

        frm = ttk.Frame(self, padding=12)
        frm.pack(fill="both", expand=True)
        frm.columnconfigure(1, weight=1)
        ttk.Label(frm, text="Пароль приложения создаётся в Mail.ru: Настройки → Безопасность → «Пароли для внешних "
                            "приложений». Обычный пароль от почты сюда не подходит.", wraplength=600,
                  foreground="#555").grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 8))

        self.rows = []
        r = 1
        for i, login in enumerate(logins[:4]):
            b = saved.get(login.lower(), {})
            box = ttk.LabelFrame(frm, text=f"Ящик {i + 1}", padding=8)
            box.grid(row=r, column=0, columnspan=3, sticky="ew", pady=4)
            box.columnconfigure(1, weight=1)
            v_login = tk.StringVar(value=login)
            v_pwd = tk.StringVar(value=b.get("password", ""))
            v_state = tk.StringVar(value=("последнее скачивание: " + b["last_ok"]) if b.get("last_ok") else "ещё не скачивали")
            ttk.Label(box, text="Адрес").grid(row=0, column=0, sticky="w")
            ttk.Entry(box, textvariable=v_login).grid(row=0, column=1, sticky="ew", padx=4)
            ttk.Label(box, text="Пароль приложения").grid(row=1, column=0, sticky="w")
            ttk.Entry(box, textvariable=v_pwd, show="•").grid(row=1, column=1, sticky="ew", padx=4, pady=2)
            ttk.Button(box, text="Проверить вход",
                       command=lambda l=v_login, p=v_pwd, st=v_state: self.check(l, p, st)).grid(row=1, column=2)
            ttk.Label(box, textvariable=v_state, foreground="#555").grid(row=2, column=1, sticky="w", padx=4)
            self.rows.append((v_login, v_pwd, v_state, b))
            r += 1

        first = next((b.get("start") for b in s.get("boxes", []) if b.get("start")), "")
        self.start = tk.StringVar(value=first or f"{date.today() - timedelta(days=7):%d.%m.%Y}")
        self.out_dir = tk.StringVar(value=s.get("out_dir") or DEFAULT_DIR)
        ttk.Label(frm, text="Первый раз скачать с даты").grid(row=r, column=0, sticky="w", pady=(8, 2))
        ttk.Entry(frm, textvariable=self.start, width=12).grid(row=r, column=1, sticky="w", pady=(8, 2))
        r += 1
        ttk.Label(frm, text="Папка для почты").grid(row=r, column=0, sticky="w")
        ttk.Entry(frm, textvariable=self.out_dir).grid(row=r, column=1, columnspan=2, sticky="ew")
        r += 1

        btns = ttk.Frame(frm)
        btns.grid(row=r, column=0, columnspan=3, sticky="ew", pady=(14, 0))
        ttk.Button(btns, text="Сохранить", command=self.save).pack(side="left")
        ttk.Button(btns, text="Скачать сейчас", command=self.run_now).pack(side="left", padx=6)
        ttk.Button(btns, text="Журнал", command=lambda: self.open(LOG)).pack(side="right")
        ttk.Button(btns, text="Папка отчётов", command=lambda: self.open(REPORTS)).pack(side="right", padx=6)

    def check(self, v_login, v_pwd, v_state):
        login, pwd = v_login.get().strip(), v_pwd.get().strip()
        if not (login and pwd):
            v_state.set("введите адрес и пароль приложения")
            return
        v_state.set("проверяю…")

        def run():
            err = check_login(HOST, login, pwd)
            self.after(0, lambda: v_state.set("✗ " + err if err else "✓ вход есть, письма видно"))
        threading.Thread(target=run, daemon=True).start()

    def save(self, quiet=False):
        try:
            datetime.strptime(self.start.get().strip(), "%d.%m.%Y")
        except ValueError:
            messagebox.showwarning("Неверная дата", "Дату пишите так: 01.11.2026")
            return False
        boxes = []
        for v_login, v_pwd, _, old in self.rows:
            login = v_login.get().strip()
            if not login:
                continue
            b = dict(old) if old.get("login", "").lower() == login.lower() else {}
            b.update({"login": login, "host": HOST, "password": v_pwd.get().strip(), "start": self.start.get().strip()})
            boxes.append(b)
        s = load_settings()
        s.update({"boxes": boxes, "out_dir": self.out_dir.get().strip() or DEFAULT_DIR})
        save_settings(s)
        if not quiet:
            messagebox.showinfo("Сохранено", "Настройки сохранены на этом компьютере.")
        return True

    def run_now(self):
        if not self.save(quiet=True):
            return
        script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "nightly_mail.py")
        pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
        subprocess.Popen([pyw if os.path.exists(pyw) else sys.executable, script])
        messagebox.showinfo("Запущено", "Скачивание идёт в фоне. Ход — в «Журнале», итог — в «Папке отчётов» "
                                        "(отчёт появится после распознавания, обычно через 5–30 минут).")

    @staticmethod
    def open(path):
        if os.path.exists(path):
            os.startfile(path)
        else:
            messagebox.showinfo("Пока пусто", "Появится после первого скачивания.")


if __name__ == "__main__":
    try:  # чёткое окно при масштабе экрана 125–175 %, размер — по содержимому (оба ящика видно целиком)
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    Settings().mainloop()
