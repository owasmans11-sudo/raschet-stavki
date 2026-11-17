"""Разбор файлов из вечерней почты (C:\\РАБОТА\\Почта) ПЕРЕНОСОМ, без копий — решение владельца 05.11.2026.

    python tools/razbor_pochty.py --pomoyka    тексты писем и логотипы → Почта\\ПОМОЙКА (вечером — до распознавания)
    python tools/razbor_pochty.py --undo       вернуть ВСЁ перенесённое обратно на старые места (по журналу)

Остальное вызывает tools/pary_zayavok.py после сборки пар (razlozhit):
  * Перевозка Перевозки\\<Клиент>\\<дата> Откуда–Куда, Фамилия\\: заявка с клиентом, заявка с перевозчиком и относящиеся
    к ним счёт, акт, УПД, ТН (по номеру заявки, машине, водителю, маршруту, дате; ТН — ещё по теме и тексту письма).
  * ВУ, паспорт, СТС, ПТС, договор аренды (+ нечитаемые фото из того же письма) → Перевозки\\_Водители и машины\\<Фамилия>\\.
  * ПОМОЙКА: тексты писем, логотипы, рассылки («Прочее»), нечитаемые фото, трек-номера и почтовые квитанции.
  * Реквизиты фирм — к их заявке, счёту или водителю из того же письма; не нашлось — в ПОМОЙКУ.
  * Всё, в чём программа не уверена, ОСТАЁТСЯ в «Почте» — это и есть список «посмотреть глазами».
Старый архив C:\\РАБОТА (не «Почта») не трогается. Каждый перенос — в журнал razbor_moves.json; кэши распознавания
переписываются на новый путь (повторно не распознаём); опись писем (Опись.csv/html) показывает новое место.
"""
import argparse, csv, json, os, re, sys
from datetime import date, datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import find_files as ff
import kart_fields as kf

MAIL = os.path.join(ff.WORK, 'Почта')
JUNK = os.path.join(MAIL, 'ПОМОЙКА')
OUT = os.path.join(ff.WORK, 'Перевозки')
DRV_DIR = os.path.join(OUT, '_Водители и машины')
# заявка перевозчику без пары с клиентом + её счета/акты/ТН (владелец: «счета и акты перевозчика храни вместе с заявкой»)
LONE_DIR = os.path.join(OUT, '_Перевозчик без клиента')
# счёт/акт/УПД, не привязанный ни к какой заявке, — сюда по контрагенту, в «Почте» их не оставляем (владелец 05.11.2026)
BUH_DIR = os.path.join(OUT, '_Счета и акты')
BUH_NAME = re.compile(r'сч[её]т|(?<![а-я])сч[\s._№-]|(?<![а-я])акт(?![а-я])|акт[\s_]|упд|фактур|invoice', re.I)
MAIL_APP = os.path.join(ff.PROJECT, 'mail-downloader')
JOURNAL = os.path.join(os.path.dirname(ff.CACHE), 'razbor_moves.json')
CACHES = [ff.CACHE, ff.OCR_CACHE, ff.XLS_CACHE, ff.IMPORTED_CACHE, ff.PHOTO_CACHE]
IMG = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.jfif', '.heic', '.tif', '.tiff'}
SMALL_IMG = 15_000  # как mail_core.JUNK_IMG_SIZE


def norm(p):
    return os.path.normcase(os.path.normpath(p))


def in_dir(path, folder):
    return norm(path).startswith(norm(folder) + os.sep)


def boxes():
    if not os.path.isdir(MAIL):
        return []
    return [os.path.join(MAIL, d) for d in os.listdir(MAIL)
            if os.path.isdir(os.path.join(MAIL, d)) and d.upper() != 'ПОМОЙКА']


def box_of(path):
    return next((b for b in boxes() if in_dir(path, b)), None)


def from_mail(path):
    """Файл лежит в папке ящика (ещё не разобран)."""
    return box_of(path) is not None


def mail_variants(c):
    """Карточка картотеки → по карточке на каждый её экземпляр в «Почте». Картотека склеивает одинаковые файлы
    (тот же ВУ в архиве и в письме) и помнит один путь — экземпляр из почты иначе остался бы неразобранным."""
    out = []
    for p in [c['path']] + list(c.get('other_paths') or []):
        if p and os.path.exists(p) and from_mail(p) and norm(p) not in {norm(x['path']) for x in out}:
            out.append(c if p == c['path'] else dict(c, path=p, file=os.path.basename(p), folder=os.path.dirname(p)))
    return out


def same_file(a, b):
    if os.path.getsize(a) != os.path.getsize(b):
        return False
    with open(a, 'rb') as x, open(b, 'rb') as y:
        return x.read() == y.read()


