# Печать заявок ВЛ из приложения «Склад».
# Юридический текст и наши реквизиты берутся слово в слово из утверждённых шаблонов «новый дизайн» в корне проекта,
# оформление — tools/vl_style.py (стиль «вариант 3»). Поля заполняются данными груза или фуры; чего нет — пусто, как в бланке.
import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
from vl_style import (BLANK_REQ, DARK, LIGHT, bar, gap, header, keystrip, para, paragraphs,  # noqa: E402
                      parties, run, save, section, section_pair, title)

OUT_DIR = ROOT / 'Заявки из приложения'

# какой шаблон для какого документа и компании
TPL = {
    'zabor': {'ООО ВЛ': 'Заявка с перевозчиком до склада ВЛ (новый дизайн).docx',
              'ИП Шерстов': 'Заявка с перевозчиком до склада ИПШ (новый дизайн).docx'},
    'razvoz': {'ООО ВЛ': 'Заявка с перевозчиком со склада ВЛ (новый дизайн).docx',
               'ИП Шерстов': 'Заявка с перевозчиком со склада ИПШ (новый дизайн).docx'},
    'fura': {'ООО ВЛ': 'Заявка с перевозчиком межгород фура ВЛ (новый дизайн).docx'},
    'klient': {'ООО ВЛ': 'Заявка с клиентом ВЛ (вариант 3).docx',
               'ИП Шерстов': 'Заявка с клиентом ИПШ (новый дизайн).docx',
               'ТК МВЛ': 'Заявка с клиентом по МВЛ (новый дизайн).docx'},
}
KIND_NAME = {'zabor': 'перевозчику забор', 'razvoz': 'перевозчику развоз', 'fura': 'на фуру', 'klient': 'с клиентом'}
MONTHS = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря']


class NetShablona(Exception):
    pass


# ---------- разбор шаблона ----------

def parse_template(name):
    """Из готового шаблона: шапка компании, абзацы условий, наши реквизиты, заголовки сторон, поля раздела 2 (клиент)."""
    ps = [t.strip() for t in paragraphs(ROOT / name)]
    co = dict(brand=ps[0], legal=ps[1].split(' · ')[0], inn=ps[2], ogrn=ps[3],
              phone=ps[4].removeprefix('Тел.:').strip(), email=ps[5])
    h = next(i for i in range(len(ps) - 1) if ps[i + 1] in ('12. Заказчик', '16. Заказчик') and len(ps[i]) < 40)
    req, k = [], h + 2
    while not ps[k].startswith('_______________ /'):
        if ps[k]:
            req.append(ps[k])
        k += 1
    own = [l for l in req if l not in BLANK_REQ]
    start = next(i for i, t in enumerate(ps) if t.startswith('10. Условия перевозки') or t.startswith('9. Порядок расчетов'))
    after = lambda label: next((ps[i + 1] for i, t in enumerate(ps) if t == label and ps[i + 1] and not re.match(r'^\d\. ', ps[i + 1])), '')
    return dict(co=co, legal=[t for t in ps[start:h] if t], own=own, own_left=req[0] not in BLANK_REQ,
                titles=(ps[h], ps[h + 1]),
                email=after('Адрес электронной почты и № факсов и телефонов (в т.ч. мессенджеров)'),
                postal=after('Почтовый адрес для обмена оригиналами документов'))


def template_for(kind, company):
    name = TPL[kind].get(company or 'ООО ВЛ')
    if not name:
        have = ', '.join(TPL[kind])
        raise NetShablona(f'Нет шаблона заявки «{KIND_NAME[kind]}» для «{company}» — есть только для: {have}. '
                          f'Поменяйте компанию в грузе или попросите сделать шаблон.')
    return parse_template(name)


# ---------- мелочи ----------

def money(v):
    return f'{round(v):,}'.replace(',', ' ') if v else ''


def n(v, d=2):
    if v in (None, ''):
        return ''
    s = f'{v:,.{d}f}'.replace(',', ' ').replace('.', ',')
    return s.rstrip('0').rstrip(',') if ',' in s else s


