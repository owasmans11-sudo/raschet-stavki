"""Бегающий пиксельный крипер для окна поиска. Щелчок по нему — мигает и «шипит»."""
import random
import tkinter as tk

PX = 4  # размер одного «пикселя»
GREENS = ['#4caf3f', '#5cc24d', '#3f9a35', '#6fd35f', '#2f7d28']
FACE = '#111'
# лицо 8×8: 1 — чёрный
FACE_MAP = ['00000000',
            '00000000',
            '01100110',
            '01100110',
            '00011000',
            '00111100',
            '00111100',
            '00100100']


class Creeper:
    def __init__(self, parent, height=80, bg='white'):
        self.canvas = tk.Canvas(parent, height=height, bg=bg, highlightthickness=0)
        self.x, self.dx, self.step, self.flash = 20, 2, 0, 0
        rnd = random.Random(7)
        self.tex = [[rnd.choice(GREENS) for _ in range(8)] for _ in range(17)]
        self.canvas.bind('<Button-1>', self.click)
        self.canvas.after(40, self.tick)

    def pack(self, **kw):
        self.canvas.pack(**kw)

    def click(self, e):
        if self.x - 4 <= e.x <= self.x + 8 * PX + 4:
            self.flash = 24

    def draw(self):
        c = self.canvas
        c.delete('cr')
        h = int(c.winfo_height()) or 80
        top = h - 17 * PX - 4
        white = self.flash and (self.flash // 3) % 2 == 0
        hop = 0 if self.step % 8 < 4 else 1  # лёгкое покачивание при ходьбе

        def px(col, row, color):
            x0 = self.x + col * PX
            y0 = top + row * PX - hop
            c.create_rectangle(x0, y0, x0 + PX, y0 + PX, fill='white' if white else color, outline='', tags='cr')

        for r in range(8):  # голова
            for k in range(8):
                px(k, r, FACE if FACE_MAP[r][k] == '1' else self.tex[r][k])
        for r in range(8, 14):  # туловище
            for k in range(2, 6):
                px(k, r, self.tex[r][k])
        front = self.step % 8 < 4  # ноги: пары по очереди
        for r in range(14, 17):
            for k in (0, 1, 6, 7) if front else (1, 2, 5, 6):
                px(k, r, self.tex[r][k])
        if self.flash:
            c.create_text(self.x + 4 * PX, top - 8, text='шшш…', fill='#2f7d28',
                          font=('Segoe UI', 9, 'italic'), tags='cr')

    def tick(self):
        w = int(self.canvas.winfo_width()) or 600
        if not self.flash:
            self.x += self.dx
            if self.x < 4 or self.x > w - 8 * PX - 4:
                self.dx = -self.dx
            self.step += 1
        else:
            self.flash -= 1
        self.draw()
        self.canvas.after(40, self.tick)
