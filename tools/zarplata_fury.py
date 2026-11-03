import sys
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.formatting.rule import FormulaRule
from openpyxl.utils import get_column_letter as L
import datetime as dt

OUT = sys.argv[1]
NF, NZ = 100, 400  # строк под фуры и заявки

BLUE, DARK, PALE, BORDER = "1E6FE0", "0B4AA8", "EAF2FE", "A9C8F5"
INPUT = "FFFFFF"
F = lambda **k: Font(name="Arial", size=k.pop("size", 10), **k)
fill = lambda c: PatternFill("solid", fgColor=c)
thin = Side(style="thin", color=BORDER)
box = Border(left=thin, right=thin, top=thin, bottom=thin)
MONEY, KG, PCT, DATE = '#,##0', '#,##0', '0.0%', 'DD.MM.YYYY'

wb = Workbook()

# ---------- Настройки ----------
st = wb.active
st.title = "Настройки"
st["A1"] = "Настройки расчёта"; st["A1"].font = F(size=14, bold=True, color=DARK)
rows = [
    ("Процент зарплаты логиста от остатка прибыли", 0.20, PCT, "ZP_PCT"),
    ("Налог на прибыль (для ОСНО)", 0.25, PCT, "NNP"),
]
for i, (t, v, f, name) in enumerate(rows, start=3):
    st.cell(i, 1, t).font = F(); c = st.cell(i, 2, v); c.number_format = f; c.font = F(bold=True); c.border = box
from openpyxl.workbook.defined_name import DefinedName
wb.defined_names["ZP_PCT"] = DefinedName("ZP_PCT", attr_text="Настройки!$B$3")
wb.defined_names["NNP"] = DefinedName("NNP", attr_text="Настройки!$B$4")

st["A7"] = "Форма оплаты"; st["B7"] = "Пишешь в таблице"; st["C7"] = "Что значит"
forms = [("с НДС", 1.22, "НДС 22% — налог = сумма − сумма/1,22; НДС перевозчиков 1,22 идёт к вычету (только у ОСНО)"),
         ("без НДС", 1.06, "УСН 6% с дохода"),
         ("нал", 1, "наличные — налог 0")]
for i, (a, b, c) in enumerate(forms, start=8):
    st.cell(i, 1, a); st.cell(i, 2, b).number_format = "0.00"; st.cell(i, 3, c)
wb.defined_names["FORMS"] = DefinedName("FORMS", attr_text="Настройки!$B$8:$B$10")
wb.defined_names["FORMS_T"] = DefinedName("FORMS_T", attr_text="Настройки!$A$8:$B$10")

st["A13"] = "Компания"; st["B13"] = "Режим налога"; st["C13"] = "Пометка"
comps = [("ООО «Восточная Логистика»", "ОСНО", ""),
         ("ИП Шерстов", "УСН", ""),
         ("ООО «ТК МВЛ»", "ОСНО", "")]
for i, (a, b, c) in enumerate(comps, start=14):
    st.cell(i, 1, a); st.cell(i, 2, b); st.cell(i, 3, c)
for r in range(17, 20):  # запас под новые компании
    pass
wb.defined_names["COMPS"] = DefinedName("COMPS", attr_text="Настройки!$A$14:$A$19")
wb.defined_names["COMPS_T"] = DefinedName("COMPS_T", attr_text="Настройки!$A$14:$B$19")

st["A22"] = "Логисты"
logists = ["Александр", "Артём", "Таня", "Ильяс", "Оля", "Андрей", "Илья"]
for i, n in enumerate(logists, start=23):
    st.cell(i, 1, n)
wb.defined_names["LOGISTS"] = DefinedName("LOGISTS", attr_text="Настройки!$A$23:$A$35")

for cell in ("A7", "B7", "C7", "A13", "B13", "C13", "A22"):
    st[cell].font = F(bold=True, color="FFFFFF"); st[cell].fill = fill(BLUE)
for r in list(range(8, 11)) + list(range(14, 20)) + list(range(23, 36)):
    for c in (1, 2, 3) if r < 22 else (1,):
        st.cell(r, c).border = box
        if st.cell(r, c).font.name != "Arial":
            st.cell(r, c).font = F()
