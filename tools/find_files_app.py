"""Окно «Поиск файлов»: ищет файлы проекта и C:\\РАБОТА по похожим словам.
Двойной щелчок по строке — открыть файл. Движок — find_files.py рядом."""
import os
import queue
import re
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import ttk

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import find_files as ff  # noqa: E402
from scooby import Scooby  # noqa: E402


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('Поиск файлов — похожие слова')
        self.geometry('1000x620')
        self.minsize(700, 420)
        self.events = queue.Queue()
        self.busy = False
        self.rows = {}

        top = ttk.Frame(self, padding=10)
        top.pack(fill='x')
        ttk.Label(top, text='Что ищем:').pack(side='left')
        self.query = tk.StringVar()
        entry = ttk.Entry(top, textvariable=self.query, font=('Segoe UI', 12))
        entry.pack(side='left', fill='x', expand=True, padx=8)
        entry.bind('<Return>', lambda e: self.start())
        entry.bind('<KeyRelease>', self.on_type)
        entry.bind('<Down>', lambda e: self.sugg_focus())
        entry.bind('<Escape>', lambda e: self.sugg_hide())
        entry.focus_set()
        self.entry = entry

        # выпадающий список похожих слов под строкой поиска
        self.counts = None
        self.sugg_job = None
        self.sugg = tk.Listbox(self, font=('Segoe UI', 11), height=8, activestyle='dotbox',
                               borderwidth=1, relief='solid', highlightthickness=0)
        self.sugg_items = []
        self.sugg.bind('<Return>', lambda e: self.sugg_pick())
        self.sugg.bind('<Double-1>', lambda e: self.sugg_pick())
        self.sugg.bind('<ButtonRelease-1>', lambda e: self.sugg_pick())
        self.sugg.bind('<Escape>', lambda e: (self.sugg_hide(), self.entry.focus_set()))
        self.sugg.bind('<Up>', lambda e: self.entry.focus_set() if self.sugg.curselection() == (0,) else None)
        self.bind('<Button-1>', lambda e: self.sugg_hide() if e.widget not in (self.sugg, self.entry) else None, add='+')
        self.btn = ttk.Button(top, text='Найти', command=self.start)
        self.btn.pack(side='left')

        opts = ttk.Frame(self, padding=(10, 0))
        opts.pack(fill='x')
        self.inside = tk.BooleanVar(value=True)
        ttk.Checkbutton(opts, text='искать и внутри файлов (Word, Excel, PDF, распознанные сканы)',
                        variable=self.inside).pack(side='left')
        ttk.Label(opts, text='   Папки: проект и C:\\РАБОТА', foreground='#666').pack(side='left')

        self.variants = ttk.Frame(self, padding=(10, 6))
        self.variants.pack(fill='x')

        mid = ttk.Frame(self, padding=(10, 0))
        mid.pack(fill='both', expand=True)
        cols = ('score', 'where', 'name', 'folder')
        self.tree = ttk.Treeview(mid, columns=cols, show='headings', selectmode='browse')
        for c, title, w, st in (('score', 'Похоже', 70, False), ('where', 'Где нашлось', 110, False),
                                ('name', 'Файл', 430, True), ('folder', 'Папка', 380, True)):
            self.tree.heading(c, text=title)
            self.tree.column(c, width=w, stretch=st, anchor='center' if not st else 'w')
        sb = ttk.Scrollbar(mid, orient='vertical', command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side='left', fill='both', expand=True)
        sb.pack(side='left', fill='y')
        self.tree.bind('<Double-1>', lambda e: self.open_file())
        self.tree.bind('<Return>', lambda e: self.open_file())
        self.tree.bind('<<TreeviewSelect>>', lambda e: self.on_select())
        # строки-заголовки блоков «ДОКУМЕНТЫ» / «СВОДНЫЕ ТАБЛИЦЫ И ОПИСИ»
        self.tree.tag_configure('hdr', font=('Segoe UI', 10, 'bold'), background='#e8eef7')
        self.last_sel = None

        Scooby(self, height=130, bg='#f4f8f2').pack(fill='x', padx=10, pady=(6, 0))

        bottom = ttk.Frame(self, padding=10)
        bottom.pack(fill='x')
        self.snippet = ttk.Label(bottom, text='', foreground='#333', wraplength=960, justify='left')
        self.snippet.pack(fill='x')
        btns = ttk.Frame(bottom)
        btns.pack(fill='x', pady=(6, 0))
        ttk.Button(btns, text='Открыть файл', command=self.open_file).pack(side='left')
        ttk.Button(btns, text='Показать в папке', command=self.show_in_folder).pack(side='left', padx=6)
        self.status = ttk.Label(btns, text='Введи имя, компанию или слово и нажми Enter. '
                                           'Первый поиск внутри файлов может занять несколько минут.',
                                foreground='#666')
        self.status.pack(side='left', padx=10)

        self.after(100, self.poll)
        threading.Thread(target=self.load_counts, daemon=True).start()

    # ---------- подсказки при наборе ----------
    def load_counts(self):
        self.events.put(('status', 'Готовлю подсказки…'))
        counts = ff.word_counts(ff.DEFAULT_ROOTS, progress=lambda name: self.events.put(('progress', name)))
        self.events.put(('counts', counts))

    def on_type(self, e):
        if e.keysym in ('Return', 'Escape', 'Down', 'Up', 'Left', 'Right', 'Tab'):
            return
        if self.sugg_job:
            self.after_cancel(self.sugg_job)
        self.sugg_job = self.after(250, self.sugg_request)

    def sugg_request(self):
        self.sugg_job = None
        q = self.query.get()
        if not self.counts or len(q.strip()) < 2:
            self.sugg_hide()
            return
        counts = self.counts
        threading.Thread(target=lambda: self.events.put(('sugg', q, ff.suggest(q, counts))), daemon=True).start()

    def sugg_show(self, q, items):
        if q != self.query.get() or self.busy:
            return  # пока считали, текст уже изменился
        self.sugg_items = [w for w, c in items]
        self.sugg.delete(0, 'end')
        if not items:
            self.sugg_hide()
            return
        for w, c in items:
            self.sugg.insert('end', f'  {w}   — файлов: {c}')
        self.sugg.config(height=min(10, len(items)))
        self.sugg.place(in_=self.entry, x=0, rely=1.0, relwidth=1.0)
        self.sugg.lift()

    def sugg_hide(self):
        self.sugg.place_forget()

    def sugg_focus(self):
        if self.sugg.winfo_ismapped():
            self.sugg.focus_set()
            self.sugg.selection_clear(0, 'end')
            self.sugg.selection_set(0)
            self.sugg.activate(0)

    def sugg_pick(self):
        sel = self.sugg.curselection()
        if not sel:
            return
        word = self.sugg_items[sel[0]]
        q = self.query.get()
        ws = [w for w in re.findall(r'\w+', q) if len(w) >= 2]
        if ws:  # заменяем самое длинное слово, инициалы и остальное оставляем
            longest = max(ws, key=len)
            i = q.find(longest)
            q = q[:i] + word.capitalize() + q[i + len(longest):]
        else:
            q = word.capitalize()
        self.sugg_hide()
        self.entry.focus_set()
        self.start(q)

    # ---------- поиск в фоне ----------
    def start(self, text=None):
        if text is not None:
            self.query.set(text)
        self.sugg_hide()
        q = self.query.get().strip()
        if not q or self.busy:
            return
        self.busy = True
        self.btn.state(['disabled'])
        self.status.config(text='Ищу…')
        inside = self.inside.get()

        def work():
            try:
                res = ff.search(q, ff.DEFAULT_ROOTS, only_names=not inside, limit=200,
                                progress=lambda name: self.events.put(('progress', name)))
                self.events.put(('done', q, res))
            except Exception as e:
                self.events.put(('error', str(e)))

        threading.Thread(target=work, daemon=True).start()

    def poll(self):
        try:
            while True:
                ev = self.events.get_nowait()
                if ev[0] == 'progress':
                    self.status.config(text=f'Читаю текст файлов (только первый раз): {ev[1][:60]}')
                elif ev[0] == 'status':
                    self.status.config(text=ev[1])
                elif ev[0] == 'counts':
                    self.counts = ev[1]
                    if not self.busy:
                        self.status.config(text='Начни печатать — под строкой появятся похожие слова. '
                                                'Enter — искать, стрелка вниз — выбрать подсказку.')
                elif ev[0] == 'sugg':
                    self.sugg_show(ev[1], ev[2])
                elif ev[0] == 'done':
                    self.fill(ev[1], *ev[2])
                elif ev[0] == 'error':
                    self.finish(f'Ошибка: {ev[1]}')
        except queue.Empty:
            pass
        self.after(100, self.poll)

    def finish(self, msg):
        self.busy = False
        self.btn.state(['!disabled'])
        self.status.config(text=msg)

    def fill(self, q, results, total, variants):
        self.tree.delete(*self.tree.get_children())
        self.rows.clear()
        self.snippet.config(text='')
        for w in self.variants.winfo_children():
            w.destroy()
        if variants:
            ttk.Label(self.variants, text='Похожие слова:').pack(side='left')
            for word, n in list(variants.items())[:12]:
                ttk.Button(self.variants, text=f'{word} ({n})',
                           command=lambda w=word: self.start(w)).pack(side='left', padx=2)
        group = None
        for score, where, path, snip, g in results:
            if g != group:
                group = g
                self.tree.insert('', 'end', values=('', '', ff.GROUP_TITLES[g], ''), tags=('hdr',))
            iid = self.tree.insert('', 'end', values=(f'{round(score * 100)}%', where,
                                                      os.path.basename(path), os.path.dirname(path)))
            self.rows[iid] = (path, snip)
        if results:
            first = next(iid for iid in self.tree.get_children() if iid in self.rows)
            self.last_sel = first
            self.tree.selection_set(first)
            self.tree.focus(first)
        shown = f'показаны {len(results)}' if total > len(results) else ''
        self.finish(f'«{q}»: найдено {total} {shown}'.strip() if total else f'По «{q}» ничего похожего не нашлось')

    # ---------- действия ----------
    def selected(self):
        sel = self.tree.selection()
        return self.rows.get(sel[0]) if sel else None

    def on_select(self):
        sel = self.tree.selection()
        if sel and sel[0] not in self.rows:  # заголовок блока не выбирается — перескакиваем дальше
            items = self.tree.get_children()
            i = items.index(sel[0])
            step = -1 if self.last_sel in items and items.index(self.last_sel) > i else 1
            j = i + step
            if not 0 <= j < len(items):
                j = i - step
            if 0 <= j < len(items):
                self.tree.selection_set(items[j])
                self.tree.focus(items[j])
            return
        self.last_sel = sel[0] if sel else None
        self.show_snippet()

    def show_snippet(self):
        row = self.selected()
        self.snippet.config(text=f'В тексте: … {ff.mask(row[1])} …' if row and row[1] else '')

    def open_file(self):
        row = self.selected()
        if row:
            os.startfile(row[0])

    def show_in_folder(self):
        row = self.selected()
        if row:
            subprocess.Popen(['explorer', '/select,', os.path.normpath(row[0])])


if __name__ == '__main__':
    App().mainloop()
