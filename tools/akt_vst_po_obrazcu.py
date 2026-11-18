import sys, os, subprocess
sys.stdout.reconfigure(encoding='utf-8')
OUT = r"C:\Users\user\Downloads"
SCR = os.path.dirname(os.path.abspath(__file__))

CO = {
 "ВЛ": dict(brand="ВОСТОЧНАЯ ЛОГИСТИКА",
   full='ООО «Восточная Логистика», ИНН 3812166710, КПП 381201001, ОГРН 1253800008087, 664040, Иркутская обл., г. Иркутск, ул. Павла Красильникова, 172, кв. 59',
   req=["ИНН 3812166710 · КПП 381201001", "ОГРН 1253800008087", "Тел.: +7 (995) 610-33-45", "Vostok.logist@list.ru"],
   short='ООО «Восточная Логистика»',
   addr="664040, Иркутская обл., г. Иркутск, ул. Павла Красильникова, 172",
   file="ЭР ВСТ — акт от ООО Восточная Логистика"),
 "ИП": dict(brand="ИП ШЕРСТОВ А. В.",
   full='ИП Шерстов Андрей Витальевич, ИНН 381100987938, ОГРНИП 325385000056839, 664040, Иркутская обл., г. Иркутск, ул. Павла Красильникова, 172, кв. 59',
   req=["ИНН 381100987938", "ОГРНИП 325385000056839", "Тел.: +7 (995) 610-33-45", "грузоперевозки по России"],
   short='ИП Шерстов А. В.',
   addr="664040, Иркутская обл., г. Иркутск, ул. Павла Красильникова, 172",
   file="ЭР ВСТ — акт от ИП Шерстов"),
}

CSS = """
body{font-family:Arial;font-size:9pt;color:#1a1a1a}
table{border-collapse:collapse;width:100%}
td,th{border:1px solid #A9C8F5;padding:1.5pt 4pt;vertical-align:top;font-size:9pt}
th{background:#EAF2FE;color:#0B4AA8;font-weight:bold;text-align:center}
.nb td{border:none;padding:1pt 2pt}
.sec{background:#1E6FE0;color:#fff;font-weight:bold;font-size:10pt;text-align:center}
.lbl{color:#0B4AA8;font-weight:bold;width:28%}
.h{height:13pt}
.small{font-size:7pt;color:#444}
"""

