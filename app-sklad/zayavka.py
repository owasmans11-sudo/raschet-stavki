# Груз из заявки клиента: за один проход по файлу — реквизиты заказчика (firma.py) и данные перевозки:
# номер и дата заявки, адреса и даты погрузки/выгрузки, груз, вес, объём, места, ставка, НДС.
# Номер, ставку, НДС и погрузку разбирает уже проверенный код картотеки (tools/kart_fields.py).
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'tools'))
import kart_fields as K  # noqa: E402
import firma as F  # noqa: E402
from raspoznat import fix  # noqa: E402

UNLOAD_LABEL = re.compile(r'(адрес|место|пункт)[^\n]{0,25}(выгрузк|разгрузк|доставк)|^(выгрузка|разгрузка)\b|'
                          r'грузополучатель и место (вы|раз)грузки', re.I)
NOT_PLACE = re.compile(r'дата|время|контакт|способ|тип|погруз|загруз|телефон|тел\.', re.I)


def iso(d):
    """«дд.мм.гггг» → «гггг-мм-дд» для поля даты в браузере."""
    return '-'.join(reversed(d.split('.'))) if d and re.fullmatch(r'\d{2}\.\d{2}\.\d{4}', d) else ''


def unloading(lines):
    """Как K.loading, только для выгрузки: дата и место."""
    date = place = ''
    for i, l in enumerate(lines):
        low = l.lower()
        if not date and re.search(r'(дата|время|срок)[^\n]{0,25}(выгрузк|разгрузк|доставк)|(выгрузк|разгрузк)[^\n]{0,15}(дата|:)', low):
            date = K.find_date(' '.join(lines[i:i + 3]))
        if not place and UNLOAD_LABEL.search(l):
            rest = re.split(r'(?:выгрузк|разгрузк|доставк)\S*', l, maxsplit=1, flags=re.I)[-1]
            rest = re.sub(r'^[\s:.\-1)]+', '', rest).rstrip(' :-')
            cand = rest if len(re.findall(r'[А-Яа-яЁё]{3,}', rest)) >= 2 and not NOT_PLACE.match(rest) else ''
            k = i + 1
            while not cand and k < min(i + 4, len(lines)):
                if not NOT_PLACE.search(lines[k]) and len(re.findall(r'[А-Яа-яЁё]{3,}', lines[k])) >= 2:
                    cand = lines[k]
                k += 1
            place = cand[:150]
    return date, place


def _num(s):
    s = s.strip().split('\n')[0]  # число могло захватить перенос строки («26\n1130»)
    return float(s.replace(' ', '').replace(',', '.'))


def cargo(text, lines):
    r = {}
    label = re.compile(r'(?:наименование\s+(?:и\s+характер\s+)?груза|характер\s+груза|описание\s+груза|род\s+груза|^\s*груз\b)\s*[:\-–]?\s*', re.I)
    for i, l in enumerate(lines):  # значение — в той же строке после подписи или (таблица) в следующей
        m = label.search(l)
        if not m:
            continue
        val = l[m.end():].strip()
        if len(re.findall(r'[А-Яа-яЁёA-Za-z]{3,}', val)) < 1 and i + 1 < len(lines):
            val = lines[i + 1].strip()
        val = re.split(r'\s+(?:вес|масса|объ[её]м|кол-?во|количество|габарит)\b', val, maxsplit=1, flags=re.I)[0].strip(' ,.:')
        if 3 <= len(val) <= 80 and not re.match(r'(вес|масса|объ|кол|адрес|дата|отправ|получ)', val, re.I):
            r['cargo'] = val
            break
    w = re.search(r'(?:вес|масса)[^\d\n]{0,25}(\d[\d\s]{0,6}(?:[.,]\d+)?)\s*(кг|т\b|тн|тонн)', text, re.I) or \
        re.search(r'(\d[\d\s]{0,6}(?:[.,]\d+)?)\s*(кг|тн|тонн)\b', text, re.I)
    if w:
        v = _num(w.group(1))
        kg = v if w.group(2).lower() == 'кг' else v * 1000
        if 1 <= kg <= 60000:
            r['kg'] = round(kg)
    v = re.search(r'(\d+(?:[.,]\d+)?)\s*(?:м3|м³|м\.?\s?куб|куб\.?\s*м|кубов|куба?)\b', text, re.I)
    if v and 0 < _num(v.group(1)) <= 130:
        r['m3'] = _num(v.group(1))
    p = re.search(r'(?:кол-?во|количество)\s+(?:мест|грузовых\s+мест)\D{0,10}(\d{1,4})|(\d{1,4})\s*(?:мест|паллет\w*|палл\.?|коробок|короб\.?)\b', text, re.I)
    if p:
        r['places'] = int(p.group(1) or p.group(2))
    return r


def parse(text):
    """Текст заявки → поля груза и сомнения."""
    t = fix(text).replace('\t', ' ')
    lines = K.norm_lines(t)
    num, date, _ = K.title_info(lines)
    money = K.money_candidates(lines)
    amount = K.pick_amount(money)
    ld, lp = K.loading(lines)
    ud, up = unloading(lines)
    f = {}
    if num or date:
        f['client_doc'] = f'Заявка клиента № {num or "б/н"}{" от " + date if date else ""}'
    if lp:
        f['from_addr'] = lp
    if up:
        f['to_addr'] = up
    if ld:
        f['dt_load'] = iso(ld)
    if ud:
        f['dt_unload'] = iso(ud)
    if amount:
        f['rate_client'] = amount
    v = K.vat(t, K.amount_ctx(money, lines))
    if v:
        f['pay_form'] = v
    f.update(cargo(t, lines))
    bad = {}
    if amount and K.amount_doubt(money):
        bad['rate_client'] = 'в заявке несколько похожих сумм — проверьте ставку'
    if ld and ud and iso(ud) < iso(ld):
        bad['dt_unload'] = 'выгрузка раньше погрузки?'
    return f, bad


def from_files(files):
    """[(имя, байты)] → компании-кандидаты (как firma) + поля груза из заявки."""
    texts = F.read_all(files)
    res = F.from_texts(texts)
    gruz, bad = {}, {}
    for name, text, err in texts:
        if text is None:
            continue
        f, b = parse(text)
        for k, v in f.items():
            gruz.setdefault(k, v)
        for k, v in b.items():
            bad.setdefault(k, v)
    res['gruz'] = gruz
    res['gruz_doubts'] = bad
    return res
