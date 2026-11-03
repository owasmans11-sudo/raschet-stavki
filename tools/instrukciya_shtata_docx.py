import re, sys, zipfile, shutil
from xml.sax.saxutils import escape

TPL = sys.argv[1]
OUT = sys.argv[2]

BLUE, DARK, GRAY, LIGHT, LINE, INK = '1E6FE0', '0B4AA8', '6B6B6B', 'EAF2FE', 'A9C8F5', '1F1F1F'


def run(t, b=False, color=INK, sz=20, caps=False):
    rpr = '<w:rFonts w:ascii="Arial" w:hAnsi="Arial" w:cs="Arial"/>' + ('<w:b/>' if b else '') + \
          ('<w:caps/>' if caps else '') + f'<w:color w:val="{color}"/><w:sz w:val="{sz}"/><w:szCs w:val="{sz}"/>'
    return f'<w:r><w:rPr>{rpr}</w:rPr><w:t xml:space="preserve">{escape(t)}</w:t></w:r>'


def para(runs, jc='left', before=0, after=80, ind=None, shd=None, keep=False, border=None):
    ppr = ''
    if keep:
        ppr += '<w:keepNext/>'
    if border:
        ppr += f'<w:pBdr><w:bottom w:val="single" w:sz="{border}" w:space="1" w:color="{BLUE}"/></w:pBdr>'
    if shd:
        ppr += f'<w:shd w:val="clear" w:color="auto" w:fill="{shd}"/>'
    ppr += f'<w:spacing w:before="{before}" w:after="{after}" w:line="264" w:lineRule="auto"/>'
    if ind:
        ppr += f'<w:ind w:left="{ind[0]}" w:hanging="{ind[1]}"/>'
    ppr += f'<w:jc w:val="{jc}"/>'
    if not runs.startswith('<w:r>'):
        runs = run(runs)
    return f'<w:p><w:pPr>{ppr}</w:pPr>{runs}</w:p>'


def section(n, title):
    return para(run(f'{n}. {title}', b=True, color='FFFFFF', sz=21, caps=True),
                before=240, after=120, shd=BLUE, keep=True)


def numbered(items):
    return ''.join(para(run(f'{i}.  ', b=True, color=BLUE) + rich(t), ind=(400, 400), after=60)
                   for i, t in enumerate(items, 1))


def checks(items):
    return ''.join(para(run('☐  ', color=BLUE, sz=22) + rich(t), ind=(400, 400), after=60, keep=True) for t in items)


def rich(t, sz=20, color=INK):
    # **жирный** внутри строки
    out = ''
    for k, part in enumerate(re.split(r'\*\*', t)):
        if part:
            out += run(part, b=bool(k % 2), color=color, sz=sz)
    return out


def cell(content, w, fill=None, valign='center', span=1):
    tcpr = f'<w:tcW w:w="{w}" w:type="dxa"/>' + (f'<w:gridSpan w:val="{span}"/>' if span > 1 else '') + \
           (f'<w:shd w:val="clear" w:color="auto" w:fill="{fill}"/>' if fill else '') + f'<w:vAlign w:val="{valign}"/>'
    return f'<w:tc><w:tcPr>{tcpr}</w:tcPr>{content}</w:tc>'


def cp(t, b=False, color=INK, sz=19, jc='left', keep=False):
    return para(rich(t, sz=sz, color=color) if not b else run(t, b=True, color=color, sz=sz), jc=jc, after=0, keep=keep)


def table(widths, header, rows, border=LINE, inside=True):
    total = sum(widths)
    bd = ''.join(f'<w:{s} w:val="single" w:sz="4" w:space="0" w:color="{border}"/>'
                 for s in (['top', 'left', 'bottom', 'right'] + (['insideH', 'insideV'] if inside else [])))
    x = f'<w:tbl><w:tblPr><w:tblW w:w="{total}" w:type="dxa"/><w:tblBorders>{bd}</w:tblBorders>' \
        f'<w:tblLayout w:type="fixed"/><w:tblCellMar><w:top w:w="70" w:type="dxa"/><w:left w:w="110" w:type="dxa"/>' \
        f'<w:bottom w:w="70" w:type="dxa"/><w:right w:w="110" w:type="dxa"/></w:tblCellMar></w:tblPr><w:tblGrid>' + \
        ''.join(f'<w:gridCol w:w="{w}"/>' for w in widths) + '</w:tblGrid>'
    if header:
        x += '<w:tr><w:trPr><w:cantSplit/><w:tblHeader/></w:trPr>' + \
             ''.join(cell(cp(h, b=True, color='FFFFFF', sz=18), w, fill=BLUE) for h, w in zip(header, widths)) + '</w:tr>'
    for i, r in enumerate(rows):
        fill = LIGHT if i % 2 == 0 else None
        x += '<w:tr><w:trPr><w:cantSplit/></w:trPr>' + ''.join(
            c if c.startswith('<w:tc>') else cell(cp(c, b=(j == 0), color=DARK if j == 0 else INK), w, fill=fill)
            for j, (c, w) in enumerate(zip(r, widths))) + '</w:tr>'
    return x + '</w:tbl>'


