# Приложение «Экспедирование через склад»: грузы (заявки), склады, фуры.
# База — один файл sklad.db рядом. Окно — в браузере.
# Запуск: python app-sklad/server.py  → откроется http://127.0.0.1:8765
import json
import os
import re
import sqlite3
import sys
import threading
import webbrowser
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
DB = Path(os.environ.get('SKLAD_DB') or HERE / 'sklad.db')   # SKLAD_DB / SKLAD_PORT — для проверки на копии
STATIC = HERE / 'static'
PORT = int(os.environ.get('SKLAD_PORT') or 8765)

SKLADY = ['Щёлково', 'Красноярск', 'Иркутск', 'Улан-Удэ', 'Чита']  # слова владельца, 2026-11-02
MANAGERS = ['Александр', 'Артём', 'Таня', 'Ильяс', 'Оля', 'Андрей', 'Илья']  # логисты из плана зп с прибыли по фуре

SCHEMA = """
CREATE TABLE IF NOT EXISTS sklad(
  id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, address TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS gruz(
  id INTEGER PRIMARY KEY, nomer TEXT, created TEXT,
  client TEXT DEFAULT '', company TEXT DEFAULT 'ООО ВЛ', pay_form TEXT DEFAULT '',
  cargo TEXT DEFAULT '', kg REAL, m3 REAL, places INTEGER,
  from_addr TEXT DEFAULT '', to_addr TEXT DEFAULT '', rate_client REAL,
  sklad_from INTEGER, sklad_to INTEGER,          -- склад отправки и склад назначения (он же точка выгрузки фуры)
  status TEXT DEFAULT 'ждёт забора',             -- ждёт забора / на складе / в фуре / прибыл / доставлен
  sklad_id INTEGER, fura_id INTEGER,             -- где груз сейчас: склад или фура (пока едет)
  note TEXT DEFAULT '', parent_id INTEGER);      -- parent_id — от какого груза отделена часть
                                                 -- остальные поля — NEW_COLS (менеджер, оплата, прочие расходы)
CREATE TABLE IF NOT EXISTS manager(
  id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE);
CREATE TABLE IF NOT EXISTS voditel(              -- водители: паспорт, права, машина (личные данные — только здесь)
  id INTEGER PRIMARY KEY, created TEXT, fio TEXT DEFAULT '', phone TEXT DEFAULT '', birth_date TEXT DEFAULT '',
  passport TEXT DEFAULT '', passport_issued_by TEXT DEFAULT '', passport_date TEXT DEFAULT '', passport_code TEXT DEFAULT '',
  vu TEXT DEFAULT '', vu_date TEXT DEFAULT '', vu_until TEXT DEFAULT '', vu_cats TEXT DEFAULT '',
  auto_brand TEXT DEFAULT '', auto_plate TEXT DEFAULT '', auto_sts TEXT DEFAULT '',
  trailer_brand TEXT DEFAULT '', trailer_plate TEXT DEFAULT '', trailer_sts TEXT DEFAULT '',
  carrier TEXT DEFAULT '', carrier_inn TEXT DEFAULT '', note TEXT DEFAULT '',
  files TEXT DEFAULT '[]');                      -- оригиналы документов в app-sklad/files/voditel/<id>/
CREATE TABLE IF NOT EXISTS kontragent(           -- клиенты и перевозчики: реквизиты для заявок
  id INTEGER PRIMARY KEY, created TEXT, name TEXT DEFAULT '', inn TEXT DEFAULT '', kpp TEXT DEFAULT '', ogrn TEXT DEFAULT '',
  address TEXT DEFAULT '', post_address TEXT DEFAULT '', rs TEXT DEFAULT '', bank TEXT DEFAULT '', bik TEXT DEFAULT '',
  ks TEXT DEFAULT '', director TEXT DEFAULT '', basis TEXT DEFAULT '', phone TEXT DEFAULT '', email TEXT DEFAULT '',
  note TEXT DEFAULT '', files TEXT DEFAULT '[]'); -- оригиналы в app-sklad/files/firma/<id>/
CREATE TABLE IF NOT EXISTS reys(                 -- какими фурами ехал груз (может быть несколько — перегруз)
  id INTEGER PRIMARY KEY, gruz_id INTEGER, fura_id INTEGER,
  point INTEGER,                                 -- склад, где выгрузить груз из этой фуры
  UNIQUE(gruz_id, fura_id));
CREATE TABLE IF NOT EXISTS leg(                  -- отрезки: «забор» (до склада) и «развоз» (со склада)
  id INTEGER PRIMARY KEY, gruz_id INTEGER, kind TEXT,
  zayavka TEXT DEFAULT '', dt TEXT DEFAULT '', from_addr TEXT DEFAULT '', to_addr TEXT DEFAULT '',
  carrier TEXT DEFAULT '', driver TEXT DEFAULT '', rate REAL,
  UNIQUE(gruz_id, kind));
CREATE TABLE IF NOT EXISTS fura(
  id INTEGER PRIMARY KEY, nomer_ts TEXT DEFAULT '', carrier TEXT DEFAULT '', driver TEXT DEFAULT '',
  zayavka TEXT DEFAULT '', dt_out TEXT DEFAULT '', sklad_from INTEGER,
  route TEXT DEFAULT '[]',                       -- склады выгрузки по порядку (id)
  cap_m3 REAL DEFAULT 82, cap_t REAL DEFAULT 20, rate REAL,
  status TEXT DEFAULT 'собирается',              -- собирается / в пути / прибыла
  note TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS platezh(              -- поступления из банковских выписок
  id INTEGER PRIMARY KEY, key TEXT NOT NULL UNIQUE,  -- отпечаток: счёт|№ п/п|дата|сумма|ИНН — повтор не задваивает
  acc TEXT, company TEXT, num TEXT, dt TEXT, sum REAL, payer TEXT, inn TEXT, purp TEXT,
  loaded TEXT, ignored INTEGER DEFAULT 0);       -- ignored — «не к грузам» (проценты банка, возвраты и т.п.)
CREATE TABLE IF NOT EXISTS oplata(               -- какой платёж к какому грузу и на сколько
  id INTEGER PRIMARY KEY, platezh_id INTEGER, gruz_id INTEGER, sum REAL,
  UNIQUE(platezh_id, gruz_id));
CREATE TABLE IF NOT EXISTS log(                  -- история движения груза
  id INTEGER PRIMARY KEY, gruz_id INTEGER, dt TEXT, action TEXT, sklad_id INTEGER, fura_id INTEGER);
"""

