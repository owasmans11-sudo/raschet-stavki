"""Проекты перевозочных документов. Не подписывают и не отправляют ЭПД."""
import json
import re
import uuid
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import pechat as P

TEMPLATES = Path(__file__).resolve().parent / 'templates'
RECEIPTS = {'ООО ВЛ': 'receipt-vl.docx', 'ИП Шерстов': 'receipt-ip.docx'}
NOTICE = ('Редактируемый проект для проверки. С 01.09.2026 ТН и экспедиторские документы '
          'по общему правилу оформляются электронно; Word не заменяет ЭПД и подписи участников. '
          'Бумажное оформление допускается только в предусмотренных случаях. '
          'Фактический приём, выдачу, полномочия и подписи заполняют участники.')
LABELS = {
    'number': 'Номер документа', 'date': 'Дата документа',
    'sender': 'Грузоотправитель — наименование, ИНН, адрес, контакт',
    'receiver': 'Грузополучатель — наименование, ИНН, адрес, контакт',
    'client': 'Клиент экспедитора', 'cargo': 'Наименование груза',
    'kg': 'Масса по заявке, кг (не подтверждает брутто/нетто)', 'm3': 'Объём, м³', 'places': 'Количество мест',
    'from_addr': 'Адрес погрузки выбранного участка', 'to_addr': 'Адрес выгрузки выбранного участка',
    'load_date': 'Плановая дата погрузки', 'carrier': 'Перевозчик — наименование и реквизиты',
    'driver': 'Водитель выбранного участка', 'phone': 'Телефон водителя',
    'auto': 'Автомобиль / тягач', 'trailer': 'Прицеп / полуприцеп',
    'basis': 'Основание — договор / заявка', 'packaging': 'Упаковка, маркировка, состояние',
    'attachments': 'Сопроводительные документы', 'instructions': 'Указания и особые условия',
    'value': 'Объявленная стоимость (если согласована)',
}


def get(con, table, ident):
    r = con.execute(f'SELECT * FROM {table} WHERE id=?', (ident,)).fetchone() if ident else None
    return dict(r) if r else {}


def firm_text(f):
    return '; '.join(str(f[k]) for k in ('name', 'inn', 'address', 'phone') if f.get(k))