# ---------- перенос с журналом ----------
class Mover:
    """Переносит файлы, помнит старое→новое; finish() правит описи, кэши распознавания и журнал."""

    def __init__(self, dry=False, why_default=''):
        self.dry, self.moves = dry, []  # [(откуда, куда, почему)]

    def move(self, src, folder, why='', card=None):
        if not os.path.exists(src):
            return src
        if norm(os.path.dirname(src)) == norm(folder):
            return src
        root, ext = os.path.splitext(os.path.join(folder, os.path.basename(src)))
        dst, n = root + ext, 1
        while os.path.exists(dst) and not same_file(src, dst):
            dst, n = f'{root} ({n}){ext}', n + 1
        if not self.dry:
            os.makedirs(folder, exist_ok=True)
            try:
                if os.path.exists(dst):  # точно такой же файл уже там (письмо пришло дважды)
                    os.remove(src)
                else:
                    os.replace(src, dst)
            except OSError:  # файл открыт — попробуем в следующий раз
                return src
        self.moves.append((src, dst, why))
        if card is not None:
            card['path'], card['folder'] = dst, os.path.dirname(dst)
        return dst

    def finish(self, log=print):
        if self.dry or not self.moves:
            return
        per_box = {}
        for src, dst, _ in self.moves:
            b = box_of(src) or box_of(dst)
            if b:
                per_box.setdefault(b, {})[os.path.relpath(src, b)] = os.path.relpath(dst, b)
        for b, ren in per_box.items():
            fix_opis(b, ren, log)
        rekey_caches({norm(s): norm(d) for s, d, _ in self.moves})
        j = ff.load_cache(JOURNAL) or {'moves': []}
        stamp = datetime.now().strftime('%d.%m.%Y %H:%M')
        j['moves'] += [{'from': s, 'to': d, 'why': w, 'when': stamp} for s, d, w in self.moves]
        ff.save_cache(j, JOURNAL)


def rekey_caches(mapping):
    """Кэши поиска и распознавания: тот же текст под новым путём (иначе вечером распознавали бы заново)."""
    for path in CACHES:
        c = ff.load_cache(path)
        if not isinstance(c, dict) or not c:
            continue
        changed = False
        for old, new in mapping.items():
            for k in (old, os.path.normcase(old)):
                if k in c:
                    c[os.path.normcase(new)] = c.pop(k)
                    changed = True
                    break
        if changed:
            ff.save_cache(c, path)


def fix_opis(box, renamed, log=print):
    path = os.path.join(box, 'Опись.csv')
    if not os.path.exists(path):
        return
    with open(path, encoding='utf-8-sig', newline='') as f:
        rd = csv.DictReader(f, delimiter=';')
        cols, rows = rd.fieldnames, list(rd)
    low = {norm(k): v for k, v in renamed.items()}
    for r in rows:
        for k in ('Путь к файлу', 'Текст письма'):
            v = r.get(k)
            if v and norm(v) in low:
                r[k] = low[norm(v)]
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=cols, delimiter=';')
        w.writeheader()
        w.writerows(rows)
    os.replace(tmp, path)
    try:
        sys.path.insert(0, MAIL_APP)
        from mail_core import Opis
        Opis(box).write_html()
    except Exception as e:
        log(f'опись HTML не обновлена: {e}')


def undo(log=print):
    """Вернуть всё по журналу (с конца). Возвращает число возвращённых."""
    j = ff.load_cache(JOURNAL) or {'moves': []}
    back, left = Mover(), []
    for m in reversed(j['moves']):
        src, dst = m['from'], m['to']
        if os.path.exists(dst) and not os.path.exists(src):
            os.makedirs(os.path.dirname(src), exist_ok=True)
            os.replace(dst, src)
            back.moves.append((dst, src, 'откат'))
        elif not os.path.exists(src):
            left.append(m)
    per_box = {}
    for s, d, _ in back.moves:
        b = box_of(d)
        if b:
            per_box.setdefault(b, {})[os.path.relpath(s, b)] = os.path.relpath(d, b)
    for b, ren in per_box.items():
        fix_opis(b, ren, log)
    rekey_caches({norm(s): norm(d) for s, d, _ in back.moves})
    ff.save_cache({'moves': left}, JOURNAL)
    for r, ds, fs in sorted(os.walk(OUT), key=lambda x: -len(x[0])):  # пустые папки перевозок
        if r != OUT and not os.listdir(r):
            os.rmdir(r)
    return len(back.moves)


# ---------- ПОМОЙКА для текстов писем и логотипов (вечером до распознавания) ----------
def is_junk(name, size):
    low = name.lower()
    if low.endswith('.txt') and '_письмо_' in low:
        return True
    return os.path.splitext(low)[1] in IMG and (size < SMALL_IMG or 'mailrusigimg' in low)


def junk_folder(path):
    b = box_of(path)
    return os.path.join(JUNK, os.path.basename(b), os.path.relpath(os.path.dirname(path), b))


def pomoyka(log=print):
    mv = Mover()
    for box in boxes():
        for dirpath, _, files in os.walk(box):
            for fn in files:
                src = os.path.join(dirpath, fn)
                if is_junk(fn, os.path.getsize(src)):
                    mv.move(src, junk_folder(src), 'текст письма / логотип')
    mv.finish(log)
    return len(mv.moves)