# Поля, добавленные после первой версии (в новой базе создаются сразу, в старую дописываются в init_db).
# Формы оплаты — текстом: «с НДС» (1,22), «без НДС» (1,06), «наличные» (1) — как в таблице зп с прибыли по фуре.
NEW_COLS = {
    'gruz': {'manager': "TEXT DEFAULT ''", 'client_id': 'INTEGER',          # заказчик из справочника контрагентов
             'other_cost': 'REAL', 'other_form': "TEXT DEFAULT ''",          # прочие свои расходы (СДЭК, кран)
             'paid_sum': 'REAL', 'paid_date': "TEXT DEFAULT ''",             # оплата клиента — для начисления зп
             'schet': "TEXT DEFAULT ''",                                     # № счёта клиенту — ищем в назначении платежа
             'paid_manual': 'REAL'},                                         # часть оплаты, введённая руками до выписки
    'leg': {'pay_form': "TEXT DEFAULT ''",                                   # форма оплаты перевозчика
            'voditel_id': 'INTEGER', 'carrier_id': 'INTEGER'},               # водитель и перевозчик из справочников
    'fura': {'voditel_id': 'INTEGER', 'rate_form': "TEXT DEFAULT ''",
             'sklad_load': 'REAL', 'sklad_load_form': "TEXT DEFAULT ''",     # общие расходы фуры: склад погрузки,
             'sklad_unload': 'REAL', 'sklad_unload_form': "TEXT DEFAULT ''",  # склад приёмки,
             'other': 'REAL', 'other_form': "TEXT DEFAULT ''"},              # прочие общие
}

GRUZ_FIELDS = ['client', 'company', 'pay_form', 'cargo', 'kg', 'm3', 'places', 'from_addr', 'to_addr',
               'rate_client', 'sklad_from', 'sklad_to', 'note', 'manager', 'other_cost', 'other_form',
               'paid_sum', 'paid_date', 'client_id', 'schet']
LEG_FIELDS = ['zayavka', 'dt', 'from_addr', 'to_addr', 'carrier', 'driver', 'rate', 'pay_form', 'voditel_id', 'carrier_id']
KONTRAGENT_FIELDS = ['name', 'inn', 'kpp', 'ogrn', 'address', 'post_address', 'rs', 'bank', 'bik', 'ks',
                     'director', 'basis', 'phone', 'email', 'note']
VODITEL_FIELDS = ['fio', 'phone', 'birth_date', 'passport', 'passport_issued_by', 'passport_date', 'passport_code',
                  'vu', 'vu_date', 'vu_until', 'vu_cats', 'auto_brand', 'auto_plate', 'auto_sts',
                  'trailer_brand', 'trailer_plate', 'trailer_sts', 'carrier', 'carrier_inn', 'note']
FILES = HERE / 'files'  # оригиналы документов водителей (не в git)
FURA_FIELDS = ['nomer_ts', 'carrier', 'driver', 'voditel_id', 'zayavka', 'dt_out', 'sklad_from', 'route',
               'cap_m3', 'cap_t', 'rate', 'note', 'rate_form', 'sklad_load', 'sklad_load_form',
               'sklad_unload', 'sklad_unload_form', 'other', 'other_form']


class Oshibka(Exception):
    """Ошибка, которую показываем пользователю как есть."""


def connect():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA foreign_keys = ON')
    return con


def init_db():
    con = connect()
    con.executescript(SCHEMA)
    # перевод базы фазы 1: одна фура на груз → таблица рейсов
    if 'parent_id' not in [r[1] for r in con.execute('PRAGMA table_info(gruz)')]:
        con.execute('ALTER TABLE gruz ADD COLUMN parent_id INTEGER')
        con.execute('INSERT OR IGNORE INTO reys(gruz_id, fura_id, point) '
                    'SELECT id, fura_id, sklad_to FROM gruz WHERE fura_id IS NOT NULL')
        con.execute("UPDATE gruz SET fura_id=NULL WHERE status!='в фуре'")
    for table, cols in NEW_COLS.items():  # поля, добавленные позже, — дописываем в старую базу
        have = [r[1] for r in con.execute(f'PRAGMA table_info({table})')]
        for col, typ in cols.items():
            if col not in have:
                con.execute(f'ALTER TABLE {table} ADD COLUMN {col} {typ}')
    if not con.execute('SELECT 1 FROM sklad').fetchone():
        con.executemany('INSERT INTO sklad(name) VALUES (?)', [(s,) for s in SKLADY])
    if not con.execute('SELECT 1 FROM manager').fetchone():
        con.executemany('INSERT INTO manager(name) VALUES (?)', [(m,) for m in MANAGERS])
    con.commit()
    con.close()


