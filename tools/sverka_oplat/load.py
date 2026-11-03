import openpyxl,json,re,datetime
wb=openpyxl.load_workbook('C:/РАБОТА/Заявки ВЛ и УПД — вариант 6.xlsx')
ws=wb.worksheets[0]
hdr=[c.value for c in ws[1]]
rows=[]
for i,r in enumerate(ws.iter_rows(min_row=2,values_only=True),start=2):
    d=dict(zip(hdr,r)); d['_row']=i
    for k,v in d.items():
        if isinstance(v,(datetime.datetime,datetime.date)): d[k]=v.strftime('%d.%m.%Y')
    rows.append(d)
json.dump(rows,open('rows.json','w',encoding='utf-8'),ensure_ascii=False,default=str)
print(len(rows), sum(1 for d in rows if d['№ УПД']))
import collections
print(collections.Counter(type(d['Стоимость заявки, ₽']).__name__ for d in rows))
print(collections.Counter(d['Статус сверки'] for d in rows))