# ---------- письмо, из которого пришёл файл ----------
def letters():
    """{путь файла сейчас: {'from', 'addr', 'subject', 'text_path'}} по описям ящиков."""
    out = {}
    for box in boxes():
        path = os.path.join(box, 'Опись.csv')
        if not os.path.exists(path):
            continue
        with open(path, encoding='utf-8-sig', newline='') as f:
            for r in csv.DictReader(f, delimiter=';'):
                if r.get('Путь к файлу'):
                    out[norm(os.path.join(box, r['Путь к файлу']))] = {
                        'from': r.get('От кого') or '', 'addr': r.get('Адрес отправителя') or '', 'subject': r.get('Тема') or '',
                        'text_path': os.path.normpath(os.path.join(box, r['Текст письма'])) if r.get('Текст письма') else ''}
    return out


def letter_body(info, limit=4000):
    p = info.get('text_path') if info else ''
    if not p or not os.path.exists(p):
        return ''
    try:
        with open(p, encoding='utf-8-sig', errors='ignore') as f:
            t = f.read()
    except OSError:
        return ''
    t = t.split('-' * 60, 1)[-1]
    t = re.split(r'\n\s*(-{2,}\s*\n|>|с уважением|best regards|отправлено из|-----original|пересылаемое сообщение)', t, 1, flags=re.I)[0]
    return t[:limit]


# ---------- имена ----------
def clean(s, limit=50):
    s = re.sub(r'[\\/:*?"<>|\r\n\t«»“”„]+', ' ', s or '')
    return re.sub(r'\s+', ' ', s).strip(' .,-')[:limit].strip(' .,-')


BAD_CP = re.compile(r'лицо|уполномоч|^г\.|\bг\.\s|москв|иркутск|област|район|улиц|\bул\.|покупател|продав|поставщ|грузо|@', re.I)


def org_name(s):
    s = clean(s, 90)
    ip = re.match(r'^ИП\s+([А-ЯЁ][а-яё]+)', s)
    if ip:
        return 'ИП ' + ip.group(1)
    s = re.sub(r'\b(ООО|ОАО|ЗАО|АО|ПАО|ТК)\b', ' ', s)
    words = []
    for w in s.split():
        if w.lower() not in (x.lower() for x in words):
            words.append(w)
    return clean(' '.join(words))


SELLER = re.compile(r'(продавец|поставщик|исполнитель|получатель)\W{0,6}(ип|ооо|оао|зао|пао|ао)\s+[«"“]?\s*'
                    r'([а-яёa-z0-9][а-яёa-z0-9 .-]{2,40}?)\s*(?=[»"”,(]|\s(адрес|инн|кпп|огрн|р/с|расч|юр)|$)', re.I)


def seller(raw):
    for m in SELLER.finditer(re.sub(r'\s+', ' ', raw or '')[:3000]):
        form, name = m.group(2).upper(), m.group(3).strip(' .-')
        if kf.VL.search(name) or len(name) < 3:
            continue
        name = ' '.join(w[:1].upper() + w[1:].lower() if w.islower() else w for w in name.split())
        return f'{form} {name}'
    return ''


def counterparty(card, info, raw=''):
    """(контрагент, откуда взято) — для отчёта."""
    cp = card.get('counterparty') or ''
    if not cp or kf.VL.search(cp) or BAD_CP.search(cp):
        cp = seller(raw) or cp
    if cp and not kf.VL.search(cp) and not BAD_CP.search(cp) and len(org_name(cp)) >= 3:
        return org_name(cp), 'из документа'
    sender = (info or {}).get('from') or ''
    if sender and not kf.VL.search(sender) and '@' not in sender:
        return org_name(sender), 'по отправителю письма'
    return '', ''


STOP = set('''паспорт пасп паспорта прописка прописки регистрация права прав водительское водительского удостоверение
удостоверения вод уд ву стс птс свид свидетельство тс осаго полис скан сканы фото документы документ док доки водителя
водитель водителю машина машины прицеп прицепа тягач тягача лист листы стр страница страницы копия копии новый новая
img image scan photo fwd re fw dc jpg jpeg pdf png doc docx для от на по и с без темы письмо сзади спереди лицевая
оборот разворот главная первая вторая данные паспортные карта карточка трудовой договор аренды аренда диагностическая
снилс инн гпх ип ооо водительские справка путевой лист файлов файл'''.split())
SURNAME_END = re.compile(r'(ов|ев|ёв|ин|ын|ова|ева|ёва|ина|ына|ский|цкий|ская|цкая|енко|ко|ук|юк|их|ых|ян|ец|ич)$')
BRANDS = re.compile(r'^(камаз|маз|ман|вольво|скани|мерседес|хово|шахман|шакман|ситрак|фусо|газел|исузу|хендай|хино|даф|ивеко|'
                    r'фотон|донгфенг|джак|валдай|рено|фав|урал|зил|краз|тонар|шмиц|кроне|когель|вектор|ниссан|тойот|тягач|'
                    r'полуприцеп|комсомольск|братск|болохов|щелков|мытищ|лосин)')


def surname(text):
    from pary_zayavok import cities
    for w in re.findall(r'[А-ЯЁа-яё]{4,}', text or ''):
        lw = w.lower().replace('ё', 'е')
        if lw in STOP or BRANDS.match(lw) or not SURNAME_END.search(lw) or cities(lw) or any(
                lw.startswith(s) for s in ('паспорт', 'удост', 'свидетел', 'водит', 'прицеп', 'докум', 'регистрац',
                                           'страниц', 'прописк', 'файл', 'перевоз', 'заявк', 'рейс', 'груз', 'логист')):
            continue
        return w[0].upper() + w[1:].lower()
    return ''


