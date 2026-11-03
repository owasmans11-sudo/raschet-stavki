import json,sys,glob
out=[]
for f in glob.glob('C:/РАБОТА/kl_to_1c_*.txt'):
    acc=f.split('kl_to_1c_')[1][:20]
    cur=None
    for line in open(f,encoding='cp1251'):
        line=line.rstrip('\r\n')
        if line.startswith('СекцияДокумент'):
            cur={'_acc':acc,'Вид':line.split('=',1)[1]}
        elif line=='КонецДокумента':
            out.append(cur);cur=None
        elif cur is not None and '=' in line:
            k,v=line.split('=',1);cur[k]=v
json.dump(out,open('ops.json','w',encoding='utf-8'),ensure_ascii=False,indent=0)
for acc in set(o['_acc'] for o in out):
    inc=[o for o in out if o['_acc']==acc and o.get('ПолучательСчет')==acc]
    print(acc,len([o for o in out if o['_acc']==acc]),'входящих',len(inc),sum(float(o['Сумма']) for o in inc))
