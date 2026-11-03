exec(open('match2.py',encoding='utf-8').read().split("cand=[]")[0])
# --- группы платежей: один плательщик (ИНН) + один счёт ---
def inv_key(p):
    P=p['purp'].upper()
    m=re.search(r'(?:СЧ[ЕЁ]?Т[А-Я]*|СЧ\.|СЧ(?![А-Я])|СЧ-Ф|УПД|С/Ф|АКТ[А-Я]*)\s*(?:НА ОПЛАТУ)?\s*(?:№|N|NO)?\s*([ПКSАA]?)\s?-?\s?(\d{1,4})(?![\d.,/])',P.translate(LAT).replace('Ё','Е'))
    if m: return (m.group(1).replace('A','А'),str(int(m.group(2))))
    m=re.search(r'ЗАЯВК[А-Я]*\s*(?:№|N)?\s*([0-9А-Я/\-]+)',P)
    if m: return ('З',m.group(1).lstrip('0'))
    return None
groups=collections.OrderedDict()
for p in pays:
    k=inv_key(p)
    gk=(p['acc'],p['inn'] or p['payer'],k) if k else (p['acc'],p['id'])
    groups.setdefault(gk,[]).append(p)
G=[]
for gk,ps in groups.items():
    G.append(dict(key=gk,inv=gk[2] if len(gk)==3 else None,ps=ps,total=sum(p['sum'] for p in ps),payer=ps[0]['payer'],acc=ps[0]['acc'],
                  d1=min(p['date'] for p in ps),purp=' || '.join(p['purp'] for p in ps).upper().replace('Ё','Е'),gid=len(G)))
print('групп',len(G))
def row_info(r):
    upd=norm_inv(r['№ УПД']) if r['№ УПД'] else None
    if upd: upd=(upd[0].replace('S','S'),upd[1])
    return upd,surname(r['Водитель']),zayavka_nums(r['№ заявки']),dt(r['Дата погрузки']) or dt(r['Дата заявки']) or dt(r['Дата УПД'])
cand=[]
for ri,r in enumerate(rows):
    cost=r['Стоимость заявки, ₽']; us=r['Сумма УПД, ₽']
    upd,sn,zn,rd=row_info(r)
    for g in G:
        cm=same_cust(r['Заказчик'],g['payer'])
        rs=[];strong=0
        if upd and g['inv'] and g['inv']==upd and cm: strong=3;rs.append(f'счёт/УПД {r["№ УПД"]}')
        if sn and re.search(r'(?<![А-Я])'+sn,g['purp']): strong=max(strong,2);rs.append(f'водитель {sn.title()}')
        for n in zn:
            if re.search(r'(?<!\d)0*'+n.lstrip('0')+r'(?!\d)',g['purp']) and len(n.lstrip('0'))>=3: strong=max(strong,2);rs.append(f'заявка № {n}');break
        if rd:
            dd=(g['d1']-rd).days
            if dd<-75 or dd>200: continue
        else: dd=30
        tot=g['total']; amt=None
        for v,lab in ((cost,'стоимость'),(us,'сумма УПД')):
            if v and abs(tot-v)<1: amt='full';break
        if not amt and cost:
            for k in (0.3,0.5,0.7): 
                if abs(tot-cost*k)<1: amt='part';break
        if not amt and cost and tot<cost: amt='less'
        if not amt and cost and tot>cost: amt='more'
        # счёт в платеже есть, но другой (а у строки свой УПД) — не наш, если нет водителя/заявки
        if upd and g['inv'] and g['inv'][0]!='З' and g['inv']!=upd and strong<2: continue
        if strong>=3: sc=100
        elif strong==2 and (cm or amt=='full'): sc=80
        elif cm and amt=='full' and -20<=dd<=150: sc=50
        elif cm and amt=='part' and -20<=dd<=60: sc=30
        else: continue
        if g['acc']=='ИП': sc-=5
        cand.append((sc,-abs(dd),ri,g['gid'],rs,amt))
cand.sort(key=lambda x:(x[0],x[1]),reverse=True)
usedg={};assign=collections.defaultdict(list)
for sc,_,ri,gid,rs,amt in cand:
    if gid in usedg: continue
    r=rows[ri];cost=r['Стоимость заявки, ₽'] or r['Сумма УПД, ₽'] or 0
    got=sum(G[x]['total'] for x,_,_ in assign[ri])
    if sc<80 and assign[ri]: continue
    if sc>=80 and assign[ri] and cost and got>=cost-1: continue
    usedg[gid]=ri;assign[ri].append((gid,rs,sc))
print('строк с оплатой',len(assign),'групп привязано',len(usedg))
import pickle;pickle.dump((G,assign,usedg),open('m3.pkl','wb'))
for ri in sorted(assign):
    r=rows[ri];s=sum(G[g]['total'] for g,_,_ in assign[ri])
    print(r['№'],r['Заказчик'][:20],r['№ заявки'],r['Дата погрузки'],r['Стоимость заявки, ₽'],r['№ УПД'],'| опл',s,[(G[g]['acc'],G[g]['inv'],str(G[g]['d1']),G[g]['total'],sc,';'.join(rs)) for g,rs,sc in assign[ri]])
print('=== СТРОКИ БЕЗ ОПЛАТЫ, у которых есть непривязанные платежи того же заказчика')
for ri,r in enumerate(rows):
    if ri in assign: continue
    gs=[g for g in G if g['gid'] not in usedg and same_cust(r['Заказчик'],g['payer'])]
    if not gs: continue
    print('\n*',r['№'],r['Заказчик'][:25],r['№ заявки'],r['Дата погрузки'],r['Стоимость заявки, ₽'],r['№ УПД'],r['Сумма УПД, ₽'],str(r['Водитель'])[:14])
    for g in gs: print('     ',g['acc'],g['inv'],g['d1'],g['total'],'|',g['purp'][:120])
