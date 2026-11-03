import openpyxl, sys, json, datetime as dt
from openpyxl.styles import PatternFill, Font, Alignment
SP, OUT = sys.argv[1], sys.argv[2]
cargo = json.load(open(SP + "/cargo.json", encoding="utf-8"))
ved = openpyxl.load_workbook(r"C:\РАБОТА\Ведомости — все в одном.xlsx", data_only=True)["Стоимость фур"]
fury = {}
for r in ved.iter_rows(min_row=2, values_only=True):
    if r[3]: fury[r[3]] = dict(reis=r[2], carrier=r[6], sum=r[9], pol=r[13])
ob = openpyxl.load_workbook(r"C:\РАБОТА\Работа ребят\Общая таблица логистов.xlsx", data_only=True)["Все заявки"]
hdr = [c.value for c in ob[1]]
deal = {i: dict(zip(hdr, r)) for i, r in enumerate(ob.iter_rows(min_row=2, values_only=True), start=2)}
# груз (ПОЭ) -> строка общей таблицы логистов, пометка
M = {
 "ПОЭ1721": (24, ""), "ПОЭ1746": (28, ""),
 "ПОЭ1790": (27, ""), "ПОЭ1792": (4, ""), "ПОЭ1795": (29, "вес в заявке 1250, в ведомости 1300; отправитель ТК Полихем"),
 "ПОЭ1710": (23, ""),
 "ПОЭ1834": (30, ""), "ПОЭ1805": (5, "вес в заявке 5600, в ведомости 5260; бумага Лента → АйМастер"),
 "ПОЭ1830": (32, "в заявке Москва–Ангарск, в ведомости Красноярск"),
 "ПОЭ1800": (69, ""), "ПОЭ1839": (68, "вес 3000/3060 и Новосибирск совпали, объём разный (13 / 3,3); у Тани обе — «фура37»"),
 "ПОЭ1837": (34, ""), "ПОЭ1838": (36, "совпало по названию Деко Минералс; вес 2000/2150"), "ПОЭ1842": (7, ""),
 "ПОЭ1841": (6, ""), "ПОЭ1861": (37, "текстиль Рузаевка–Чита 2800 кг ≈ одежда БТК 2794 кг — проверить"),
 "ПОЭ1865": (8, "логист в общей таблице не указан — строка из файла Оли, поставил Олю"),
 "ПОЭ1866": (31, ""), "ПОЭ1876": (9, ""), "ПОЭ1881": (10, ""),
 "ПОЭ1883": (39, "совпал получатель Ста-Групп; вес 530/700 — проверить"),
 "ПОЭ1891": (44, "совпал получатель Агроторг; вес 550/783 — проверить"),
}
KF = {1.22: 1.22, 1.06: 1.06, 1.05: 1.05, 1: 1, 1.0: 1}
def kf(v): return KF.get(v) if isinstance(v, (int, float)) else None
def comp(k):
    return {1.22: "ООО «Восточная Логистика»", 1.06: "ИП Шерстов", 1: "ИП Шерстов"}.get(k)

wb = openpyxl.load_workbook(OUT)
fu, za = wb["Фуры"], wb["Заявки"]
yellow = PatternFill("solid", fgColor="FFF2CC"); grey = Font(name="Arial", size=10, color="888888")
notes = []
fr, zr = 5, 5
order = []
for c in cargo:
    if c["ts"] not in order: order.append(c["ts"])
