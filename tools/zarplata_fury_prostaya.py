"""Простая версия «Зарплата с прибыли по фурам»: меньше столбцов, расчёт тот же.
Запуск: python tools/zarplata_fury_prostaya.py <выход.xlsx> [--example]"""
import sys
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.formatting.rule import FormulaRule
from openpyxl.workbook.defined_name import DefinedName
from openpyxl.utils import get_column_letter as L
import datetime as dt

OUT = sys.argv[1]
NF, NZ = 100, 400  # строк под фуры и заявки

BLUE, DARK, PALE, BORDER, GREY = "1E6FE0", "0B4AA8", "EAF2FE", "A9C8F5", "F2F2F2"
F = lambda **k: Font(name="Arial", size=k.pop("size", 10), **k)
fill = lambda c: PatternFill("solid", fgColor=c)
thin = Side(style="thin", color=BORDER)
box = Border(left=thin, right=thin, top=thin, bottom=thin)
MONEY, KG, PCT, DATE, R2 = '#,##0', '#,##0', '0.0%', 'DD.MM.YYYY', '#,##0.00'

wb = Workbook()
dn = lambda name, ref: wb.defined_names.__setitem__(name, DefinedName(name, attr_text=ref))

# ---------- Настройки ----------
st = wb.active
st.title = "Настройки"
st["A1"] = "Настройки расчёта"; st["A1"].font = F(size=14, bold=True, color=DARK)
for i, (t, v) in enumerate([("Процент зарплаты логиста от остатка прибыли", 0.20),
                            ("Налог на прибыль (для ОСНО)", 0.25)], start=3):
    st.cell(i, 1, t).font = F(); c = st.cell(i, 2, v); c.number_format = PCT; c.font = F(bold=True); c.border = box
dn("ZP_PCT", "Настройки!$B$3"); dn("NNP", "Настройки!$B$4")

st["A7"] = "Форма оплаты"; st["B7"] = "Коэффициент"; st["C7"] = "Что значит"
for i, (a, b, c) in enumerate([("с НДС", 1.22, "НДС 22%"), ("без НДС", 1.06, "УСН 6% с дохода"),
                               ("нал", 1, "наличные — налог 0")], start=8):
    st.cell(i, 1, a); st.cell(i, 2, b).number_format = "0.00"; st.cell(i, 3, c)
dn("FORMS", "Настройки!$A$8:$A$10"); dn("FORMS_T", "Настройки!$A$8:$B$10")

st["A13"] = "Компания"; st["B13"] = "Режим налога"
for i, (a, b) in enumerate([("ООО «Восточная Логистика»", "ОСНО"), ("ИП Шерстов", "УСН"),
                            ("ООО «ТК МВЛ»", "ОСНО")], start=14):
    st.cell(i, 1, a); st.cell(i, 2, b)
dn("COMPS", "Настройки!$A$14:$A$19"); dn("COMPS_T", "Настройки!$A$14:$B$19")

st["A22"] = "Логисты"
for i, n in enumerate(["Александр", "Артём", "Таня", "Ильяс", "Оля", "Андрей", "Илья"], start=23):
    st.cell(i, 1, n)
dn("LOGISTS", "Настройки!$A$23:$A$35")

MONTHS = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь", "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"]
st["E22"] = "Месяцы"
for i, m in enumerate(MONTHS, start=23):
    st.cell(i, 5, m)
dn("MONTHS", "Настройки!$E$23:$E$34")

for cell in ("A7", "B7", "C7", "A13", "B13", "A22", "E22"):
    st[cell].font = F(bold=True, color="FFFFFF"); st[cell].fill = fill(BLUE)
for r in list(range(8, 11)) + list(range(14, 20)) + list(range(23, 36)):
    for c in ((1, 2, 3) if r < 11 else (1, 2) if r < 22 else (1,)):
        st.cell(r, c).border = box
        if st.cell(r, c).font.name != "Arial":
            st.cell(r, c).font = F()
