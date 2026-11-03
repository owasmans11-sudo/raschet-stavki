"""Шаблон «Заявка с клиентом ВЛ», вариант 2: синяя шапка с монограммой, маршрут-схема,
поля в виде строк с подчёркиванием, условия в две колонки.
Запуск: python build_zayavka_klient_v2.py <старый.docx> <новый.docx>"""
import zipfile, re, sys
from xml.sax.saxutils import escape

SRC, OUT = sys.argv[1], sys.argv[2]

BLUE = "1E6FE0"; NAVY = "0A2A66"; LIGHT = "EAF2FE"; PALE = "D6E6FD"; LINE = "A9C8F5"; GRAY = "6B6B6B"
FONT = "Arial"
W = 10206  # ширина текста A4 при полях 850

# --- юридический текст 9-14 из старого шаблона, слово в слово
x = zipfile.ZipFile(SRC).read("word/document.xml").decode("utf-8")
ps = [''.join(re.findall(r'<w:t[^>]*>([^<]*)', p)) for p in re.findall(r'<w:p[ >].*?</w:p>', x, re.S)]
ps = [p.replace('&amp;', '&') for p in ps]
i9 = next(i for i, t in enumerate(ps) if t.strip().startswith('9.'))
i15 = next(i for i, t in enumerate(ps) if t.strip().startswith('15.'))
legal = [t.strip() for t in ps[i9:i15] if t.strip()]

def run(text, sz=18, bold=False, color=None, font=FONT, spacing=None):
    rpr = f'<w:rFonts w:ascii="{font}" w:hAnsi="{font}" w:cs="{font}"/>'
    if bold: rpr += '<w:b/>'
    if color: rpr += f'<w:color w:val="{color}"/>'
    if spacing: rpr += f'<w:spacing w:val="{spacing}"/>'
    rpr += f'<w:sz w:val="{sz}"/><w:szCs w:val="{sz}"/>'
    return f'<w:r><w:rPr>{rpr}</w:rPr><w:t xml:space="preserve">{escape(text)}</w:t></w:r>'

def para(runs="", jc="left", before=0, after=0, extra="", keep=False, line=252):
    ppr = (('<w:keepNext/>' if keep else '') + extra +
           f'<w:spacing w:before="{before}" w:after="{after}" w:line="{line}" w:lineRule="auto"/><w:jc w:val="{jc}"/>')
    return f'<w:p><w:pPr>{ppr}</w:pPr>{runs}</w:p>'

def bdr(sides, color, sz=4):
    return "".join(f'<w:{s} w:val="single" w:sz="{sz}" w:space="0" w:color="{color}"/>' for s in sides)

NIL = "".join(f'<w:{s} w:val="nil"/>' for s in ["top", "left", "bottom", "right", "insideH", "insideV"])

def cell(content, w, fill=None, span=1, valign="center", borders=None, mar=None):
    tcpr = f'<w:tcW w:w="{w}" w:type="dxa"/>'
    if span > 1: tcpr += f'<w:gridSpan w:val="{span}"/>'
    if borders: tcpr += f'<w:tcBorders>{borders}</w:tcBorders>'
    if fill: tcpr += f'<w:shd w:val="clear" w:color="auto" w:fill="{fill}"/>'
    if mar: tcpr += f'<w:tcMar>{mar}</w:tcMar>'
    tcpr += f'<w:vAlign w:val="{valign}"/>'
    return f'<w:tc><w:tcPr>{tcpr}</w:tcPr>{content or para()}</w:tc>'

def row(cells, h=None, exact=False):
    trpr = '<w:cantSplit/>'
    if h: trpr += f'<w:trHeight w:val="{h}"' + (' w:hRule="exact"' if exact else '') + '/>'
    return f'<w:tr><w:trPr>{trpr}</w:trPr>{"".join(cells)}</w:tr>'

def table(rows, cols, borders=NIL, pad=100):
    grid = "".join(f'<w:gridCol w:w="{c}"/>' for c in cols)
    mar = f'<w:tblCellMar><w:top w:w="30" w:type="dxa"/><w:left w:w="{pad}" w:type="dxa"/><w:bottom w:w="30" w:type="dxa"/><w:right w:w="{pad}" w:type="dxa"/></w:tblCellMar>'
    return (f'<w:tbl><w:tblPr><w:tblW w:w="{sum(cols)}" w:type="dxa"/><w:tblBorders>{borders}</w:tblBorders>'
            f'<w:tblLayout w:type="fixed"/>{mar}</w:tblPr><w:tblGrid>{grid}</w:tblGrid>{"".join(rows)}</w:tbl>')

