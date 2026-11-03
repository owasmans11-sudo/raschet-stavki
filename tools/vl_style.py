"""Общий стиль шаблонов «вариант 3» (одобрен Андреем 2026-10-23): яркий синий, Arial, A4,
поля «плитками» без линий сетки. Только стандартная библиотека Python."""
import zipfile, re, html
from xml.sax.saxutils import escape

BLUE = "1E6FE0"; DARK = "0B4AA8"; LIGHT = "EAF2FE"; VAL = "F6F9FE"; GRAY = "6B6B6B"; WHITE = "FFFFFF"
FONT = "Arial"
W = 10206  # ширина текста A4 при полях 850


def paragraphs(src):
    """Все абзацы .docx (включая таблицы) как текст."""
    x = zipfile.ZipFile(src).read("word/document.xml").decode("utf-8")
    return [html.unescape(''.join(re.findall(r'<w:t[^>]*>([^<]*)', p)))
            for p in re.findall(r'<w:p[ >].*?</w:p>', x, re.S)]


def slice_between(ps, start, stop):
    """Абзацы от первого, начинающегося с start, до первого после него, начинающегося с stop."""
    i = next(i for i, t in enumerate(ps) if t.strip().startswith(start))
    j = next(j for j in range(i + 1, len(ps)) if ps[j].strip().startswith(stop))
    return [t.strip() for t in ps[i:j] if t.strip()]


def run(text, sz=18, bold=False, color=None):
    rpr = f'<w:rFonts w:ascii="{FONT}" w:hAnsi="{FONT}" w:cs="{FONT}"/>'
    if bold: rpr += '<w:b/>'
    if color: rpr += f'<w:color w:val="{color}"/>'
    rpr += f'<w:sz w:val="{sz}"/><w:szCs w:val="{sz}"/>'
    return f'<w:r><w:rPr>{rpr}</w:rPr><w:t xml:space="preserve">{escape(text)}</w:t></w:r>'


def para(runs="", jc="left", before=0, after=0, extra="", keep=False):
    ppr = f'<w:spacing w:before="{before}" w:after="{after}" w:line="252" w:lineRule="auto"/><w:jc w:val="{jc}"/>'
    if keep: ppr = '<w:keepNext/>' + ppr
    return f'<w:p><w:pPr>{extra}{ppr}</w:pPr>{runs}</w:p>'


def borders(color=WHITE, sz=16):
    return "<w:tblBorders>" + "".join(f'<w:{s} w:val="single" w:sz="{sz}" w:space="0" w:color="{color}"/>'
                                      for s in ["top", "left", "bottom", "right", "insideH", "insideV"]) + "</w:tblBorders>"


NOB = "<w:tblBorders>" + "".join(f'<w:{s} w:val="nil"/>' for s in ["top", "left", "bottom", "right", "insideH", "insideV"]) + "</w:tblBorders>"


def cell(content, w, fill=None, span=1, valign="center"):
    tcpr = f'<w:tcW w:w="{w}" w:type="dxa"/>'
    if span > 1: tcpr += f'<w:gridSpan w:val="{span}"/>'
    if fill: tcpr += f'<w:shd w:val="clear" w:color="auto" w:fill="{fill}"/>'
    tcpr += f'<w:vAlign w:val="{valign}"/>'
    return f'<w:tc><w:tcPr>{tcpr}</w:tcPr>{content or para()}</w:tc>'


def row(cells, h=None):
    trpr = '<w:cantSplit/>' + (f'<w:trHeight w:val="{h}"/>' if h else '')
    return f'<w:tr><w:trPr>{trpr}</w:trPr>{"".join(cells)}</w:tr>'


def table(rows, cols, bord=None):
    grid = "".join(f'<w:gridCol w:w="{c}"/>' for c in cols)
    mar = '<w:tblCellMar><w:top w:w="40" w:type="dxa"/><w:left w:w="100" w:type="dxa"/><w:bottom w:w="40" w:type="dxa"/><w:right w:w="100" w:type="dxa"/></w:tblCellMar>'
    return (f'<w:tbl><w:tblPr><w:tblW w:w="{sum(cols)}" w:type="dxa"/>{bord or borders()}<w:tblLayout w:type="fixed"/>{mar}</w:tblPr>'
            f'<w:tblGrid>{grid}</w:tblGrid>{"".join(rows)}</w:tbl>')


def bar(text):
    """Синяя полоса-заголовок раздела."""
    return para(run(text, 19, True, WHITE), before=140, after=60, keep=True,
                extra=f'<w:shd w:val="clear" w:color="auto" w:fill="{BLUE}"/><w:ind w:left="60" w:right="60"/>')


def gap(after=60):
    return para("", after=after)


# --- крупные блоки

def header(co):
    """Шапка на светло-голубой плашке. co: brand, legal, inn, ogrn, phone, email."""
    left = para(run(co["brand"], 34, True, BLUE)) + para(run(f'{co["legal"]} · грузоперевозки по России', 17, color=DARK))
    right = (para(run(co["inn"], 16, color=GRAY), "right") + para(run(co["ogrn"], 16, color=GRAY), "right") +
             para(run(f'Тел.: {co["phone"]}', 16, color=GRAY), "right") + para(run(co["email"], 16, color=BLUE), "right"))
    return table([row([cell(left, 5600, LIGHT), cell(right, W - 5600, LIGHT)], 1000)], [5600, W - 5600], NOB) + gap()


def title(big, small):
    return (para(run(big, 28, True, DARK), "center", before=160) +
            para(run(small, 20, color=DARK), "center", after=160))