st["A37"] = "Новые компании и логистов дописывай в пустые строки своих списков — они сразу появятся в выпадающих списках."
st["A37"].font = F(italic=True, color="666666")
d = DataValidation(type="list", formula1='"ОСНО,УСН"', allow_blank=True); st.add_data_validation(d); d.add("B14:B19")
st.column_dimensions["A"].width = 46; st.column_dimensions["B"].width = 14; st.column_dimensions["C"].width = 22
st.column_dimensions["E"].width = 12

# ---------- столбцы ----------
# (заголовок, ширина, формат, формула или None — вписываешь сам)
fcols = [
    ("№ фуры", 11, None, None),                                                         # A
    ("Дата", 11, DATE, None),                                                           # B
    ("Маршрут", 28, None, None),                                                        # C
    ("Фура, ₽", 12, MONEY, None),                                                       # D
    ("Склады (погрузка + приёмка), ₽", 13, MONEY, None),                                # E
    ("Прочие (кран и т.п.), ₽", 12, MONEY, None),                                       # F
    ("Из них с НДС, ₽", 11, MONEY, None),                                               # G
    ("Вес, кг", 10, KG, 'IF(A{r}="","",SUMIFS(Заявки!$G:$G,Заявки!$A:$A,A{r}))'),       # H
    ("Выручка, ₽", 12, MONEY, 'IF(A{r}="","",SUMIFS(Заявки!$F:$F,Заявки!$A:$A,A{r}))'),  # I
    ("ПРИБЫЛЬ ФУРЫ, ₽", 13, MONEY, 'IF(A{r}="","",SUMIFS(Заявки!$N:$N,Заявки!$A:$A,A{r}))'),  # J
    ("Прибыль на 1 кг, ₽", 10, R2, 'IF(A{r}="","",IFERROR(J{r}/H{r},0))'),              # K
    ("% от выручки", 9, PCT, 'IF(A{r}="","",IFERROR(J{r}/I{r},0))'),                    # L
    ("Зп начислено, ₽", 11, MONEY, 'IF(A{r}="","",SUMIFS(Заявки!$AA:$AA,Заявки!$A:$A,A{r}))'),  # M
    ("Зп ждёт оплаты, ₽", 11, MONEY, 'IF(A{r}="","",SUMIFS(Заявки!$AB:$AB,Заявки!$A:$A,A{r}))'),  # N
]
fhelp = [  # с колонки P, свёрнуты
    ("Расход на 1 кг, ₽", 11, R2, 'IF(A{r}="","",IFERROR((N(D{r})+N(E{r})+N(F{r}))/H{r},0))'),   # P
    ("НДС на 1 кг, ₽", 11, R2, 'IF(A{r}="","",IFERROR((N(G{r})-N(G{r})/1.22)/H{r},0))'),          # Q
]

