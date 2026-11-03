import json,re,datetime,collections
ops=json.load(open('ops.json',encoding='utf-8'))
rows=json.load(open('rows.json',encoding='utf-8'))
VL='40702810420000248386'; IP='40802810920000780066'
def dt(s):
    if not s: return None
    m=re.search(r'(\d{1,2})[.,/](\d{1,2})[.,/](\d{2,4})',str(s))
    if not m: return None
    d,mo,y=map(int,m.groups()); y+=2000 if y<100 else 0
    try: return datetime.date(y,mo,d)
    except: return None
LAT=str.maketrans('ABCEHKMOPTXYabcekmopxy','АВСЕНКМОРТХУавсекморху')
STOP={'ООО','ОБЩЕСТВО','С','ОГРАНИЧЕННОЙ','ОТВЕТСТВЕННОСТЬЮ','ИП','ИНДИВИДУАЛЬНЫЙ','ПРЕДПРИНИМАТЕЛЬ','АО','ПАО','ЗАО','ТК','ТЛК','ТЭК','ГК','ГРУППА','КОМПАНИЙ','КОМПАНИЯ','ТРАНСПОРТНАЯ','ЛОГИСТИЧЕСКАЯ','ТД','ТОРГОВЫЙ','ДОМ','НПК','ПТО','ПРОИЗВОДСТВЕННО','ТОРГОВОЕ','ОБЪЕДИНЕНИЕ','ПРОИЗВОДСТВЕННОЕ','ПРЕДПРИЯТИЕ','ООО»','В','Г','ФИЛИАЛ','БАНК'}
def toks(name):
    s=str(name or '').upper().translate(LAT).replace('Ё','Е')
    s=re.sub(r'Р/С.*','',s)
    w=re.findall(r'[А-Я0-9]+',s)
    return [x for x in w if x not in STOP and len(x)>1]
def same_cust(a,b):
    ta,tb=toks(a),toks(b)
    if not ta or not tb: return False
    ja,jb=''.join(ta),''.join(tb)
    if ja==jb: return True
    GEN={'ЛОГИСТИКА','ЛОГИСТИК','ТРАНС','ГРУПП','ЭКСПРЕСС','СЕРВИС','ТРАНСПОРТ','МАГИСТРАЛЬ','КОМПАНИЯ','ЛОГИСТИКС'}
    sa,sb=sorted((ja,jb),key=len)
    if len(sa)>=6 and sa not in GEN and sb.startswith(sa): return True
    return ta[0]==tb[0] and len(ta[0])>=6 and ta[0] not in GEN and (len(ta)==1 or len(tb)==1 or ta[1]==tb[1])
def norm_inv(x):
    s=str(x).upper().translate(LAT).replace(' ','').replace('-','')
    s=s.replace('S','S')
    m=re.match(r'([А-ЯS]*)0*(\d+)',s)
    return (m.group(1),m.group(2)) if m else None
INV_RE=re.compile(r'(?<![A-Za-zА-Яа-я0-9])([ПпКкSsАаAa])\s?[-№]?\s?(\d{1,3})(?![\d.,/])')
def invs(purp):
    out=set()
    for L,n in INV_RE.findall(purp):
        out.add((L.upper().translate(LAT).replace('A','А'),str(int(n))))
    return out
pays=[]
for o in ops:
    if o.get('ПолучательСчет')!=o['_acc']: continue
    if 'ВОСТОЧНАЯ ЛОГИСТИКА' in o['Плательщик1'].upper() or 'ШЕРСТОВ' in o['Плательщик1'].upper(): continue
    p=dict(acc='ВЛ' if o['_acc']==VL else 'ИП',date=dt(o.get('ДатаПоступило') or o['Дата']),sum=float(o['Сумма']),
           payer=o['Плательщик1'],inn=o.get('ПлательщикИНН',''),purp=o['НазначениеПлатежа'],num=o['Номер'],id=len(pays))
    p['inv']=invs(p['purp']); pays.append(p)
json.dump([{**p,'date':str(p['date']),'inv':sorted(p['inv'])} for p in pays],open('pays.json','w',encoding='utf-8'),ensure_ascii=False)
print('платежей',len(pays),collections.Counter(p['acc'] for p in pays))