def keystrip(items):
    """Плашка с главным: [(подпись, значение)], последняя — синяя (сумма)."""
    kw = [3700, 3300, W - 7000]
    cells = []
    for i, (lab, val) in enumerate(items):
        last = i == len(items) - 1
        c = para(run(lab, 15, color="D6E6FD" if last else BLUE)) + para(run(val, 20, True, WHITE if last else DARK), before=40)
        cells.append(cell(c, kw[i], BLUE if last else LIGHT))
    return table([row(cells, 700)], kw, borders(WHITE, 24)) + gap(100)


def section(title_, fields, label_w=4000):
    """Раздел: синий заголовок + строки «подпись | поле» плитками."""
    R = W - label_w
    rows = [row([cell(para(run(title_, 19, True, WHITE), keep=True), W, BLUE, span=2)], 320)]
    for label, value in fields:
        rows.append(row([cell(para(run(label, 17, color=DARK)), label_w, LIGHT),
                         cell(para(run(value, 18)) if value else "", R, VAL)], 380))
    return table(rows, [label_w, R]) + gap()


def section_pair(t1, f1, t2, f2):
    """Два раздела рядом (Загрузка | Разгрузка). Поля попарно."""
    lw, vw = 1750, W // 2 - 1750
    cols = [lw, vw, lw, W - 2 * lw - vw]
    rows = [row([cell(para(run(t1, 19, True, WHITE), keep=True), lw + vw, BLUE, span=2),
                 cell(para(run(t2, 19, True, WHITE), keep=True), cols[2] + cols[3], BLUE, span=2)], 320)]
    for (l1, v1), (l2, v2) in zip(f1, f2):
        rows.append(row([cell(para(run(l1, 16, color=DARK)), lw, LIGHT), cell(para(run(v1, 17)) if v1 else "", vw, VAL),
                         cell(para(run(l2, 16, color=DARK)), lw, LIGHT), cell(para(run(v2, 17)) if v2 else "", cols[3], VAL)], 520))
    return table(rows, cols) + gap()


def parties(t1, lines1, t2, lines2):
    """Реквизиты и подписи двух сторон."""
    hw = W // 2
    req = lambda ls: "".join(para(run(l, 16), keep=True) for l in ls)  # keep: шапка не отрывается от реквизитов
    sign = (para("", before=200) + para(run("_______________ / _______________ /", 18), before=200) +
            para(run("подпись                   ФИО", 14, color=GRAY)) + para(run("М.П.", 16, color=GRAY), before=120))
    hdr = lambda t: para(run(t, 19, True, WHITE), keep=True)
    return gap(80) + table([
        row([cell(hdr(t1), hw, BLUE), cell(hdr(t2), W - hw, BLUE)], 320),
        row([cell(req(lines1), hw, VAL, valign="top"), cell(req(lines2), W - hw, VAL, valign="top")]),
        row([cell(sign, hw, VAL, valign="top"), cell(sign, W - hw, VAL, valign="top")]),
    ], [hw, W - hw])


BLANK_REQ = ["Наименование: ____________________________", "Юр. адрес: _______________________________",
             "Почт. адрес: _____________________________", "ИНН / КПП: _______________________________",
             "ОГРН: ___________________________________", "р/с: _____________________________________",
             "Банк: ___________________________________", "к/с: ______________________ БИК: __________",
             "Эл. почта: ______________________________", "Тел.: ____________________________________"]


def save(out, body, footer_text):
    NS = ('xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
          'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"')
    sect = ('<w:sectPr><w:footerReference w:type="default" r:id="rIdFooter"/>'
            '<w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="850" w:right="850" w:bottom="850" w:left="850" w:header="400" w:footer="400" w:gutter="0"/></w:sectPr>')
    document = f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document {NS}><w:body>{"".join(body)}{sect}</w:body></w:document>'
    FR = f'<w:rPr><w:sz w:val="14"/><w:szCs w:val="14"/><w:color w:val="{GRAY}"/></w:rPr>'
    fld = lambda code: (f'<w:r>{FR}<w:fldChar w:fldCharType="begin"/></w:r><w:r>{FR}<w:instrText xml:space="preserve"> {code} </w:instrText></w:r>'
                        f'<w:r>{FR}<w:fldChar w:fldCharType="separate"/></w:r>{run("1", 14, color=GRAY)}<w:r>{FR}<w:fldChar w:fldCharType="end"/></w:r>')
    footer = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:ftr {NS}>'
              + para(run(footer_text + "        Стр. ", 14, color=GRAY) + fld("PAGE") + run(" из ", 14, color=GRAY) + fld("NUMPAGES"), "center")
              + '</w:ftr>')
    styles = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
              f'<w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="{FONT}" w:hAnsi="{FONT}" w:cs="{FONT}" w:eastAsia="{FONT}"/><w:sz w:val="18"/><w:lang w:val="ru-RU"/></w:rPr></w:rPrDefault>'
              '<w:pPrDefault><w:pPr><w:spacing w:after="0" w:line="240" w:lineRule="auto"/></w:pPr></w:pPrDefault></w:docDefaults>'
              '<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style></w:styles>')
    ct = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
          '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>'
          '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
          '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
          '<Override PartName="/word/footer1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"/></Types>')
    rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
    drels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
             '<Relationship Id="rIdStyles" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
             '<Relationship Id="rIdFooter" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer" Target="footer1.xml"/></Relationships>')
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", ct)
        z.writestr("_rels/.rels", rels)
        z.writestr("word/document.xml", document)
        z.writestr("word/styles.xml", styles)
        z.writestr("word/footer1.xml", footer)
        z.writestr("word/_rels/document.xml.rels", drels)