def today():
    return date.today().isoformat()


def rows(con, sql, *args):
    return [dict(r) for r in con.execute(sql, args)]


def one(con, sql, *args):
    r = con.execute(sql, args).fetchone()
    if r is None:
        raise Oshibka('Запись не найдена')
    return dict(r)


def add_log(con, gruz_id, dt, action, sklad_id=None, fura_id=None):
    con.execute('INSERT INTO log(gruz_id, dt, action, sklad_id, fura_id) VALUES (?,?,?,?,?)',
                (gruz_id, dt or today(), action, sklad_id, fura_id))


def state(con):
    gruzy = rows(con, 'SELECT * FROM gruz ORDER BY id DESC')
    legs = rows(con, 'SELECT * FROM leg')
    for g in gruzy:
        g['legs'] = {l['kind']: l for l in legs if l['gruz_id'] == g['id']}
    furas = rows(con, 'SELECT * FROM fura ORDER BY id DESC')
    for f in furas:
        f['route'] = json.loads(f['route'] or '[]')
    return {'today': today(),
            'sklady': rows(con, 'SELECT * FROM sklad ORDER BY id'),
            'managers': rows(con, 'SELECT * FROM manager ORDER BY id'),
            'voditeli': [{**v, 'files': json.loads(v['files'] or '[]')} for v in rows(con, 'SELECT * FROM voditel ORDER BY fio')],
            'firmy': [{**v, 'files': json.loads(v['files'] or '[]')} for v in rows(con, 'SELECT * FROM kontragent ORDER BY name')],
            'oplaty': rows(con, 'SELECT o.id, o.gruz_id, o.sum, o.platezh_id, p.dt, p.num, p.company, p.payer '
                                'FROM oplata o JOIN platezh p ON p.id=o.platezh_id ORDER BY p.dt, o.id'),
            'gruzy': gruzy, 'furas': furas, 'reys': rows(con, 'SELECT * FROM reys ORDER BY id'),
            'log': rows(con, 'SELECT * FROM log ORDER BY dt, id')}


# ---------- действия ----------

def gruz_save(con, d):
    vals = {k: d.get(k) for k in GRUZ_FIELDS}
    if d.get('id'):
        gid = d['id']
        con.execute('UPDATE gruz SET ' + ', '.join(f'{k}=?' for k in vals) + ' WHERE id=?', [*vals.values(), gid])
    else:
        cur = con.execute('INSERT INTO gruz(created, ' + ', '.join(vals) + ') VALUES (?' + ',?' * len(vals) + ')',
                          [today(), *vals.values()])
        gid = cur.lastrowid
        con.execute('UPDATE gruz SET nomer=? WHERE id=?', (f'Г-{gid:04d}', gid))
    paid_recalc(con, gid)  # есть платежи из выписки — оплата считается из них, а не из поля
    for kind, leg in (d.get('legs') or {}).items():
        lv = {k: leg.get(k) for k in LEG_FIELDS}
        con.execute('INSERT INTO leg(gruz_id, kind, ' + ', '.join(lv) + ') VALUES (?,?' + ',?' * len(lv) + ') '
                    'ON CONFLICT(gruz_id, kind) DO UPDATE SET ' + ', '.join(f'{k}=excluded.{k}' for k in lv),
                    [gid, kind, *lv.values()])
    return {'id': gid}


def gruz_delete(con, d):
    g = one(con, 'SELECT * FROM gruz WHERE id=?', d['id'])
    if g['status'] == 'в фуре':
        raise Oshibka('Груз в фуре — сначала уберите его из фуры')
    for t in ('leg', 'log', 'reys', 'oplata'):
        con.execute(f'DELETE FROM {t} WHERE gruz_id=?', (g['id'],))
    con.execute('DELETE FROM gruz WHERE id=?', (g['id'],))


def gruz_accept(con, d):
    g = one(con, 'SELECT * FROM gruz WHERE id=?', d['id'])
    if g['status'] != 'ждёт забора':
        raise Oshibka(f'Принять можно только груз «ждёт забора», а этот — «{g["status"]}»')
    sk = d.get('sklad_id') or g['sklad_from']
    if not sk:
        raise Oshibka('Выберите склад')
    con.execute("UPDATE gruz SET status='на складе', sklad_id=?, sklad_from=? WHERE id=?", (sk, sk, g['id']))
    add_log(con, g['id'], d.get('dt'), 'принят на склад', sk)


def gruz_deliver(con, d):
    g = one(con, 'SELECT * FROM gruz WHERE id=?', d['id'])
    if g['status'] not in ('прибыл', 'на складе'):
        raise Oshibka(f'Выдать можно груз со склада, а этот — «{g["status"]}»')
    add_log(con, g['id'], d.get('dt'), 'выдан на развоз / доставлен', g['sklad_id'])
    con.execute("UPDATE gruz SET status='доставлен', sklad_id=NULL WHERE id=?", (g['id'],))


