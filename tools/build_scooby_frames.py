"""Рисует кадры бега для окна поиска: Скуби, Шэгги и призрак (по 8 кадров, PNG с прозрачным фоном).
Запуск: python tools/build_scooby_frames.py → tools/scooby_frames/*.png. Рисунок — SVG, в картинку переводит PyMuPDF."""
import math
import os

import pymupdf

FRAMES = 8
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'scooby_frames')
INK = '#2a1a0a'

# размер в окне: (масштаб, левый край, верх, ширина, высота) в единицах рисунка
BOX = {'scooby': (0.72, -26, -14, 220, 140),
       'shaggy': (0.75, -6, -14, 116, 166),
       'ghost': (0.72, 6, -14, 170, 160)}


def stroke(d, color, w, outline=True):
    """Линия с чёрным контуром: сначала толстая тёмная, сверху цветная."""
    s = ''
    if outline:
        s += f'<path d="{d}" fill="none" stroke="{INK}" stroke-width="{w + 4}" stroke-linecap="round" stroke-linejoin="round"/>'
    return s + f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{w}" stroke-linecap="round" stroke-linejoin="round"/>'


def limb(hx, hy, a, b, l1, l2):
    """Бедро+голень: a — наклон бедра от вертикали (плюс — вперёд), b — сгиб в колене. Возвращает (путь, стопа)."""
    kx, ky = hx + l1 * math.sin(a), hy + l1 * math.cos(a)
    fx, fy = kx + l2 * math.sin(a + b), ky + l2 * math.cos(a + b)
    return f'M{hx:.1f} {hy:.1f} L{kx:.1f} {ky:.1f} L{fx:.1f} {fy:.1f}', (fx, fy)


def scooby(ph):
    fur, far, = '#c58a3e', '#a06a28'
    up = -5 * abs(math.sin(ph))
    wag = 6 * math.sin(ph * 2)
    flap = 4 * math.sin(ph)
    g = []

    def leg(hx, hy, a, b, color):
        d, (fx, fy) = limb(hx, hy, a, b, 26, 26)
        g.append(stroke(d, color, 8))
        g.append(f'<ellipse cx="{fx + 4:.1f}" cy="{fy + 1:.1f}" rx="9" ry="5" fill="{color}" stroke="{INK}" stroke-width="2"/>')

    sw = 0.75
    leg(47, 68, sw * math.sin(ph + 0.6), 0.4, far)               # дальняя задняя
    leg(108, 66, sw * math.sin(ph + math.pi + 0.6), -0.4, far)    # дальняя передняя
    g.append(stroke(f'M34 58 C20 52 {12 + wag / 2:.1f} 40 {14 + wag:.1f} 24', fur, 7))  # хвост
    g.append(f'<path d="M28 62 C30 44 60 40 85 42 C105 43 120 48 122 62 C122 78 100 82 75 80 C50 80 28 78 28 62 Z" '
             f'fill="{fur}" stroke="{INK}" stroke-width="2.5"/>')
    g.append('<path d="M45 76 C60 82 95 82 112 74 C100 70 60 70 45 76 Z" fill="#dcab68"/>')
    for cx, cy, rx, ry in ((55, 54, 7, 5), (74, 49, 5, 3.5), (92, 57, 6, 4), (66, 66, 4, 3)):
        g.append(f'<ellipse cx="{cx}" cy="{cy}" rx="{rx}" ry="{ry}" fill="#1c1c1c"/>')
    leg(44, 70, sw * math.sin(ph), 0.4, fur)                     # ближняя задняя
    leg(112, 68, sw * math.sin(ph + math.pi), -0.4, fur)          # ближняя передняя
    g.append(f'<path d="M106 54 C114 42 120 32 124 22 L140 26 C134 40 128 54 120 66 Z" fill="{fur}" stroke="{INK}" '
             f'stroke-width="2.5" stroke-linejoin="round"/>')
    g.append(f'<path d="M118 20 C116 6 130 -2 144 2 C152 4 158 10 168 12 C178 13 182 20 178 27 C172 33 158 32 146 34 '
             f'C134 36 120 32 118 20 Z" fill="{fur}" stroke="{INK}" stroke-width="2.5"/>')
    g.append(f'<path d="M150 28 C160 30 170 29 176 26" fill="none" stroke="{INK}" stroke-width="2" stroke-linecap="round"/>')
    t = 2 * abs(math.sin(ph))  # язык болтается
    g.append(f'<path d="M160 29 C161 {37 + t:.1f} 168 {37 + t:.1f} 169 29" fill="#e2566b" stroke="{INK}" stroke-width="1.5"/>')
    g.append('<ellipse cx="178" cy="17" rx="6" ry="5" fill="#111"/><ellipse cx="176" cy="15" rx="1.8" ry="1.2" fill="#fff"/>')
    g.append(f'<ellipse cx="148" cy="11" rx="7" ry="8" fill="#fff" stroke="{INK}" stroke-width="2"/>'
             '<circle cx="151" cy="12" r="2.5" fill="#111"/>')
    g.append(f'<path d="M140 0 C146 -4 152 -3 156 1" fill="none" stroke="{INK}" stroke-width="2" stroke-linecap="round"/>')
    g.append(f'<path d="M130 6 C118 2 {110 - flap:.1f} {14 + flap:.1f} {112 - flap:.1f} {28 + flap:.1f} C118 24 124 18 132 14 Z" '
             f'fill="#6b3d12" stroke="{INK}" stroke-width="2" stroke-linejoin="round"/>')
    g.append(stroke('M108 50 C116 56 126 58 134 54', '#22a99c', 5))
    g.append(f'<path d="M124 57 L130 63 L124 69 L118 63 Z" fill="#f2c81b" stroke="{INK}" stroke-width="1.5"/>')
    lines = f'<path d="M6 40 L-14 40 M2 56 L-20 56 M6 72 L-12 72" stroke="#9a9a9a" stroke-width="3" stroke-linecap="round"/>'
    return lines + f'<g transform="translate(0 {up:.1f})">' + ''.join(g) + '</g>'


