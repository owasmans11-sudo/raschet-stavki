import zipfile, re, sys
from xml.sax.saxutils import escape

SRC = sys.argv[1]   # старый шаблон (для юридического текста)
OUT = sys.argv[2]

BLUE = "1E6FE0"      # яркий фирменный синий
DARK = "0B4AA8"      # тёмно-синий для акцентов
LIGHT = "EAF2FE"     # светлая заливка подписей полей
LINE = "A9C8F5"      # линии таблиц
VAL = "F6F9FE"       # заливка полей для заполнения (вместо линий)
GRAY = "6B6B6B"
FONT = "Arial"

# --- юридический текст разделов 9-14 берём из старого шаблона слово в слово
x = zipfile.ZipFile(SRC).read("word/document.xml").decode("utf-8")
ps = [''.join(re.findall(r'<w:t[^>]*>([^<]*)', p)) for p in re.findall(r'<w:p[ >].*?</w:p>', x, re.S)]
ps = [re.sub(r'&amp;', '&', p) for p in ps]
i9 = next(i for i, t in enumerate(ps) if t.strip().startswith('9.'))
i15 = next(i for i, t in enumerate(ps) if t.strip().startswith('15.'))
legal = [t.strip() for t in ps[i9:i15] if t.strip()]

def run(text, sz=18, bold=False, color=None, italic=False):
    rpr = f'<w:rFonts w:ascii="{FONT}" w:hAnsi="{FONT}" w:cs="{FONT}"/>'
    if bold: rpr += '<w:b/>'
    if italic: rpr += '<w:i/>'
    if color: rpr += f'<w:color w:val="{color}"/>'
    rpr += f'<w:sz w:val="{sz}"/><w:szCs w:val="{sz}"/>'
    return f'<w:r><w:rPr>{rpr}</w:rPr><w:t xml:space="preserve">{escape(text)}</w:t></w:r>'

def para(runs="", jc="left", before=0, after=0, extra="", keep=False):
    ppr = f'<w:spacing w:before="{before}" w:after="{after}" w:line="252" w:lineRule="auto"/><w:jc w:val="{jc}"/>'
    if keep: ppr = '<w:keepNext/>' + ppr
    return f'<w:p><w:pPr>{extra}{ppr}</w:pPr>{runs}</w:p>'

def borders(color=LINE, sz=4, inner=True):
    sides = ["top", "left", "bottom", "right"] + (["insideH", "insideV"] if inner else [])
    return "<w:tblBorders>" + "".join(f'<w:{s} w:val="single" w:sz="{sz}" w:space="0" w:color="{color}"/>' for s in sides) + "</w:tblBorders>"

NOB = "<w:tblBorders>" + "".join(f'<w:{s} w:val="nil"/>' for s in ["top", "left", "bottom", "right", "insideH", "insideV"]) + "</w:tblBorders>"
W = 10206  # ширина текста A4 при полях 850

def cell(content, w, fill=None, span=1, valign="center", mar=None):
    tcpr = f'<w:tcW w:w="{w}" w:type="dxa"/>'
    if span > 1: tcpr += f'<w:gridSpan w:val="{span}"/>'
    if fill: tcpr += f'<w:shd w:val="clear" w:color="auto" w:fill="{fill}"/>'
    if mar: tcpr += mar
    tcpr += f'<w:vAlign w:val="{valign}"/>'
    return f'<w:tc><w:tcPr>{tcpr}</w:tcPr>{content}</w:tc>'

def row(cells, h=None, header=False):
    trpr = '<w:cantSplit/>'
    if h: trpr += f'<w:trHeight w:val="{h}"/>'
    return f'<w:tr><w:trPr>{trpr}</w:trPr>{"".join(cells)}</w:tr>'

def table(rows, cols, bord):
    grid = "".join(f'<w:gridCol w:w="{c}"/>' for c in cols)
    mar = '<w:tblCellMar><w:top w:w="40" w:type="dxa"/><w:left w:w="100" w:type="dxa"/><w:bottom w:w="40" w:type="dxa"/><w:right w:w="100" w:type="dxa"/></w:tblCellMar>'
    return (f'<w:tbl><w:tblPr><w:tblW w:w="{sum(cols)}" w:type="dxa"/>{bord}<w:tblLayout w:type="fixed"/>{mar}</w:tblPr>'
            f'<w:tblGrid>{grid}</w:tblGrid>{"".join(rows)}</w:tbl>')

L, R = 4000, W - 4000