def page(c):
    rows_cargo = [
        ("МИА91 Москва – Иркутск (авто)", "Ким Андрей Владиславович", "Двигатель", "1 паллет", "", "2 566"),
        ("МИА91 Москва – Иркутск (авто)", "Ким Андрей Владиславович", "Двигатель", "1 коробка", "", ""),
    ]
    cargo = "".join(f"<tr>{''.join(f'<td align=center>{v}</td>' for v in r)}</tr>" for r in rows_cargo)
    req = "<br>".join(c["req"])
    empty = lambda n, cols: "".join("<tr class=h>" + "<td>&nbsp;</td>"*cols + "</tr>" for _ in range(n))
    return f"""<html><head><meta charset="utf-8"><style>{CSS}</style></head><body>
<table class=nb><tr>
<td style="width:55%"><span style="font-size:16pt;font-weight:bold;color:#1E6FE0">{c['brand']}</span></td>
<td align=right style="font-size:8pt;color:#0B4AA8">{req}</td></tr></table>
<table class=nb><tr><td style="border-bottom:2pt solid #1E6FE0;font-size:2pt">&nbsp;</td></tr></table>
<p align=center style="font-size:12pt;font-weight:bold;color:#0B4AA8;margin:4pt 0 1pt">АКТ ПРИЁМА-ПЕРЕДАЧИ ГРУЗА НА СТАНЦИИ НАЗНАЧЕНИЯ № ______</p>
<p align=center style="margin:0 0 4pt">от «____» ______________ 20___ г.</p>

<table>
<tr><td class=lbl>Дата получения груза</td><td>«___» _________ 20__ г.</td><td class=lbl>Документы</td><td>Счёт-фактура, Акт &nbsp;&nbsp;☐</td></tr>
<tr><td class=lbl>Наличие оплаты</td><td>☐</td><td class=lbl>Основание</td><td>ЭР № 17029 от 11.08.2025</td></tr>
<tr><td class=lbl>ЭКСПЕДИТОР</td><td colspan=3>{c['full']}</td></tr>
<tr><td class=lbl>ЗАКАЗЧИК</td><td colspan=3>&nbsp;</td></tr>
<tr><td class=lbl>Город отправления</td><td>Москва</td><td class=lbl>Город назначения</td><td>Иркутск</td></tr>
<tr><td class=lbl>ГРУЗОПОЛУЧАТЕЛЬ</td><td colspan=3>&nbsp;</td></tr>
</table><div style="font-size:4pt">&nbsp;</div>

<table>
<tr><th>ТС №</th><th>Грузоотправитель</th><th>Характер груза</th><th>Кол-во мест</th><th>Объём, м³</th><th>Вес, кг</th></tr>
{cargo}
<tr><td colspan=3 align=right><b>Итого:</b></td><td align=center><b>2 места</b></td><td align=center><b>5,7</b></td><td align=center><b>2 566</b></td></tr>
</table>

<p style="margin:6pt 0 2pt"><b style="color:#0B4AA8">Особые отметки о состоянии груза на станции отправления:</b></p>
<p class=small style="margin:0 0 6pt">Груз принят к перевозке в универсальном крытом вагоне/контейнере без поддержания температурного режима.
Груз принят без внутреннего пересчёта и осмотра. Груз в фабричной упаковке, возможны скрытые повреждения.
Упаковка слабая, не обеспечивает сохранность товарного вида содержимого. Груз принят в присутствии экспедитора.
Стоимость груза — 3 388 200 руб.</p>

<table>
<tr><td colspan=5 class=sec>Доставка автотранспортом</td></tr>
<tr><th>№ автомобиля</th><th>Пломба</th><th>Количество мест</th><th>ФИО водителя</th><th>Подпись</th></tr>
{empty(2,5)}
</table><div style="font-size:4pt">&nbsp;</div>

<table>
<tr><td colspan=5 class=sec>Данные о несоответствии объёма и веса груза</td></tr>
<tr><th>Заявленный объём / вес</th><th>Фактический объём / вес по перемеру</th><th>Объём с поправочным коэффициентом 1,1</th><th>С коэффициентом 1,2</th><th>Итого</th></tr>
<tr class=h><td align=center>5,7 м³</td><td></td><td></td><td></td><td></td></tr>
<tr class=h><td align=center>2 566 кг</td><td></td><td></td><td></td><td></td></tr>
<tr><td colspan=5 align=right>Подтверждаю: Грузополучатель ____________________</td></tr>
</table><div style="font-size:4pt">&nbsp;</div>

<table>
<tr><td class=lbl style="width:40%">Сумма к оплате:</td><td>&nbsp;</td></tr>
<tr><td class=lbl style="width:40%">Оплачено наличными денежными средствами в сумме:</td><td>&nbsp;</td></tr>
</table><div style="font-size:4pt">&nbsp;</div>

<table>
<tr><td class=sec>Отметки о недостаче, повреждении, порче груза и упаковки при получении</td></tr>
{empty(2,1)}
<tr><td align=right>Подтверждаю: Грузополучатель ____________________</td></tr>
</table><div style="font-size:4pt">&nbsp;</div>

<table>
<tr><td class=lbl style="width:60%">Наличие сопроводительных документов</td><td>Да ☐ &nbsp;&nbsp;&nbsp; Нет ☐</td></tr>
</table>
<p class=small style="margin:6pt 0">В соответствии с п. 1 ст. 8 Федерального закона «О транспортно-экспедиционной деятельности»: если при выдаче груза
Грузополучатель (или его уполномоченное лицо) не уведомил Экспедитора в письменной форме (запись в разделе «Отметки о недостаче,
повреждении, порче груза и упаковки при получении») об утрате, недостаче или повреждении (порче) груза с указанием их количества и характера,
считается, что груз получен неповреждённым и в полном объёме. Подпись и печать Грузополучателя означают отсутствие претензий к качеству
оказанных Экспедитором услуг.</p>

<table class=nb>
<tr><td style="width:50%"><b style="color:#0B4AA8">Представитель Экспедитора</b><br>{c['short']}</td>
<td><b style="color:#0B4AA8">Грузополучатель в лице</b><br>_______________________________________</td></tr>
<tr><td>&nbsp;</td><td>действующего на основании доверенности № ________<br>от «____» ______________ 20___ г.</td></tr>
<tr><td><br>__________________ / ____________________<br><span class=small>подпись &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; ФИО</span> &nbsp;&nbsp;&nbsp; М.П.</td>
<td><br>__________________ / ____________________<br><span class=small>подпись &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; ФИО</span> &nbsp;&nbsp;&nbsp; М.П.</td></tr>
</table>
<table class=nb><tr><td style="border-top:1pt solid #1E6FE0;font-size:7.5pt;color:#0B4AA8">{c['short']} · {c['addr']} · Тел.: +7 (995) 610-33-45 · Vostok.logist@list.ru</td></tr></table>
</body></html>"""

ps = []
for k, c in CO.items():
    h = os.path.join(SCR, f"akt_{k}.html")
    open(h, "w", encoding="utf-8").write(page(c))
    ps.append((h, os.path.join(OUT, c["file"])))

lines = ["$w = New-Object -ComObject Word.Application; $w.Visible = $false"]
for h, o in ps:
    lines += [f"$d = $w.Documents.Open('{h}')",
              "$d.PageSetup.TopMargin=30; $d.PageSetup.BottomMargin=30; $d.PageSetup.LeftMargin=42; $d.PageSetup.RightMargin=42",
              "$d.PageSetup.PaperSize = 7",
              f"$d.SaveAs2('{o}.docx', 16)",
              f"$d.ExportAsFixedFormat('{o}.pdf', 17)",
              "$d.Close($false)"]
lines.append("$w.Quit()")
p = os.path.join(SCR, "conv.ps1")
open(p, "w", encoding="utf-8-sig").write("\n".join(lines))
r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", p], capture_output=True, text=True)
print(r.stdout, r.stderr)
for _, o in ps:
    for e in (".docx", ".pdf"):
        print(o + e, os.path.exists(o + e))