body = []

# --- 1. шапка: синяя полоса во всю ширину, слева монограмма «ВЛ»
mono = para(run("ВЛ", 30, True, BLUE), "center")
name = (para(run("ВОСТОЧНАЯ ЛОГИСТИКА", 30, True, "FFFFFF", spacing=20)) +
        para(run("грузоперевозки по России · Иркутск", 16, color=PALE)))
contacts = (para(run("+7 (924) 990-90-19", 17, True, "FFFFFF"), "right") +
            para(run("Vostok.logist@list.ru", 16, color=PALE), "right") +
            para(run("ИНН 3812166710 · КПП 381201001", 14, color=PALE), "right"))
gap = 140
body.append(table([row([
    cell(mono, 900, "FFFFFF", mar=f'<w:left w:w="0" w:type="dxa"/><w:right w:w="0" w:type="dxa"/>'),
    cell(name, 5300, BLUE, mar=f'<w:left w:w="{gap * 2}" w:type="dxa"/>'),
    cell(contacts, W - 6200, BLUE, mar='<w:right w:w="200" w:type="dxa"/>'),
], 900)], [900, 5300, W - 6200], pad=60))

# --- 2. заголовок: номер крупно, слева подпись мелко
body.append(table([row([
    cell(para(run("ДОГОВОР (ЗАКАЗ-НАРЯД)", 16, True, GRAY, spacing=30)) +
         para(run("на фрахтование транспортом", 16, color=GRAY)), 4200, valign="bottom"),
    cell(para(run("№ ________  от «___» ____________ 20___ г.", 24, True, NAVY), "right"), W - 4200, valign="bottom"),
], 620)], [4200, W - 4200], borders=f'<w:bottom w:val="single" w:sz="6" w:space="0" w:color="{LINE}"/>'))
body.append(para("", after=120))

# --- 3. маршрут-схема: ● погрузка ——— 🚚 ——— ● выгрузка  |  ставка
dot = lambda c: run("●", 22, color=c)
dash = run("——————", 16, color=LINE)
truck = run("🚚", 26, font="Segoe UI Emoji")
route_line = para(dot(BLUE) + run(" ", 10) + dash + run("  ", 10) + truck + run("  ", 10) + dash + run(" ", 10) + dot(NAVY), "center")
rw = [2900, 3500, 3806]
body.append(table([
    row([cell(para(run("ПОГРУЗКА", 14, True, BLUE, spacing=20)), rw[0], LIGHT),
         cell(route_line, rw[1], LIGHT),
         cell(para(run("ВЫГРУЗКА", 14, True, NAVY, spacing=20), "right"), rw[2], LIGHT)], 280),
    row([cell(para(run("город: ________________", 18, True, NAVY)) + para(run("дата: ___.___.20___", 16, color=GRAY), before=40), rw[0], LIGHT),
         cell(para(run("СТАВКА", 14, True, PALE, spacing=20), "center") + para(run("__________ ₽", 26, True, "FFFFFF"), "center"), rw[1], BLUE),
         cell(para(run("город: ________________", 18, True, NAVY), "right") + para(run("дата: ___.___.20___", 16, color=GRAY), "right", before=40), rw[2], LIGHT)], 620),
], rw, pad=160))
body.append(para("", after=160))