def is_rent(card, raw):
    return bool(re.search(r'аренд', card['file'], re.I) or
                re.search(r'аренд\S*\s+(транспортн|автомоб|тс\b|тягач|прицеп|полуприцеп)', (raw or '')[:2000], re.I))


def driver_folder(card, info, feat):
    base = re.sub(r'^\d{4}-\d\d-\d\d_', '', os.path.splitext(card['file'])[0])
    s = surname(base)
    if s:
        return s, 'из имени файла'
    if feat.get('driver') and surname(feat['driver']):
        return surname(feat['driver']), 'из документа'
    if feat.get('plates'):
        return min(feat['plates']), 'номер машины из документа'
    s = surname((info or {}).get('subject', ''))
    if s:
        return s, 'из темы письма'
    sender = (info or {}).get('from') or ''
    if sender and not kf.VL.search(sender):
        return clean(sender), 'по отправителю письма'
    return 'Не определено', ''


# ---------- к какой перевозке относится ТН / счёт / акт ----------
ORG_STOP = {'восточная', 'логистика', 'логистик', 'logistics', 'транс', 'трансп', 'групп', 'group', 'сервис', 'компания',
            'индивидуальный', 'предприниматель', 'общество', 'ограниченной', 'перевозчик', 'клиент', 'фирма',
            'транспорт', 'транспортная', 'новые', 'центр', 'восток', 'сибирь', 'москва', 'город', 'назначения',
            'система', 'системы', 'налог', 'карточка', 'реквизиты', 'банк', 'сбербанк', 'альфа'}


def org_keys(cp):
    """Ключи названия фирмы из заявки для поиска в реквизитах: «ИП Нестерович Максим» → «нестерови»,
    «ООО "ВЭЛМО ЛОГИСТИК"» → «вэлмо». Окончание (падеж) отрезаем."""
    import pary_zayavok as pz
    words = [w for w in re.findall(r'[а-яa-z]{4,}', pz.norm_org(cp)) if w not in ORG_STOP]
    if not words or 'восточн' in (cp or '').lower():
        return []
    w = words[0]
    return [w[:-1] if len(w) >= 6 else w]


def trip_folder_of(members):
    """Папка перевозки, если кто-то из её заявок уже лежит в Перевозки\\<Клиент>\\<папка>\\."""
    for m in members:
        d = os.path.dirname(m['path'])
        if norm(os.path.dirname(os.path.dirname(d))) == norm(OUT) and not os.path.basename(os.path.dirname(d)).startswith('_'):
            return d
    return None


def digits(s):
    m = re.search(r'\d{1,7}', s or '')
    return m.group(0).lstrip('0') if m else ''


def targets_of(res):
    """Перевозки (уверенные пары) и одиночные заявки — с чем сравнивать ТН и счета."""
    import pary_zayavok as pz

    def one(members, trip):
        f = [m['f'] for m in members]
        d = sorted(x['load'] or x['doc'] for x in f if x['load'] or x['doc'])
        return {'plates': set().union(*(x['plates'] for x in f)), 'surnames': {x['surname'] for x in f if x['surname']},
                'date': d[0] if d else None, 'from': next((x['from'] for x in f if x['from']), ''),
                'to': next((x['to'] for x in f if x['to']), ''), 'trip': trip,
                'nums': {digits(m.get('num')) for m in members if digits(m.get('num'))},
                'orgs': {pz.norm_org(m.get('counterparty')) for m in members if pz.norm_org(m.get('counterparty'))},
                'title': (os.path.basename(trip['folder']) if trip and trip.get('folder') else members[0]['file'])}
    out = [one(t['clients'] + t['carriers'], t) for t in res['sure']]
    for c in res['lone_c'] + res['lone_p']:
        x = one([c], None)
        x['lone'] = c  # одиночная заявка (клиента или перевозчику) — документ кладём к ней только при сильном совпадении
        out.append(x)
    return out


def when_ok(doc_date, received, t, before=3, after=10, late=45):
    """(точно?, в окне?, текст) — дата документа против даты погрузки перевозки."""
    if doc_date:
        days = (doc_date - t['date']).days
        return abs(days) <= before, -before <= days <= after, f'дата документа {days:+d} дн. от погрузки'
    if received:
        late_d = (received - t['date']).days
        return False, -2 <= late_d <= late, f'письмо через {late_d} дн. после погрузки'
    return False, False, ''


