"""Окно приложения: выбрать папку с вложениями и найти среди них заявки."""

import json
import os
import queue
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scanner import scan  # noqa: E402

SETTINGS_FILE = os.path.join(os.path.expanduser("~"), ".zayavki", "settings.json")
DOWNLOADS = os.path.join(os.path.expanduser("~"), "Downloads")
DEFAULT_SRC = os.path.join(DOWNLOADS, "Вложения из почты")
DEFAULT_OUT = os.path.join(DOWNLOADS, "Найденные заявки")
DEFAULT_COMPANY = "Восточная логистика"


def load_settings():
    try:
        with open(SETTINGS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_settings(data):
    try:
        os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def open_path(p):
    if os.name == "nt":
        os.startfile(p)
    elif sys.platform == "darwin":
        os.system(f'open "{p}"')
    else:
        os.system(f'xdg-open "{p}"')


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Поиск заявок")
        self.geometry("680x540")
        self.minsize(560, 420)
        s = load_settings()
        self.events = queue.Queue()
        self.worker = None
        self.stop_requested = False
        self.report = None

        top = ttk.Frame(self, padding=12)
        top.pack(fill="x")
        self.btn = ttk.Button(top, text="🔍  Найти заявки", command=self.start)
        self.btn.pack(side="left", ipadx=12, ipady=6)
        self.status = ttk.Label(top, text="")
        self.status.pack(side="left", padx=12)

        box = ttk.LabelFrame(self, text="Настройки", padding=10)
        box.pack(fill="x", padx=12)
        box.columnconfigure(1, weight=1)
        self.src = tk.StringVar(value=s.get("src", DEFAULT_SRC))
        self.out = tk.StringVar(value=s.get("out", DEFAULT_OUT))
        self.company = tk.StringVar(value=s.get("company", DEFAULT_COMPANY))

        for i, (label, var) in enumerate([("Где искать", self.src), ("Куда сложить", self.out)]):
            ttk.Label(box, text=label).grid(row=i, column=0, sticky="w")
            row = ttk.Frame(box)
            row.grid(row=i, column=1, sticky="ew", pady=2)
            ttk.Entry(row, textvariable=var).pack(side="left", fill="x", expand=True)
            ttk.Button(row, text="…", width=3,
                       command=lambda v=var: self.choose_dir(v)).pack(side="left", padx=(4, 0))
        ttk.Label(box, text="Наша компания").grid(row=2, column=0, sticky="w")
        ttk.Entry(box, textvariable=self.company).grid(row=2, column=1, sticky="ew", pady=2)
        ttk.Label(box, text="Можно несколько через запятую: название, ИНН",
                  foreground="gray").grid(row=3, column=1, sticky="w")

        self.bar = ttk.Progressbar(self, mode="determinate")
        self.bar.pack(fill="x", padx=12, pady=(10, 4))
        self.log_box = tk.Text(self, height=12, state="disabled", wrap="word")
        self.log_box.pack(fill="both", expand=True, padx=12, pady=(0, 6))

        bottom = ttk.Frame(self, padding=(12, 0, 12, 10))
        bottom.pack(fill="x")
        ttk.Button(bottom, text="Открыть папку с заявками",
                   command=lambda: self.open_dir(self.out.get())).pack(side="right")
        self.rep_btn = ttk.Button(bottom, text="Открыть отчёт", state="disabled",
                                  command=lambda: open_path(self.report))
        self.rep_btn.pack(side="right", padx=6)
        self.after(100, self.poll)

    def choose_dir(self, var):
        d = filedialog.askdirectory(initialdir=var.get() or os.path.expanduser("~"))
        if d:
            var.set(os.path.normpath(d))

    def open_dir(self, d):
        os.makedirs(d, exist_ok=True)
        open_path(d)

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
        src, out = self.src.get().strip(), self.out.get().strip()
        names = [x.strip() for x in self.company.get().split(",") if x.strip()]
        if not os.path.isdir(src):
            messagebox.showwarning("Нет папки", f"Папка не найдена:\n{src}")
            return
        save_settings({"src": src, "out": out, "company": self.company.get()})
        self.stop_requested = False
        self.bar["value"] = 0
        self.btn.configure(text="■  Остановить")
        self.log("— Ищу заявки —")

        def run():
            try:
                counts, copied, report = scan(
                    src, out, names,
                    log=lambda t: self.events.put(("log", t)),
                    progress=lambda d, t: self.events.put(("progress", (d, t))),
                    stop_flag=lambda: self.stop_requested)
                self.events.put(("done", (counts, copied, report)))
            except Exception as e:
                self.events.put(("error", str(e)))

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
                    self.status.configure(text=f"{done} из {total}")
                elif kind == "done":
                    counts, copied, report = val
                    self.report = report
                    self.rep_btn.configure(state="normal")
                    self.btn.configure(text="🔍  Найти заявки", state="normal")
                    msg = (f"Заявок: {counts.get('Заявка', 0)}\n"
                           f"Проверить вручную: {counts.get('Проверить', 0)}\n"
                           f"Где мы заказчик: {counts.get('Мы заказчик', 0)}\n"
                           f"Не заявки: {counts.get('Не заявка', 0)}, "
                           f"дубликатов: {counts.get('Дубликат', 0)}\n\n"
                           f"Скопировано файлов: {copied}\nОтчёт: {report}")
                    self.log(msg)
                    messagebox.showinfo("Готово", msg)
                elif kind == "error":
                    self.btn.configure(text="🔍  Найти заявки", state="normal")
                    self.log("Ошибка: " + val)
                    messagebox.showerror("Ошибка", val)
        except queue.Empty:
            pass
        self.after(100, self.poll)


def cli():
    """python app.py --cli ПАПКА КУДА — без окна, для проверки."""
    src, out = sys.argv[2], sys.argv[3]
    counts, copied, report = scan(src, out, [DEFAULT_COMPANY], log=print,
                                  progress=lambda d, t: d % 200 == 0 and print(f"{d}/{t}", flush=True),
                                  stop_flag=lambda: False)
    print(counts, copied, report)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--cli":
        cli()
    else:
        App().mainloop()
