exec(open('match.py',encoding='utf-8').read().split("pays=[]")[0])
import json
pays=json.load(open('pays.json',encoding='utf-8'))
NUMINV=re.compile(r'(?:СЧ[ЕЁ]?Т[А-Я]*|СЧ\.|СЧ|УПД|С/Ф|СЧ-Ф|АКТ[А-Я]*)\s*(?:НА ОПЛАТУ)?\s*(?:№|N|NO)?\s*(\d{1,4})(?![\d.,/])')
for p in pays:
    for n in NUMINV.findall(p['purp'].upper()): p.setdefault('numinv',[]).append(('',str(int(n))))
for p in pays: p['date']=dt(p['date'].replace('-','.')) if False else datetime.date.fromisoformat(p['date']); p['inv']=set(map(tuple,p['inv']))|set(map(tuple,p.get('numinv',[])))
def surname(v):
    v=str(v or '').strip()
    if not v or v=='—': return None
    w=v.split()[0].upper().replace('Ё','Е')
    return w if len(w)>=4 and w not in ('ВОДИТЕЛЬ','НЕТ') else None
def zayavka_nums(z):
    z=str(z or '')
    z=re.sub(r'\d{1,2}[./]\d{1,2}[./]\d{2,4}','',z)
    z=re.sub(r'(СЧ[ЕЁ]Т[А-Я]*|СЧ\.?)\s*[А-ЯA-Z]?\d+','',z.upper())
    return [n for n in re.findall(r'\d{3,}',z) if n not in ('2025','2026')]
cand=[]  # (score,row_idx,pay_id,reasons)
for ri,r in enumerate(rows):
    cost=r['Стоимость заявки, ₽']
    rd=dt(r['Дата погрузки']) or dt(r['Дата заявки']) or dt(r['Дата УПД'])
    upd=norm_inv(r['№ УПД']) if r['№ УПД'] else None
    sn=surname(r['Водитель']); zn=zayavka_nums(r['№ заявки'])
    for p in pays:
        P=p['purp'].upper().replace('Ё','Е')
        reasons=[];score=0
        cm=same_cust(r['Заказчик'],p['payer'])
        if upd and upd in p['inv']: score+=5;reasons.append(f'в платеже счёт/УПД {r["№ УПД"]}')
        if sn and sn in P: score+=4;reasons.append(f'в платеже водитель {sn.title()}')
        for n in zn:
            if re.search(r'(?<!\d)'+n+r'(?!\d)',P) and not re.search(r'НДС[^0-9]{0,20}'+n,P):
                score+=4;reasons.append(f'в платеже заявка № {n}');break
        if cm: score+=3;reasons.append('плательщик = заказчик')
        amt=None
        if cost:
            if abs(p['sum']-cost)<1: score+=2;amt='full';reasons.append('сумма = стоимости')
            elif r['Сумма УПД, ₽'] and abs(p['sum']-r['Сумма УПД, ₽'])<1: score+=2;amt='full';reasons.append('сумма = УПД')
            elif p['sum']<cost: amt='part'
        if rd and p['date']:
            dd=(p['date']-rd).days
            if dd<-60 or dd>200: continue
        else: dd=None
        other_inv = upd and p['inv'] and upd not in p['inv']
        if other_inv and not any(k in ' '.join(reasons) for k in ('водитель','заявка №')): continue
        strong=score>=4 and any(k in ' '.join(reasons) for k in ('счёт/УПД','водитель','заявка №'))
        ok=(strong and (cm or amt=='full')) or (cm and amt=='full' and dd is not None and -15<=dd<=150) or (upd and upd in p['inv'] and cm)
        if ok: cand.append((score,-abs(dd or 0),ri,p['id'],reasons))
cand.sort(reverse=True)
used={};assign=collections.defaultdict(list)
# первый проход: сильные связи (номер счёта/водитель/заявка) — платёж может быть частичным, несколько на строку
for sc,_,ri,pid,rs in cand:
    if pid in used: continue
    r=rows[ri];cost=r['Стоимость заявки, ₽'] or 0
    got=sum(pays[x]['sum'] for x,_ in assign[ri])
    weak=not any(k in ' '.join(rs) for k in ('счёт/УПД','водитель','заявка №'))
    if weak and assign[ri]: continue
    if cost and got>=cost-1 and weak: continue
    used[pid]=ri;assign[ri].append((pid,rs))
json.dump({str(k):v for k,v in assign.items()},open('assign.json','w',encoding='utf-8'),ensure_ascii=False)
paid=sum(1 for r in assign);print('строк с оплатой',paid,'из',len(rows),'платежей привязано',len(used))
for ri in sorted(assign)[:400]:
    r=rows[ri];s=sum(pays[p]['sum'] for p,_ in assign[ri])
    print(r['№'],r['Заказчик'][:22],r['№ заявки'],r['Стоимость заявки, ₽'],r['№ УПД'],'| опл',s,[ (pays[p]['acc'],str(pays[p]['date']),pays[p]['sum'],'; '.join(rs)) for p,rs in assign[ri]])
print('=== НЕ ПРИВЯЗАНЫ (ВЛ, с 01.04)')
for p in pays:
    if p['id'] in used or p['acc']!='ВЛ' or p['date']<datetime.date(2026,4,1): continue
    print(p['id'],p['date'],p['sum'],p['payer'][:35],'|',p['purp'][:140])
print('=== НЕПРИВЯЗАННЫЕ, у кого есть строки-заказчики')
for p in pays:
    if p['id'] in used or p['acc']!='ВЛ' or p['date']<datetime.date(2026,4,1): continue
    rs=[r for r in rows if same_cust(r['Заказчик'],p['payer'])]
    if not rs: continue
    print('\n#',p['id'],p['date'],p['sum'],p['payer'][:30],'|',p['purp'][:110])
    for r in rs:
        ri=rows.index(r)
        print('    ',r['№'],r['№ заявки'],r['Дата погрузки'],r['Стоимость заявки, ₽'],r['№ УПД'],r['Сумма УПД, ₽'],str(r['Водитель'])[:15],'опл:',sum(pays[x]['sum'] for x,_ in assign.get(ri,[])))
