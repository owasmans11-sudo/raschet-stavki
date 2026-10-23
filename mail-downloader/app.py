"""Окно приложения: кнопка «Скачать» и выбор периода."""

import json
import os
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from mail_core import PERIODS, PROVIDERS, download_attachments

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
        self.geometry("620x520")
        self.minsize(520, 420)

        s = load_settings()
        self.events = queue.Queue()
        self.worker = None
        self.stop_requested = False

        # --- Верх: кнопка и период ---
        top = ttk.Frame(self, padding=12)
        top.pack(fill="x")

        self.btn = ttk.Button(top, text="⬇  Скачать", command=self.start)
        self.btn.pack(side="left", ipadx=12, ipady=6)

        self.period = tk.StringVar(value=s.get("period", "Месяц"))
        for name in PERIODS:
            ttk.Radiobutton(top, text=name, value=name,
                            variable=self.period).pack(side="left", padx=(16, 0))

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

        # --- Прогресс и журнал ---
        self.bar = ttk.Progressbar(self, mode="determinate")
        self.bar.pack(fill="x", padx=12, pady=(10, 4))

        self.log_box = tk.Text(self, height=12, state="disabled", wrap="word")
        self.log_box.pack(fill="both", expand=True, padx=12, pady=(0, 6))

        bottom = ttk.Frame(self, padding=(12, 0, 12, 10))
        bottom.pack(fill="x")
        ttk.Button(bottom, text="Открыть папку", command=self.open_dir).pack(side="right")

        self.after(100, self.poll)

    # ---------- действия ----------
    def on_provider(self, _=None):
        host = PROVIDERS.get(self.provider.get(), "")
        if host:
            self.host.set(host)

    def choose_dir(self):
        d = filedialog.askdirectory(initialdir=self.out_dir.get() or os.path.expanduser("~"))
        if d:
            self.out_dir.set(d)

    def open_dir(self):
        d = self.out_dir.get()
        os.makedirs(d, exist_ok=True)
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

        save_settings({
            "period": self.period.get(), "provider": self.provider.get(),
            "host": host, "login": login, "out_dir": self.out_dir.get(),
            "password": pwd if self.remember.get() else "",
        })

        days = PERIODS[self.period.get()]
        out_dir = self.out_dir.get()
        self.stop_requested = False
        self.bar["value"] = 0
        self.btn.configure(text="■  Остановить")
        self.log(f"— Скачиваю вложения за период: {self.period.get().lower()} —")

        def run():
            try:
                letters, files = download_attachments(
                    host, login, pwd, days, out_dir,
                    log=lambda t: self.events.put(("log", t)),
                    progress=lambda d, t: self.events.put(("progress", (d, t))),
                    stop_flag=lambda: self.stop_requested,
                )
                self.events.put(("done", f"Готово: просмотрено писем {letters}, "
                                         f"сохранено файлов {files}.\nПапка: {out_dir}"))
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