def gap(after=60):
    return para('', after=after)


W = 10206
body = ''
# заголовок документа
body += para(run('ИНСТРУКЦИЯ ДЛЯ ШТАТА', b=True, color=DARK, sz=30), jc='center', before=160, after=40)
body += para(run('Путь рейса и документы · редакция от 26.10.2026', color=DARK, sz=20), jc='center', after=200)
body += para(rich('У каждого участка рейса есть один ответственный. **Счёт-УПД делается в день выгрузки в любом случае. '
                  'Встать у клиента на оплату можно только с полным комплектом документов.**'), after=120)

# 1
body += section(1, 'Кто за что отвечает')
body += table([2300, 1900, 3906, 2100], ['Кто', 'Участок', 'Что делает', 'Кому передаёт'], [
    ['Логисты: Ильяс, Артём, Оля, Александр, Таня', 'Поиск заявок, плечо МО → склад',
     'Ищут заявки, ставят машину, оформляют договоры-заявки с клиентом и перевозчиком, ведут рейс до склада, '
     'в «Умной логистике» первую заявку сразу делают сложной и добавляют в неё ВостСибТранс',
     'Груз — складу; сложную заявку вместе с её номером — Константину'],
    ['ВостСибТранс', 'Склад → межгород', 'Везёт груз фурой со склада Москвы/МО до склада в городе назначения',
     'Груз — Константину'],
    ['Константин (Костя)', 'Склад → клиент', 'Развозит груз клиенту, забирает документы: фото погрузки, фото выгрузки, ТН; '
     'доделывает заключительное плечо в «Умной логистике»; в день выгрузки сообщает о ней Анастасии; '
     'не смог забрать документы сразу — ставит пометку, где они находятся',
     'В день выгрузки — сообщение и документы Анастасии'],
    ['Анастасия, менеджер', 'Документы, счёт-УПД', 'Собирает и проверяет комплект документов по каждому рейсу, '
     'в день выгрузки создаёт счёт-УПД',
     'С полным комплектом — встаёт у клиента на оплату и обозначает ориентировочный срок оплаты'],
    ['Люба', 'ЭДО — весь путь рейса', 'Отвечает за ЭДО по рейсу с самого начала до самого конца', '—'],
])

# 2
body += section(2, 'Ведение в «Умной логистике»')
body += para(rich('Каждый логист сам заполняет и ведёт свою работу в «Умной логистике». Весь рейс ведётся одной '
                  '**сложной заявкой**:'), after=100)
body += table([4600, 1700, 3906], ['Шаг', 'Кто', 'Когда'], [
    ['Первая заявка (МО → склад): оформить как сложную и сразу добавить ВостСибТранс', 'Логист',
     'Сразу, при заполнении первой заявки'],
    ['Межгород: внести данные ВостСибТранса', 'Логист', 'Когда ВостСибТранс выставит счёт с весом и объёмом'],
    ['Передать сложную заявку вместе с её номером', 'Логист', 'После этого'],
    ['Заключительное плечо: склад → клиент', 'Константин', 'Доделывает в той же сложной заявке'],
])

# 3 — схема
body += section(3, 'Путь рейса')
steps = [('ЛОГИСТЫ', 'Поиск заявок на АТИ, МО → склад Москвы'),
         ('ВОСТСИБТРАНС', 'Межгород фурой до склада в городе'),
         ('КОНСТАНТИН', 'Склад → клиент, забирает документы'),
         ('АНАСТАСИЯ', 'Счёт-УПД в день выгрузки, проверяет комплект')]
sw, aw = 2250, 402
widths, cells = [], []
for k, (name, txt) in enumerate(steps):
    widths.append(sw)
    cells.append(cell(cp(name, b=True, color=BLUE, sz=18, keep=True) + cp(txt, sz=17, keep=True), sw, fill=LIGHT, valign='top'))
    if k < 3:
        widths.append(aw)
        cells.append(cell(cp('→', b=True, color=BLUE, sz=28, jc='center', keep=True), aw))
