"""Чтение .xlsx без сторонних библиотек: листы, ячейки (текст, формула, жирность), объединения.
Плюс «отпечаток» листа — для проверки, что лист не изменился."""
import zipfile, re, html, hashlib

NS = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'


def _txt(xml_fragment):
    return html.unescape(''.join(re.findall(r'<t[^>]*>([^<]*)</t>', xml_fragment, re.S)))


def col_num(letters):
    n = 0
    for ch in letters:
        n = n * 26 + ord(ch) - 64
    return n


class Book:
    def __init__(self, path):
        z = zipfile.ZipFile(path)
        self.z = z
        ss = z.read('xl/sharedStrings.xml').decode('utf-8') if 'xl/sharedStrings.xml' in z.namelist() else ''
        self.strings = [_txt(si) for si in re.findall(r'<si>(.*?)</si>', ss, re.S)]
        st = z.read('xl/styles.xml').decode('utf-8')
        fonts = re.findall(r'<font>(.*?)</font>|<font/>', re.search(r'<fonts[^>]*>(.*?)</fonts>', st, re.S).group(1), re.S)
        self.bold_font = ['<b/>' in f or '<b val="1"/>' in f for f in fonts]
        xfs = re.search(r'<cellXfs[^>]*>(.*?)</cellXfs>', st, re.S).group(1)
        self.xf_font = [int(m) for m in re.findall(r'<xf [^>]*?fontId="(\d+)"', xfs)]
        wbx = z.read('xl/workbook.xml').decode('utf-8')
        rels = z.read('xl/_rels/workbook.xml.rels').decode('utf-8')
        target = dict(re.findall(r'Id="([^"]+)"[^>]*Target="([^"]+)"', rels))
        target.update({k: v for v, k in re.findall(r'Target="([^"]+)"[^>]*Id="([^"]+)"', rels)})
        self.sheets = {}
        for name, rid in re.findall(r'<sheet [^>]*name="([^"]+)"[^>]*r:id="([^"]+)"', wbx):
            t = target[rid].lstrip('/')
            self.sheets[html.unescape(name)] = t if t.startswith('xl/') else 'xl/' + t

    def raw(self, sheet):
        return self.z.read(self.sheets[sheet]).decode('utf-8')

    def cells(self, sheet):
        """[(row, col, addr, text, formula, bold)] — только непустые."""
        x = self.raw(sheet)
        out = []
        for m in re.finditer(r'<c r="([A-Z]+)(\d+)"([^>]*?)(?:/>|>(.*?)</c>)', x, re.S):
            letters, row, attrs, inner = m.group(1), int(m.group(2)), m.group(3), m.group(4) or ''
            t = re.search(r't="(\w+)"', attrs); s = re.search(r's="(\d+)"', attrs)
            f = re.search(r'<f[^>]*>(.*?)</f>|<f [^>]*/>', inner, re.S)
            v = re.search(r'<v>(.*?)</v>', inner, re.S)
            if t and t.group(1) == 's' and v: text = self.strings[int(v.group(1))]
            elif t and t.group(1) == 'inlineStr': text = _txt(inner)
            else: text = html.unescape(v.group(1)) if v else ''
            bold = bool(s) and self.bold_font[self.xf_font[int(s.group(1))]] if s else False
            if text.strip() or f:
                out.append((row, col_num(letters), letters + str(row), text, html.unescape(f.group(1) or '') if f else None, bold))
        return out

    def fingerprint(self, sheet):
        """Значения и формулы листа (без оформления)."""
        cs = self.cells(sheet)
        h = hashlib.md5('|'.join(f'{a}={t}={f}' for _, _, a, t, f, _ in cs).encode('utf-8')).hexdigest()
        return h, sum(1 for c in cs if c[4] is not None)