def shaggy(ph):
    shirt, pants, skin, hair = '#86bb46', '#8b6936', '#f2c9a0', '#9b6a30'
    up = -5 * abs(math.sin(ph))
    g = []

    def leg(a, b, color):
        d, (fx, fy) = limb(48, 94, a, b, 22, 22)
        g.append(stroke(d, color, 9))
        g.append(f'<ellipse cx="{fx + 5:.1f}" cy="{fy + 2:.1f}" rx="10" ry="5" fill="#4a3424" stroke="{INK}" stroke-width="2"/>')

    def arm(sx, a, color):
        d, (hx, hy) = limb(sx, 46, a, 1.4, 19, 17)
        g.append(stroke(d, color, 6))
        g.append(f'<circle cx="{hx:.1f}" cy="{hy:.1f}" r="5" fill="{skin}" stroke="{INK}" stroke-width="1.5"/>')

    s = math.sin(ph)
    leg(-0.8 * s, -0.4 - 0.9 * max(0.0, -math.cos(ph)), '#6f5229')       # дальняя нога
    arm(42, 1.0 * s, '#6f9e34')                                              # дальняя рука
    g.append(f'<path d="M32 42 C36 32 58 30 66 42 L64 96 L36 96 Z" fill="{shirt}" stroke="{INK}" stroke-width="2.5" '
             f'stroke-linejoin="round"/>')
    leg(0.8 * s, -0.4 - 0.9 * max(0.0, math.cos(ph)), pants)                # ближняя нога
    arm(56, -1.0 * s, shirt)                                                 # ближняя рука
    g.append(f'<rect x="44" y="28" width="10" height="8" fill="{skin}" stroke="{INK}" stroke-width="1.5"/>')
    g.append(f'<ellipse cx="54" cy="16" rx="13" ry="16" fill="{skin}" stroke="{INK}" stroke-width="2.5"/>')
    g.append(f'<path d="M66 14 C72 14 74 18 68 20" fill="{skin}" stroke="{INK}" stroke-width="2"/>')
    g.append(f'<path d="M54 30 C58 36 62 36 64 28" fill="{hair}" stroke="{INK}" stroke-width="1.5"/>')
    hb = 2 * math.cos(ph * 2)  # чёлка подпрыгивает
    g.append(f'<path d="M40 14 C36 0 50 {-8 + hb:.1f} 62 {-4 + hb:.1f} C70 -2 70 4 64 2 C60 0 52 2 50 6 C46 6 44 10 46 16 '
             f'L42 22 C38 20 38 16 40 14 Z" fill="{hair}" stroke="{INK}" stroke-width="2" stroke-linejoin="round"/>')
    g.append(f'<ellipse cx="60" cy="10" rx="4" ry="5" fill="#fff" stroke="{INK}" stroke-width="1.5"/>'
             '<circle cx="61.5" cy="11" r="1.6" fill="#111"/>')
    g.append(f'<ellipse cx="60" cy="24" rx="3" ry="{2.5 + abs(s):.1f}" fill="{INK}"/>')  # кричит
    return f'<g transform="translate(0 {up:.1f})">' + ''.join(g) + '</g>'