st["A37"] = "Новые компании и логистов дописывай в пустые строки своих списков — они сразу появятся в выпадающих списках."
st["A37"].font = F(italic=True, color="666666")
dv_reg = DataValidation(type="list", formula1='"ОСНО,УСН"', allow_blank=True)
st.add_data_validation(dv_reg); dv_reg.add("B14:B19")
st.column_dimensions["A"].width = 48; st.column_dimensions["B"].width = 14; st.column_dimensions["C"].width = 70

# ---------- Фуры ----------
fu = wb.create_sheet("Фуры", 0)
fcols = [
    # (заголовок, ширина, формат, формула или None для ввода)
    ("№ фуры", 10, None, None),
    ("Номер ТС", 13, None, None),
    ("Дата отправки", 12, DATE, None),
    ("Маршрут", 26, None, None),
    ("Перевозчик фуры", 20, None, None),
    ("Ставка фуры, ₽", 13, MONEY, None),
    ("Форма оплаты фуры", 11, "0.00", None),
    ("Склад погрузки, ₽", 12, MONEY, None),
    ("Форма оплаты склада погр.", 11, "0.00", None),
    ("Склад приёмки, ₽", 12, MONEY, None),
    ("Форма оплаты склада приёмки", 11, "0.00", None),
    ("Прочие общие (кран и т.п.), ₽", 13, MONEY, None),
    ("Форма оплаты прочих", 11, "0.00", None),
    # расчёт
    ("Общие расходы, ₽", 13, MONEY, 'IF(A{r}="","",F{r}+H{r}+J{r}+L{r})'),
    ("НДС в общих расходах, ₽", 12, MONEY,
     'IF(A{r}="","",IF(G{r}=1.22,F{r}-F{r}/1.22,0)+IF(I{r}=1.22,H{r}-H{r}/1.22,0)'
     '+IF(K{r}=1.22,J{r}-J{r}/1.22,0)+IF(M{r}=1.22,L{r}-L{r}/1.22,0))'),
    ("Вес фуры, кг", 11, KG, 'IF(A{r}="","",SUMIFS(Заявки!$I:$I,Заявки!$A:$A,A{r}))'),
    ("Расход на 1 кг, ₽", 11, '#,##0.00', 'IF(A{r}="","",IFERROR(N{r}/P{r},0))'),
    ("Выручка фуры, ₽", 13, MONEY, 'IF(A{r}="","",SUMIFS(Заявки!$H:$H,Заявки!$A:$A,A{r}))'),
    ("Остаток прибыли фуры, ₽", 13, MONEY, 'IF(A{r}="","",SUMIFS(Заявки!$AB:$AB,Заявки!$A:$A,A{r}))'),
    ("Прибыль на 1 кг, ₽", 11, '#,##0.00', 'IF(A{r}="","",IFERROR(S{r}/P{r},0))'),
    ("% прибыли от выручки", 10, PCT, 'IF(A{r}="","",IFERROR(S{r}/R{r},0))'),
    ("Заявок / оплачено", 10, None,
     'IF(A{r}="","",COUNTIFS(Заявки!$A:$A,A{r})&" / "&COUNTIFS(Заявки!$A:$A,A{r},Заявки!$AE:$AE,"Оплачено"))'),
    ("Зп начислено, ₽", 12, MONEY, 'IF(A{r}="","",SUMIFS(Заявки!$AH:$AH,Заявки!$A:$A,A{r}))'),
    ("Зп ждёт оплаты, ₽", 12, MONEY, 'IF(A{r}="","",SUMIFS(Заявки!$AI:$AI,Заявки!$A:$A,A{r}))'),
]