# --- 4. разделы 1-8: номер в тёмно-синем квадрате, поля строками с подчёркиванием
def section(num, title, fields, two_col=True):
    out = [table([row([
        cell(para(run(str(num), 20, True, "FFFFFF"), "center"), 420, NAVY, mar='<w:left w:w="0" w:type="dxa"/><w:right w:w="0" w:type="dxa"/>'),
        cell(para(run(title, 20, True, NAVY), keep=True), W - 420, borders=bdr(["bottom"], BLUE, 12)),
    ], 380)], [420, W - 420])]
    rows = []
    under = bdr(["bottom"], LINE, 4)
    if two_col:
        half = W // 2
        for i in range(0, len(fields), 2):
            pair = fields[i:i + 2] + [("", "")] * (2 - len(fields[i:i + 2]))
            rows.append(row([cell(para(run(l, 14, color=GRAY)) + para(run(v, 18) if v else "", before=60), half,
                                  valign="bottom", borders=under if l else None) for l, v in pair], 560))
        out.append(table(rows, [W // 2, W // 2], pad=60))
    else:
        for l, v in fields:
            rows.append(row([cell(para(run(l, 14, color=GRAY)) + para(run(v, 18) if v else "", before=60), W,
                                  valign="bottom", borders=under)], 560))
        out.append(table(rows, [W], pad=60))
    return "".join(out) + para("", after=140)

body.append(section(1, "Заказчик", [
    ("Наименование / ФИО", ""), ("ИНН, ОГРН / КПП, паспортные данные", ""),
    ("ФИО уполномоченного лица Заказчика (если юр. л.)", ""), ("Основания полномочий подписанта (если юр. л.)", ""),
    ("Адрес электронной почты и № телефонов (в т.ч. мессенджеров)", "")]))
body.append(section(2, "Фрахтовщик", [
    ("Менеджер Фрахтовщика, принявший заказ", ""), ("Телефон менеджера", ""),
    ("Эл. почта, № факсов и телефонов (в т.ч. мессенджеров)", "Vostok.logist@list.ru"),
    ("Почтовый адрес для обмена оригиналами документов", "664040, г. Иркутск, ул. Павла Красильникова, д. 172")]))
body.append(section(3, "Погрузка", [
    ("Адрес подачи ТС Заказчику", ""), ("Дата и время подачи ТС (начало срока фрахтования)", ""),
    ("Контактное лицо в месте подачи ТС", "")]))
body.append(section(4, "Выгрузка", [
    ("Адрес места окончания фрахтования", ""), ("Дата и время окончания срока фрахтования", ""),
    ("Контактное лицо в месте окончания фрахтования", "")]))
body.append(section(5, "Фрахт", [
    ("Стоимость фрахтования", ""),
    ("Сроки и условия оплаты (аванс, постоплата, наличные, безнал, р/с, карта и т.п.)", "")]))
body.append(section(6, "Груз", [
    ("Габариты груза (вес, объём, размеры)", ""), ("Количество мест груза", ""),
    ("Наименование и характер груза", ""), ("Особые условия, режимы груза", ""),
    ("Сопроводительные документы", ""), ("Способ погрузки в ТС", ""),
    ("Дополнительные условия Заказа-наряда (при наличии)", "")]))
body.append(section(7, "Транспортное средство", [
    ("Авто, тягач (марка, модель)", ""), ("Полуприцеп", ""),
    ("Гос. рег. номер ТС", ""), ("Грузоподъёмность, длина, иное", "")]))
body.append(section(8, "Водитель фрахтуемого ТС (справочно)", [
    ("ФИО", ""), ("Паспорт / водительское удостоверение", ""), ("Телефон", "")]))

# --- 5. условия 9-14 в две колонки (отдельный раздел документа)
FTR = '<w:footerReference w:type="default" r:id="rIdFooter"/>'
PG = '<w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="850" w:right="850" w:bottom="850" w:left="850" w:header="400" w:footer="400" w:gutter="0"/>'
def sect_break(cols):
    return f'<w:p><w:pPr><w:spacing w:before="0" w:after="0"/><w:sectPr>{FTR}<w:type w:val="continuous"/>{PG}<w:cols w:num="{cols}" w:space="340"/></w:sectPr></w:pPr></w:p>'

body.append(para(run("УСЛОВИЯ ДОГОВОРА", 18, True, NAVY, spacing=30), before=60, after=80, keep=True,
                 extra=f'<w:pBdr><w:bottom w:val="single" w:sz="12" w:space="2" w:color="{BLUE}"/></w:pBdr>'))
body.append(sect_break(1))
for t in legal:
    if re.match(r'^12\.\d\.', t) and len(t) < 60:
        body.append(para(run(t, 14, True, BLUE), before=40, after=10, keep=True, line=228))
    elif re.match(r'^\d{1,2}\.\D', t) and len(t) < 60:
        m = re.match(r'^(\d{1,2})\.\s*(.*)$', t)
        body.append(para(run(f"{m.group(1)}. {m.group(2)}", 15, True, NAVY), before=100, after=30, keep=True, line=228,
                         extra=f'<w:pBdr><w:left w:val="single" w:sz="24" w:space="4" w:color="{BLUE}"/></w:pBdr>'))
    elif t.startswith('14.'):
        body.append(para(run(t, 13, True, NAVY), "both", before=100, after=20, line=228,
                         extra=f'<w:pBdr><w:left w:val="single" w:sz="24" w:space="4" w:color="{BLUE}"/></w:pBdr>'))
    else:
        body.append(para(run(t, 14), "both", after=20, line=228))
body.append(sect_break(2))

# --- 6. реквизиты и подписи
vl = ["ООО «Восточная Логистика»",
      "Юр. адрес: 664040, Иркутская обл., г. Иркутск, ул. Павла Красильникова, 172, кв. 59",
      "Почт. адрес: 664040, Иркутская обл., г. Иркутск, ул. Павла Красильникова, 172",
      "ИНН 3812166710 · КПП 381201001 · ОГРН 1253800008087",
      "р/с 40702810323080005142", "к/с 30101810600000000774",
      "ФИЛИАЛ \"НОВОСИБИРСКИЙ\" АО \"АЛЬФА-БАНК\", БИК 045004774",
      "Vostok.logist@list.ru · +7 (924) 990-90-19"]
cl = ["Наименование: ________________________________", "Юр. адрес: ___________________________________",
      "Почт. адрес: _________________________________", "ИНН / КПП / ОГРН: ____________________________",
      "р/с: _________________________________________", "к/с: _________________________________________",
      "Банк, БИК: ___________________________________", "Эл. почта, тел.: ______________________________"]
hw = W // 2 - 100
def party(title, lines):
    return (para(run(title, 18, True, "FFFFFF"), after=0) , "".join(para(run(l, 15), after=20) for l in lines))
sign = (para("", before=300) + para(run("______________________ / ____________________", 17)) +
        para(run("подпись                                          ФИО", 13, color=GRAY)) +
        para(run("М.П.", 15, True, LINE), before=120))
h1, b1 = party("15. ФРАХТОВЩИК-ИСПОЛНИТЕЛЬ", vl)
h2, b2 = party("16. ЗАКАЗЧИК", cl)
cols = [hw, W - 2 * hw, hw]
body.append(para("", before=200))
box = bdr(["left", "right", "bottom"], LINE, 4)
side = bdr(["left", "right"], LINE, 4)
body.append(table([
    row([cell(h1, hw, NAVY), cell("", cols[1]), cell(h2, hw, NAVY)], 360),
    row([cell(b1, hw, valign="top", borders=side), cell("", cols[1]), cell(b2, hw, valign="top", borders=side)]),
    row([cell(sign, hw, valign="top", borders=box), cell("", cols[1]), cell(sign, hw, valign="top", borders=box)]),
], cols, pad=140))

sect = f'<w:sectPr>{FTR}<w:type w:val="continuous"/>{PG}<w:cols w:space="340"/></w:sectPr>'
NS = ('xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
      'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"')
document = f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document {NS}><w:body>{"".join(body)}{sect}</w:body></w:document>'

FR = f'<w:rPr><w:sz w:val="14"/><w:szCs w:val="14"/><w:color w:val="{GRAY}"/></w:rPr>'
fld = lambda code: (f'<w:r>{FR}<w:fldChar w:fldCharType="begin"/></w:r><w:r>{FR}<w:instrText xml:space="preserve"> {code} </w:instrText></w:r>'
                    f'<w:r>{FR}<w:fldChar w:fldCharType="separate"/></w:r>{run("1", 14, color=GRAY)}<w:r>{FR}<w:fldChar w:fldCharType="end"/></w:r>')
footer = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:ftr {NS}>'
          + para(run("ВОСТОЧНАЯ ЛОГИСТИКА", 14, True, BLUE, spacing=20) +
                 run("   ·   Vostok.logist@list.ru   ·   +7 (924) 990-90-19   ·   стр. ", 14, color=GRAY)
                 + fld("PAGE") + run(" из ", 14, color=GRAY) + fld("NUMPAGES"), "center")
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

with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
    z.writestr("[Content_Types].xml", ct)
    z.writestr("_rels/.rels", rels)
    z.writestr("word/document.xml", document)
    z.writestr("word/styles.xml", styles)
    z.writestr("word/footer1.xml", footer)
    z.writestr("word/_rels/document.xml.rels", drels)
print("ok", len(legal))