def gruz_split(con, d):
    """Отделить часть груза в новую заявку. Деньги делятся пропорционально весу (нет веса — объёму, потом местам)."""
    g = one(con, 'SELECT * FROM gruz WHERE id=?', d['id'])
    if g['status'] not in ('на складе', 'прибыл', 'ждёт забора'):
        raise Oshibka('Делить можно груз, который не едет в фуре')
    part = {k: d.get(k) for k in ('kg', 'm3', 'places')}
    ratio = None
    for k in ('kg', 'm3', 'places'):
        if g[k] and part[k]:
            ratio = part[k] / g[k]
            break
    if ratio is None or not 0 < ratio < 1:
        raise Oshibka('Укажите, сколько отделить: меньше, чем есть у груза (кг, м³ или места)')
    for k in ('kg', 'm3', 'places'):           # не указали — делим в той же пропорции
        if g[k] and not part[k]:
            part[k] = round(g[k] * ratio, 3) if k != 'places' else round(g[k] * ratio)
        if g[k] and part[k] >= g[k]:
            raise Oshibka('Отделяемая часть должна быть меньше всего груза')
    rest = {k: (g[k] - part[k]) if g[k] else None for k in part}
    money = lambda v, r: round(v * r, 2) if v else v

    kids = con.execute('SELECT COUNT(*) FROM gruz WHERE parent_id=?', (g['id'],)).fetchone()[0]
    copy = ['created', 'client', 'company', 'pay_form', 'cargo', 'from_addr', 'to_addr',
            'sklad_from', 'sklad_to', 'status', 'sklad_id', 'manager', 'other_form', 'paid_date']
    split = ['rate_client', 'other_cost', 'paid_sum']  # деньги делятся в той же пропорции
    nid = con.execute(
        'INSERT INTO gruz(nomer, ' + ', '.join(copy + split) + ', kg, m3, places, note, parent_id) '
        'VALUES (?' + ',?' * len(copy + split) + ',?,?,?,?,?)',
        [f'{g["nomer"]}-{kids + 2}', *[g[k] for k in copy], *[money(g[k], ratio) for k in split],
         part['kg'], part['m3'], part['places'],
         f'Часть от {g["nomer"]}. {g["note"] or ""}'.strip(), g['id']]).lastrowid
    con.execute('UPDATE gruz SET kg=?, m3=?, places=?, ' + ', '.join(f'{k}=?' for k in split) + ' WHERE id=?',
                (rest['kg'], rest['m3'], rest['places'], *[money(g[k], 1 - ratio) for k in split], g['id']))
    for leg in rows(con, 'SELECT * FROM leg WHERE gruz_id=?', g['id']):
        con.execute('INSERT INTO leg(gruz_id, kind, ' + ', '.join(LEG_FIELDS) + ') VALUES (?,?' + ',?' * len(LEG_FIELDS) + ')',
                    [nid, leg['kind'], *[money(leg[k], ratio) if k == 'rate' else leg[k] for k in LEG_FIELDS]])
        con.execute('UPDATE leg SET rate=? WHERE id=?', (money(leg['rate'], 1 - ratio), leg['id']))
    # история и прошлые рейсы — общие у обеих частей
    con.execute('INSERT INTO log(gruz_id, dt, action, sklad_id, fura_id) '
                'SELECT ?, dt, action, sklad_id, fura_id FROM log WHERE gruz_id=? ORDER BY id', (nid, g['id']))
    con.execute('INSERT INTO reys(gruz_id, fura_id, point) SELECT ?, fura_id, point FROM reys WHERE gruz_id=?',
                (nid, g['id']))
    add_log(con, nid, d.get('dt'), f'отделён от {g["nomer"]}', g['sklad_id'])
    add_log(con, g['id'], d.get('dt'), f'отделена часть {g["nomer"]}-{kids + 2}', g['sklad_id'])
    return {'id': nid}


def sklad_save(con, d):
    name = (d.get('name') or '').strip()
    if not name:
        raise Oshibka('Название склада пустое')
    if d.get('id'):
        con.execute('UPDATE sklad SET name=?, address=? WHERE id=?', (name, d.get('address', ''), d['id']))
    else:
        con.execute('INSERT INTO sklad(name, address) VALUES (?,?)', (name, d.get('address', '')))


def sklad_delete(con, d):
    sid = d['id']
    used = con.execute('SELECT COUNT(*) FROM gruz WHERE sklad_id=? OR sklad_from=? OR sklad_to=?',
                       (sid, sid, sid)).fetchone()[0]
    used += con.execute('SELECT COUNT(*) FROM fura WHERE sklad_from=?', (sid,)).fetchone()[0]
    if used:
        raise Oshibka('Склад уже используется в грузах или фурах — удалить нельзя')
    con.execute('DELETE FROM sklad WHERE id=?', (sid,))


def raspoznat(con, d):
    """Файлы (base64 из браузера) → сохранить во «входящие» и распознать: водителя (kind=voditel), компанию (kind=firma)
    или заявку клиента — компания + данные груза (kind=zayavka)."""
    import base64
    import time
    import raspoznat as R
    import firma as F
    import zayavka as Z
    inbox = FILES / 'inbox'
    inbox.mkdir(parents=True, exist_ok=True)
    files, saved = [], []
    for i, f in enumerate(d.get('files', [])):
        data = base64.b64decode(f['data'].split(',', 1)[-1])
        name = re.sub(r'[\\/:*?"<>|]+', '_', f.get('name') or f'вставка-{i + 1}.png')[-80:]
        path = inbox / f'{int(time.time() * 1000)}_{i}_{name}'
        path.write_bytes(data)
        files.append((name, data))
        saved.append(path.relative_to(FILES).as_posix())
    res = {'firma': F, 'zayavka': Z}.get(d.get('kind'), R).from_files(files)
    for doc, p in zip(res['docs'], saved):
        doc['file'] = p
    return res