def match(doc, targets, kind):
    """(уровень 'sure'/'doubt'/None, перевозка, почему). kind: 'tn' или 'buh'."""
    from pary_zayavok import same_surname
    found = []
    for t in targets:
        if not t['date']:
            continue
        car = doc['plates'] & t['plates']
        drv = any(same_surname(a, b) for a in doc['surnames'] for b in t['surnames'])
        num = bool(doc['nums'] & t['nums'])
        org = bool(doc['org'] and doc['org'] in t['orgs'])
        if kind == 'tn':
            strict, loose, when = when_ok(doc['date'], doc['received'], t)
        else:  # счёт/акт выставляют после перевозки — до 2 месяцев
            strict, loose, when = when_ok(doc['date'], doc['received'], t, before=5, after=60, late=75)
        route_known = list(dict.fromkeys(x for x in (t['from'], t['to']) if x))
        route = len(route_known) == 2 and all(x in doc['cities'] for x in route_known)
        one_city = any(x in doc['cities'] and x != 'Иркутск' for x in route_known)
        why = ', '.join(filter(None, [f'№ заявки' if num else '', 'контрагент' if org else '',
                                      'машина ' + ', '.join(sorted(car)) if car else '', 'водитель' if drv else '',
                                      'маршрут ' + '–'.join(route_known) if route else
                                      ('город ' + ', '.join(x for x in route_known if x in doc['cities']) if one_city else ''),
                                      when]))
        if (car or drv) and loose:
            score = 5 + num + org
        elif num and (org or loose):
            score = 4 + org
        elif route and strict:
            score = 3
        elif car or drv or num or (route and loose) or (one_city and strict) or (org and loose and kind == 'buh'):
            score = 1
        else:
            continue
        found.append((score, t, why))
    if not found:
        return None, None, ''
    found.sort(key=lambda x: -x[0])
    best_score, best, why = found[0]
    key = lambda t: id(t['trip']) if t['trip'] else id(t)
    rivals = [x for x in found[1:] if x[0] == best_score and key(x[1]) != key(best)]
    # к одиночной заявке — только машина/водитель/№ заявки (маршрут+дата для неё слабо: Щёлково–Иркутск каждый день)
    need = 3 if best['trip'] else 4
    if best_score >= need and not rivals:
        if best_score == 3 and len([x for x in found if x[0] == 3]) > 1:
            return 'doubt', best, why + ' — таких перевозок несколько'
        return 'sure', best, why + ('' if best['trip'] else ' — к заявке без пары')
    note = ' — подходят несколько перевозок' if rivals else ' — совпадение слабое'
    return 'doubt', best, why + note