def section(title, fields):
    rows = [row([cell(para(run(title, 19, True, "FFFFFF"), keep=True), W, BLUE, span=2)], 320)]
    for label, value in fields:
        rows.append(row([cell(para(run(label, 17, color=DARK)), L, LIGHT),
                         cell(para(run(value, 18) if value else ""), R, VAL)], 380))
    return table(rows, [L, R], borders("FFFFFF", 16)) + para("", after=60)

body = []

# --- шапка
left = (para(run("ВОСТОЧНАЯ ЛОГИСТИКА", 34, True, BLUE)) +
        para(run("ООО «Восточная Логистика» · грузоперевозки по России", 17, color=DARK)))
right = (para(run("ИНН 3812166710 · КПП 381201001", 16, color=GRAY), "right") +
         para(run("ОГРН 1253800008087", 16, color=GRAY), "right") +
         para(run("Тел.: +7 (924) 990-90-19", 16, color=GRAY), "right") +
         para(run("Vostok.logist@list.ru", 16, color=BLUE), "right"))
body.append(table([row([cell(left, 5600, LIGHT), cell(right, W - 5600, LIGHT)], 1000)], [5600, W - 5600], NOB))
body.append(para("", after=60))

# --- заголовок
body.append(para(run("ДОГОВОР (ЗАКАЗ-НАРЯД)", 28, True, DARK), "center", before=160))
body.append(para(run("на фрахтование транспортом № ______ от «___» ______________ 20___ г.", 20, color=DARK), "center", after=160))

# --- плашка с главным
def key(label, value, fill, lc, vc):
    return para(run(label, 15, color=lc)) + para(run(value, 20, True, vc), before=40)
kw = [3700, 3300, W - 7000]
body.append(table([row([
    cell(key("Маршрут", "_____________ → _____________", LIGHT, BLUE, DARK), kw[0], LIGHT),
    cell(key("Погрузка → выгрузка", "___.___ → ___.___.20___", LIGHT, BLUE, DARK), kw[1], LIGHT),
    cell(key("Стоимость фрахтования", "__________ ₽", BLUE, "D6E6FD", "FFFFFF"), kw[2], BLUE),
], 700)], kw, borders("FFFFFF", 24)))
body.append(para("", after=100))

# --- разделы 1-8
body.append(section("1. Сведения о Заказчике", [
    ("Наименование / ФИО", ""), ("ИНН, ОГРН / КПП, паспортные данные", ""),
    ("ФИО уполномоченного лица Заказчика (если юр. л.)", ""),
    ("Основания полномочий подписанта Заказчика (если юр. л.)", ""),
    ("Адрес электронной почты и № телефонов (в т.ч. мессенджеров)", "")]))
body.append(section("2. Сведения о Фрахтовщике", [
    ("Менеджер Фрахтовщика, принявший заказ", ""), ("Телефон менеджера", ""),
    ("Адрес электронной почты и № факсов и телефонов (в т.ч. мессенджеров)", "Vostok.logist@list.ru"),
    ("Почтовый адрес для обмена оригиналами документов", "664040, Иркутская обл., г. Иркутск, ул. Павла Красильникова, д. 172")]))
body.append(section("3. Погрузка", [
    ("Адрес подачи ТС Заказчику", ""), ("Дата и время подачи ТС Заказчику (начало срока фрахтования)", ""),
    ("Контактное лицо в месте подачи ТС Заказчику", "")]))
body.append(section("4. Выгрузка", [
    ("Адрес места окончания фрахтования", ""), ("Дата и время окончания срока фрахтования", ""),
    ("Контактное лицо в месте окончания фрахтования", "")]))
body.append(section("5. Фрахт", [
    ("Стоимость фрахтования", ""),
    ("Сроки и иные условия оплаты за фрахтование (аванс, постоплата, наличные, безнал, р/с, карта и т.п.)", "")]))
body.append(section("6. Груз", [
    ("Габариты груза (вес, объём, размеры)", ""), ("Количество мест груза", ""),
    ("Наименование и характер груза", ""), ("Сведения об особых условиях, режимах груза", ""),
    ("Состав и наличие сопроводительных документов", ""), ("Способ погрузки в ТС", ""),
    ("Дополнительные условия Заказа-наряда (при наличии)", "")]))
body.append(section("7. Сведения о ТС", [
    ("Авто, тягач (марка, модель)", ""), ("Полуприцеп", ""), ("Гос. рег. номер ТС", ""),
    ("Грузоподъёмность, длина, иное", "")]))