def prepare(con, kind, ident, segment='', overrides=None):
    if kind not in ('tn', 'receipt'):
        raise P.NetShablona('Неизвестный вид документа')
    g = get(con, 'gruz', ident)
    if not g:
        raise P.NetShablona('Заявка не найдена')
    company = g.get('company')
    if company not in RECEIPTS:
        raise P.NetShablona('Документы доступны для ООО ВЛ и ИП Шерстов. Проверьте компанию заявки.')
    segments = [{'id': 'zabor', 'label': 'Забор до склада'}, {'id': 'razvoz', 'label': 'Развоз со склада'}]
    rr = [dict(r) for r in con.execute('SELECT * FROM reys WHERE gruz_id=? ORDER BY id', (ident,))]
    for r in rr:
        f = get(con, 'fura', r['fura_id'])
        segments.append({'id': f'fura:{r["fura_id"]}', 'label': f'Межгород — {f.get("nomer_ts") or r["fura_id"]}'})
    if segment and segment not in [s['id'] for s in segments]:
        raise P.NetShablona('Этот участок / фура не связан с заявкой')
    l, frm, to = {}, '', ''
    sk = lambda i: get(con, 'sklad', i).get('address') or ''
    if segment in ('zabor', 'razvoz'):
        row = con.execute('SELECT * FROM leg WHERE gruz_id=? AND kind=?', (ident, segment)).fetchone()
        l = dict(row) if row else {}
        frm = l.get('from_addr') or (g.get('from_addr') if segment == 'zabor' else sk(g.get('sklad_to')))
        to = l.get('to_addr') or (sk(g.get('sklad_from')) if segment == 'zabor' else g.get('to_addr'))
    elif segment.startswith('fura:'):
        fid = int(segment.split(':')[1])
        l = get(con, 'fura', fid)
        r = next(r for r in rr if r['fura_id'] == fid)
        frm, to = sk(l.get('sklad_from')), sk(r.get('point'))
        l['dt'] = l.get('dt_out')
    v = get(con, 'voditel', l.get('voditel_id'))
    cf = get(con, 'kontragent', g.get('client_id'))
    # Клиент не обязательно отправитель или получатель; эти роли подтверждаются вручную.
    fields = {k: '' for k in LABELS}
    fields.update(client=firm_text(cf) or g.get('client') or '', cargo=g.get('cargo') or '',
                  kg=P.n(g.get('kg')), m3=P.n(g.get('m3')), places=P.n(g.get('places'), 0),
                  from_addr=frm or '', to_addr=to or '', load_date=l.get('dt') or '',
                  carrier=firm_text(get(con, 'kontragent', l.get('carrier_id'))) or l.get('carrier') or '',
                  driver=v.get('fio') or l.get('driver') or '', phone=v.get('phone') or '',
                  auto=', '.join(x for x in (v.get('auto_brand'), v.get('auto_plate')) if x) or l.get('nomer_ts') or '',
                  trailer=', '.join(x for x in (v.get('trailer_brand'), v.get('trailer_plate')) if x),
                  basis=l.get('zayavka') or '')
    if overrides is not None:
        if not isinstance(overrides, dict) or set(overrides) - set(LABELS):
            raise P.NetShablona('Неизвестные поля документа')
        for k, value in overrides.items():
            if not isinstance(value, (str, int, float)) or len(str(value)) > 3000:
                raise P.NetShablona('Поле документа слишком длинное или имеет неверный формат')
            fields[k] = str(value).strip()
    required = ['number', 'date', 'sender', 'receiver', 'cargo', 'places', 'from_addr', 'to_addr']
    if kind == 'tn':
        required += ['carrier', 'driver', 'auto', 'load_date']
    return dict(kind=kind, company=company, nomer=g.get('nomer') or '', segment=segment,
                segments=segments, fields=fields, labels=LABELS, notice=NOTICE,
                missing=[LABELS[k] for k in required if not fields[k]],
                segment_label=next((s['label'] for s in segments if s['id'] == segment), 'Участок не выбран'))


def build(con, d):
    p = prepare(con, d['kind'], d['id'], d.get('segment', ''), d.get('fields'))
    if not p['segment']:
        raise P.NetShablona('Выберите участок перевозки')
    if p['missing'] and not d.get('allow_incomplete'):
        raise P.NetShablona('Не заполнено: ' + ', '.join(p['missing']) + '. Дополните или скачайте незаполненный проект.')
    f = p['fields']
    P.OUT_DIR.mkdir(parents=True, exist_ok=True)
    name = 'ТН проект' if p['kind'] == 'tn' else 'Экспедиторская расписка проект'
    stem = re.sub(r'[\\/:*?"<>|]', '', f'{name} {p["nomer"]}')[:100]
    path = P.OUT_DIR / f'{stem} {uuid.uuid4().hex[:10]}.docx'
    if p['kind'] == 'receipt':
        receipt(path, p)
    else:
        with zipfile.ZipFile(TEMPLATES / RECEIPTS[p['company']]) as z:
            root = ET.fromstring(z.read('word/document.xml'))
        ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
        ps = [''.join(t.text or '' for t in para.findall('.//w:t', ns)) for para in root.findall('.//w:p', ns)]
        co = dict(brand=ps[0], legal=ps[1].split(' · ')[0], inn=ps[2], ogrn=ps[3],
                  phone=ps[4].removeprefix('Тел.:').strip(), email=ps[5])
        body = [P.header(co), P.title('ТРАНСПОРТНАЯ НАКЛАДНАЯ', 'Проект сведений по выбранному участку'),
                P.para(P.run(NOTICE, 16)), P.section('Заявка и участок', [('Заявка', p['nomer']), ('Участок', p['segment_label'])])]
        for heading, keys in [
            ('Документ и стороны', ['number', 'date', 'basis', 'sender', 'receiver', 'client']),
            ('Груз', ['cargo', 'kg', 'm3', 'places', 'packaging', 'value', 'attachments']),
            ('Перевозка выбранного участка', ['from_addr', 'to_addr', 'load_date', 'carrier', 'driver', 'phone', 'auto', 'trailer', 'instructions']),
        ]:
            body.append(P.section(heading, [(LABELS[k], f[k]) for k in keys]))
        body.append(P.section('Заполняют участники при фактической передаче', [
            ('Приём груза — дата, время, состояние, оговорки', ''), ('Выдача груза — дата, время, состояние, оговорки', ''),
            ('Изменение условий, переадресовка, замена транспорта', ''), ('Стоимость перевозки и расчёты', ''),
            ('Груз сдал / принял — полномочия, ФИО, подписи', '')]))
        P.save(str(path), body, co['legal'])
    return path


