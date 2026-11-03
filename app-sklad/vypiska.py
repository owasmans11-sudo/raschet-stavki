# Банковская выписка в формате 1С (1CClientBankExchange — так выгружают и Точка, и Альфа):
# разбор файла → поступления на наш счёт → предложения, к какому грузу относится платёж.
# Сравнение названий фирм — из tools/sverka_oplat/match.py (сверка оплат, вариант 7).
import re
from datetime import date, timedelta

# наши счета → компания (по выпискам в C:\РАБОТА, 2026-11-02); незнакомый счёт — по виду: 40802 = ИП
ACCOUNTS = {'40702810420000248386': 'ООО ВЛ',   # Точка
            '40802810920000780066': 'ИП Шерстов',  # Точка
            '40702810323080005142': 'ООО ВЛ',   # Альфа
            '40702810323080005171': 'ООО ВЛ',   # Альфа
            '40802810123080005611': 'ИП Шерстов'}  # Альфа
OWN_INN = {'3812166710'}                        # ООО «Восточная логистика» — переводы между своими не оплата
OWN_NAMES = ('ВОСТОЧНАЯ ЛОГИСТИКА', 'ШЕРСТОВ')
EARLY_DAYS = 30                                 # платёж может прийти раньше создания груза (предоплата)
SURE_EARLY_DAYS = 10                            # раньше этого — только «проверь», не «уверенно»


class NeVypiska(Exception):
    pass


def company_of(acc):
    return ACCOUNTS.get(acc) or ('ИП Шерстов' if acc.startswith('40802') else 'ООО ВЛ')


def iso(s):
    m = re.match(r'(\d{1,2})\.(\d{1,2})\.(\d{4})', s or '')
    return f'{m[3]}-{int(m[2]):02d}-{int(m[1]):02d}' if m else ''


def parse(data):
    """Байты файла → (наш р/с, список поступлений). Исходящие и переводы от своих фирм пропускаем."""
    head = data[:400].decode('cp1251', 'replace')
    if not head.startswith('1CClientBankExchange'):
        raise NeVypiska('Это не выписка в формате 1С (в начале файла нет «1CClientBankExchange»). '
                        'В банке выгрузите выписку «для 1С» — файл .txt.')
    text = data.decode('cp866' if 'Кодировка=DOS' in head else 'cp1251', 'replace')
    acc, docs, cur = '', [], None
    for line in text.splitlines():
        if line.startswith('РасчСчет=') and not acc:
            acc = line.split('=', 1)[1].strip()
        if line.startswith('СекцияДокумент'):
            cur = {}
        elif line.strip() == 'КонецДокумента':
            if cur is not None:
                docs.append(cur)
            cur = None
        elif cur is not None and '=' in line:
            k, v = line.split('=', 1)
            cur[k.strip()] = v.strip()
    if not acc:
        raise NeVypiska('В выписке не указан расчётный счёт')
    pays, own = [], 0
    for o in docs:
        if o.get('ПолучательСчет') != acc:
            continue                              # списание с нашего счёта
        payer = o.get('Плательщик1') or o.get('Плательщик') or ''
        inn = o.get('ПлательщикИНН', '')
        if inn in OWN_INN or any(n in payer.upper() for n in OWN_NAMES) or o.get('ПлательщикСчет') in ACCOUNTS:
            own += 1
            continue
        dt = iso(o.get('ДатаПоступило') or o.get('Дата'))
        s = round(float((o.get('Сумма') or '0').replace(',', '.')), 2)
        num = o.get('Номер', '')
        pays.append({'key': f'{acc}|{num}|{dt}|{s:.2f}|{inn}', 'acc': acc, 'company': company_of(acc),
                     'num': num, 'dt': dt, 'sum': s, 'payer': payer, 'inn': inn,
                     'purp': o.get('НазначениеПлатежа', '')})
    return acc, pays, own


SERVICE = re.compile(r'процент|кэшбэк|кешбэк|вознагражд|комисси|внесение|^\s*возврат', re.I)