body.append(section("8. Сведения о водителе фрахтуемого ТС (справочно)", [
    ("ФИО", ""), ("Паспорт / водительское удостоверение", ""), ("Телефон", "")]))

# --- разделы 9-14: текст без изменений, только оформление
BAR = f'<w:shd w:val="clear" w:color="auto" w:fill="{BLUE}"/><w:ind w:left="60" w:right="60"/>'
for t in legal:
    if re.match(r'^12\.\d\.', t) and len(t) < 60:   # подзаголовок 12.2 / 12.3
        body.append(para(run(t, 17, True, DARK), before=60, after=20, keep=True))
    elif re.match(r'^\d{1,2}\.\D', t) and len(t) < 60:   # заголовок раздела
        m = re.match(r'^(\d{1,2})\.\s*(.*)$', t)
        body.append(para(run(f"{m.group(1)}. {m.group(2)}", 19, True, "FFFFFF"), before=140, after=60, keep=True, extra=BAR))
    elif t.startswith('14.'):
        body.append(para(run(t, 16, True, DARK), "both", before=140, after=40))
    else:
        body.append(para(run(t, 15), "both", after=40))

# --- реквизиты и подписи
def req_ul(lines):
    return "".join(para(run(l, 16)) for l in lines)
vl = ["ООО «Восточная Логистика»",
      "Юр. адрес: 664040, Иркутская обл., г. Иркутск, ул. Павла Красильникова, 172, кв. 59",
      "Почт. адрес: 664040, Иркутская обл., г. Иркутск, ул. Павла Красильникова, 172",
      "ИНН 3812166710 · КПП 381201001", "ОГРН 1253800008087",
      "р/с 40702810323080005142", "к/с 30101810600000000774",
      "в ФИЛИАЛ \"НОВОСИБИРСКИЙ\" АО \"АЛЬФА-БАНК\", БИК 045004774",
      "Эл. почта: Vostok.logist@list.ru", "Тел.: +7 (924) 990-90-19"]
cl = ["Наименование: ____________________________", "Юр. адрес: _______________________________",
      "Почт. адрес: _____________________________", "ИНН / КПП: _______________________________",
      "ОГРН: ___________________________________", "р/с: _____________________________________",
      "Банк: ___________________________________", "к/с: ______________________ БИК: __________",
      "Эл. почта: ______________________________", "Тел.: ____________________________________"]
sign = (para("", before=200) + para(run("_______________ / _______________ /", 18), before=200) +
        para(run("подпись                   ФИО", 14, color=GRAY)) + para(run("М.П.", 16, color=GRAY), before=120))
hw = W // 2
hdr = lambda t: para(run(t, 19, True, "FFFFFF"))
body.append(para("", after=80))
body.append(table([
    row([cell(hdr("15. Фрахтовщик-Исполнитель"), hw, BLUE), cell(hdr("16. Заказчик"), W - hw, BLUE)], 320),
    row([cell(req_ul(vl), hw, VAL, valign="top"), cell(req_ul(cl), W - hw, VAL, valign="top")]),
    row([cell(sign, hw, VAL, valign="top"), cell(sign, W - hw, VAL, valign="top")]),
], [hw, W - hw], borders("FFFFFF", 16)))

sect = ('<w:sectPr><w:footerReference w:type="default" r:id="rIdFooter"/>'
        '<w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="850" w:right="850" w:bottom="850" w:left="850" w:header="400" w:footer="400" w:gutter="0"/></w:sectPr>')

NS = ('xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
      'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"')
document = f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document {NS}><w:body>{"".join(body)}{sect}</w:body></w:document>'

FR = f'<w:rPr><w:sz w:val="14"/><w:szCs w:val="14"/><w:color w:val="{GRAY}"/></w:rPr>'
fld = lambda code: (f'<w:r>{FR}<w:fldChar w:fldCharType="begin"/></w:r><w:r>{FR}<w:instrText xml:space="preserve"> {code} </w:instrText></w:r>'
                    f'<w:r>{FR}<w:fldChar w:fldCharType="separate"/></w:r>{run("1", 14, color=GRAY)}<w:r>{FR}<w:fldChar w:fldCharType="end"/></w:r>')
footer = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:ftr {NS}>'
          + para(run("ООО «Восточная Логистика» · Vostok.logist@list.ru · +7 (924) 990-90-19        Стр. ", 14, color=GRAY)
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
print("ok, абзацев условий:", len(legal))