OSNO = 'T{r}="ОСНО"'
zcols = [
    ("№ фуры", 11, None, None),                                   # A
    ("Клиент", 26, None, None),                                   # B
    ("Логист", 12, None, None),                                   # C
    ("Компания", 24, None, None),                                 # D
    ("Оплата клиента", 10, None, None),                           # E
    ("Сумма клиента, ₽", 12, MONEY, None),                        # F
    ("Вес, кг", 9, KG, None),                                     # G
    ("Забор (водитель до склада), ₽", 12, MONEY, None),           # H
    ("Доставка (развоз до получателя), ₽", 12, MONEY, None),      # I
    ("Прочие (СДЭК, кран), ₽", 11, MONEY, None),                  # J
    ("Из них с НДС, ₽", 11, MONEY, None),                         # K
    ("Оплачено клиентом, ₽", 12, MONEY, None),                    # L
    ("Дата полной оплаты", 11, DATE, None),                       # M
    ("ПРИБЫЛЬ, ₽", 12, MONEY, 'IF(F{r}="","",X{r}-Y{r})'),        # N
    ("Прибыль на 1 кг, ₽", 10, R2, 'IF(F{r}="","",IFERROR(N{r}/G{r},0))'),   # O
    ("% от выручки", 9, PCT, 'IF(F{r}="","",IFERROR(N{r}/F{r},0))'),         # P
    ("Зп логиста, ₽", 11, MONEY, 'IF(F{r}="","",MAX(N{r},0)*ZP_PCT)'),       # Q
    ("Пометка", 24, None,
     'IF(F{r}="","",IF(A{r}="","нет № фуры",IF(ISNA(MATCH(A{r},Фуры!$A:$A,0)),"фуры нет на листе Фуры",'
     'IF(N(G{r})=0,"нет веса",IF(S{r}="","нет оплаты клиента (форма)",IF(T{r}="","нет компании",'
     'IF(Z{r}="да",IF(M{r}="","оплачено, нет даты","зп начислена"),"ждёт оплаты, долг "&FIXED(F{r}-N(L{r}),0))))))))'),  # R
]
zhelp = [  # с колонки S, свёрнуты
    ("Кф", 6, "0.00", 'IF(F{r}="","",IFERROR(VLOOKUP(E{r},FORMS_T,2,FALSE),""))'),                  # S
    ("Режим компании", 8, None, 'IF(F{r}="","",IFERROR(VLOOKUP(D{r},COMPS_T,2,FALSE),""))'),         # T
    ("Налог с выручки, ₽", 11, MONEY, 'IF(OR(F{r}="",S{r}=""),"",F{r}-F{r}/S{r})'),                   # U
    ("Доля общих расходов фуры, ₽", 12, MONEY,
     'IF(F{r}="","",N(G{r})*IFERROR(VLOOKUP(A{r},Фуры!$A:$P,16,FALSE),0))'),                            # V
    ("НДС к вычету, ₽", 11, MONEY,
     'IF(F{r}="","",IF(AND(E{r}="с НДС",' + OSNO + '),(N(K{r})-N(K{r})/1.22)'
     '+N(G{r})*IFERROR(VLOOKUP(A{r},Фуры!$A:$Q,17,FALSE),0),0))'),                                      # W
    ("Прибыль до налога на прибыль, ₽", 12, MONEY,
     'IF(F{r}="","",F{r}-N(U{r})-N(H{r})-N(I{r})-N(J{r})-V{r}+W{r})'),                                 # X
    ("Налог на прибыль, ₽", 11, MONEY,
     'IF(F{r}="","",IF(AND(' + OSNO + ',E{r}<>"нал",X{r}>0),X{r}*NNP,0))'),                             # Y
    ("Оплачено полностью", 9, None, 'IF(F{r}="","",IF(N(L{r})>=F{r},"да","нет"))'),                    # Z
    ("Зп начислено, ₽", 11, MONEY, 'IF(F{r}="","",IF(Z{r}="да",Q{r},0))'),                             # AA
    ("Зп ждёт оплаты, ₽", 11, MONEY, 'IF(F{r}="","",Q{r}-AA{r})'),                                     # AB
]


def build(ws, cols, helpers, hcol, nrows, title, hint):
    ws["A1"] = title; ws["A1"].font = F(size=14, bold=True, color=DARK)
    ws["A2"] = hint; ws["A2"].font = F(italic=True, color="666666")
    hr = 4
    allc = [(j, c, False) for j, c in enumerate(cols, start=1)] + \
           [(j, c, True) for j, c in enumerate(helpers, start=hcol)]
    for j, (h, w, fmt, formula), helper in allc:
        c = ws.cell(hr, j, h)
        c.font = F(bold=True, color="FFFFFF" if not helper else "333333", size=9)
        c.fill = fill(GREY if helper else (BLUE if formula is None else DARK))
        c.alignment = Alignment(wrap_text=True, vertical="center", horizontal="center")
        c.border = box
        ws.column_dimensions[L(j)].width = w
    ws.row_dimensions[hr].height = 48
    for r in range(hr + 1, hr + 1 + nrows):
        for j, (h, w, fmt, formula), helper in allc:
            c = ws.cell(r, j)
            if formula:
                c.value = "=" + formula.format(r=r)
                c.fill = fill(GREY if helper else PALE)
            c.font = F(color="555555" if helper else "000000"); c.border = box
            if fmt: c.number_format = fmt
    # расчётные столбцы — свёрнутой группой справа
    ws.column_dimensions.group(L(hcol), L(hcol + len(helpers) - 1), outline_level=1, hidden=True)
    ws.cell(3, hcol, "расчёт по шагам (раскрой «+» над столбцами)").font = F(italic=True, size=8, color="888888")
    ws.freeze_panes = ws.cell(hr + 1, 3)
    ws.auto_filter.ref = f"A{hr}:{L(len(cols))}{hr + nrows}"
    return hr + 1, hr + nrows


