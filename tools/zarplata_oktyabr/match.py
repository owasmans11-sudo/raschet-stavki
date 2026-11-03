import openpyxl, sys, datetime as dt, json
SP = sys.argv[1]
ved = openpyxl.load_workbook(r"C:\РАБОТА\Ведомости — все в одном.xlsx", data_only=True)
gr = ved["Все грузы"]
cargo = []
for r in gr.iter_rows(min_row=2, values_only=True):
    if not r[0] or r[23]: continue  # повтор
    if r[0] < dt.datetime(2026, 10, 1): continue
    cargo.append(dict(date=r[0].date().isoformat(), reis=r[1], ts=r[2], kp=r[4], sender=r[5], recv=r[6], to=r[9], gruz=r[10], logist=r[11], kg=r[13] or 0, m3=r[14] or 0))
ob = openpyxl.load_workbook(r"C:\РАБОТА\Работа ребят\Общая таблица логистов.xlsx", data_only=True)["Все заявки"]
hdr = [c.value for c in ob[1]]
deals = []
for i, r in enumerate(ob.iter_rows(min_row=2, values_only=True), start=2):
    if not any(r): continue
    d = dict(zip(hdr, r)); d["row"] = i; deals.append(d)
o = open(SP + "/match.txt", "w", encoding="utf-8")
used = {}
for c in cargo:
    cands = []
    for d in deals:
        kg = d.get("Вес, кг")
        if isinstance(kg, (int, float)) and kg and abs(kg - c["kg"]) <= max(30, 0.03 * c["kg"]):
            cands.append(d)
    o.write(f"{c['ts']} {c['date']} {c['kp']} | {c['sender']} -> {c['recv']} ({c['to']}) {c['gruz']} {c['kg']}кг {c['m3']}м3 лог={c['logist']}\n")
    for d in cands:
        o.write(f"     ?? стр{d['row']} {d['Логист']} | {d['Компания']} | {d['Груз']} | {d['Вес, кг']}кг {d['Объём, м³']} | {d['Маршрут']} | {d['Стоимость']} кф{d['Форма оплаты']} | забор {d['Сумма']} кф{d['Форма оплаты2']} | доставка {d['Сумма4']} кф{d['Форма оплаты3']} | забор {d['Дата забора']} | фура={d['Фура']} | оплата={d['Оплата']} / {d['Оплата (итог)']} {d['Дата оплаты']}\n")
o.write("\nВСЕ СДЕЛКИ ОКТЯБРЯ (дата забора с 20.09):\n")
for d in deals:
    z = d.get("Дата забора")
    if isinstance(z, dt.datetime) and z >= dt.datetime(2026, 9, 20) or z is None:
        o.write(f"стр{d['row']} {d['Логист']} | {d['Компания']} | {d['Груз']} | {d['Вес, кг']}кг {d['Объём, м³']} | {d['Маршрут']} | {d['Стоимость']} кф{d['Форма оплаты']} | {d['Сумма']} кф{d['Форма оплаты2']} | {d['Сумма4']} кф{d['Форма оплаты3']} | забор {z} | фура={d['Фура']} | опл={d['Оплата']}/{d['Оплата (итог)']}\n")
json.dump(cargo, open(SP + "/cargo.json", "w", encoding="utf-8"), ensure_ascii=False, indent=0)
print(len(cargo), len(deals))
