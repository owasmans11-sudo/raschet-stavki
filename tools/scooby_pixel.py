"""Пиксельный (старый) вариант: Скуби-Ду убегает от призрака в окне поиска.
Щелчок по Скуби — «Ру-ро!» и рывок вперёд, по призраку — «Ууу-у!»."""
import tkinter as tk

PX = 4  # размер одного «пикселя»
COLORS = {'B': '#b07436', 'D': '#5e3a14', 'K': '#111', 'W': '#fff',
          'C': '#2bb3a8', 'Y': '#f2c81b',
          'G': '#a993de', 'H': '#7c62c2', 'E': '#ffe94d'}

# Скуби бежит вправо: голова справа, хвост слева
SCOOBY_TOP = ['............DD.....',
              '...........DBBBB...',
              '...........BBWKBB..',
              '...........BBBBBBBK',
              'D...........BBBBBBK',
              '.D..........BBBBB..',
              '..D........CYCC....',
              '..BBBBBBBBBBBBB....',
              '..BBDBBBBDBBBBB....',
              '..BBBBBDBBBBBBB....',
              '...BBBBBBBBBBB.....']
SCOOBY_LEGS = [['..BB.......BB......',  # ноги врозь
                '.BB.........BB.....',
                'DD...........DD....'],
               ['....BB...BB........',  # ноги вместе
                '.....BB.BB.........',
                '.....DD.DD.........']]

# призрак летит вправо, тянет руки к Скуби
GHOST_TOP = ['....GGGGG.....',
             '...GGGGGGG....',
             '..GGGGGGGGG...',
             '..GGEKGGEKG...',
             '..GGKKGGKKG...',
             '..GGGGGGGGG...',
             '..GGGHHHGGG...',
             'GGGGGHHHGGGGGG',
             '..GGGGGGGGGGGG',
             '..GGGGGGGGG...',
             '..GGGGGGGGG...']
GHOST_HEM = [['..H.HH.HH.H...'], ['..HH.HH.HH....']]

SCOOBY_W = len(SCOOBY_TOP[0]) * PX
GHOST_W = len(GHOST_TOP[0]) * PX


class Scooby:
    def __init__(self, parent, height=80, bg='white'):
        self.canvas = tk.Canvas(parent, height=height, bg=bg, highlightthickness=0)
        self.x, self.gap, self.step = 140.0, 90.0, 0
        self.boost = 0   # рывок Скуби после щелчка
        self.say_s = 0   # сколько кадров показывать «Ру-ро!»
        self.say_g = 0   # сколько кадров показывать «Ууу-у!»
        self.canvas.bind('<Button-1>', self.click)
        self.canvas.after(40, self.tick)

    def pack(self, **kw):
        self.canvas.pack(**kw)

    def ghost_x(self):
        return self.x - self.gap - GHOST_W

    def click(self, e):
        if self.x - 4 <= e.x <= self.x + SCOOBY_W + 4:
            self.boost, self.say_s = 25, 30
        elif self.ghost_x() - 4 <= e.x <= self.ghost_x() + GHOST_W + 4:
            self.say_g = 30

    def sprite(self, rows, x, top, tag):
        c = self.canvas
        for r, line in enumerate(rows):
            for k, ch in enumerate(line):
                if ch != '.':
                    x0, y0 = x + k * PX, top + r * PX
                    c.create_rectangle(x0, y0, x0 + PX, y0 + PX, fill=COLORS[ch], outline='', tags=tag)

    def draw(self):
        c = self.canvas
        c.delete('sc')
        h = int(c.winfo_height()) or 80
        run = (self.step // 3) % 2
        # Скуби подпрыгивает на бегу
        top = h - 14 * PX - 4 - (2 if run == 0 else 0)
        self.sprite(SCOOBY_TOP + SCOOBY_LEGS[run], self.x, top, 'sc')
        for i, dy in enumerate((14, 26, 38)):  # полоски скорости за спиной
            x1 = self.x - 4 - i * 3
            c.create_line(x1 - 14, top + dy, x1, top + dy, fill='#b9b9b9', width=2, tags='sc')
        if self.say_s:
            c.create_text(self.x + SCOOBY_W - 10, top - 8, text='Ру-ро!', fill='#5e3a14',
                          font=('Segoe UI', 9, 'bold italic'), tags='sc')
        # призрак плавно качается вверх-вниз
        gx = self.ghost_x()
        gtop = h - 12 * PX - 10 + (3 if (self.step // 6) % 2 else 0)
        self.sprite(GHOST_TOP + GHOST_HEM[run], gx, gtop, 'sc')
        if self.say_g:
            c.create_text(gx + GHOST_W / 2, gtop - 8, text='Ууу-у!', fill='#7c62c2',
                          font=('Segoe UI', 9, 'italic'), tags='sc')

    def tick(self):
        w = int(self.canvas.winfo_width()) or 600
        speed = 5.0 if self.boost else 3.0
        self.x += speed
        # призрак то догоняет, то отстаёт, а после рывка Скуби отрывается
        self.gap += 2.0 if self.boost else (0.6 if (self.step // 60) % 2 else -0.6)
        self.gap = max(20.0, min(160.0, self.gap))
        if self.ghost_x() > w:  # оба убежали за край — выбегают слева
            self.x = -SCOOBY_W
            self.gap = 90.0
        self.boost = max(0, self.boost - 1)
        self.say_s = max(0, self.say_s - 1)
        self.say_g = max(0, self.say_g - 1)
        self.step += 1
        self.draw()
        self.canvas.after(40, self.tick)


if __name__ == '__main__':  # посмотреть отдельно: python scooby.py
    root = tk.Tk()
    root.geometry('700x100')
    Scooby(root, height=80, bg='#f4f8f2').pack(fill='x', padx=10, pady=6)
    root.mainloop()