def dmy(iso):
    return '.'.join(reversed(iso.split('-'))) if iso else ''


def date_words(d=None):
    d = d or date.today()
    return f'«{d.day:02d}» {MONTHS[d.month - 1]} {d.year} г.'


def city(addr):
    return re.sub(r'\s*\(.*', '', (addr or '').split(',')[0]).strip()


def cargo_text(kg=None, m3=None, places=None, name=''):
    parts = [name, f'{n(kg, 0)} кг' if kg else '', f'{n(m3)} м³' if m3 else '', f'{n(places, 0)} мест' if places else '']
    return ', '.join(p for p in parts if p)


def blank_with_name(name):
    return [f'Наименование: {name}'] + BLANK_REQ[1:] if name else BLANK_REQ


def firm(con, firm_id):
    r = con.execute('SELECT * FROM kontragent WHERE id=?', (firm_id,)).fetchone() if firm_id else None
    return dict(r) if r else None


def firm_req(f, fallback_name=''):
    """Реквизиты стороны для блока подписей: что есть — заполняем, чего нет — пустая строка, как в бланке."""
    if not f:
        return blank_with_name(fallback_name)
    blank = lambda i: BLANK_REQ[i].split(':', 1)[1]
    val = lambda v, i: f' {v}' if v else blank(i)
    inn_kpp = ' / '.join(x for x in (f['inn'], f['kpp']) if x)
    return [f'Наименование:{val(f["name"] or fallback_name, 0)}', f'Юр. адрес:{val(f["address"], 1)}',
            f'Почт. адрес:{val(f["post_address"], 2)}', f'ИНН / КПП:{val(inn_kpp, 3)}', f'ОГРН:{val(f["ogrn"], 4)}',
            f'р/с:{val(f["rs"], 5)}', f'Банк:{val(f["bank"], 6)}',
            f'к/с: {f["ks"] or "______________________"} БИК: {f["bik"] or "__________"}',
            f'Эл. почта:{val(f["email"], 8)}', f'Тел.:{val(f["phone"], 9)}']


# ---------- оформление условий (как в tools/build_templates_v3.py) ----------

def carrier_legal(legal):
    body, intro = [], True
    note = f'<w:shd w:val="clear" w:color="auto" w:fill="{LIGHT}"/>'
    for i, t in enumerate(legal):
        if i == 0:
            m = re.match(r'^(10\.\s*Условия перевозки:)\s*(.*)$', t, re.S)
            body.append(bar(m.group(1) if m else t))
            if m and m.group(2):
                body.append(para(run(m.group(2), 16, True, DARK), 'both', extra=note))
            continue
        if re.match(r'^1\.\s', t):
            intro = False
            body.append(gap(40))
        body.append(para(run(t, 16, True, DARK), 'both', extra=note) if intro else para(run(t, 15), 'both', after=40))
    return body


def client_legal(legal):
    body = []
    for t in legal:
        if re.match(r'^12\.\d\.', t) and len(t) < 60:
            body.append(para(run(t, 17, True, DARK), before=60, after=20, keep=True))
        elif re.match(r'^\d{1,2}\.\D', t) and len(t) < 60:
            m = re.match(r'^(\d{1,2})\.\s*(.*)$', t)
            body.append(bar(f'{m.group(1)}. {m.group(2)}'))
        elif t.startswith('14.'):
            body.append(para(run(t, 16, True, DARK), 'both', before=140, after=40))
        else:
            body.append(para(run(t, 15), 'both', after=40))
    return body


# ---------- документы ----------

