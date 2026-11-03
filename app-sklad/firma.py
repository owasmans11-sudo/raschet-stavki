# Клиент / перевозчик из файлов: реквизиты компании из карточки предприятия или из заявки клиента.
# Распознавание файлов — raspoznat.read_file (тот же OCR, что для водителей).
# В заявке обычно две стороны: наши реквизиты отбрасываем, остальные компании — кандидаты на выбор.
import re

from raspoznat import fix, inn_ok, read_file

OUR_INN = {'3812166710': 'ООО «Восточная Логистика»', '381100987938': 'ИП Шерстов А. В.', '3812162635': 'ООО «ТК МВЛ»'}
OUR_NAME = re.compile(r'восточн\w*\s+логист|шерстов|тк\s*мвл', re.I)

ORG = re.compile(r'(общество\s+с\s+ограниченной\s+ответственностью|публичное\s+акционерное\s+общество|акционерное\s+общество|'
                 r'индивидуальный\s+предприниматель|\bООО\b|\bПАО\b|\bЗАО\b|\bОАО\b|\bНАО\b|\bАО\b|\bИП\b)'
                 r'\s*[«"“„]?\s*([^«»"“”\n,;()]{2,70}?)\s*(?:[»"”]|(?=[,;\n(]|$|\s+(?:инн|огрн|кпп|юр|юридическ|адрес|сокращ|полное|'
                 r'тел|в\s+лице|почт|место|р/с|расч|банк|бик|именуем)))', re.I)
SHORT = {'общество с ограниченной ответственностью': 'ООО', 'публичное акционерное общество': 'ПАО',
         'акционерное общество': 'АО', 'индивидуальный предприниматель': 'ИП'}


# ---------- контрольные суммы ----------

def ogrn_ok(s):
    if len(s) == 13:
        return int(s[:12]) % 11 % 10 == int(s[12])
    if len(s) == 15:
        return int(s[:14]) % 13 % 10 == int(s[14])
    return False


def _key(digits23):
    w = [7, 1, 3] * 8
    return sum(int(c) * k for c, k in zip(digits23, w)) % 10 == 0


def rs_ok(rs, bik):
    """Расчётный счёт проверяется вместе с БИК (3 последние цифры БИК + счёт)."""
    return len(rs) == 20 and len(bik) == 9 and _key(bik[-3:] + rs)


def ks_ok(ks, bik):
    return len(ks) == 20 and len(bik) == 9 and _key('0' + bik[4:6] + ks)


# ---------- разбор ----------

def _joined(t):
    """Цифры, разбитые пробелами на группы (4070 2810 …), склеиваем — длинные номера ищем в этом тексте.
    Позиции символов сохраняем: пробел внутри числа заменяем на «\x00», а не удаляем."""
    return re.sub(r'(?<=\d)[ \u00a0](?=\d)', '\x00', t)


def _num(t, pattern, join=False):
    """Все совпадения числа: [(позиция, число)]. join — склеить группы цифр (счета 4070 2810 …)."""
    j = _joined(t) if join else t
    return [(m.start(), m.group(1).replace('\x00', '')) for m in re.finditer(pattern, j)]


def _after(t, label, stop=r'\n|(?:инн|кпп|огрн|р/?с|расч|бик|к/?с|корр|тел|e-?mail|эл\.?\s*почта|банк)\b'):
    """Текст после подписи до следующей подписи / конца строки: [(позиция, текст)]."""
    out = []
    for m in re.finditer(label, t, re.I):
        rest = t[m.end():m.end() + 220]
        s = re.split(stop, rest, maxsplit=1, flags=re.I)[0]
        s = re.sub(r'\s+', ' ', s).strip(' :;,.-')
        if len(s) >= 5:
            out.append((m.start(), s))
    return out


def _name(kind, body):
    kind = SHORT.get(re.sub(r'\s+', ' ', kind.lower()), kind.upper())
    body = re.sub(r'\s+', ' ', body).strip(' .')
    if kind == 'ИП':
        return f'ИП {body.title() if body.islower() or body.isupper() else body}'
    return f'{kind} «{body.upper() if body.islower() else body}»'


LABEL = re.compile(r'инн|огрн|кпп|бик|р/?с|адрес|банк', re.I)