def ghost(ph):
    edge = '#4a3d7a'
    up = 4 * math.sin(ph)
    w = [4 * math.sin(ph + i * 1.3) for i in range(6)]
    hem = (f'C102 {116 + w[0]:.1f} 96 {128 + w[1]:.1f} 88 120 C80 {128 + w[2]:.1f} 74 {116 + w[3]:.1f} 66 124 '
           f'C58 {116 + w[4]:.1f} 52 {126 + w[5]:.1f} 44 118 C30 112 20 {98 + w[0]:.1f} 14 {84 + w[1]:.1f}')
    reach = 4 * math.sin(ph * 2)
    g = [f'<path d="M40 30 C42 4 92 -6 106 24 C112 40 112 56 110 70 L{148 + reach:.1f} 60 C{158 + reach:.1f} 58 '
         f'{160 + reach:.1f} 70 {152 + reach:.1f} 74 L110 90 C110 104 112 114 110 122 {hem} C24 80 34 72 40 58 Z" '
         f'fill="#f4f1ff" stroke="{edge}" stroke-width="2.5" stroke-linejoin="round"/>',
         '<path d="M46 40 C44 64 40 84 26 92 C34 100 44 108 52 112 C50 90 52 64 58 40 Z" fill="#ddd6f5"/>',
         f'<path d="M{148 + reach:.1f} 60 L{160 + reach:.1f} 54 M{152 + reach:.1f} 66 L{164 + reach:.1f} 64 '
         f'M{152 + reach:.1f} 72 L{162 + reach:.1f} 76" stroke="{edge}" stroke-width="2.5" stroke-linecap="round"/>',
         '<ellipse cx="66" cy="34" rx="7" ry="10" fill="#2b2347"/><ellipse cx="88" cy="34" rx="7" ry="10" fill="#2b2347"/>',
         '<path d="M56 20 L72 26 M98 20 L82 26" stroke="#2b2347" stroke-width="3" stroke-linecap="round"/>',
         f'<ellipse cx="78" cy="58" rx="8" ry="{10 + 2 * abs(math.sin(ph)):.1f}" fill="#2b2347"/>']
    return f'<g transform="translate(0 {up:.1f})">' + ''.join(g) + '</g>'


def render(name, body):
    s, x0, y0, w, h = BOX[name]
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w * s:.0f}" height="{h * s:.0f}" '
           f'viewBox="{x0} {y0} {w} {h}">{body}</svg>')
    doc = pymupdf.open(stream=svg.encode(), filetype='svg')
    return doc[0].get_pixmap(alpha=True)


def main():
    os.makedirs(OUT, exist_ok=True)
    for i in range(FRAMES):
        ph = 2 * math.pi * i / FRAMES
        for name, fn in (('scooby', scooby), ('shaggy', shaggy), ('ghost', ghost)):
            render(name, fn(ph)).save(os.path.join(OUT, f'{name}_{i}.png'))
    print('кадры готовы:', OUT)


if __name__ == '__main__':
    main()