def _save_card(con, table, fields, d, need, need_msg):
    """Общее сохранение карточки (водитель / контрагент): поля + файлы из «входящих» в папку карточки."""
    vals = {k: (d.get(k) or '').strip() if isinstance(d.get(k), str) else (d.get(k) or '') for k in fields}
    if not any(vals[k] for k in need):
        raise Oshibka(need_msg)
    if d.get('id'):
        vid = d['id']
        con.execute(f'UPDATE {table} SET ' + ', '.join(f'{k}=?' for k in vals) + ' WHERE id=?', [*vals.values(), vid])
        old = json.loads(one(con, f'SELECT files FROM {table} WHERE id=?', vid)['files'] or '[]')
    else:
        vid = con.execute(f'INSERT INTO {table}(created, ' + ', '.join(vals) + ') VALUES (?' + ',?' * len(vals) + ')',
                          [today(), *vals.values()]).lastrowid
        old = []
    folder = 'voditel' if table == 'voditel' else 'firma'
    keep = []
    for p in d.get('files') or []:
        src = (FILES / p).resolve()
        if FILES.resolve() not in src.parents or not src.exists():
            continue
        if p.startswith('inbox/'):
            dst = FILES / folder / str(vid) / src.name.split('_', 2)[-1]
            dst.parent.mkdir(parents=True, exist_ok=True)
            n = 2
            while dst.exists():
                dst = dst.with_name(f'{dst.stem} ({n}){dst.suffix}')
                n += 1
            src.replace(dst)
            p = dst.relative_to(FILES).as_posix()
        keep.append(p)
    con.execute(f'UPDATE {table} SET files=? WHERE id=?', (json.dumps(list(dict.fromkeys(old + keep)), ensure_ascii=False), vid))
    return {'id': vid}


def voditel_save(con, d):
    return _save_card(con, 'voditel', VODITEL_FIELDS, d, ('fio', 'auto_plate'), 'Нужно хотя бы ФИО или госномер')


def kontragent_save(con, d):
    return _save_card(con, 'kontragent', KONTRAGENT_FIELDS, d, ('name', 'inn'), 'Нужно хотя бы название или ИНН')


def kontragent_delete(con, d):
    con.execute('UPDATE gruz SET client_id=NULL WHERE client_id=?', (d['id'],))
    con.execute('UPDATE leg SET carrier_id=NULL WHERE carrier_id=?', (d['id'],))
    con.execute('DELETE FROM kontragent WHERE id=?', (d['id'],))  # файлы в папке остаются


def voditel_delete(con, d):
    con.execute('UPDATE leg SET voditel_id=NULL WHERE voditel_id=?', (d['id'],))
    con.execute('UPDATE fura SET voditel_id=NULL WHERE voditel_id=?', (d['id'],))
    con.execute('DELETE FROM voditel WHERE id=?', (d['id'],))  # файлы в папке остаются — удаляет человек сам


def manager_save(con, d):
    name = (d.get('name') or '').strip()
    if not name:
        raise Oshibka('Имя менеджера пустое')
    if d.get('id'):
        old = one(con, 'SELECT name FROM manager WHERE id=?', d['id'])['name']
        con.execute('UPDATE manager SET name=? WHERE id=?', (name, d['id']))
        con.execute('UPDATE gruz SET manager=? WHERE manager=?', (name, old))  # переименование — и в заявках
    else:
        con.execute('INSERT INTO manager(name) VALUES (?)', (name,))


def manager_delete(con, d):
    con.execute('DELETE FROM manager WHERE id=?', (d['id'],))  # в старых заявках имя остаётся


def fura_save(con, d):
    vals = {k: d.get(k) for k in FURA_FIELDS}
    vals['route'] = json.dumps(vals['route'] or [])
    if d.get('id'):
        con.execute('UPDATE fura SET ' + ', '.join(f'{k}=?' for k in vals) + ' WHERE id=?', [*vals.values(), d['id']])
        return {'id': d['id']}
    cur = con.execute('INSERT INTO fura(' + ', '.join(vals) + ') VALUES (' + ','.join('?' * len(vals)) + ')',
                      list(vals.values()))
    return {'id': cur.lastrowid}


def fura_delete(con, d):
    if con.execute('SELECT 1 FROM reys WHERE fura_id=?', (d['id'],)).fetchone():
        raise Oshibka('В фуре есть грузы — сначала уберите их')
    con.execute('DELETE FROM fura WHERE id=?', (d['id'],))


def fura_add(con, d):
    f = one(con, 'SELECT * FROM fura WHERE id=?', d['fura_id'])
    if f['status'] != 'собирается':
        raise Oshibka('Фура уже уехала — грузить нельзя')
    route = json.loads(f['route'] or '[]')
    for gid in d.get('gruz_ids', []):
        g = one(con, 'SELECT * FROM gruz WHERE id=?', gid)
        if g['status'] not in ('на складе', 'прибыл') or g['sklad_id'] != f['sklad_from']:
            raise Oshibka(f'{g["nomer"]} не лежит на складе погрузки этой фуры')
        if con.execute('SELECT 1 FROM reys WHERE gruz_id=? AND fura_id=?', (gid, f['id'])).fetchone():
            raise Oshibka(f'{g["nomer"]} уже ехал этой фурой')
        # выгрузка по умолчанию: склад назначения, если фура туда идёт; иначе выбрать вручную
        point = g['sklad_to'] if g['sklad_to'] in route else None
        con.execute('INSERT INTO reys(gruz_id, fura_id, point) VALUES (?,?,?)', (gid, f['id'], point))
        con.execute("UPDATE gruz SET status='в фуре', fura_id=?, sklad_id=NULL WHERE id=?", (f['id'], gid))
        add_log(con, gid, d.get('dt'), 'погружен в фуру', f['sklad_from'], f['id'])


