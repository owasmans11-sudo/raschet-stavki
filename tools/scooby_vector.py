"""Вариант из плавных фигур (рисуется прямо в окне): Скуби-Ду убегает от призрака.
Щелчок по Скуби — «Ру-ро!» и рывок вперёд, по призраку — «Ууу-у!».
Сейчас в окне — кадры-картинки (scooby.py), пиксельный вариант — scooby_pixel.py."""
import math
import tkinter as tk

FUR = '#b5772f'
FUR_DARK = '#8a5520'   # дальние лапы, тень
EAR = '#6b3d12'
SPOT = '#1c1c1c'
COLLAR = '#22a99c'
TAG = '#f2c81b'
GHOST = '#ece8f8'
GHOST_EDGE = '#8f82c0'
GHOST_HOLE = '#3a2f5c'

SCOOBY_LEN = 122   # длина Скуби от хвоста до носа в «единицах» рисунка
GHOST_LEN = 100


class Scooby:
    def __init__(self, parent, height=120, bg='white'):
        self.canvas = tk.Canvas(parent, height=height, bg=bg, highlightthickness=0)
        self.x, self.gap, self.step = 150.0, 70.0, 0
        self.boost = 0   # рывок Скуби после щелчка
        self.say_s = 0   # сколько кадров показывать «Ру-ро!»
        self.say_g = 0   # сколько кадров показывать «Ууу-у!»
        self.s = 1.0     # масштаб: подстраивается под высоту окна
        self.canvas.bind('<Button-1>', self.click)
        self.canvas.after(40, self.tick)

    def pack(self, **kw):
        self.canvas.pack(**kw)

    def ghost_x(self):
        return self.x - self.gap - GHOST_LEN * self.s

    def click(self, e):
        if self.x - 4 <= e.x <= self.x + SCOOBY_LEN * self.s + 4:
            self.boost, self.say_s = 25, 30
        elif self.ghost_x() - 4 <= e.x <= self.ghost_x() + GHOST_LEN * self.s + 4:
            self.say_g = 30

    # --- рисование: координаты рисунка (x вправо, y вверх от земли) -> холст
    def pt(self, ox, gy, lx, ly):
        return ox + lx * self.s, gy - ly * self.s

    def poly(self, ox, gy, pts, **kw):
        flat = []
        for lx, ly in pts:
            flat += self.pt(ox, gy, lx, ly)
        self.canvas.create_polygon(flat, smooth=True, tags='sc', **kw)

    def oval(self, ox, gy, x0, y0, x1, y1, **kw):
        a, b = self.pt(ox, gy, x0, y1)
        c, d = self.pt(ox, gy, x1, y0)
        self.canvas.create_oval(a, b, c, d, tags='sc', **kw)

    def line(self, ox, gy, pts, width, **kw):
        flat = []
        for lx, ly in pts:
            flat += self.pt(ox, gy, lx, ly)
        self.canvas.create_line(flat, width=max(1, width * self.s), capstyle='round',
                                joinstyle='round', tags='sc', **kw)

    def leg(self, ox, gy, hx, hy, swing, bend, color):
        """Лапа из бедра и голени; swing — наклон бедра, bend — сгиб в колене."""
        kx, ky = hx + 21 * math.sin(swing), hy - 21 * math.cos(swing)
        fa = swing + bend
        fx, fy = kx + 22 * math.sin(fa), ky - 22 * math.cos(fa)
        self.line(ox, gy, [(hx, hy), (kx, ky)], 9, fill=color)
        self.line(ox, gy, [(kx, ky), (fx, fy)], 7, fill=color)
        self.oval(ox, gy, fx - 3, fy - 3, fx + 8, fy + 3, fill=color, outline='')

    def draw_scooby(self, ox, gy, ph):
        up = 4 * abs(math.sin(ph))           # подпрыгивает на бегу
        o = lambda pts: [(x, y + up) for x, y in pts]  # noqa: E731
        sw = 0.75
        # дальние лапы (темнее), сдвинуты по фазе
        self.leg(ox, gy, 34, 46 + up, sw * math.sin(ph + math.pi + 0.5), 0.5, FUR_DARK)
        self.leg(ox, gy, 80, 46 + up, sw * math.sin(ph + 0.5), -0.6, FUR_DARK)
        # хвост
        wag = 4 * math.sin(ph * 2)
        self.line(ox, gy, o([(30, 56), (18, 62), (10, 72 + wag), (8, 80 + wag)]), 6, fill=FUR, smooth=True)
        # туловище
        self.poly(ox, gy, o([(26, 52), (30, 62), (50, 64), (72, 62), (88, 58), (92, 48),
                             (84, 40), (62, 38), (40, 40), (28, 44)]), fill=FUR, outline='')
        for sx, sy, r in ((44, 56, 4), (58, 59, 3), (70, 52, 3.5), (52, 47, 2.5)):  # пятна
            self.oval(ox, gy, sx - r, sy - r * 0.7 + up, sx + r, sy + r * 0.7 + up, fill=SPOT, outline='')
        # ближние лапы
        self.leg(ox, gy, 34, 46 + up, sw * math.sin(ph + math.pi), 0.5, FUR)
        self.leg(ox, gy, 80, 46 + up, sw * math.sin(ph), -0.6, FUR)
        # шея и голова (вытянута вперёд — бежит в испуге)
        self.poly(ox, gy, o([(80, 50), (84, 64), (92, 78), (100, 76), (96, 60), (90, 48)]), fill=FUR, outline='')
        self.poly(ox, gy, o([(88, 80), (92, 92), (102, 96), (110, 92), (118, 86), (124, 82),
                             (126, 76), (120, 72), (108, 70), (96, 72)]), fill=FUR, outline='')
        # ухо болтается от бега
        flap = 3 * math.sin(ph)
        self.poly(ox, gy, o([(96, 92), (90, 90), (84, 80 + flap), (86, 74 + flap), (92, 80)]), fill=EAR, outline='')
        # нос, глаз, рот
        self.oval(ox, gy, 120, 77 + up, 128, 83 + up, fill=SPOT, outline='')
        self.oval(ox, gy, 103, 81 + up, 111, 91 + up, fill='white', outline='#333', width=1)
        self.oval(ox, gy, 106, 83 + up, 109, 87 + up, fill=SPOT, outline='')
        self.line(ox, gy, o([(102, 94), (108, 95), (112, 93)]), 1.5, fill='#333', smooth=True)  # бровь домиком
        self.line(ox, gy, o([(112, 73), (118, 74), (123, 76)]), 1.5, fill='#5a3510', smooth=True)
        # ошейник с жетоном
        self.line(ox, gy, o([(84, 62), (90, 66), (97, 66)]), 5, fill=COLLAR, smooth=True)
        tx, ty = self.pt(ox, gy, 91, 59 + up)
        r = 4 * self.s
        self.canvas.create_polygon(tx, ty - r, tx + r, ty, tx, ty + r, tx - r, ty, fill=TAG,
                                   outline='#b8950f', tags='sc')

    def draw_ghost(self, ox, gy, ph):
        fl = 30 + 5 * math.sin(ph / 2)      # парит над землёй и покачивается
        w = [3 * math.sin(ph * 1.5 + i) for i in range(7)]  # колышется подол
        pts = [(20, fl + 42), (24, fl + 62), (38, fl + 72), (54, fl + 70), (64, fl + 58),
               (66, fl + 46), (84, fl + 50), (98, fl + 48), (100, fl + 42), (88, fl + 38),
               (66, fl + 34), (64, fl + 18), (58, fl + 2 + w[0]), (52, fl + 10), (45, fl + w[1]),
               (38, fl + 9), (31, fl - 2 + w[2]), (24, fl + 8), (14, fl + 4 + w[3]),
               (6, fl + 12 + w[4]), (12, fl + 26)]
        self.poly(ox, gy, pts, fill=GHOST, outline=GHOST_EDGE, width=2)
        # пальцы на вытянутой руке
        for dy in (-4, 0, 4):
            self.line(ox, gy, [(96, fl + 44 + dy), (103, fl + 45 + dy * 1.4)], 2.5, fill=GHOST_EDGE)
        # пустые глаза, злые брови, открытый рот
        self.oval(ox, gy, 38, fl + 50, 46, fl + 61, fill=GHOST_HOLE, outline='')
        self.oval(ox, gy, 50, fl + 50, 58, fl + 61, fill=GHOST_HOLE, outline='')
        self.line(ox, gy, [(36, fl + 66), (46, fl + 62)], 2, fill=GHOST_HOLE)
        self.line(ox, gy, [(50, fl + 62), (60, fl + 66)], 2, fill=GHOST_HOLE)
        m = 2 * abs(math.sin(ph / 2))
        self.oval(ox, gy, 44, fl + 36 - m, 54, fl + 46, fill=GHOST_HOLE, outline='')
        return fl

    def draw(self):
        c = self.canvas
        c.delete('sc')
        h = int(c.winfo_height()) or 120
        self.s = max(0.4, (h - 18) / 100)
        gy = h - 3
        ph = self.step * (0.55 if self.boost else 0.4)
        # тень под Скуби и полоски скорости
        self.oval(self.x, gy, 22, -2, 112, 2, fill='#dfe5da', outline='')
        for i, ly in enumerate((70, 58, 46)):
            self.line(self.x, gy, [(-6 - i * 4, ly), (6 - i * 4, ly)], 2, fill='#bcbcbc')
        self.draw_scooby(self.x, gy, ph)
        if self.say_s:
            tx, ty = self.pt(self.x, gy, 112, 104)
            c.create_text(tx, ty, text='Ру-ро!', fill=EAR, font=('Segoe UI', 10, 'bold italic'), tags='sc')
        gx = self.ghost_x()
        fl = self.draw_ghost(gx, gy, ph)
        if self.say_g:
            tx, ty = self.pt(gx, gy, 40, fl + 80)
            c.create_text(tx, ty, text='Ууу-у!', fill=GHOST_EDGE, font=('Segoe UI', 10, 'italic'), tags='sc')

    def tick(self):
        w = int(self.canvas.winfo_width()) or 600
        self.x += (5.0 if self.boost else 3.0) * self.s
        # призрак то догоняет, то отстаёт, а после рывка Скуби отрывается
        self.gap += 2.0 if self.boost else (0.6 if (self.step // 60) % 2 else -0.6)
        self.gap = max(10.0, min(150.0, self.gap))
        if self.ghost_x() > w:  # оба убежали за край — выбегают слева
            self.x = -SCOOBY_LEN * self.s
            self.gap = 70.0
        self.boost = max(0, self.boost - 1)
        self.say_s = max(0, self.say_s - 1)
        self.say_g = max(0, self.say_g - 1)
        self.step += 1
        self.draw()
        self.canvas.after(40, self.tick)


if __name__ == '__main__':  # посмотреть отдельно: python scooby.py
    root = tk.Tk()
    root.geometry('760x140')
    Scooby(root, height=120, bg='#f4f8f2').pack(fill='x', padx=10, pady=6)
    root.mainloop()
