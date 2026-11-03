exec(open('match3.py',encoding='utf-8').read().split("print('=== СТРОКИ")[0].replace("for ri in sorted(assign):","for ri in []:"))
import openpyxl,copy
from openpyxl.styles import PatternFill,Font,Alignment
def money(x): return f"{x:,.0f}".replace(',',' ')
def d(x): return x.strftime('%d.%m.%Y')
byno={r['№']:ri for ri,r in enumerate(rows)}
res={}
def glines(g,label=None):
    out=[]
    for p in g['ps']:
        out.append(f"{d(p['date'])} — {money(p['sum'])} ₽"+(f" ({label})" if label else '')+(' [на р/с ИП]' if p['acc']=='ИП' else ''))
    return out
SURE={100:'точно: в платеже номер этого УПД/счёта',80:'точно: в платеже № этой заявки или фамилия водителя',
      50:'вероятно: тот же заказчик и та же сумма (номер счёта в платеже другой или не указан)',
      30:'вероятно, частично: тот же заказчик, сумма = 30–70 % заявки'}
for ri,lst in assign.items():
    paid=0;lines=[];sure=[];ip=False
    for gid,rs,sc in lst:
        g=G[gid];paid+=g['total']
        inv=g['inv']; lab=None
        if inv and inv[0]!='З': lab='счёт '+inv[0]+inv[1]
        elif inv: lab='заявка '+inv[1]
        lines+=glines(g,lab)
        base=sc+5 if g['acc']=='ИП' else sc
        sure.append(SURE.get(base,'вероятно'))
        if g['acc']=='ИП': ip=True
    res[ri]=dict(paid=paid,lines=lines,sure='; '.join(sorted(set(sure))),comment='',ip=ip)
# ---- ручные разборы сложных клиентов ----
def ps_where(sub,payer):
    return [p for p in pays if sub in p['purp'].upper() and payer in p['payer'].upper() and p['acc']=='ВЛ']
def line(p,lab): return f"{d(p['date'])} — {money(p['sum'])} ₽ ({lab})"
az538=ps_where('538','АЗИМУТ')[0]; s38=ps_where('S38','АЗИМУТ')[0]; s39=ps_where('S39','АЗИМУТ')[0]; s40=ps_where('S40','АЗИМУТ')[0]
p238=ps_where('№238','АЗИМУТ')
AZ_NOTE='Азимут платил по счетам 538/539 (предоплата 500 000 одной суммой) и S38/S39 (по 300 000) — это старые счета, которые потом заменены УПД П59/П60. Вместе 1 100 000 = две перевозки по 550 000. Какая половина к какому рейсу — моё допущение.'
res[byno[104]]=dict(paid=550000,lines=[f"{d(az538['date'])} — 250 000 ₽ (половина предоплаты 500 000 по счетам 538 и 539)",line(s38,'счёт S38')],sure='вероятно: номера счетов старые (S38, 538/539), суммы сходятся',comment=AZ_NOTE,ip=False)
res[byno[115]]=dict(paid=550000,lines=[f"{d(az538['date'])} — 250 000 ₽ (половина предоплаты 500 000 по счетам 538 и 539)",line(s39,'счёт S39')],sure='вероятно: номера счетов старые (S39, 538/539), суммы сходятся',comment=AZ_NOTE,ip=False)
res[byno[101]]=dict(paid=150000,lines=[line(s40,'предоплата по счёту S40')],sure='вероятно: S40 — счёт той же серии от 30.06 (S38–S40 вы назвали ошибочными), рейс 24.06 на 550 000',comment='Пришла только предоплата 150 000 по счёту S40. Доплаты 400 000 в выписках нет.',ip=False)
res[byno[318]]=dict(paid=550000,lines=[line(p,'счёт 238 от 10.09') for p in p238],sure='вероятно: счёт 238 от 10.09 — в один день с УПД 44 (10.09), в сумме 550 000',comment='',ip=False)
S37='Платёж 250 000 по счёту S37 от 24.06 (пришёл 07.07) отнесён к строке Косачкова (погрузка 22.06). У Азимута две перевозки по 250 000 в июне (Виноградов 18.06 и Косачков 22.06) — может быть, наоборот. Вторая из них в выписке не оплачена.'
res[byno[103]]['comment']=S37
res[byno[95]]=dict(paid=0,lines=[],sure='',comment=S37,ip=False)
am=[p for p in pays if 'АЙМАСТЕР' in p['payer'].upper() and re.search(r'№(39|40)',p['purp'])]
AM='АйМастер оплатил счета 39, 40, 41 от 20.07 тремя платежами: '+'; '.join(line(p,'счёт '+re.search(r'№([\d,]+)',p['purp']).group(1)) for p in am)+'. Всего 418 000 = 127 000 + 236 000 + 55 000 — три заявки 15/10, 15/11, 15/13 оплачены полностью.'
for no,amt,inv in ((148,127000,'39'),(152,236000,'40'),(151,55000,'41')):
    res[byno[no]]=dict(paid=amt,lines=[f'по счёту {inv} от 20.07 (общие платежи 21.07, 15.09, 15.10)'],sure='точно: в платежах номера счетов 39, 40, 41, сумма трёх сходится',comment=AM,ip=False)