def columns(t):
    """Реквизиты двух сторон в две колонки: строки вида «левое\tправое» (см. raspoznat._lines).
    Если таких строк с подписями слева и справа хотя бы две — возвращаем текст каждой колонки отдельно."""
    lines = t.split('\n')
    both = sum(1 for l in lines if '\t' in l and all(LABEL.search(p) for p in l.split('\t', 1)))
    if both < 2:
        return None
    left, right = [], []
    for l in lines:
        a, _, b = l.partition('\t')
        left.append(a)
        right.append(b)
    return ['\n'.join(left), '\n'.join(right)]


def candidates(text):
    """Все компании в документе. Две колонки реквизитов разбираем по отдельности, затем — весь текст
    (для компаний вне колонок, например грузоотправитель в шапке). Наши — отбрасываем."""
    t = re.sub(r'(?<![\w])[ОO0]{3}(?=\s*[«"“])', 'ООО', fix(text))  # «О0О «…»» → ООО
    cols = columns(t)
    if not cols:
        return _candidates(t.replace('\t', ' '))
    found = {}
    for part in cols + [t.replace('\t', ' ')]:
        for c in _candidates(part):
            cur = found.setdefault(c['inn'], {})
            for k, v in c.items():
                if v and not cur.get(k):
                    cur[k] = v
    out = [dict(c, name=c.get('name', '')) for c in found.values()]
    out.sort(key=lambda c: -len(c))
    return out


def _candidates(t):
    """Поля привязываем к ближайшему по тексту ИНН."""
    anchors = {}
    for pos, v in _num(t, r'(?<![\d\x00])(\d{10}|\d{12})(?![\d\x00])'):
        if inn_ok(v):
            anchors.setdefault(v, []).append(pos)
    if not anchors:
        return []
    comp = {inn: {'inn': inn} for inn in anchors}

    def nearest(pos, before=False):
        """ИНН, ближайший к позиции. before — значение обычно стоит ДО своего ИНН (название компании)."""
        best, dist = None, 900
        for inn, ps in anchors.items():
            for p in ps:
                if before and p - pos < -40:
                    continue
                if abs(p - pos) < dist:
                    best, dist = inn, abs(p - pos)
        return best

    def put(field, pos, val, before=False):
        inn = nearest(pos, before)
        if inn and field not in comp[inn]:
            comp[inn][field] = val

    for pos, v in _num(t, r'(?<![\d\x00])(\d{13}|\d{15})(?![\d\x00])'):
        if ogrn_ok(v) or re.search(r'огрн', t[max(0, pos - 15):pos], re.I):
            put('ogrn', pos, v)
    for m in re.finditer(r'кпп[\s:/]*(?:\d{10,12}\s*/\s*)?(\d{9})(?!\d)', t, re.I):
        put('kpp', m.start(1), m.group(1))
    for m in re.finditer(r'инн\s*/\s*кпп[\s:]*\d{10}[\s/\\|]+(\d{9})(?!\d)', t, re.I):
        put('kpp', m.start(1), m.group(1))
    for pos, v in _num(t, r'(?<![\d\x00])(04\d{7})(?![\d\x00])'):
        put('bik', pos, v)
    for pos, v in _num(t, r'(?<![\d\x00])(40[5-8]\d{17}|423\d{17})(?![\d\x00])', join=True):
        put('rs', pos, v)
    for pos, v in _num(t, r'(?<![\d\x00])(301\d{17})(?![\d\x00])', join=True):
        put('ks', pos, v)
    for pos, s in _after(t, r'(юридическ\w*\s+адрес|юр\.?\s*адрес|адрес\s+регистрации|место\s*нахождени\w*|адрес\s+местонахождени\w*)'):
        put('address', pos, s)
    for pos, s in _after(t, r'(почтов\w*\s+адрес|почт\.?\s*адрес|фактическ\w*\s+адрес|адрес\s+для\s+корреспонденци\w*)'):
        put('post_address', pos, s)
    for pos, s in _after(t, r'(?:наименование\s+банка|банк\s+получателя|\bбанк\b)[\s:]*', stop=r'\n|бик|к/?с|корр|р/?с|инн|г\.\s*\w+\s*$'):
        if not re.match(r'(получател|бик|\d)', s, re.I):
            put('bank', pos, s)
    for m in re.finditer(r'в\s+лице\s+(.{5,90}?),?\s+действующ\w+\s+на\s+основании\s+([А-Яа-яЁё]+(?:\s+№?\s*[\w/-]+)?)', t, re.I | re.S):
        put('director', m.start(), re.sub(r'\s+', ' ', m.group(1)).strip())
        put('basis', m.start(), m.group(2).strip())
    W = r'[А-ЯЁа-яё][а-яё]+|[А-ЯЁ]{2,}'
    for m in re.finditer(rf'(генеральн\w*\s+директор\w*|директор\w*|руководител\w*)[\s:—-]+((?:{W})\s+(?:(?:{W})\s+(?:{W})|[А-ЯЁа-яё]\.\s*[А-ЯЁа-яё]\.?))', t, re.I):
        fio = m.group(2)
        if not re.search(r'действ|на основании|общества|организац', fio, re.I):
            put('director', m.start(), f'{m.group(1).capitalize()} {" ".join(w.capitalize() if not w.endswith(".") else w.upper() for w in fio.split())}')
    for m in re.finditer(r'(?:\+7|\b8)[\s(-]*(\d{3})[\s)-]*(\d{3})[\s-]*(\d{2})[\s-]*(\d{2})\b', t):
        put('phone', m.start(), f'+7 ({m[1]}) {m[2]}-{m[3]}-{m[4]}')
    for m in re.finditer(r'[\w.+-]+@[\w-]+\.[\w.]+', t):
        put('email', m.start(), m.group(0).lower())
    # название: «Сокращённое наименование» в карточке, иначе ближайшая организационная форма перед ИНН
    for pos, s in _after(t, r'сокращ\w*\s+(?:фирменн\w*\s+)?наименовани\w*', stop=r'\n|инн|огрн'):
        m = ORG.search(s)
        if m:
            put('name', pos, _name(m.group(1), m.group(2)))
    for m in ORG.finditer(t):
        if not OUR_NAME.search(m.group(0)):
            put('name', m.start(), _name(m.group(1), m.group(2)), before=True)

    out = []
    for inn, c in comp.items():
        if inn in OUR_INN:
            continue
        c.setdefault('name', '')
        out.append(c)
    # сначала те, у кого больше реквизитов (обычно это и есть сторона договора)
    out.sort(key=lambda c: -len(c))
    return out


