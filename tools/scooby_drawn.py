"""Мои нарисованные кадры (запасной вариант, если нет наклеек GIPHY): Шэгги и Скуби-Ду убегают от призрака — из готовых кадров-картинок (tools/scooby_frames).
Кадры рисует build_scooby_frames.py. Щелчок по Скуби — «Ру-ро!», по Шэгги — «Зоинкс!» (оба делают рывок),
по призраку — «Ууу-у!». Другие варианты: scooby_vector.py (плавные фигуры), scooby_pixel.py (квадратики)."""
import os
import tkinter as tk

FRAMES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'scooby_frames')
FRAMES = 8
FRAME_TICKS = 2  # кадр меняется каждые 2 тика по 40 мс


class Scooby:
    def __init__(self, parent, height=130, bg='white'):
        self.canvas = tk.Canvas(parent, height=height, bg=bg, highlightthickness=0)
        self.img = {n: [tk.PhotoImage(master=self.canvas, file=os.path.join(FRAMES_DIR, f'{n}_{i}.png'))
                        for i in range(FRAMES)] for n in ('scooby', 'shaggy', 'ghost')}
        self.wd = {n: imgs[0].width() for n, imgs in self.img.items()}
        self.x, self.gap, self.step = 160.0, 40.0, 0
        self.boost = 0
        self.say = {'scooby': 0, 'shaggy': 0, 'ghost': 0}  # сколько кадров показывать реплику
        self.canvas.bind('<Button-1>', self.click)
        self.canvas.after(40, self.tick)

    def pack(self, **kw):
        self.canvas.pack(**kw)

    def places(self):
        """Левые края героев: призрак сзади, Скуби в середине, Шэгги впереди."""
        sx = self.x
        return {'ghost': sx - self.gap - self.wd['ghost'],
                'scooby': sx,
                'shaggy': sx + self.wd['scooby'] + 6}

    def click(self, e):
        for name, x in self.places().items():
            if x <= e.x <= x + self.wd[name]:
                self.say[name] = 30
                if name != 'ghost':
                    self.boost = 25
                return

    def draw(self):
        c = self.canvas
        c.delete('sc')
        h = int(c.winfo_height()) or 130
        frame = (self.step // FRAME_TICKS) % FRAMES
        words = {'scooby': ('Ру-ро!', '#6b3d12'), 'shaggy': ('Зоинкс!', '#4f7a22'), 'ghost': ('Ууу-у!', '#4a3d7a')}
        for name, x in self.places().items():
            # у призрака кадры сдвинуты, чтобы он колыхался не в такт с бегунами
            f = (frame + 3) % FRAMES if name == 'ghost' else frame
            c.create_image(x, h - 2, image=self.img[name][f], anchor='sw', tags='sc')
            if self.say[name]:
                text, color = words[name]
                top = h - 2 - self.img[name][0].height()
                if name == 'shaggy':  # Шэгги высокий — реплика сбоку, а не над головой
                    tx, ty, anchor = x + self.wd[name] - 4, top + 24, 'w'
                else:
                    tx, ty, anchor = x + self.wd[name] * 0.6, max(8, top + 4), 'center'
                c.create_text(tx, ty, text=text, fill=color, anchor=anchor,
                              font=('Segoe UI', 10, 'bold italic'), tags='sc')

    def tick(self):
        w = int(self.canvas.winfo_width()) or 600
        self.x += 5.0 if self.boost else 3.0
        # призрак то догоняет, то отстаёт, а после рывка отстаёт сильнее
        self.gap += 2.0 if self.boost else (0.6 if (self.step // 60) % 2 else -0.6)
        self.gap = max(0.0, min(140.0, self.gap))
        if self.places()['ghost'] > w:  # все убежали за край — выбегают слева
            self.x = -self.wd['scooby'] - self.wd['shaggy']
            self.gap = 40.0
        self.boost = max(0, self.boost - 1)
        for k in self.say:
            self.say[k] = max(0, self.say[k] - 1)
        self.step += 1
        self.draw()
        self.canvas.after(40, self.tick)


if __name__ == '__main__':  # посмотреть отдельно: python scooby.py
    root = tk.Tk()
    root.geometry('800x150')
    Scooby(root, height=130, bg='#f4f8f2').pack(fill='x', padx=10, pady=6)
    root.mainloop()