def not_client(p):
    """Явно не оплата клиента: проценты и кэшбэк банка, возврат комиссии, внесение наличных, возврат наших платежей."""
    return bool(SERVICE.search(p['purp']) and ('БАНК' in p['payer'].upper() or p['purp'].strip().lower().startswith('возврат')))


# ---------- клиент: то же сравнение названий, что в сверке оплат ----------
LAT = str.maketrans('ABCEHKMOPTXYabcekmopxy', 'АВСЕНКМОРТХУавсекморху')
STOP = {'ООО', 'ОБЩЕСТВО', 'С', 'ОГРАНИЧЕННОЙ', 'ОТВЕТСТВЕННОСТЬЮ', 'ИП', 'ИНДИВИДУАЛЬНЫЙ', 'ПРЕДПРИНИМАТЕЛЬ', 'АО', 'ПАО',
        'ЗАО', 'ТК', 'ТЛК', 'ТЭК', 'ГК', 'ГРУППА', 'КОМПАНИЙ', 'КОМПАНИЯ', 'ТРАНСПОРТНАЯ', 'ЛОГИСТИЧЕСКАЯ', 'ТД', 'ТОРГОВЫЙ',
        'ДОМ', 'НПК', 'ПТО', 'ПРОИЗВОДСТВЕННО', 'ТОРГОВОЕ', 'ОБЪЕДИНЕНИЕ', 'ПРОИЗВОДСТВЕННОЕ', 'ПРЕДПРИЯТИЕ', 'В', 'Г',
        'ФИЛИАЛ', 'БАНК'}
GEN = {'ЛОГИСТИКА', 'ЛОГИСТИК', 'ТРАНС', 'ГРУПП', 'ЭКСПРЕСС', 'СЕРВИС', 'ТРАНСПОРТ', 'МАГИСТРАЛЬ', 'КОМПАНИЯ', 'ЛОГИСТИКС'}


def toks(name):
    s = str(name or '').upper().translate(LAT).replace('Ё', 'Е')
    s = re.sub(r'Р/С.*', '', s)
    return [x for x in re.findall(r'[А-Я0-9]+', s) if x not in STOP and len(x) > 1]


def same_cust(a, b):
    ta, tb = toks(a), toks(b)
    if not ta or not tb:
        return False
    ja, jb = ''.join(ta), ''.join(tb)
    if ja == jb:
        return True
    sa, sb = sorted((ja, jb), key=len)
    if len(sa) >= 6 and sa not in GEN and sb.startswith(sa):
        return True
    return ta[0] == tb[0] and len(ta[0]) >= 6 and ta[0] not in GEN and (len(ta) == 1 or len(tb) == 1 or ta[1] == tb[1])


def schet_digits(s):
    m = re.findall(r'\d+', str(s or ''))
    return str(int(m[-1])) if m else ''


def purp_numbers(purp):
    """Номера счетов/заявок из назначения: «по счёту № 123», «сч.45», «заявка №7 от …»."""
    out = set()
    for m in re.finditer(r'(?:сч[её]т\w*|сч\.?|с/ф|заявк\w*|№)\s*(?:на оплату\s*)?№?\s*([A-Za-zА-Яа-я]{0,3}[-\s]?\d{1,7})(?![\d.,/])',
                         purp, re.I):
        out.add(schet_digits(m[1]))
    return out