def carrier_doc(tpl, v):
    """Договор-заявка перевозчику. v — значения полей (пустое остаётся пустым)."""
    co = tpl['co']
    body = [header(co),
            title('ДОГОВОР-ЗАЯВКА', f'об организации перевозок груза автомобильным транспортом № {v.get("nomer") or "______"} '
                                    f'от {date_words()}'),
            keystrip([('Маршрут', f'{v.get("from_city") or "_____________"} → {v.get("to_city") or "_____________"}'),
                      ('Загрузка → разгрузка', f'{dmy(v.get("dt_load")) or "___.___"} → {dmy(v.get("dt_unload")) or "___.___.20___"}'),
                      ('Фрахт за перевозку', f'{money(v.get("rate")) or "__________"} ₽')])]
    body.append(section_pair(
        '1. Загрузка', [('1.1. Грузоотправитель', v.get('sender', '')), ('1.2. Контактное лицо', ''),
                        ('1.3. Дата погрузки', dmy(v.get('dt_load'))), ('1.4. Место (а) загрузки', v.get('load_place', ''))],
        '2. Разгрузка', [('2.1. Грузополучатель', v.get('receiver', '')), ('2.2. Контактное лицо', ''),
                         ('2.3. Дата разгрузки', dmy(v.get('dt_unload'))), ('2.4. Место (а) разгрузки', v.get('unload_place', ''))]))
    body.append(section('3–4. Фрахт и оплата', [
        ('3. Фрахт за перевозку', f'{money(v.get("rate")) or "__________"} руб.   '
                                  f'{"☑" if v.get("nds") == "с НДС" else "□"} с НДС   {"☑" if v.get("nds") == "без НДС" else "□"} без НДС'),
        ('4. Условия оплаты', 'наличные' if v.get('nds') == 'наличные' else '')]))
    body.append(section('5–7. Груз и транспорт', [
        ('5. Описание груза и вес, объём', v.get('cargo', '')), ('6. Требование к транспорту', v.get('transport', '')),
        ('7. Вид загрузки / выгрузки', '')]))
    body.append(section('8. Данные на машину', [
        ('Авто, тягач (марка, гос. номер, СТС)', v.get('auto') or ''), ('Полуприцеп (марка, гос. номер, СТС)', v.get('trailer') or '')]))
    body.append(section('9. Данные на водителя', [
        ('ФИО', v.get('driver') or ''), ('Паспорт (серия, номер, кем и когда выдан)', v.get('passport') or ''),
        ('Водительское удостоверение', v.get('vu') or ''), ('Телефон', v.get('phone') or '')]))
    body += carrier_legal(tpl['legal'])
    body.append(parties(tpl['titles'][0], firm_req(v.get('carrier_firm'), v.get('carrier') or ''), tpl['titles'][1], tpl['own']))
    return body