def receipt(path, p):
    """Сохраняет фирменный бланк, меняя только текст отмеченных абзацев."""
    source = TEMPLATES / RECEIPTS[p['company']]
    if not source.is_file():
        raise P.NetShablona('Нет бланка экспедиторской расписки')
    ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
    f = p['fields']
    values = {
        8: f'ПРОЕКТ · № {f["number"] or "________"} от {f["date"] or "________"}',
        9: 'Для проверки · Word не заменяет электронный ЭПД',
        12: f['client'], 14: f['sender'], 16: f['receiver'], 22: f['cargo'],
        26: f['packaging'],
        27: 'Количество мест · масса по заявке, кг',
        28: f'{f["places"] or "____"} мест; {f["kg"] or "____"} кг (брутто/нетто уточнить)',
        30: f'{f["m3"] or "____"} м³; стоимость {f["value"] or "____"}',
        32: '; '.join(x for x in (f['attachments'], f['basis']) if x),
        40: f['instructions'],
        42: f'{p["segment_label"]}: {f["from_addr"] or "____"} → {f["to_addr"] or "____"}' + (f'; план {f["load_date"]}' if f['load_date'] else ''),
        44: '; '.join(x for x in (f['carrier'], f['auto'], f['trailer'], f['driver'], f['phone']) if x),
    }
    # Меняем только document.xml; остальные ZIP-части сохраняются побайтно.
    with zipfile.ZipFile(source) as zin, zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as zout:
        xml = zin.read('word/document.xml').decode('utf-8')
        paragraphs = list(re.finditer(r'<w:p(?:\s[^>]*)?>.*?</w:p>', xml, re.S))
        from xml.sax.saxutils import escape
        for i in sorted(values, reverse=True):
            m = paragraphs[i]
            para = m.group()
            texts = list(re.finditer(r'<w:t(?:\s[^>]*)?>.*?</w:t>', para, re.S))
            if texts:
                for j, t in reversed(list(enumerate(texts))):
                    para = para[:t.start()] + '<w:t xml:space="preserve">' + (escape(values[i]) if j == 0 else '') + '</w:t>' + para[t.end():]
            else:
                para = para[:-6] + '<w:r><w:t>' + escape(values[i]) + '</w:t></w:r></w:p>'
            xml = xml[:m.start()] + para + xml[m.end():]
        # Явный статус проекта в исходном служебном подзаголовке, без изменения шапки компании.
        xml = xml.replace('к Порядку оформления и формы экспедиторских документов (п.5)', 'Проект для проверки · Word не заменяет электронный ЭПД')
        ET.fromstring(xml)
        for item in zin.infolist():
            zout.writestr(item, xml.encode('utf-8') if item.filename == 'word/document.xml' else zin.read(item.filename))