ag=[p for p in pays if 'АГАМА' in p['payer'].upper() and '254' in p['purp']][0]
res[byno[296]]=dict(paid=ag['sum'],lines=[line(ag,'счёт 254 от 23.09')],sure='вероятно: тот же заказчик и та же сумма, но в платеже счёт 254, а у нас УПД 251',comment='Проверить: может, счёт 254 — к другой перевозке Агамы.',ip=False)
res[byno[73]]['comment']='Все три платежа — по счёту П15 от 22.06, а сам счёт выставлен на 55 000 (так в назначении), в заявке 731 — 150 000. Проверить: счёт на часть суммы или вторая часть пришла другим счётом/на Альфа-Банк.'
res[byno[185]]['comment']='По вашей пометке в реестре: штраф, к оплате 20 000 — клиент так и заплатил (17 500 + 2 500). Если штраф признан, долга нет.'
used_manual={az538['id'],s38['id'],s39['id'],s40['id'],ag['id']}|{p['id'] for p in p238}|{p['id'] for p in am}
# ---- статусы и комментарии ----
for ri,r in enumerate(rows):
    x=res.setdefault(ri,dict(paid=0,lines=[],sure='',comment='',ip=False))
    target=r['Сумма УПД, ₽'] or r['Стоимость заявки, ₽']
    x['target']=target
    st=str(r['Статус сверки'] or '')
    c=[]
    if x['paid']==0:
        twins=[rj for rj,q in enumerate(rows) if rj!=ri and q['№ заявки']==r['№ заявки'] and r['№ заявки'] not in (None,'б/н','1') and same_cust(q['Заказчик'],r['Заказчик'])]
        paid_tw=[rows[rj]['№'] for rj in twins if res.get(rj,{}).get('paid')]
        if 'версия заявки' in st or 'УПД привязан к заявке в строке' in st or paid_tw:
            x['status']='версия / дубль'
            if paid_tw: c.append(f'Это версия той же заявки — оплата учтена в строке № {", ".join(map(str,paid_tw))}.')
            else: c.append('Версия заявки (см. «Статус сверки») — оплату смотреть в основной строке.')
        elif 'лишн' in str(r['Примечание'] or '').lower():
            x['status']='строка лишняя'
        else:
            x['status']='оплата не найдена'
            ld=dt(r['Дата погрузки']) or dt(r['Дата заявки'])
            if ld and ld>=datetime.date(2026,10,1): c.append('Перевозка октябрьская — оплата, возможно, ещё впереди.')
            if not target: c.append('В строке нет суммы — сверять не с чем.')
    else:
        diff=x['paid']-(target or 0)
        if not target: x['status']='оплачено (сумма заявки неизвестна)'
        elif abs(diff)<1: x['status']='оплачено полностью'
        elif diff<0: x['status']='оплачено частично'; c.append(f'Не доплачено {money(-diff)} ₽.')
        else: x['status']='переплата'; c.append(f'Пришло больше на {money(diff)} ₽ — проверить, не оплата ли это ещё одной перевозки.')
        if r['Сумма УПД, ₽'] and r['Стоимость заявки, ₽'] and abs(r['Сумма УПД, ₽']-r['Стоимость заявки, ₽'])>=1:
            c.append(f'Сверено с суммой УПД ({money(r["Сумма УПД, ₽"])}), в заявке {money(r["Стоимость заявки, ₽"])}.')
        if x['ip']: c.append('Деньги пришли на р/с ИП Шерстов (Точка …0066), а не на ООО ВЛ — возможно, перевозку закрывали от ИП.')
    x['comment']=' '.join([x['comment']]+c).strip()
# ---- запись ----
wb=openpyxl.load_workbook('C:/РАБОТА/Заявки ВЛ и УПД — вариант 6.xlsx')
ws=wb.worksheets[0]
H=['Оплачено, ₽','Оплаты (дата — сумма)','Остаток долга, ₽','Статус оплаты','Насколько уверен','Комментарий по оплате']
W=[12,40,12,20,30,60]
from openpyxl.utils import get_column_letter as L
c0=23
hdr=ws.cell(1,1)
for i,(h,w) in enumerate(zip(H,W)):
    c=ws.cell(1,c0+i,h); c.font=copy.copy(hdr.font); c.fill=copy.copy(hdr.fill); c.alignment=copy.copy(hdr.alignment); c.border=copy.copy(hdr.border)
    ws.column_dimensions[L(c0+i)].width=w