fu = wb.create_sheet("Фуры", 0)
za = wb.create_sheet("Заявки", 1)
f1, f2 = build(fu, fcols, fhelp, 16, NF, "Фуры — расходы и прибыль по каждой фуре",
               "Синие заголовки — вписываешь сам. Тёмные — считаются сами из листа «Заявки» по № фуры.")
z1, z2 = build(za, zcols, zhelp, 19, NZ, "Заявки — прибыль и зарплата по каждой заявке",
               "Одна строка — одна заявка клиента. Зарплата начисляется, только когда клиент оплатил всю сумму.")

def dv(ws, formula, rng):
    d = DataValidation(type="list", formula1=formula, allow_blank=True); ws.add_data_validation(d); d.add(rng)

dv(za, "=FORMS", f"E{z1}:E{z2}")
dv(za, "=LOGISTS", f"C{z1}:C{z2}")
dv(za, "=COMPS", f"D{z1}:D{z2}")
dv(za, f"=Фуры!$A${f1}:$A${f2}", f"A{z1}:A{z2}")

red, green, yellow = fill("F8D7DA"), fill("D4EDDA"), fill("FFF2CC")
za.conditional_formatting.add(f"R{z1}:R{z2}", FormulaRule(formula=[f'R{z1}="зп начислена"'], fill=green))
za.conditional_formatting.add(f"R{z1}:R{z2}", FormulaRule(formula=[f'LEFT(R{z1},5)="ждёт "'], fill=red))
za.conditional_formatting.add(f"R{z1}:R{z2}", FormulaRule(formula=[f'R{z1}<>""'], fill=yellow))
za.conditional_formatting.add(f"N{z1}:N{z2}", FormulaRule(formula=[f'AND(ISNUMBER(N{z1}),N{z1}<0)'], fill=red))
fu.conditional_formatting.add(f"J{f1}:J{f2}", FormulaRule(formula=[f'AND(ISNUMBER(J{f1}),J{f1}<0)'], fill=red))
for r in range(z1, z2 + 1):
    za[f"N{r}"].font = F(bold=True)
for r in range(f1, f2 + 1):
    fu[f"J{r}"].font = F(bold=True)

# ---------- Зарплата ----------
zp = wb.create_sheet("Зарплата", 2)
zp["A1"] = "Зарплата логистов"; zp["A1"].font = F(size=14, bold=True, color=DARK)
zp["A2"] = "Месяц:"; zp["B2"] = MONTHS[dt.date.today().month - 1]
zp["A3"] = "Год:"; zp["B3"] = dt.date.today().year
for c in ("B2", "B3"):
    zp[c].font = F(bold=True); zp[c].border = box; zp[c].fill = fill("FFFFFF")
zp["C2"] = "← выбери месяц и год"; zp["C2"].font = F(italic=True, color="666666")
dv(zp, "=MONTHS", "B2")
heads = ["Логист", "Начислено за месяц, ₽", "Начислено за год, ₽", "Ждёт оплаты клиентов, ₽"]
for j, h in enumerate(heads, start=1):
    c = zp.cell(5, j, h); c.font = F(bold=True, color="FFFFFF"); c.fill = fill(BLUE); c.border = box
    c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    zp.column_dimensions[L(j)].width = 16 if j == 1 else 18
zp.row_dimensions[5].height = 32
Y, C, K = (f"Заявки!${x}${z1}:${x}${z2}" for x in ("AA", "C", "M"))
MSTART = 'DATE($B$3,MATCH($B$2,MONTHS,0),1)'
NL = 13
for i in range(NL):
    r = 6 + i
    zp.cell(r, 1, f'=IF(Настройки!A{23 + i}="","",Настройки!A{23 + i})')
    zp.cell(r, 2, f'=IF($A{r}="","",IFERROR(SUMIFS({Y},{C},$A{r},{K},">="&{MSTART},{K},"<"&EDATE({MSTART},1)),0))')
    zp.cell(r, 3, f'=IF($A{r}="","",SUMIFS({Y},{C},$A{r},{K},">="&DATE($B$3,1,1),{K},"<"&DATE($B$3+1,1,1)))')
    zp.cell(r, 4, f'=IF($A{r}="","",SUMIFS(Заявки!$AB${z1}:$AB${z2},{C},$A{r}))')
    for j in range(1, 5):
        c = zp.cell(r, j); c.border = box; c.font = F(bold=(j in (1, 2)))
        if j > 1: c.number_format = MONEY