def fura_remove(con, d):
    f = one(con, 'SELECT * FROM fura WHERE id=?', d['fura_id'])
    if f['status'] != 'собирается':
        raise Oshibka('Фура уже уехала — убрать груз нельзя')
    gid = d['gruz_id']
    con.execute("UPDATE gruz SET status='на складе', fura_id=NULL, sklad_id=? WHERE id=? AND fura_id=?",
                (f['sklad_from'], gid, f['id']))
    con.execute('DELETE FROM reys WHERE gruz_id=? AND fura_id=?', (gid, f['id']))
    con.execute("DELETE FROM log WHERE gruz_id=? AND fura_id=? AND action='погружен в фуру'", (gid, f['id']))


def reys_point(con, d):
    """Где выгрузить груз из фуры: склад назначения или промежуточный склад (перегруз)."""
    r = one(con, 'SELECT * FROM reys WHERE gruz_id=? AND fura_id=?', d['gruz_id'], d['fura_id'])
    g = one(con, 'SELECT * FROM gruz WHERE id=?', d['gruz_id'])
    if g['status'] != 'в фуре' or g['fura_id'] != d['fura_id']:
        raise Oshibka('Груз уже выгружен из этой фуры')
    con.execute('UPDATE reys SET point=? WHERE id=?', (d.get('point'), r['id']))


def fura_send(con, d):
    f = one(con, 'SELECT * FROM fura WHERE id=?', d['id'])
    if f['status'] != 'собирается':
        raise Oshibka('Фура уже отправлена')
    ids = [r[0] for r in con.execute("SELECT id FROM gruz WHERE fura_id=? AND status='в фуре'", (f['id'],))]
    if not ids:
        raise Oshibka('В фуре нет грузов')
    dt = d.get('dt') or today()
    con.execute("UPDATE fura SET status='в пути', dt_out=? WHERE id=?", (dt, f['id']))
    for gid in ids:
        add_log(con, gid, dt, 'фура выехала', f['sklad_from'], f['id'])


def fura_unload(con, d):
    f = one(con, 'SELECT * FROM fura WHERE id=?', d['fura_id'])
    if f['status'] != 'в пути':
        raise Oshibka('Выгружать можно только фуру «в пути»')
    sk = d['sklad_id']
    ids = rows(con, "SELECT g.id, g.sklad_to FROM gruz g JOIN reys r ON r.gruz_id=g.id AND r.fura_id=g.fura_id "
                    "WHERE g.fura_id=? AND g.status='в фуре' AND r.point=?", f['id'], sk)
    for g in ids:
        # на складе назначения — «прибыл»; на промежуточном — снова «на складе», ждёт следующую фуру
        final = g['sklad_to'] in (None, sk)
        con.execute('UPDATE gruz SET status=?, sklad_id=?, fura_id=NULL WHERE id=?',
                    ('прибыл' if final else 'на складе', sk, g['id']))
        add_log(con, g['id'], d.get('dt'), 'выгружен из фуры на склад' if final else 'выгружен на перегруз', sk, f['id'])
    left = con.execute("SELECT COUNT(*) FROM gruz WHERE fura_id=? AND status='в фуре'", (f['id'],)).fetchone()[0]
    route = json.loads(f['route'] or '[]')
    if not left or (route and route[-1] == sk):
        con.execute("UPDATE fura SET status='прибыла' WHERE id=?", (f['id'],))
    return {'unloaded': len(ids), 'left': left}


# ---------- банковская выписка: платежи → оплаты грузов ----------

def paid_recalc(con, gid):
    """«Клиент оплатил» = введённое руками до выписки + привязанные платежи; «Дата полной оплаты» — дата платежа,
    которым набралась ставка клиента. Без привязанных платежей поле не трогаем (наличные — руками)."""
    links = rows(con, 'SELECT o.sum, p.dt FROM oplata o JOIN platezh p ON p.id=o.platezh_id WHERE o.gruz_id=? ORDER BY p.dt, o.id', gid)
    if not links:
        return
    g = one(con, 'SELECT rate_client, paid_manual FROM gruz WHERE id=?', gid)
    total, full = g['paid_manual'] or 0, ''
    for l in links:
        total += l['sum']
        if not full and g['rate_client'] and total >= g['rate_client'] - 0.5:
            full = l['dt']
    con.execute('UPDATE gruz SET paid_sum=?, paid_date=? WHERE id=?', (round(total, 2), full, gid))


def _rest(con, pid):
    p = one(con, 'SELECT sum FROM platezh WHERE id=?', pid)
    used = con.execute('SELECT COALESCE(SUM(sum), 0) FROM oplata WHERE platezh_id=?', (pid,)).fetchone()[0]
    return round(p['sum'] - used, 2)


def vypiska_load(con, d):
    """Файлы выписок (base64 из браузера) → новые поступления в platezh. Уже загруженные пропускаются по отпечатку."""
    import base64
    import vypiska as V
    res = []
    for f in d.get('files', []):
        try:
            acc, pays, own = V.parse(base64.b64decode(f['data'].split(',', 1)[-1]))
        except (V.NeVypiska, ValueError) as e:
            res.append({'file': f.get('name'), 'error': str(e)})
            continue
        new = 0
        for p in pays:
            cur = con.execute('INSERT OR IGNORE INTO platezh(key, acc, company, num, dt, sum, payer, inn, purp, loaded, ignored) '
                              'VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                              (p['key'], p['acc'], p['company'], p['num'], p['dt'], p['sum'], p['payer'], p['inn'], p['purp'],
                               today(), 1 if V.not_client(p) else 0))  # проценты банка, возвраты — сразу в скрытые
            new += cur.rowcount
        res.append({'file': f.get('name'), 'acc': acc[-4:], 'company': V.company_of(acc), 'total': len(pays),
                    'new': new, 'old': len(pays) - new, 'own': own})
    return {'files': res}