for ts in order:
    cs = [c for c in cargo if c["ts"] == ts and c["kg"]]
    f = fury[ts]
    dests = []
    for c in cs:
        if c["to"] not in dests: dests.append(c["to"])
    vals = [ts, ts, dt.datetime.fromisoformat(cs[0]["date"]), "Москва → " + ", ".join(dests), f["carrier"], f["sum"], 1.06,
            f["pol"], None, None, None, None, None]
    for j, v in enumerate(vals, start=1):
        fu.cell(fr, j, v)
    if not f["pol"]:
        fu.cell(fr, 8).fill = yellow
        notes.append((ts, "", "Фура", "счёта Полярной (склад погрузки) нет — склад погрузки пустой"))
    fu.cell(fr, 9).fill = yellow; fu.cell(fr, 10).fill = yellow; fu.cell(fr, 11).fill = yellow
    fr += 1
    for c in cs:
        m = M.get(c["kp"])
        if m:
            d = deal[m[0]]
            lg = d["Логист"] if d["Логист"] and d["Логист"].strip() else "Оля"
            k1 = kf(d["Форма оплаты"])
            row = [ts, f'{c["kp"]} / стр.{m[0]}', d["Дата забора"], d["Компания"].strip(), lg.strip(), comp(k1), k1,
                   d["Стоимость"], c["kg"], c["m3"] or None,
                   d["Сумма"] if isinstance(d["Сумма"], (int, float)) else None, kf(d["Форма оплаты2"]),
                   d["Сумма4"] if isinstance(d["Сумма4"], (int, float)) else None, kf(d["Форма оплаты3"]),
                   None, None, None, None]
            for j, v in enumerate(row, start=1):
                za.cell(zr, j, v)
            why = m[1]
            if d["Сумма4"] and kf(d["Форма оплаты3"]) is None: why = (why + "; " if why else "") + f'форма оплаты доставки «{d["Форма оплаты3"]}» — не указана'
            if d["Сумма"] and kf(d["Форма оплаты2"]) is None: why = (why + "; " if why else "") + f'форма оплаты забора «{d["Форма оплаты2"]}» — не указана'
            notes.append((ts, c["kp"], f'{d["Компания"].strip()} ({lg.strip()}, стр. {m[0]} общей таблицы)', why or "совпало по весу, грузу и дате"))
            if m[1]:
                for j in (2, 4): za.cell(zr, j).fill = yellow
        else:
            row = [ts, f'{c["kp"]} — нет заявки', dt.datetime.fromisoformat(c["date"]), f'{c["sender"]} → {c["recv"]}',
                   c["logist"], None, None, None, c["kg"], c["m3"] or None]
            for j, v in enumerate(row, start=1):
                za.cell(zr, j, v)
            for j in range(1, 11): za.cell(zr, j).fill = yellow
            notes.append((ts, c["kp"], f'{c["sender"]} → {c["recv"]}, {c["gruz"]}, {c["kg"]} кг', "в общей таблице логистов заявки нет — внеси сумму клиента, логиста, компанию и расходы"))
        zr += 1
# убрать пример-пометки
for ws in (fu, za):
    for cell in ("F2", "L2"):
        if ws[cell].value and "ПРИМЕР" in str(ws[cell].value): ws[cell].value = None
fu["F2"] = "Заполнено по ведомостям октября 2026 (8 фур). Жёлтое — проверить или дописать, см. лист «Пояснения заполнения»."
fu["F2"].font = Font(name="Arial", bold=True, color="C00000")
za["L2"] = "Жёлтые строки — нет заявки в общей таблице или есть сомнение. Оплаты клиентов не внесены — вся зп пока «ждёт оплаты»."
za["L2"].font = Font(name="Arial", bold=True, color="C00000")
pn = wb.create_sheet("Пояснения заполнения")
pn.append(["Фура", "Груз (ПОЭ)", "Клиент / груз", "Пометка"])
for n in notes: pn.append(list(n))
pn.append([])
pn.append(["Откуда взято: грузы и вес — «Ведомости — все в одном.xlsx» (лист «Все грузы», без повторов); ставка фуры и Полярная — лист «Стоимость фур»;"])
pn.append(["клиент, сумма, логист, забор, доставка и формы оплаты — «Общая таблица логистов.xlsx». Вес заявки — по ведомости (фактический)."])
pn.append(["Допущения: компания по форме оплаты клиента (1,22 → ООО ВЛ, 1,06 и нал → ИП Шерстов); форма оплаты фуры 1,06 (без НДС);"])
pn.append(["Полярная (склад погрузки) и склад приёмки — форма оплаты не указана (НДС к вычету по ним не считается). Склад приёмки — сумм нет."])
pn.append(["Прибыль фуры пока считается только по заявкам с суммой: у грузов без заявки доля расходов фуры не вычтена."])
for c in pn[1]: c.font = Font(name="Arial", bold=True)
pn.column_dimensions["A"].width = 13; pn.column_dimensions["B"].width = 11; pn.column_dimensions["C"].width = 60; pn.column_dimensions["D"].width = 90
wb.save(OUT)
print("фур", fr - 5, "строк заявок", zr - 5, "совпало", sum(1 for c in cargo if c["kp"] in M and c["kg"]))