tr = 6 + NL
zp.cell(tr, 1, "ИТОГО")
for j in range(2, 5):
    zp.cell(tr, j, f"=SUM({L(j)}6:{L(j)}{tr - 1})").number_format = MONEY
for j in range(1, 5):
    c = zp.cell(tr, j); c.font = F(bold=True); c.fill = fill(PALE); c.border = box
zp.cell(tr + 2, 1, "Зарплата попадает в месяц «Даты полной оплаты» — только когда клиент оплатил всю сумму.").font = F(italic=True, color="666666")

# ---------- Как считается ----------
hw = wb.create_sheet("Как считается")
lines = [
    "Как считается",
    "",
    "Прибыль заявки = Сумма клиента − налог − расходы заявки − доля расходов фуры − налог на прибыль.",
    "",
    "• Налог с суммы клиента: с НДС — 22% (сумма − сумма/1,22); без НДС — 6% (УСН); нал — 0.",
    "• Расходы заявки = забор (водитель до склада) + доставка (развоз) + прочие (СДЭК, кран).",
    "• Доля расходов фуры: (фура + склады + прочие) делим на вес всех заявок фуры → расход на 1 кг × вес заявки.",
    "• НДС перевозчиков («Из них с НДС») возвращается в плюс, только если клиент платит с НДС и компания на ОСНО.",
    "• Налог на прибыль 25% — у компаний на ОСНО, если прибыль в плюсе и оплата не наличными.",
    "• Зарплата логиста = 20% от прибыли (минус — 0). Начисляется, только когда клиент оплатил всю сумму.",
    "",
    "Пока внесены не все заявки фуры, расход на 1 кг завышен — прибыль внесённых заявок временно занижена.",
    "Промежуточные шаги расчёта — в свёрнутых серых столбцах справа (кнопка «+» над столбцами).",
]
for i, t in enumerate(lines, start=1):
    hw.cell(i, 1, t).font = F(size=14 if i == 1 else 10, bold=(i in (1, 3)), color=DARK if i == 1 else "000000")
hw.column_dimensions["A"].width = 120

# ---------- Пример ----------
if "--example" in sys.argv:
    for j, v in enumerate(["ПРИМЕР-1", dt.date(2026, 10, 1), "Москва (Щербинка) → Иркутск", 580000, 27000, 0, 0], start=1):
        fu.cell(f1, j, v)
    ex = [
        ["ПРИМЕР-1", "Клиент А (пример)", "Оля", "ООО «Восточная Логистика»", "с НДС", 420000, 9000, 25000, 15000, 3000, 25000, 420000, dt.date(2026, 10, 20)],
        ["ПРИМЕР-1", "Клиент Б (пример)", "Артём", "ИП Шерстов", "без НДС", 260000, 6000, 20000, 10000, 0, 0, 100000, None],
        ["ПРИМЕР-1", "Клиент В (пример)", "Таня", "ИП Шерстов", "нал", 200000, 5000, 15000, 8000, 0, 0, 200000, dt.date(2026, 11, 5)],
    ]
    for i, row in enumerate(ex):
        for j, v in enumerate(row, start=1):
            za.cell(z1 + i, j, v)
    for ws, r1, n in ((fu, f1, 1), (za, z1, 3)):
        for r in range(r1, r1 + n):
            ws.cell(r, 1).fill = fill("FFF2CC")
    for ws in (fu, za):
        ws["H2"] = "Жёлтые строки ПРИМЕР-1 — для проверки, удали их перед работой."
        ws["H2"].font = F(bold=True, color="C00000")

for ws in (fu, za):
    ws.page_setup.orientation = "landscape"; ws.page_setup.fitToWidth = 1; ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
wb.active = 1
wb.save(OUT)
print("ok")