def oplaty_list(con, d):
    """Платежи, у которых есть непривязанный остаток, с предложениями, к какому грузу их отнести."""
    from datetime import timedelta
    import vypiska as V
    gruzy = rows(con, 'SELECT id, nomer, client, client_id, company, created, rate_client, paid_sum, schet FROM gruz')
    for g in gruzy:
        g['debt'] = round((g['rate_client'] or 0) - (g['paid_sum'] or 0), 2)
    inns = {r['id']: (r['inn'] or '').strip() for r in rows(con, 'SELECT id, inn FROM kontragent')}
    since = min((g['created'] for g in gruzy if g['created']), default=today())
    since = (date.fromisoformat(since) - timedelta(days=V.EARLY_DAYS)).isoformat()
    pays = rows(con, 'SELECT p.*, ROUND(p.sum - COALESCE((SELECT SUM(o.sum) FROM oplata o WHERE o.platezh_id=p.id), 0), 2) AS rest '
                     'FROM platezh p ORDER BY p.dt, p.id')
    pays = [p for p in pays if p['rest'] > 0.5]
    hidden = [p for p in pays if p['ignored']]
    active = [p for p in pays if not p['ignored']]
    old = [p for p in active if p['dt'] < since]
    if not d.get('all'):
        active = [p for p in active if p['dt'] >= since]
    props = V.propose(active, [g for g in gruzy if g['rate_client']], lambda g: inns.get(g['client_id'], ''))
    return {'items': [{**r['p'], 'kind': r['kind'], 'links': r['links'], 'cands': r['cands'], 'why': r['why']} for r in props],
            'hidden': hidden, 'old': 0 if d.get('all') else len(old), 'since': since,
            'total': con.execute('SELECT COUNT(*) FROM platezh').fetchone()[0]}


def oplata_link(con, d):
    """Привязать платежи к грузам: links=[{platezh_id, gruz_id, sum}]; manual={gruz_id: 'add'|'replace'} —
    что делать с «Клиент оплатил», введённым руками до первой привязки."""
    manual = {int(k): v for k, v in (d.get('manual') or {}).items()}
    done = set()
    for l in d.get('links', []):
        pid, gid, s = int(l['platezh_id']), int(l['gruz_id']), round(float(l['sum'] or 0), 2)
        if s <= 0:
            raise Oshibka('Сумма привязки должна быть больше нуля')
        rest = _rest(con, pid)
        if s > rest + 0.5:
            rub = lambda v: f'{v:,.0f}'.replace(',', ' ')
            raise Oshibka(f'Платёж уже разнесён: свободно {rub(rest)} ₽, а привязываем {rub(s)} ₽')
        g = one(con, 'SELECT id, paid_sum FROM gruz WHERE id=?', gid)
        if not con.execute('SELECT 1 FROM oplata WHERE gruz_id=?', (gid,)).fetchone():
            con.execute('UPDATE gruz SET paid_manual=? WHERE id=?',
                        ((g['paid_sum'] or None) if manual.get(gid) == 'add' else None, gid))
        con.execute('INSERT INTO oplata(platezh_id, gruz_id, sum) VALUES (?,?,?) '
                    'ON CONFLICT(platezh_id, gruz_id) DO UPDATE SET sum=sum+excluded.sum', (pid, gid, s))
        done.add(gid)
    for gid in done:
        paid_recalc(con, gid)
    return {'gruzy': len(done)}


def oplata_unlink(con, d):
    o = one(con, 'SELECT * FROM oplata WHERE id=?', d['id'])
    con.execute('DELETE FROM oplata WHERE id=?', (o['id'],))
    if con.execute('SELECT 1 FROM oplata WHERE gruz_id=?', (o['gruz_id'],)).fetchone():
        paid_recalc(con, o['gruz_id'])
    else:  # последний платёж отвязан — остаётся то, что было введено руками
        g = one(con, 'SELECT paid_manual FROM gruz WHERE id=?', o['gruz_id'])
        con.execute("UPDATE gruz SET paid_sum=?, paid_date='', paid_manual=NULL WHERE id=?", (g['paid_manual'], o['gruz_id']))


def platezh_ignore(con, d):
    con.execute('UPDATE platezh SET ignored=? WHERE id=?', (1 if d.get('ignored', True) else 0, d['id']))


def print_doc(con, d):
    """Заявка ВЛ в Word: собрать .docx в «Заявки из приложения» и открыть."""
    import os
    import pechat
    try:
        path = pechat.build(con, d['kind'], d['id'])
    except pechat.NetShablona as e:
        raise Oshibka(str(e))
    if d.get('open', True):
        os.startfile(path)
    return {'file': path.name}


def export_excel(con, d):
    """Заявки в Excel: строки уже посчитаны страницей (тот же расчёт, что во вкладке «Зарплата»)."""
    import excel
    path = excel.build(d.get('rows') or [], d.get('manager') or '', d.get('date_from') or '', d.get('date_to') or '')
    if d.get('open', True):
        os.startfile(path)
    return {'file': path.name, 'rows': len(d.get('rows') or [])}