def doubts(c):
    bad = {}
    if c.get('ogrn') and not ogrn_ok(c['ogrn']):
        bad['ogrn'] = 'ОГРН не проходит проверку — сверьте цифры'
    if c.get('rs') and c.get('bik') and not rs_ok(c['rs'], c['bik']):
        bad['rs'] = 'счёт не сходится с БИК — ошибка в цифрах счёта или БИК'
    if c.get('ks') and c.get('bik') and not ks_ok(c['ks'], c['bik']):
        bad['ks'] = 'корр. счёт не сходится с БИК'
    if c.get('kpp') and len(c['kpp']) != 9:
        bad['kpp'] = 'КПП — 9 цифр'
    if not c.get('name'):
        bad['name'] = 'название не найдено — впишите'
    if len(c.get('inn', '')) == 12 and c.get('kpp'):
        bad['kpp'] = 'у ИП нет КПП — проверьте'
    return bad


def read_all(files):
    """[(имя, байты)] → [(имя, текст или None, ошибка)] — каждый файл распознаём один раз."""
    out = []
    for name, data in files:
        try:
            out.append((name, read_file(name, data), ''))
        except Exception as e:
            out.append((name, None, str(e)[:200]))
    return out


def from_texts(texts):
    """[(имя, текст, ошибка)] → кандидаты-компании (без наших) с сомнительными полями."""
    found, docs = {}, []
    for name, text, err in texts:
        if text is None:
            docs.append({'name': name, 'found': 0, 'error': err})
            continue
        cs = candidates(text)
        docs.append({'name': name, 'found': len(cs)})
        for c in cs:  # одна компания в нескольких файлах — дополняем
            cur = found.setdefault(c['inn'], {})
            for k, v in c.items():
                if v and not cur.get(k):
                    cur[k] = v
    cands = sorted(found.values(), key=lambda c: -len(c))
    return {'candidates': [{'fields': c, 'doubts': doubts(c)} for c in cands], 'docs': docs}


def from_files(files):
    return from_texts(read_all(files))