# ---------- сопоставление ----------
def propose(pays, gruzy, inn_of):
    """pays — платежи с остатком 'rest' (не привязанная часть), по дате; gruzy — грузы с долгом 'debt'.
    inn_of(груз) → ИНН заказчика из справочника. Возвращает для каждого платежа kind (sure/check/none), links, cands."""
    debt = {g['id']: g['debt'] for g in gruzy}
    out = []
    for p in sorted(pays, key=lambda x: (x['dt'], x['id'])):
        pnums = purp_numbers(p['purp'])
        # грузы и другой фирмы: клиент мог заплатить не на тот счёт — такие пары только «проверь» (ниже)
        mine = [g for g in gruzy
                if not g['created'] or p['dt'] >= (date.fromisoformat(g['created']) - timedelta(days=EARLY_DAYS)).isoformat()]

        def client(g):
            gi = inn_of(g)
            return (gi and p['inn'] and gi == p['inn']) or same_cust(g['client'], p['payer'])

        def inv(g):
            d = schet_digits(g.get('schet'))
            return bool(d) and d in pnums
        open_ = [g for g in mine if debt[g['id']] > 0.5]
        cli = [g for g in open_ if client(g)]
        rest = p['rest']
        eq = lambda a, b: abs(a - b) < 0.5
        res = {'p': p, 'kind': 'none', 'links': [], 'cands': [], 'why': ''}
        one = [g for g in open_ if (client(g) and (eq(debt[g['id']], rest) or inv(g))) or (inv(g) and eq(debt[g['id']], rest))]
        if len(one) == 1:
            g = one[0]
            res.update(kind='sure' if eq(debt[g['id']], rest) or rest < debt[g['id']] else 'check',
                       links=[{'gruz_id': g['id'], 'sum': min(rest, debt[g['id']])}],
                       why='клиент и сумма' if client(g) and eq(debt[g['id']], rest) else 'номер счёта' if inv(g) else 'клиент, номер счёта')
            if res['kind'] == 'sure' and not eq(debt[g['id']], rest):
                res['why'] += ' (часть суммы)'
        elif not one and cli:
            group = _subset(cli, rest, debt) if len(cli) > 1 else None
            if group:
                res.update(kind='sure', links=[{'gruz_id': g['id'], 'sum': debt[g['id']]} for g in group],
                           why=f'клиент, один платёж за {len(group)} груза')
            else:
                g = cli[0]
                res.update(kind='check', links=[{'gruz_id': g['id'], 'sum': min(rest, debt[g['id']])}],
                           why='клиент совпал, сумма нет' + (' — оплата частями?' if rest < debt[g['id']] else ''))
        elif len(one) > 1:
            g = one[0]
            res.update(kind='check', links=[{'gruz_id': g['id'], 'sum': min(rest, debt[g['id']])}],
                       why=f'подходят {len(one)} груза — выбери')
        else:
            same = [g for g in open_ if eq(debt[g['id']], rest) and g['company'] == p['company']]
            if len(same) == 1:
                g = same[0]
                res.update(kind='check', links=[{'gruz_id': g['id'], 'sum': rest}], why='только сумма совпала, клиент другой')
        other = [l for l in res['links'] if next(g for g in gruzy if g['id'] == l['gruz_id'])['company'] != p['company']]
        if other:
            res.update(kind='check', why=res['why'] + ' — деньги пришли на другую фирму')
        rano = [l for l in res['links'] if (g := next(g for g in gruzy if g['id'] == l['gruz_id']))['created']
                and p['dt'] < (date.fromisoformat(g['created']) - timedelta(days=SURE_EARLY_DAYS)).isoformat()]
        if rano and res['kind'] == 'sure':
            res.update(kind='check', why=res['why'] + ' — оплата сильно раньше даты груза')
        res['cands'] = [g['id'] for g in (one or cli or [g for g in open_ if g['company'] == p['company']])]
        if res['kind'] == 'sure':
            for l in res['links']:
                debt[l['gruz_id']] -= l['sum']
        out.append(res)
    return out


def _subset(cands, total, debt, max_n=4):
    """Ровно один набор грузов клиента (2–4 шт.), чьи долги в сумме = платёж; иначе None."""
    from itertools import combinations
    cands = cands[:12]
    found = []
    for n in range(2, min(max_n, len(cands)) + 1):
        for c in combinations(cands, n):
            if abs(sum(debt[g['id']] for g in c) - total) < 0.5:
                found.append(c)
                if len(found) > 1:
                    return None
    return list(found[0]) if found else None