ACTIONS = {f.__name__: f for f in (vypiska_load, oplaty_list, oplata_link, oplata_unlink, platezh_ignore, print_doc, export_excel, gruz_save, gruz_delete, gruz_accept, gruz_deliver, gruz_split, sklad_save,
                                   sklad_delete, manager_save, manager_delete, raspoznat, voditel_save,
                                   voditel_delete, kontragent_save, kontragent_delete, fura_save, fura_delete, fura_add, fura_remove, reys_point,
                                   fura_send, fura_unload)}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, code, body, ctype='application/json; charset=utf-8', headers=()):
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Cache-Control', 'no-store')
        for k, v in headers:
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def token(self):
        from http.cookies import SimpleCookie
        c = SimpleCookie(self.headers.get('Cookie') or '')
        return c['sklad_s'].value if 'sklad_s' in c else ''

    def authorized(self):
        import vhod
        con = connect()
        try:
            return vhod.check(con, self.token())
        finally:
            con.close()

    def do_GET(self):
        if self.path.split('?')[0] == '/login':
            return self.send(200, (STATIC / 'login.html').read_bytes(), 'text/html; charset=utf-8')
        if not self.authorized():  # без входа — только страница входа
            if self.path.startswith(('/api/', '/files/')):
                return self.send(401, {'error': 'нужно войти', 'login': True})
            return self.send(302, b'', 'text/plain', [('Location', '/login')])
        if self.path == '/api/state':
            con = connect()
            try:
                return self.send(200, state(con))
            finally:
                con.close()
        if self.path.startswith('/files/'):  # документы водителей — для просмотра рядом с полями
            from urllib.parse import unquote
            p = (FILES / unquote(self.path[len('/files/'):].split('?')[0])).resolve()
            if FILES.resolve() not in p.parents or not p.is_file():
                return self.send(404, {'error': 'нет файла'})
            ctype = {'.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.jfif': 'image/jpeg', '.png': 'image/png',
                     '.webp': 'image/webp', '.bmp': 'image/bmp', '.pdf': 'application/pdf'}.get(p.suffix.lower(), 'application/octet-stream')
            return self.send(200, p.read_bytes(), ctype)
        name = 'index.html' if self.path in ('/', '') else self.path.lstrip('/').split('?')[0]
        p = (STATIC / name).resolve()
        if STATIC not in p.parents or not p.is_file():
            return self.send(404, {'error': 'нет такой страницы'})
        ctype = {'.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css'}.get(p.suffix, 'text/plain')
        self.send(200, p.read_bytes(), ctype + '; charset=utf-8')

    def do_POST(self):
        import vhod
        name = self.path.removeprefix('/api/')
        d = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))) or b'{}')
        if name in ('login', 'logout', 'password'):
            con = connect()
            try:
                if name == 'login':
                    tok = vhod.login(con, d.get('login'), d.get('password'))
                    con.commit()
                    if not tok:
                        return self.send(403, {'error': 'Неверный логин или пароль'})
                    cookie = f'sklad_s={tok}; Path=/; HttpOnly; SameSite=Lax; Max-Age={vhod.SESSION_DAYS * 86400}'
                    return self.send(200, {'ok': True}, headers=[('Set-Cookie', cookie)])
                if not vhod.check(con, self.token()):
                    return self.send(401, {'error': 'нужно войти', 'login': True})
                if name == 'logout':
                    vhod.logout(con, self.token())
                    con.commit()
                    return self.send(200, {'ok': True}, headers=[('Set-Cookie', 'sklad_s=; Path=/; Max-Age=0')])
                err = vhod.change(con, d.get('old'), d.get('new'), PORT)
                con.commit()
                return self.send(400, {'error': err}) if err else self.send(200, {'ok': True, 'relogin': True})
            finally:
                con.close()
        if not self.authorized():
            return self.send(401, {'error': 'нужно войти', 'login': True})
        act = ACTIONS.get(name)
        if not act:
            return self.send(404, {'error': 'нет такого действия'})
        con = connect()
        try:
            res = act(con, d) or {}
            con.commit()
            self.send(200, {'ok': True, **res})
        except Oshibka as e:
            con.rollback()
            self.send(400, {'error': str(e)})
        except Exception as e:  # покажем, а не упадём
            con.rollback()
            self.send(500, {'error': f'Ошибка программы: {e}'})
        finally:
            con.close()


def main():
    init_db()
    import vhod
    con = connect()
    if vhod.init(con, PORT, reset='--reset-password' in sys.argv):
        print(f'Пароль для входа записан в блокнот: {vhod.CRED_FILE}')
    con.commit()
    con.close()
    if '--reset-password' in sys.argv:
        return
    url = f'http://127.0.0.1:{PORT}'
    # на Windows «reuse address» позволяет второй копии сесть на тот же порт — запрещаем
    ThreadingHTTPServer.allow_reuse_address = False
    ThreadingHTTPServer.allow_reuse_port = False
    try:
        srv = ThreadingHTTPServer(('127.0.0.1', PORT), Handler)
    except OSError:  # уже запущен (например, второй щелчок по ярлыку) — просто открываем страницу
        print(f'Склад уже запущен, открываю {url}')
        webbrowser.open(url)
        return
    print(f'Склад запущен: {url}  (закрыть — Ctrl+C или закрыть это окно)')

    def daily_backup():  # копия за сегодня, если её ещё нет (ночью компьютер мог быть выключен)
        try:
            import backup
            print(backup.make_backup())
        except Exception as e:
            print(f'Резервная копия не сделана: {e}')
    threading.Thread(target=daily_backup, daemon=True).start()
    if '--no-browser' not in sys.argv:
        threading.Timer(0.8, webbrowser.open, (url,)).start()
    srv.serve_forever()


if __name__ == '__main__':
    main()