flow = f'<w:tbl><w:tblPr><w:tblW w:w="{sum(widths)}" w:type="dxa"/><w:tblLayout w:type="fixed"/>' \
       f'<w:tblCellMar><w:top w:w="90" w:type="dxa"/><w:left w:w="110" w:type="dxa"/><w:bottom w:w="90" w:type="dxa"/>' \
       f'<w:right w:w="110" w:type="dxa"/></w:tblCellMar></w:tblPr><w:tblGrid>' + \
       ''.join(f'<w:gridCol w:w="{w}"/>' for w in widths) + '</w:tblGrid><w:tr><w:trPr><w:cantSplit/></w:trPr>' + \
       ''.join(cells) + '</w:tr></w:tbl>'
body += flow
body += para(rich('**Люба — ЭДО** с самого начала рейса до самого конца', color=DARK), shd=LIGHT, before=100, after=0, keep=True)
body += para(rich('**Счёт-УПД** — в день выгрузки в любом случае, с документами или без', color=DARK), shd=LIGHT, before=60, after=0, keep=True)
body += para(run('Комплект полный?', b=True, color=DARK, sz=20), jc='right', before=120, after=60, keep=True)
body += table([5103, 5103], None, [
    [cell(cp('ДА', b=True, color='FFFFFF', sz=18) + cp('Встаём у клиента на оплату, ориентировочный срок оплаты', color='FFFFFF'),
          5103, fill=BLUE),
     cell(cp('НЕТ', b=True, color=BLUE, sz=18) + cp('Константин дособирает; пометка, где документы'), 5103, fill=LIGHT)],
], border='FFFFFF')

# 4
body += section(4, 'Полный комплект документов')
body += para('По каждому рейсу нужны три вещи. Нет хотя бы одной — комплект неполный.', after=80, keep=True)
body += checks(['Фото с погрузки', 'Фото с выгрузки', 'ТН (транспортная накладная)'])
body += para('В день выгрузки Константин сообщает Анастасии о выгрузке и передаёт все три документа. Если забрать их сразу не получается (выгрузка в другом городе, водитель не смог '
             'привезти сразу), Константин ставит пометку, где находятся документы. На каждом файле или в подписи — '
             'номер заявки, чтобы было понятно, к какому рейсу он относится.', before=60, after=80)

# 5
body += section(5, 'Счёт-УПД и оплата')
body += para(rich('**Счёт-УПД — в день выгрузки, в любом случае**, даже если документов ещё нет. **Встать у клиента на оплату — '
                  'только с полным комплектом** (фото погрузки, фото выгрузки, ТН).'), after=80)
body += numbered(['В день выгрузки Константин сообщает Анастасии о выгрузке и передаёт документы.',
                  'Забрать документы сразу не получается — Константин ставит пометку, где они находятся.',
                  'Анастасия в день выгрузки создаёт счёт-УПД — с документами или без.',
                  'Проверяет комплект по списку выше. Чего-то не хватает — сообщает Константину, чего именно нет.',
                  'Комплект полный — встаёт у клиента на оплату и обозначает ориентировочный срок оплаты. Договоры разные, '
                  'условия оплаты тоже — срок смотрит по условиям своего договора.'])

# ознакомление
body += '<w:p><w:r><w:br w:type="page"/></w:r></w:p>'
body += para(run('С инструкцией ознакомлены', b=True, color=DARK, sz=22), before=120, after=120, keep=True, border=12)
names = ['Ильяс', 'Артём', 'Оля', 'Александр', 'Таня', 'Константин', 'Анастасия', 'Люба']
body += table([3400, 3000, 1900, 1906], ['Сотрудник', 'Должность', 'Дата', 'Подпись'],
              [[n, {'Анастасия': 'Менеджер', 'Константин': '', 'Люба': ''}.get(n, 'Логист'), '', '']
               for n in names] + [['', '', '', '']])
body += para(rich('Утверждаю: руководитель ООО «Восточная Логистика»  ____________________ / ____________________ /'),
             before=360, after=0)

# собрать
src = zipfile.ZipFile(TPL)
doc = src.read('word/document.xml').decode('utf-8')
i = doc.index('<w:body>') + len('<w:body>')
# оставляем фирменную шапку (первая таблица) и синюю линию под ней
head_end = doc.index('</w:tbl>', i) + len('</w:tbl>')
line_end = doc.index('</w:p>', head_end) + len('</w:p>')
sect = doc.rindex('<w:sectPr')
new = doc[:line_end] + body + doc[sect:]
with zipfile.ZipFile(OUT, 'w', zipfile.ZIP_DEFLATED) as z:
    for item in src.infolist():
        data = new.encode('utf-8') if item.filename == 'word/document.xml' else src.read(item.filename)
        z.writestr(item, data)
print('ok', OUT)