# ---------- Заявки ----------
za = wb.create_sheet("Заявки", 1)
zcols = [
    ("№ фуры", 10, None, None),                         # A
    ("№ заявки / счёта", 12, None, None),               # B
    ("Дата перевозки", 12, DATE, None),                 # C
    ("Клиент", 26, None, None),                         # D
    ("Логист", 12, None, None),                         # E
    ("Компания", 24, None, None),                       # F
    ("Форма оплаты клиента", 11, "0.00", None),           # G
    ("Выручка (сумма с клиента), ₽", 13, MONEY, None),  # H
    ("Вес, кг", 10, KG, None),                          # I
    ("Объём, м³", 9, '#,##0.0#', None),                 # J
    ("Водитель до склада, ₽", 12, MONEY, None),         # K
    ("Форма оплаты водителя", 11, "0.00", None),          # L
    ("Развоз до получателя, ₽", 12, MONEY, None),       # M
    ("Форма оплаты развоза", 11, "0.00", None),           # N
    ("Прочие (СДЭК, кран), ₽", 12, MONEY, None),        # O
    ("Форма оплаты прочих", 11, "0.00", None),            # P
    ("Оплачено клиентом, ₽", 13, MONEY, None),          # Q
    ("Дата полной оплаты", 12, DATE, None),             # R
    # расчёт
    ("Кф", 6, "0.00", 'IF(H{r}="","",IF(OR(G{r}=1.22,G{r}=1.06,G{r}=1),G{r},""))'),                 # S
    ("Налог с выручки (НДС / УСН), ₽", 12, MONEY, 'IF(OR(H{r}="",S{r}=""),"",H{r}-H{r}/S{r})'),     # T
    ("Свои расходы, ₽", 12, MONEY, 'IF(H{r}="","",K{r}+M{r}+O{r})'),                                 # U
    ("НДС своих перевозчиков к вычету, ₽", 12, MONEY,
     'IF(H{r}="","",IF(AND(G{r}=1.22,V_OSNO),IF(L{r}=1.22,K{r}-K{r}/1.22,0)+IF(N{r}=1.22,M{r}-M{r}/1.22,0)'
     '+IF(P{r}=1.22,O{r}-O{r}/1.22,0),0))'),                                                       # V
    ("Доля общих расходов фуры, ₽", 12, MONEY,
     'IF(H{r}="","",N(I{r})*IFERROR(VLOOKUP(A{r},Фуры!$A:$Q,17,FALSE),0))'),                           # W
    ("НДС в доле общих к вычету, ₽", 12, MONEY,
     'IF(H{r}="","",IF(AND(G{r}=1.22,V_OSNO),N(I{r})*IFERROR(VLOOKUP(A{r},Фуры!$A:$P,15,FALSE)/VLOOKUP(A{r},Фуры!$A:$P,16,FALSE),0),0))'),  # X
    ("Прибыль до налога на прибыль, ₽", 13, MONEY, 'IF(H{r}="","",H{r}-T{r}-U{r}+V{r}-W{r}+X{r})'),  # Y
    ("Режим компании", 8, None, 'IF(F{r}="","",IFERROR(VLOOKUP(F{r},COMPS_T,2,FALSE),""))'),         # Z
    ("Налог на прибыль, ₽", 12, MONEY, 'IF(H{r}="","",IF(AND(Z{r}="ОСНО",G{r}<>1,Y{r}>0),Y{r}*NNP,0))'),  # AA
    ("ОСТАТОК ПРИБЫЛИ, ₽", 13, MONEY, 'IF(H{r}="","",Y{r}-AA{r})'),                                   # AB
    ("Прибыль на 1 кг, ₽", 11, '#,##0.00', 'IF(H{r}="","",IFERROR(AB{r}/I{r},0))'),                   # AC
    ("% прибыли от выручки", 10, PCT, 'IF(H{r}="","",IFERROR(AB{r}/H{r},0))'),                        # AD
    ("Статус оплаты", 12, None, 'IF(H{r}="","",IF(N(Q{r})>=H{r},"Оплачено",IF(N(Q{r})>0,"Частично","Не оплачено")))'),  # AE
    ("Долг клиента, ₽", 12, MONEY, 'IF(H{r}="","",MAX(H{r}-N(Q{r}),0))'),                             # AF
    ("Зп логиста всего, ₽", 12, MONEY, 'IF(H{r}="","",MAX(AB{r},0)*ZP_PCT)'),                         # AG
    ("Зп начислено, ₽", 12, MONEY, 'IF(H{r}="","",IF(AE{r}="Оплачено",AG{r},0))'),                    # AH
    ("Зп ждёт оплаты, ₽", 12, MONEY, 'IF(H{r}="","",AG{r}-AH{r})'),                                   # AI
    ("Проверка", 22, None,
     'IF(H{r}="","",IF(A{r}="","нет № фуры",IF(ISNA(MATCH(A{r},Фуры!$A:$A,0)),"фуры нет на листе Фуры",'
     'IF(N(I{r})=0,"нет веса — общие расходы 0",IF(S{r}="","нет формы оплаты",IF(Z{r}="","нет компании",'
     'IF(AND(AE{r}="Оплачено",R{r}=""),"нет даты оплаты","")))))))'),                                   # AJ
]