# ---------- главное ----------
def razlozhit(res, state, dry=False, log=print):
    """Разложить файлы почты переносом. Возвращает данные для отчёта и число переносов."""
    import build_kartoteka as bk
    import pary_zayavok as pz
    from pary_zayavok import features, raw_text, received
    known, other, fixes = bk.entry_texts(), bk.other_texts(), ff.load_cache(ff.FIXES)
    mail_info = letters()
    mv = Mover(dry)
    out = {'tn': [], 'buh': [], 'drv': [], 'junk': [], 'rekv': [], 'moved': 0}

    # одиночная заявка (путь) → её папка: Перевозки\<Клиент>\… или «_Перевозчик без клиента»\<Перевозчик>\…
    # (нужно для заявок из старого архива — они сами не переезжают, а документы к ним лежат в папке)
    lone_folders = state.setdefault('lone_folders', {})

    def lone_dir_of(c):
        if in_dir(c['path'], LONE_DIR):
            return os.path.dirname(c['path'])
        d = trip_folder_of([c]) or lone_folders.get(norm(c['path']))
        return d if d and (os.path.isdir(d) or norm(d) in used) else None

    # 1) перевозки: заявки из почты — в папку перевозки (одна папка на перевозку, у главного клиента);
    #    у заявки перевозчику появился клиент — её папка из «_Перевозчик без клиента» переезжает сюда целиком
    used = set()
    for t in res['sure']:
        members = t['clients'] + t['carriers']
        their_dirs = {lone_dir_of(m) for m in members} - {None}
        lone_dirs = {d for d in their_dirs if in_dir(d, LONE_DIR)}
        t['folder'] = trip_folder_of(members) or next(iter(sorted(their_dirs - lone_dirs)), None)
        mail_members = [v for m in members for v in mail_variants(m)]
        if not t['folder'] and (mail_members or lone_dirs):
            main = sorted(t['clients'], key=lambda c: (not c.get('counterparty'), not c['f']['load'],
                                                       not (c['f']['from'] or c['f']['to']), c['path']))[0]
            t['folder'] = new_trip_folder(main, used)
        if t['folder']:
            used.add(norm(t['folder']))
            for m in mail_members:
                mv.move(m['path'], t['folder'], 'заявка ' + ('клиента' if m['kind'] == 'Заявка с клиентом' else 'перевозчику'), m)
            for d in lone_dirs:
                for fn in os.listdir(d):
                    mv.move(os.path.join(d, fn), t['folder'], 'заявка перевозчику нашла клиента — папка переехала')
                for m in members:
                    lone_folders.pop(norm(m['path']), None)
        t['folders'] = [t['folder']] if t['folder'] else []

    targets = targets_of(res)
    cards = []
    for c in res['cards']:
        if not c.get('path') or c['file'].lower().endswith('.txt'):
            continue
        cards += mail_variants(c)
        if c['type'] == 'Бухгалтерия' and in_dir(c['path'], BUH_DIR) and os.path.exists(c['path']):
            cards.append(c)
    drv_letter, weak = {}, []
    for c in cards:
        info = mail_info.get(norm(c['path']), {})
        raw = raw_text(c, known, other, fixes) if c['type'] not in ('Фото без текста',) else ''
        if c['type'].startswith('ТН') or c['type'] == 'Бухгалтерия':
            kind = 'tn' if c['type'].startswith('ТН') else 'buh'
            body = letter_body(info) if kind == 'tn' else ''
            f = features(c, raw + '\n' + info.get('subject', '') + '\n' + body)
            num_rx = r'заявк\w*\s*(?:№|n|#)?\s*([a-zа-я]{0,3}-?\d{1,7})'
            cp, how = counterparty(c, info, raw)
            doc = {'plates': f['plates'], 'surnames': {f['surname']} if f['surname'] else set(),
                   'cities': set(pz.cities(raw)) | (set(pz.cities(info.get('subject', '') + '\n' + body)) if kind == 'tn' else set()),
                   'nums': {digits(x) for x in re.findall(num_rx, raw.lower()) if digits(x)},
                   'org': pz.norm_org(cp), 'date': pz.to_date(c.get('date') or ''), 'received': received(c)}
            if doc['date'] and doc['received'] and not (-60 <= (doc['received'] - doc['date']).days <= 120):
                doc['date'] = None  # OCR перепутал год/месяц
            lvl, t, why = match(doc, targets, kind)
            out[kind].append({'card': c, 'info': info, 'level': lvl, 'target': t, 'why': why, 'cp': cp, 'how': how,
                              'cities': sorted(doc['cities']), 'plates': sorted(doc['plates']), 'folder': ''})
        elif c['type'] == 'Водитель / машина' or (c['type'] == 'Договор' and is_rent(c, raw)):
            name, how = driver_folder(c, info, features(c, raw) if raw else {})
            folder = os.path.join(DRV_DIR, name)
            out['drv'].append({'card': c, 'info': info, 'folder': folder, 'how': how})
            if info.get('text_path'):
                drv_letter.setdefault(norm(info['text_path']), folder)
        elif c['type'] in ('Фото без текста', 'Не распознано'):
            weak.append((c, info))
        elif c['type'] == 'Прочее':
            out['junk'].append({'card': c, 'why': 'прочее (рассылка, картинка, не документ)'})
        elif c['type'].startswith('Почта'):  # трек-номера, почтовые квитанции — не нужны (владелец 05.11.2026)
            out['junk'].append({'card': c, 'why': 'почта: трек-номер / квитанция', 'force': True})
        elif c['type'].startswith('Реквизит'):  # карточки фирм — к их заявке, иначе в ПОМОЙКУ
            cp, _ = counterparty(c, info, raw)
            out['rekv'].append({'card': c, 'info': info, 'cp': cp, 'folder': '', 'status': '',
                                'head': ' '.join([cp, c['file'], raw[:300]]).lower().replace('ё', 'е')})

    # документы водителя из одного письма — в одну папку: по самому надёжному имени (фамилия/номер), не по отправителю
    strength = {'из имени файла': 3, 'из документа': 3, 'номер машины из документа': 2, 'из темы письма': 1}
    groups = {}
    for x in out['drv']:
        if x['info'].get('text_path'):
            groups.setdefault(norm(x['info']['text_path']), []).append(x)
    for letter, group in groups.items():
        best = max(group, key=lambda x: strength.get(x['how'], 0))
        if strength.get(best['how'], 0) >= 2:
            for x in group:
                if strength.get(x['how'], 0) < 2:
                    x['folder'], x['how'] = best['folder'], 'из того же письма: ' + best['how']
            drv_letter[letter] = best['folder']

    # ТН из одного письма — одна перевозка
    by_letter = {}
    for x in out['tn']:
        if x['info'].get('text_path'):
            by_letter.setdefault(norm(x['info']['text_path']), []).append(x)
    for group in by_letter.values():
        sure = {id(x['target']): x['target'] for x in group if x['level'] == 'sure'}
        if len(sure) == 1:
            t = next(iter(sure.values()))
            for x in group:
                if x['level'] != 'sure':
                    x.update(level='sure', target=t, why='из того же письма, что и другая ТН этой перевозки')

    # нечитаемое: из письма с документами водителя — к нему, картинка — в ПОМОЙКУ, остальное (Word, PDF) — остаётся
    for c, info in weak:
        folder = drv_letter.get(norm(info.get('text_path') or '?'))
        if folder:
            out['drv'].append({'card': c, 'info': info, 'folder': folder, 'how': 'фото из того же письма'})
        elif os.path.splitext(c['file'])[1].lower() in IMG:
            out['junk'].append({'card': c, 'why': 'нечитаемое фото'})

    # переносы
    for kind, label in (('tn', 'ТН'), ('buh', 'счёт/акт/УПД')):
        for x in out[kind]:
            if x['level'] == 'sure' and x['target']['trip']:
                trip = x['target']['trip']
                if not trip.get('folder'):
                    main = sorted(trip['clients'], key=lambda c: (not c.get('counterparty'), c['path']))[0]
                    trip['folder'] = new_trip_folder(main, used)
                    trip['folders'] = [trip['folder']]
                    used.add(norm(trip['folder']))
                x['folder'] = trip['folder']
                x['status'] = 'перенесён к перевозке'
            elif x['level'] == 'sure':  # заявка без пары: документ — к ней, и она сама (если из почты)
                c = x['target']['lone']
                carrier = c['kind'] == 'Заявка перевозчику'
                folder = lone_dir_of(c)
                if not folder:
                    if carrier and not c.get('counterparty') and x['cp']:
                        c = dict(c, counterparty=x['cp'])  # перевозчик не прочитан в заявке — берём из его счёта
                    folder = new_trip_folder(c, used, root=LONE_DIR if carrier else OUT)
                    used.add(norm(folder))
                c = x['target']['lone']
                lone_folders[norm(c['path'])] = folder
                for v in mail_variants(c):
                    mv.move(v['path'], folder, 'заявка ' + ('перевозчику (клиента пока нет)' if carrier else
                                                           'клиента (заявки перевозчику пока нет)'), v)
                x['folder'] = folder
                x['status'] = 'перенесён к заявке ' + ('перевозчика' if carrier else 'клиента')
            elif kind == 'buh':  # не привязан — в «_Счета и акты» по контрагенту, в «Почте» не оставляем
                x['folder'] = os.path.join(BUH_DIR, x['cp'] or 'Контрагент не определён')
                x['status'] = 'в «_Счета и акты» — заявка не найдена'
            else:
                x['status'] = 'в Почте — проверь' if x['level'] else 'в Почте — перевозка не найдена'
            if x['folder']:
                mv.move(x['card']['path'], x['folder'], label + ': ' + (x['why'] or 'по контрагенту'), x['card'])
    # нечитаемый счёт (архив .zip, кривой скан): из письма с разложенным счётом — туда же; по имени «счёт/акт/УПД» — в «_Счета и акты»
    buh_letter = {norm(x['info']['text_path']): x['folder'] for x in out['buh'] if x['folder'] and x['info'].get('text_path')}
    for p, i in mail_info.items():  # разложенные раньше: соседи по письму уже лежат в «Перевозках» (не у водителей)
        if i.get('text_path') and in_dir(p, OUT) and not in_dir(p, DRV_DIR):
            buh_letter.setdefault(norm(i['text_path']), os.path.dirname(p))
    by_path = {norm(p): c for c in res['cards'] for p in [c.get('path')] + list(c.get('other_paths') or []) if p}
    unread = []  # и то, чего нет в картотеке (архивы .zip/.rar)
    for box in boxes():
        for dirpath, _, files in os.walk(box):
            for fn in files:
                p = os.path.join(dirpath, fn)
                c = by_path.get(norm(p))
                if BUH_NAME.search(fn) and not fn.startswith('Опись') and (
                        c is None or c['type'] in ('Не распознано', 'Фото без текста', 'Прочее')):
                    unread.append(c or {'path': p, 'file': fn, 'folder': dirpath, 'type': 'Не прочитан', 'received': ''})
    for c in unread:
        info = mail_info.get(norm(c['path']), {})
        folder = buh_letter.get(norm(info.get('text_path') or '?'))
        how = 'из того же письма, что и разложенный счёт'
        if not folder:
            cp, _ = counterparty(c, info)
            folder, how = os.path.join(BUH_DIR, cp or 'Контрагент не определён'), 'по имени файла, контрагент — отправитель'
        out['junk'] = [j for j in out['junk'] if j['card'] is not c]
        out['buh'].append({'card': c, 'info': info, 'level': None, 'target': None, 'why': how, 'cp': '', 'how': how,
                           'cities': [], 'plates': [], 'folder': folder, 'status': 'нечитаемый счёт/акт — по письму'})
        mv.move(c['path'], folder, 'счёт/акт (не читается): ' + how, c)
    for x in out['drv']:
        mv.move(x['card']['path'], x['folder'], 'водитель/машина: ' + x['how'], x['card'])
    # «мусор» из письма, где что-то легло к перевозке или к заявке, — скорее страницы того же комплекта: туда же
    for p, i in mail_info.items():
        if i.get('text_path') and in_dir(p, OUT) and not in_dir(p, DRV_DIR) and not in_dir(p, BUH_DIR):
            buh_letter.setdefault(norm(i['text_path']), os.path.dirname(p))
    for x in out['tn'] + out['buh']:
        if x['folder'] and x['info'].get('text_path') and not in_dir(x['folder'], BUH_DIR):
            buh_letter[norm(x['info']['text_path'])] = x['folder']
    # реквизиты: из письма с заявкой → к ней; по названию фирмы / фамилии ИП → к её заявке; из письма водителя → к нему
    reqs = []  # (заявка, её папка или None — заявка ещё в Почте)
    for t in res['sure']:
        reqs += [(m, t.get('folder')) for m in t['clients'] + t['carriers']]
    reqs += [(c, lone_dir_of(c)) for c in res['lone_c'] + res['lone_p']]
    placed = []  # (карточка, контрагент, папка) — счета/акты/заявки, уже лежащие в «Перевозках»
    if out['rekv']:
        for c in res['cards']:
            for v in [c.get('path')] + list(c.get('other_paths') or []):
                if v and in_dir(v, OUT) and not in_dir(v, DRV_DIR) and c['type'] in ('Бухгалтерия', 'Заявка') \
                        and os.path.exists(v):
                    cp, how = (c.get('counterparty'), '') if c.get('counterparty') else \
                        counterparty(c, mail_info.get(norm(v), {}))
                    if cp and 'отправител' not in how:  # имя из подписи письма («Алексей …») — не название фирмы
                        placed.append((c, cp, os.path.dirname(v)))
        for p, i in mail_info.items():  # документы водителя, разложенные раньше, — их письма
            if i.get('text_path') and in_dir(p, DRV_DIR):
                drv_letter.setdefault(norm(i['text_path']), os.path.dirname(p))
    for x in out['rekv']:
        letter = norm(x['info'].get('text_path') or '?')
        got = received(x['card'])

        def near(c, days=45):
            r = received(c)
            return bool(got and r and abs((got - r).days) <= days)

        def by_name(c):
            return any(re.search(r'(?<![а-яa-z])' + re.escape(k) + r'[а-яa-z]{0,3}(?![а-яa-z])', x['head'])
                       for k in org_keys(c.get('counterparty')))

        addr = (x['info'].get('addr') or '').lower()
        found = [(c, d) for c, d in reqs if near(c) and by_name(c)]
        if not found and addr and 'vostok.logist' not in addr:  # тот же отправитель прислал заявку
            found = [(c, d) for c, d in reqs if near(c, 20) and
                     (mail_info.get(norm(c['path']), {}).get('addr') or '').lower() == addr]
        found.sort(key=lambda cd: (cd[1] is None, abs((received(cd[0]) - got).days)))
        # счёт/акт этой же фирмы уже разложен — реквизиты туда же (к перевозке или в «_Счета и акты\<фирма>»)
        buh = sorted((b for b in placed if near(b[0], 60) and by_name({'counterparty': b[1]})),
                     key=lambda b: in_dir(b[2], BUH_DIR))
        buh = [{'folder': b[2], 'cp': b[1]} for b in buh]
        if letter in drv_letter:
            x['folder'], x['status'] = drv_letter[letter], 'к водителю: из того же письма'
        elif buh_letter.get(letter) and not in_dir(buh_letter[letter], BUH_DIR):
            x['folder'], x['status'] = buh_letter[letter], 'к заявке: из того же письма'
        elif found and found[0][1]:
            x['folder'], x['status'] = found[0][1], 'к заявке: ' + (found[0][0].get('counterparty') or '')[:40]
        elif buh:
            x['folder'], x['status'] = buh[0]['folder'], 'к счёту этой фирмы: ' + buh[0]['cp'][:40]
        elif found:
            x['status'] = 'в Почте — ждёт свою заявку (она ещё не разложена)'
        else:
            x['folder'], x['status'] = junk_folder(x['card']['path']), 'в ПОМОЙКУ: заявка не найдена'
        if x['folder']:
            mv.move(x['card']['path'], x['folder'], 'реквизиты ' + x['status'], x['card'])
    for x in out['junk']:
        info = mail_info.get(norm(x['card']['path']), {})
        letter = norm(info.get('text_path') or '?')
        folder = None if x.get('force') else buh_letter.get(letter)
        if x.get('force'):
            mv.move(x['card']['path'], junk_folder(x['card']['path']), x['why'], x['card'])
        elif folder and not in_dir(folder, BUH_DIR):
            mv.move(x['card']['path'], folder, 'из того же письма, что и документы перевозки', x['card'])
            x['why'] = 'к перевозке: из того же письма'
        elif letter in drv_letter:  # страница из письма с документами водителя
            mv.move(x['card']['path'], drv_letter[letter], 'из того же письма, что и документы водителя', x['card'])
            x['why'] = 'к водителю: из того же письма'
        else:
            mv.move(x['card']['path'], junk_folder(x['card']['path']), x['why'], x['card'])
    mv.finish(log)
    out['moved'], out['moves'] = len(mv.moves), mv.moves
    return out