def client_doc(tpl, v):
    """Договор (заказ-наряд) на фрахтование — заявка с клиентом."""
    co = tpl['co']
    body = [header(co),
            title('ДОГОВОР (ЗАКАЗ-НАРЯД)', f'на фрахтование транспортом № {v.get("nomer") or "______"} от {date_words()}'),
            keystrip([('Маршрут', f'{v.get("from_city") or "_____________"} → {v.get("to_city") or "_____________"}'),
                      ('Погрузка → выгрузка', f'{dmy(v.get("dt_load")) or "___.___"} → ___.___.20___'),
                      ('Стоимость фрахтования', f'{money(v.get("rate")) or "__________"} ₽')])]
    cf = v.get('client_firm') or {}
    ids = ', '.join(x for x in (f'ИНН {cf["inn"]}' if cf.get('inn') else '', f'ОГРН {cf["ogrn"]}' if cf.get('ogrn') else '')) + \
        (f' / КПП {cf["kpp"]}' if cf.get('kpp') else '')
    body.append(section('1. Сведения о Заказчике', [
        ('Наименование / ФИО', cf.get('name') or v.get('client', '')), ('ИНН, ОГРН / КПП, паспортные данные', ids),
        ('ФИО уполномоченного лица Заказчика (если юр. л.)', cf.get('director', '')),
        ('Основания полномочий подписанта Заказчика (если юр. л.)', cf.get('basis', '')),
        ('Адрес электронной почты и № телефонов (в т.ч. мессенджеров)', ', '.join(x for x in (cf.get('email'), cf.get('phone')) if x))]))
    body.append(section('2. Сведения о Фрахтовщике', [
        ('Менеджер Фрахтовщика, принявший заказ', v.get('manager') or ''), ('Телефон менеджера', ''),
        ('Адрес электронной почты и № факсов и телефонов (в т.ч. мессенджеров)', tpl['email']),
        ('Почтовый адрес для обмена оригиналами документов', tpl['postal'])]))
    body.append(section('3. Погрузка', [
        ('Адрес подачи ТС Заказчику', v.get('load_place', '')),
        ('Дата и время подачи ТС Заказчику (начало срока фрахтования)', dmy(v.get('dt_load'))),
        ('Контактное лицо в месте подачи ТС Заказчику', '')]))
    body.append(section('4. Выгрузка', [
        ('Адрес места окончания фрахтования', v.get('unload_place', '')), ('Дата и время окончания срока фрахтования', ''),
        ('Контактное лицо в месте окончания фрахтования', '')]))
    body.append(section('5. Фрахт', [
        ('Стоимость фрахтования', f'{money(v.get("rate"))} руб.{(" " + v["pay_form"]) if v.get("pay_form") else ""}' if v.get('rate') else ''),
        ('Сроки и иные условия оплаты за фрахтование (аванс, постоплата, наличные, безнал, р/с, карта и т.п.)', '')]))
    body.append(section('6. Груз', [
        ('Габариты груза (вес, объём, размеры)', cargo_text(v.get('kg'), v.get('m3'))),
        ('Количество мест груза', n(v.get('places'), 0)),
        ('Наименование и характер груза', v.get('cargo', '')), ('Сведения об особых условиях, режимах груза', ''),
        ('Состав и наличие сопроводительных документов', ''), ('Способ погрузки в ТС', ''),
        ('Дополнительные условия Заказа-наряда (при наличии)', '')]))
    body.append(section('7. Сведения о ТС', [
        ('Авто, тягач (марка, модель)', ''), ('Полуприцеп', ''), ('Гос. рег. номер ТС', ''), ('Грузоподъёмность, длина, иное', '')]))
    body.append(section('8. Сведения о водителе фрахтуемого ТС (справочно)', [
        ('ФИО', ''), ('Паспорт / водительское удостоверение', ''), ('Телефон', '')]))
    body += client_legal(tpl['legal'])
    client_req = firm_req(v.get('client_firm'), v.get('client') or '')
    left, right = (tpl['own'], client_req) if tpl['own_left'] else (client_req, tpl['own'])
    body.append(parties(tpl['titles'][0], left, tpl['titles'][1], right))
    return body


def driver_values(con, voditel_id, fallback=''):
    """Водитель из справочника → строки разделов 8 и 9 заявки перевозчику."""
    r = con.execute('SELECT * FROM voditel WHERE id=?', (voditel_id,)).fetchone() if voditel_id else None
    if not r:
        return {'driver': fallback}
    j = lambda *xs: ', '.join(x for x in xs if x)
    sts = lambda s: f'СТС {s}' if s else ''
    return {
        'driver': r['fio'] or fallback,
        'auto': j(r['auto_brand'], r['auto_plate'], sts(r['auto_sts'])),
        'trailer': j(r['trailer_brand'], r['trailer_plate'], sts(r['trailer_sts'])),
        'passport': j(r['passport'], (f'выдан {r["passport_issued_by"]}' if r['passport_issued_by'] else ''),
                      r['passport_date'], (f'код {r["passport_code"]}' if r['passport_code'] else '')),
        'vu': j(r['vu'], (f'от {r["vu_date"]}' if r['vu_date'] else ''), (f'кат. {r["vu_cats"]}' if r['vu_cats'] else '')),
        'phone': r['phone'],
    }


# ---------- из данных приложения ----------

