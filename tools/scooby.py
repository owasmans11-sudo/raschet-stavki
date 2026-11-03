"""Шэгги и Скуби-Ду убегают от призрака в окне поиска — анимированные наклейки из мультика (GIPHY).
Наклейки лежат в tools/scooby_gifs (в git не кладутся — картинки Warner Bros, только для себя).
Круги чередуются: то Шэгги и Скуби бегут каждый сам, то Шэгги тащит Скуби за лапу.
Щелчок по Скуби — «Ру-ро!», по Шэгги — «Зоинкс!» (рывок), по призраку — «Ууу-у!».
Нет наклеек — показываются мои нарисованные кадры (scooby_drawn.py)."""
import os
import tkinter as tk

from PIL import Image, ImageSequence, ImageTk

GIFS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'scooby_gifs')
# файл: (высота в окне, мс на кадр — None значит как в самой наклейке)
SPRITES = {'scooby': ('scooby.gif', 66, None),
           'shaggy': ('shaggy.gif', 116, 90),
           'ghost': ('ghost.gif', 100, None),
           'duo': ('shaggy_drags_scooby.gif', 92, 160)}
TICK = 40


def load_gif(path, height):
    """Кадры наклейки, обрезанные по общему контуру и уменьшенные до нужной высоты; плюс длительности кадров."""
    im = Image.open(path)
    frames, durs = [], []
    for f in ImageSequence.Iterator(im):
        frames.append(f.convert('RGBA'))
        durs.append(f.info.get('duration') or 100)
    box = None
    for f in frames:  # общий прямоугольник, чтобы фигура не прыгала между кадрами
        b = f.getbbox()
        if b:
            box = b if box is None else (min(box[0], b[0]), min(box[1], b[1]), max(box[2], b[2]), max(box[3], b[3]))
    out = []
    for f in frames:
        f = f.crop(box) if box else f
        w = max(1, round(f.width * height / f.height))
        out.append(f.resize((w, height), Image.LANCZOS))
    return out, durs


class GifScooby:
    def __init__(self, parent, height=130, bg='white'):
        self.canvas = tk.Canvas(parent, height=height, bg=bg, highlightthickness=0)
        self.spr = {}
        for name, (fname, h, ms) in SPRITES.items():
            frames, durs = load_gif(os.path.join(GIFS_DIR, fname), h)
            self.spr[name] = {'img': [ImageTk.PhotoImage(f, master=self.canvas) for f in frames],
                              'dur': [ms or d for d in durs], 'w': frames[0].width, 'h': h}
        self.x, self.gap, self.t, self.lap = 160.0, 40.0, 0, 0
        self.boost = 0
        self.say = {'scooby': 0, 'shaggy': 0, 'ghost': 0}
        self.canvas.bind('<Button-1>', self.click)
        self.canvas.after(TICK, self.tick)

    def pack(self, **kw):
        self.canvas.pack(**kw)

    def runners(self):
        """Кто бежит на этом круге и где их левые края (слева направо)."""
        x = self.x
        if self.lap % 2:  # Шэгги тащит Скуби — одна наклейка на двоих
            return [('ghost', x - self.gap - self.spr['ghost']['w']), ('duo', x)]
        return [('ghost', x - self.gap - self.spr['ghost']['w']), ('scooby', x),
                ('shaggy', x + self.spr['scooby']['w'] - 4)]

    def width(self):
        return sum(self.spr[n]['w'] for n, _ in self.runners()[1:])

    def frame(self, name):
        s = self.spr[name]
        total = sum(s['dur'])
        k = self.t % total
        for i, d in enumerate(s['dur']):
            if k < d:
                return s['img'][i]
            k -= d
        return s['img'][0]

    def click(self, e):
        for name, x in self.runners():
            if x <= e.x <= x + self.spr[name]['w']:
                if name == 'duo':  # на общей наклейке Шэгги справа, Скуби слева
                    name = 'shaggy' if e.x > x + self.spr['duo']['w'] / 2 else 'scooby'
                self.say[name] = 30
                if name != 'ghost':
                    self.boost = 25
                return

    def draw(self):
        c = self.canvas
        c.delete('sc')
        h = int(c.winfo_height()) or 130
        words = {'scooby': ('Ру-ро!', '#6b3d12'), 'shaggy': ('Зоинкс!', '#4f7a22'), 'ghost': ('Ууу-у!', '#4a5560')}
        for name, x in self.runners():
            s = self.spr[name]
            bottom = h - 2
            if name == 'ghost':  # призрак парит и покачивается
                bottom = h - 14 + 6 * ((self.t // 400) % 2)
            c.create_image(x, bottom, image=self.frame(name), anchor='sw', tags='sc')
            top = bottom - s['h']
            for who in (('scooby', 'shaggy') if name == 'duo' else (name,)):
                if not self.say[who]:
                    continue
                text, color = words[who]
                if name == 'duo':
                    tx = x + s['w'] * (0.85 if who == 'shaggy' else 0.2)
                    c.create_text(tx, max(8, top), text=text, fill=color, font=('Segoe UI', 10, 'bold italic'), tags='sc')
                elif who == 'shaggy':  # Шэгги высокий — реплика сбоку
                    c.create_text(x + s['w'] - 4, top + 24, text=text, fill=color, anchor='w',
                                  font=('Segoe UI', 10, 'bold italic'), tags='sc')
                else:
                    c.create_text(x + s['w'] * 0.6, max(8, top + 4), text=text, fill=color,
                                  font=('Segoe UI', 10, 'bold italic'), tags='sc')

    def tick(self):
        w = int(self.canvas.winfo_width()) or 600
        self.x += 5.0 if self.boost else 3.0
        # призрак то догоняет, то отстаёт, а после рывка отстаёт сильнее
        self.gap += 2.0 if self.boost else (0.6 if (self.t // 2400) % 2 else -0.6)
        self.gap = max(0.0, min(140.0, self.gap))
        if self.runners()[0][1] > w:  # все убежали за край — новый круг слева
            self.lap += 1
            self.x = -self.width()
            self.gap = 40.0
        self.boost = max(0, self.boost - 1)
        for k in self.say:
            self.say[k] = max(0, self.say[k] - 1)
        self.t += TICK
        self.draw()
        self.canvas.after(TICK, self.tick)


def Scooby(parent, height=130, bg='white'):
    """Наклейки есть — показываем их, нет — мои нарисованные кадры."""
    if all(os.path.exists(os.path.join(GIFS_DIR, f)) for f, _, _ in SPRITES.values()):
        try:
            return GifScooby(parent, height=height, bg=bg)
        except Exception:  # noqa: BLE001 — битая наклейка не должна ломать окно поиска
            pass
    from scooby_drawn import Scooby as Drawn
    return Drawn(parent, height=height, bg=bg)


if __name__ == '__main__':  # посмотреть отдельно: python scooby.py
    root = tk.Tk()
    root.geometry('800x150')
    Scooby(root, height=130, bg='#f4f8f2').pack(fill='x', padx=10, pady=6)
    root.mainloop()