def build(ws, cols, nrows, title, hint):
    ws["A1"] = title; ws["A1"].font = F(size=14, bold=True, color=DARK)
    ws["A2"] = hint; ws["A2"].font = F(italic=True, color="666666")
    hr = 4
    for j, (h, w, fmt, formula) in enumerate(cols, start=1):
        c = ws.cell(hr, j, h)
        c.font = F(bold=True, color="FFFFFF", size=9)
        c.fill = fill(BLUE if formula is None else DARK)
        c.alignment = Alignment(wrap_text=True, vertical="center", horizontal="center")
        c.border = box
        ws.column_dimensions[L(j)].width = w
    ws.row_dimensions[hr].height = 48
    for r in range(hr + 1, hr + 1 + nrows):
        for j, (h, w, fmt, formula) in enumerate(cols, start=1):
            c = ws.cell(r, j)
            if formula:
                c.value = "=" + formula.format(r=r)
                c.fill = fill(PALE)
            c.font = F(); c.border = box
            if fmt: c.number_format = fmt
    ws.freeze_panes = ws.cell(hr + 1, 3)
    ws.auto_filter.ref = f"A{hr}:{L(len(cols))}{hr + nrows}"
    return hr + 1, hr + nrows


f1, f2 = build(fu, fcols, NF, "Фуры — общие расходы и итог по фуре",
               "Белые колонки заполняешь сам, синие считаются. Вес, выручка и прибыль подтягиваются с листа «Заявки» по № фуры.")
z1, z2 = build(za, zcols, NZ, "Заявки — прибыль и зарплата по каждой заявке",
               "Одна строка — одна заявка клиента. № фуры — как на листе «Фуры». Зарплата начисляется только когда «Оплачено клиентом» ≥ выручки.")

# V_OSNO в формулах — подставляем проверку режима компании (НДС к вычету только у ОСНО)
for r in range(z1, z2 + 1):
    for col in ("V", "X"):
        c = za[f"{col}{r}"]
        c.value = c.value.replace("V_OSNO", f'IFERROR(VLOOKUP(F{r},COMPS_T,2,FALSE),"")="ОСНО"')

# выпадающие списки
def dv(ws, formula, rng):
    d = DataValidation(type="list", formula1=formula, allow_blank=True)
    ws.add_data_validation(d); d.add(rng)

for col in "GIKM":
    dv(fu, "=FORMS", f"{col}{f1}:{col}{f2}")
for col in "GLNP":
    dv(za, "=FORMS", f"{col}{z1}:{col}{z2}")
dv(za, "=LOGISTS", f"E{z1}:E{z2}")
dv(za, "=COMPS", f"F{z1}:F{z2}")
dv(za, f"=Фуры!$A${f1}:$A${f2}", f"A{z1}:A{z2}")

# подсветка
red = PatternFill("solid", fgColor="F8D7DA"); green = PatternFill("solid", fgColor="D4EDDA"); yellow = PatternFill("solid", fgColor="FFF2CC")
za.conditional_formatting.add(f"AE{z1}:AE{z2}", FormulaRule(formula=[f'AE{z1}="Оплачено"'], fill=green))
za.conditional_formatting.add(f"AE{z1}:AE{z2}", FormulaRule(formula=[f'AE{z1}="Частично"'], fill=yellow))
za.conditional_formatting.add(f"AE{z1}:AE{z2}", FormulaRule(formula=[f'AE{z1}="Не оплачено"'], fill=red))
za.conditional_formatting.add(f"AB{z1}:AB{z2}", FormulaRule(formula=[f'AND(ISNUMBER(AB{z1}),AB{z1}<0)'], fill=red))
za.conditional_formatting.add(f"AJ{z1}:AJ{z2}", FormulaRule(formula=[f'AJ{z1}<>""'], fill=yellow))
fu.conditional_formatting.add(f"S{f1}:S{f2}", FormulaRule(formula=[f'AND(ISNUMBER(S{f1}),S{f1}<0)'], fill=red))
for c in ("AB",):
    for r in range(z1, z2 + 1):
        za[f"{c}{r}"].font = F(bold=True)

