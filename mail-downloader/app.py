"""Окно приложения: кнопка «Скачать», даты «с … по …» и раскладка по папкам."""

import json
import os
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from mail_core import (LAYOUTS, PROVIDERS, QUICK_PERIODS, download_attachments,
                       parse_ru_date, quick_period)

SETTINGS_FILE = os.path.join(os.path.expanduser("~"), ".mail_downloader.json")
DEFAULT_DIR = os.path.join(os.path.expanduser("~"), "Downloads", "Вложения из почты")


def load_settings():
    try:
        with open(SETTINGS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_settings(data):
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Вложения из почты")
        self.geometry("660x600")
        self.minsize(560, 480)

        s = load_settings()
        self.events = queue.Queue()
        self.worker = None
        self.stop_requested = False

        # --- Верх: кнопка и период ---
        top = ttk.Frame(self, padding=12)
        top.pack(fill="x")

        self.btn = ttk.Button(top, text="⬇  Скачать", command=self.start)
        self.btn.pack(side="left", ipadx=12, ipady=6)

        d_from, d_to = quick_period("Месяц")
        self.date_from = tk.StringVar(value=s.get("date_from", f"{d_from:%d.%m.%Y}"))
        self.date_to = tk.StringVar(value=s.get("date_to", f"{d_to:%d.%m.%Y}"))
        ttk.Label(top, text="с").pack(side="left", padx=(16, 4))
        ttk.Entry(top, textvariable=self.date_from, width=11).pack(side="left")
        ttk.Label(top, text="по").pack(side="left", padx=(8, 4))
        ttk.Entry(top, textvariable=self.date_to, width=11).pack(side="left")

        quick = ttk.Frame(self, padding=(12, 0, 12, 8))
        quick.pack(fill="x")
        ttk.Label(quick, text="Быстро:").pack(side="left")
        for name in QUICK_PERIODS:
            ttk.Button(quick, text=name, command=lambda n=name: self.set_period(n)).pack(
                side="left", padx=(4, 0))

        # --- Настройки почты ---
        box = ttk.LabelFrame(self, text="Почта", padding=10)
        box.pack(fill="x", padx=12)
        box.columnconfigure(1, weight=1)

        self.provider = tk.StringVar(value=s.get("provider", "Gmail"))
        self.host = tk.StringVar(value=s.get("host", PROVIDERS["Gmail"]))
        self.login = tk.StringVar(value=s.get("login", ""))
        self.password = tk.StringVar(value=s.get("password", ""))
        self.remember = tk.BooleanVar(value=bool(s.get("password")))
        self.out_dir = tk.StringVar(value=s.get("out_dir", DEFAULT_DIR))

        ttk.Label(box, text="Почтовый сервис").grid(row=0, column=0, sticky="w")
        cb = ttk.Combobox(box, textvariable=self.provider, values=list(PROVIDERS),
                          state="readonly")
        cb.grid(row=0, column=1, sticky="ew", pady=2)
        cb.bind("<<ComboboxSelected>>", self.on_provider)

        ttk.Label(box, text="IMAP-сервер").grid(row=1, column=0, sticky="w")
        ttk.Entry(box, textvariable=self.host).grid(row=1, column=1, sticky="ew", pady=2)

        ttk.Label(box, text="Адрес почты").grid(row=2, column=0, sticky="w")
        ttk.Entry(box, textvariable=self.login).grid(row=2, column=1, sticky="ew", pady=2)

        ttk.Label(box, text="Пароль приложения").grid(row=3, column=0, sticky="w")
        ttk.Entry(box, textvariable=self.password, show="•").grid(
            row=3, column=1, sticky="ew", pady=2)
        ttk.Checkbutton(box, text="Запомнить пароль на этом компьютере",
                        variable=self.remember).grid(row=4, column=1, sticky="w")

        ttk.Label(box, text="Папка для файлов").grid(row=5, column=0, sticky="w")
        row = ttk.Frame(box)
        row.grid(row=5, column=1, sticky="ew", pady=2)
        ttk.Entry(row, textvariable=self.out_dir).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="…", width=3, command=self.choose_dir).pack(side="left", padx=(4, 0))

        self.layout = tk.StringVar(value=s.get("layout", "По месяцам"))
        self.save_text = tk.BooleanVar(value=s.get("save_text", True))
        ttk.Label(box, text="Раскладка").grid(row=6, column=0, sticky="w")
        ttk.Combobox(box, textvariable=self.layout, values=LAYOUTS, state="readonly").grid(
            row=6, column=1, sticky="ew", pady=2)
        ttk.Checkbutton(box, text="Сохранять текст писем (и писем без вложений — например, отмен)",
                        variable=self.save_text).grid(row=7, column=1, sticky="w")

        # --- Прогресс и журнал ---
        self.bar = ttk.Progressbar(self, mode="determinate")
        self.bar.pack(fill="x", padx=12, pady=(10, 4))

        self.log_box = tk.Text(self, height=12, state="disabled", wrap="word")
        self.log_box.pack(fill="both", expand=True, padx=12, pady=(0, 6))

        bottom = ttk.Frame(self, padding=(12, 0, 12, 10))
        bottom.pack(fill="x")
        ttk.Button(bottom, text="Открыть папку", command=self.open_dir).pack(side="right")
        ttk.Button(bottom, text="Открыть опись", command=self.open_opis).pack(side="right", padx=(0, 6))

        self.after(100, self.poll)

    # ---------- действия ----------
    def on_provider(self, _=None):
        host = PROVIDERS.get(self.provider.get(), "")
        if host:
            self.host.set(host)

    def set_period(self, name):
        d_from, d_to = quick_period(name)
        self.date_from.set(f"{d_from:%d.%m.%Y}")
        self.date_to.set(f"{d_to:%d.%m.%Y}")

    def open_opis(self):
        path = os.path.join(self.out_dir.get(), "Опись.html")
        if not os.path.exists(path):
            messagebox.showinfo("Описи пока нет", "Опись появится после первого скачивания в эту папку.")
            return
        self.open_path(path)

    def choose_dir(self):
        d = filedialog.askdirectory(initialdir=self.out_dir.get() or os.path.expanduser("~"))
        if d:
            self.out_dir.set(d)

    def open_dir(self):
        d = self.out_dir.get()
        os.makedirs(d, exist_ok=True)
        self.open_path(d)

    @staticmethod
    def open_path(d):
        if os.name == "nt":
            os.startfile(d)
        elif os.uname().sysname == "Darwin":
            os.system(f'open "{d}"')
        else:
            os.system(f'xdg-open "{d}"')

    def log(self, text):
        self.log_box.configure(state="normal")
        self.log_box.insert("end", text + "\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def start(self):
        if self.worker and self.worker.is_alive():
            self.stop_requested = True
            self.btn.configure(text="Останавливаю…", state="disabled")
            return

        host, login, pwd = self.host.get().strip(), self.login.get().strip(), self.password.get()
        if not (host and login and pwd):
            messagebox.showwarning("Не хватает данных",
                                   "Заполните сервер, адрес почты и пароль приложения.")
            return

        try:
            date_from = parse_ru_date(self.date_from.get())
            date_to = parse_ru_date(self.date_to.get())
        except ValueError:
            messagebox.showwarning("Неверная дата", "Даты пишите так: 01.07.2026")
            return
        if date_from > date_to:
            messagebox.showwarning("Неверный период", "Дата «с» позже даты «по».")
            return

        save_settings({
            "date_from": self.date_from.get().strip(), "date_to": self.date_to.get().strip(),
            "layout": self.layout.get(), "save_text": self.save_text.get(),
            "provider": self.provider.get(),
            "host": host, "login": login, "out_dir": self.out_dir.get(),
            "password": pwd if self.remember.get() else "",
        })

        layout, save_text = self.layout.get(), self.save_text.get()
        out_dir = self.out_dir.get()
        self.stop_requested = False
        self.bar["value"] = 0
        self.btn.configure(text="■  Остановить")
        self.log(f"— Скачиваю с {date_from:%d.%m.%Y} по {date_to:%d.%m.%Y}, "
                 f"раскладка: {layout.lower()} —")

        def run():
            try:
                letters, files, texts = download_attachments(
                    host, login, pwd, date_from, date_to, out_dir,
                    layout=layout, save_text=save_text,
                    log=lambda t: self.events.put(("log", t)),
                    progress=lambda d, t: self.events.put(("progress", (d, t))),
                    stop_flag=lambda: self.stop_requested,
                )
                self.events.put(("done", f"Готово: просмотрено писем {letters}, "
                                         f"сохранено файлов {files}, текстов писем {texts}.\n"
                                         f"Папка: {out_dir}\nОпись: Опись.html в этой папке"))
            except Exception as e:
                text = str(e)
                if "AUTHENTICATIONFAILED" in text or "Invalid credentials" in text:
                    text = ("Почта не пустила: неверный адрес или пароль.\n"
                            "Для Gmail нужен «пароль приложения», а не обычный пароль "
                            "(см. README).")
                self.events.put(("error", text))

        self.worker = threading.Thread(target=run, daemon=True)
        self.worker.start()

    def poll(self):
        try:
            while True:
                kind, val = self.events.get_nowait()
                if kind == "log":
                    self.log(val)
                elif kind == "progress":
                    done, total = val
                    self.bar["maximum"] = max(total, 1)
                    self.bar["value"] = done
                elif kind in ("done", "error"):
                    self.btn.configure(text="⬇  Скачать", state="normal")
                    if kind == "done":
                        self.log(val)
                        messagebox.showinfo("Готово", val)
                    else:
                        self.log("Ошибка: " + val)
                        messagebox.showerror("Ошибка", val)
        except queue.Empty:
            pass
        self.after(100, self.poll)


if __name__ == "__main__":
    App().mainloop()