def new_trip_folder(main, used, root=OUT):
    """Имя папки новой перевозки: <root>\\<Клиент или перевозчик>\\<ГГГГ-ММ-ДД> Откуда–Куда, Фамилия (+ (2), если занято)."""
    import pary_zayavok as pz
    f = main['f']
    d = f['load'] or f['doc']
    route = '–'.join(x for x in (f['from'], f['to']) if x) if f['from'] != f['to'] else f['from']
    who = f['driver'].split()[0] if f['driver'] else ''
    name = pz.clean(' '.join(p for p in (d.isoformat() if d else 'без даты', route) if p) + (', ' + who if who else ''), 90)
    who_org = pz.client_name(main)
    if root != OUT and who_org == 'Клиент не определён':
        who_org = 'Перевозчик не определён'
    path = os.path.join(root, who_org, name)
    base, n = path, 2
    while norm(path) in used or os.path.exists(path):
        path, n = f'{base} ({n})', n + 1
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--pomoyka', action='store_true', help='тексты писем и логотипы → Почта\\ПОМОЙКА')
    ap.add_argument('--undo', action='store_true', help='вернуть всё перенесённое на старые места')
    a = ap.parse_args()
    if a.pomoyka:
        print(f'В ПОМОЙКУ перенесено: {pomoyka()}')
    elif a.undo:
        print(f'Возвращено на место: {undo()}')
    else:
        ap.print_help()


if __name__ == '__main__':
    main()