# ---------- Зарплата ----------
zp = wb.create_sheet("Зарплата", 2)
zp["A1"] = "Зарплата логистов — по месяцу полной оплаты клиента"; zp["A1"].font = F(size=14, bold=True, color=DARK)
zp["A2"] = "Год:"; zp["B2"] = 2026; zp["B2"].font = F(bold=True); zp["B2"].border = box
zp["C2"] = "← поменяй год, таблица пересчитается"; zp["C2"].font = F(italic=True, color="666666")
months = ["Янв", "Фев", "Мар", "Апр", "Май", "Июн", "Июл", "Авг", "Сен", "Окт", "Ноя", "Дек"]
heads = ["Логист"] + months + ["Начислено за год", "Ждёт оплаты клиентов", "Остаток прибыли заявок", "Заявок"]
for j, h in enumerate(heads, start=1):
    c = zp.cell(4, j, h); c.font = F(bold=True, color="FFFFFF"); c.fill = fill(BLUE); c.border = box
    c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    zp.column_dimensions[L(j)].width = 12 if j > 1 else 14
zp.row_dimensions[4].height = 32
ZR = f"Заявки!$AH${z1}:$AH${z2}"; ER = f"Заявки!$E${z1}:$E${z2}"; RR = f"Заявки!$R${z1}:$R${z2}"
NL = 13
for i in range(NL):
    r = 5 + i
    zp.cell(r, 1, f"=IF(Настройки!A{23 + i}=\"\",\"\",Настройки!A{23 + i})")
    for m in range(12):
        zp.cell(r, 2 + m, f'=IF($A{r}="","",SUMIFS({ZR},{ER},$A{r},{RR},">="&DATE($B$2,{m + 1},1),{RR},"<"&DATE($B$2,{m + 2},1)))')
    zp.cell(r, 14, f'=IF($A{r}="","",SUM(B{r}:M{r}))')
    zp.cell(r, 15, f'=IF($A{r}="","",SUMIFS(Заявки!$AI${z1}:$AI${z2},{ER},$A{r}))')
    zp.cell(r, 16, f'=IF($A{r}="","",SUMIFS(Заявки!$AB${z1}:$AB${z2},{ER},$A{r}))')
    zp.cell(r, 17, f'=IF($A{r}="","",COUNTIFS({ER},$A{r},Заявки!$H${z1}:$H${z2},"<>"))')
    for j in range(1, 18):
        c = zp.cell(r, j); c.border = box; c.font = F(bold=(j in (1, 14)))
        if j > 1: c.number_format = MONEY
tr = 5 + NL
zp.cell(tr, 1, "ИТОГО")
for j in range(2, 18):
    zp.cell(tr, j, f"=SUM({L(j)}5:{L(j)}{tr - 1})").number_format = MONEY
for j in range(1, 18):
    c = zp.cell(tr, j); c.font = F(bold=True); c.fill = fill(PALE); c.border = box
zp.cell(tr + 2, 1, "Начисляется только по заявкам со статусом «Оплачено» (клиент внёс полную сумму), в месяц «Даты полной оплаты».").font = F(italic=True, color="666666")
zp.cell(tr + 3, 1, "Заявки с логистом не из списка в эту таблицу не попадут — допиши его на листе «Настройки».").font = F(italic=True, color="666666")
zp.freeze_panes = "B5"