def build(con, kind, obj_id):
    """Собрать заявку и сохранить .docx. Возвращает путь."""
    sk = {r['id']: dict(r) for r in con.execute('SELECT * FROM sklad')}
    def sk_place(i):  # «Город, адрес»; город не повторяем, если адрес с него начинается
        if i not in sk:
            return ''
        name, addr = sk[i]['name'], sk[i]['address'] or ''
        return addr if addr.startswith(name) else ', '.join(x for x in (name, addr) if x)

    if kind == 'fura':
        f = dict(con.execute('SELECT * FROM fura WHERE id=?', (obj_id,)).fetchone())
        route = json.loads(f['route'] or '[]')
        gs = [dict(r) for r in con.execute('SELECT g.* FROM gruz g JOIN reys r ON r.gruz_id=g.id WHERE r.fura_id=?', (obj_id,))]
        tpl = template_for('fura', 'ООО ВЛ')
        tot = lambda k: sum(g[k] or 0 for g in gs)
        v = dict(nomer=f['zayavka'], from_city=sk.get(f['sklad_from'], {}).get('name', ''),
                 to_city=' → '.join(sk[i]['name'] for i in route if i in sk), dt_load=f['dt_out'], rate=f['rate'],
                 sender=tpl['co']['legal'], load_place=sk_place(f['sklad_from']),
                 receiver=tpl['co']['legal'], unload_place='; '.join(f'{k}) {sk_place(i)}' for k, i in enumerate(route, 1)),
                 cargo=cargo_text(tot('kg'), tot('m3'), tot('places'), f'Сборный груз, {len(gs)} отправок'),
                 transport=f'{n(f["cap_m3"], 0)} м³, {n(f["cap_t"], 1)} т', auto=f['nomer_ts'],
                 carrier=f['carrier'], nds=f['rate_form'])
        v.update({k: x for k, x in driver_values(con, f['voditel_id'], f['driver']).items() if x})
        body, who, nomer = carrier_doc(tpl, v), f['carrier'], f['nomer_ts']
    else:
        g = dict(con.execute('SELECT * FROM gruz WHERE id=?', (obj_id,)).fetchone())
        legs = {r['kind']: dict(r) for r in con.execute('SELECT * FROM leg WHERE gruz_id=?', (obj_id,))}
        tpl = template_for(kind, g['company'])
        nomer = g['nomer']
        if kind == 'klient':
            z = legs.get('zabor', {})
            v = dict(nomer=g['nomer'], client=g['client'], manager=g['manager'], client_firm=firm(con, g['client_id']), from_city=city(g['from_addr']), to_city=city(g['to_addr']),
                     dt_load=z.get('dt'), rate=g['rate_client'], pay_form=g['pay_form'], load_place=g['from_addr'],
                     unload_place=g['to_addr'], kg=g['kg'], m3=g['m3'], places=g['places'], cargo=g['cargo'])
            body, who = client_doc(tpl, v), g['client']
        else:
            l = legs.get(kind) or {}
            zabor = kind == 'zabor'
            frm = l.get('from_addr') or (g['from_addr'] if zabor else sk_place(g['sklad_to']))
            to = l.get('to_addr') or (sk_place(g['sklad_from']) if zabor else g['to_addr'])
            v = dict(nomer=l.get('zayavka'), from_city=city(frm), to_city=city(to), dt_load=l.get('dt'), rate=l.get('rate'),
                     sender=g['client'] if zabor else tpl['co']['legal'], load_place=frm,
                     receiver=tpl['co']['legal'] if zabor else g['client'], unload_place=to,
                     cargo=cargo_text(g['kg'], g['m3'], g['places'], g['cargo']),
                     carrier=l.get('carrier'), nds=l.get('pay_form'), carrier_firm=firm(con, l.get('carrier_id')))
            v.update(driver_values(con, l.get('voditel_id'), l.get('driver') or ''))
            body, who = carrier_doc(tpl, v), l.get('carrier')

    co = tpl['co']
    OUT_DIR.mkdir(exist_ok=True)
    safe = re.sub(r'[\\/:*?"<>|«»]+', '', f'{date.today():%Y-%m-%d} Заявка {KIND_NAME[kind]} {nomer or ""} {who or ""}')
    stem = re.sub(r'\s+', ' ', safe).strip()[:150]
    path, k = OUT_DIR / f'{stem}.docx', 2
    while True:
        try:
            save(str(path), body, f'{co["legal"]} · {co["email"]} · {co["phone"]}')
            return path
        except PermissionError:  # файл открыт в Word — сохраняем рядом с номером
            path = OUT_DIR / f'{stem} ({k}).docx'
            k += 1