FILL={'оплачено полностью':'C6EFCE','оплачено частично':'FFEB9C','переплата':'F8CBAD','оплата не найдена':'FFC7CE','версия / дубль':'EDEDED','строка лишняя':'EDEDED','оплачено (сумма заявки неизвестна)':'C6EFCE'}
cnt=collections.Counter()
for ri,r in enumerate(rows):
    x=res[ri];R=r['_row'];cnt[x['status']]+=1
    vals=[x['paid'] or None,'\n'.join(x['lines']) or None,(max(x['target']-x['paid'],0) if x['target'] and x['status'] not in ('версия / дубль','строка лишняя') else None),x['status'],x['sure'] or None,x['comment'] or None]
    for i,v in enumerate(vals):
        c=ws.cell(R,c0+i,v); src=ws.cell(R,18)
        c.font=copy.copy(src.font); c.border=copy.copy(src.border); c.alignment=Alignment(wrap_text=True,vertical='top')
        if i in (0,2): c.number_format='# ##0'
    ws.cell(R,c0+3).fill=PatternFill('solid',fgColor=FILL.get(x['status'],'FFFFFF'))
    if x['ip']: ws.cell(R,c0).fill=PatternFill('solid',fgColor='E4DFEC')
ws.auto_filter.ref=f"A1:{L(c0+len(H)-1)}{ws.max_row}"
print(cnt)
# ---- лист: оплаты без заявки ----
usedp={p['id'] for gid in usedg for p in G[gid]['ps']}|used_manual
skip=re.compile(r'БАНК|СБЕРБАНК|ТБАНК|ВОЗВРАТ',re.I)
ws2=wb.create_sheet('Оплаты без заявки (Claude)',1)
ws2.append(['Дата поступления','Сумма, ₽','Плательщик','ИНН','Назначение платежа','Есть ли у заказчика строки в таблице'])
for i in range(1,7):
    c=ws2.cell(1,i); c.font=copy.copy(hdr.font); c.fill=copy.copy(hdr.fill); c.alignment=Alignment(wrap_text=True,vertical='center')
n2=0;s2=0
for p in pays:
    if p['acc']!='ВЛ' or p['id'] in usedp or skip.search(p['payer']): continue
    has=[str(r['№']) for r in rows if same_cust(r['Заказчик'],p['payer'])]
    ws2.append([d(p['date']),p['sum'],p['payer'],p['inn'],p['purp'],('да, строки № '+', '.join(has[:12])+(' …' if len(has)>12 else '')) if has else 'нет'])
    ws2.cell(ws2.max_row,2).number_format='# ##0'; n2+=1; s2+=p['sum']
    for i in range(1,7): ws2.cell(ws2.max_row,i).alignment=Alignment(wrap_text=True,vertical='top')
for col,w in zip('ABCDEF',(12,12,34,13,80,26)): ws2.column_dimensions[col].width=w
ws2.freeze_panes='A2'; ws2.auto_filter.ref=f'A1:F{ws2.max_row}'
print('без заявки',n2,s2)
# ---- пояснения ----
wp=wb['Пояснения']
paid_rows=sum(1 for x in res.values() if x['paid'])
debt=sum(max((x['target'] or 0)-x['paid'],0) for x in res.values() if x['status']=='оплачено частично')
txt=['',
 'Вариант 7 (24.10.2026): основа — вариант 6, его значения не менялись. Добавлена сверка с банковскими выписками (колонки W–AB, справа).',
 'Выписки: Банк Точка, р/с ООО ВЛ …8386 и р/с ИП Шерстов …0066, с 01.01 по 24.10.2026 (файлы kl_to_1c_… в C:\\РАБОТА).',
 'ВНИМАНИЕ: выписки по Альфа-Банку (р/с ООО ВЛ …5142, он стоит в бланке заявки с клиентом) не было — если клиент платил туда, здесь будет «оплата не найдена».',
 'Как сверял: платежи одного клиента по одному счёту сложены (предоплата + доплата). Потом ищу в назначении номер УПД/счёта, № заявки или фамилию водителя;',
 'если их нет — тот же заказчик и та же сумма (или 30/50/70 % — частичная оплата) в разумный срок после погрузки. Колонка «Насколько уверен» — по чему нашёл.',
 'Если у строки есть сумма УПД — сравниваю оплату с ней, иначе со стоимостью заявки. Сиреневая ячейка «Оплачено» — деньги пришли на р/с ИП, а не на ООО ВЛ.',
 f'Итого: строк с найденной оплатой {paid_rows} из {len(rows)}. ' + ', '.join(f'{k} — {v}' for k,v in cnt.most_common()) + f'. Недоплата по частично оплаченным — {money(debt)} ₽.',
 f'Лист «Оплаты без заявки (Claude)» — {n2} поступлений на р/с ООО ВЛ на {money(s2)} ₽, которые не удалось привязать к строке таблицы (заявки нет или номер не совпал).',
]
for t in txt: wp.append([t])
wb.save('C:/РАБОТА/Заявки ВЛ и УПД — вариант 7.xlsx'); print('saved', paid_rows, money(debt))
import pickle; pickle.dump(res,open('res.pkl','wb'))