# ---------- Как считается ----------
hw = wb.create_sheet("Как считается")
lines = [
    "Как считается остаток прибыли и зарплата",
    "",
    "1. Форма оплаты пишется числом: 1,22 — с НДС · 1,06 — без НДС (УСН 6%) · 1 — наличные.  Налог с выручки = Выручка − Выручка / форма оплаты.",
    "2. Свои расходы заявки = водитель до склада + развоз до получателя + прочие (СДЭК, кран).",
    "3. НДС своих перевозчиков к вычету — только если клиент 1,22, компания на ОСНО и перевозчик 1,22. Водители и склады через ИП (УСН) и 1,06 — налог не вычитаем.",
    "4. Общие расходы фуры (фура + склад погрузки + склад приёмки + общие прочие) делятся по весу:",
    "   расход на 1 кг = общие расходы / вес всех заявок фуры;  доля заявки = её вес × расход на 1 кг.",
    "   НДС в общих расходах к вычету — по тому же правилу, что в п. 3, пропорционально весу.",
    "5. Прибыль до налога на прибыль = Выручка − Налог − Свои расходы + НДС к вычету − Доля общих + НДС в доле общих.",
    "6. Налог на прибыль = 25% от прибыли заявки, если компания на ОСНО, оплата не наличными и прибыль в плюсе.",
    "7. ОСТАТОК ПРИБЫЛИ = Прибыль до налога на прибыль − Налог на прибыль.",
    "   Прибыль на 1 кг = Остаток / вес;  % от выручки = Остаток / Выручка.",
    "8. Зарплата логиста = 20% от остатка (если остаток в минусе — 0).",
    "   Начисляется только когда «Оплачено клиентом» ≥ выручки (статус «Оплачено»), в месяц «Даты полной оплаты».",
    "   Пока клиент не заплатил всё — сумма стоит в «Зп ждёт оплаты».",
    "",
    "Важно: вес фуры = сумма весов заявок этой фуры. Пока не внесены все заявки фуры, расход на 1 кг завышен,",
    "и прибыль уже внесённых заявок занижена. Колонка «Проверка» на листе «Заявки» подсказывает, чего не хватает.",
    "Проценты и режимы налогов компаний меняются на листе «Настройки».",
]
for i, t in enumerate(lines, start=1):
    c = hw.cell(i, 1, t); c.font = F(size=14 if i == 1 else 10, bold=(i == 1), color=DARK if i == 1 else "000000")
hw.column_dimensions["A"].width = 130

# ---------- Пример ----------
if "--example" in sys.argv:
    fu.append  # noqa
    ex_f = ["ПРИМЕР-1", "А000АА00", dt.date(2026, 10, 1), "Москва (Щербинка) → Иркутск", "пример", 580000, 1.06,
            15000, 1.06, 12000, 1.06, 0, 1]
    for j, v in enumerate(ex_f, start=1):
        fu.cell(f1, j, v)
    ex_z = [
        ["ПРИМЕР-1", "П-1", dt.date(2026, 10, 1), "Клиент А (пример)", "Оля", "ООО «Восточная Логистика»", 1.22, 420000, 9000, 35,
         25000, 1.22, 15000, 1.06, 3000, 1, 420000, dt.date(2026, 10, 20)],
        ["ПРИМЕР-1", "П-2", dt.date(2026, 10, 1), "Клиент Б (пример)", "Артём", "ИП Шерстов", 1.06, 260000, 6000, 25,
         20000, 1.06, 10000, 1.06, 0, 1, 100000, None],
        ["ПРИМЕР-1", "П-3", dt.date(2026, 10, 1), "Клиент В (пример)", "Таня", "ИП Шерстов", 1, 200000, 5000, 20,
         15000, 1, 8000, 1, 0, 1, 200000, dt.date(2026, 11, 5)],
    ]
    for i, row in enumerate(ex_z):
        for j, v in enumerate(row, start=1):
            za.cell(z1 + i, j, v)
    for ws, r1, n in ((fu, f1, 1), (za, z1, 3)):
        for r in range(r1, r1 + n):
            ws.cell(r, 1).fill = fill("FFF2CC")
    fu["F2"] = "Строка ПРИМЕР-1 и её 3 заявки — для проверки формул, удали их перед работой."
    fu["F2"].font = F(bold=True, color="C00000")
    za["L2"] = "Строки ПРИМЕР-1 — для проверки, удали перед работой."
    za["L2"].font = F(bold=True, color="C00000")

for ws in (fu, za):
    ws.page_setup.orientation = "landscape"; ws.page_setup.fitToWidth = 1; ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
wb.active = 1
wb.save(OUT)
print("ok", OUT)
