# Загрузка сложных перевозок из «Умной логистики» в приложение. Собрано 2026-11-02.
# Вход — «Отчёт по Сложным перевозкам», сохранённый из УЛ как .mxl.
# Заявка клиента → груз + отрезок «забор»; наша заявка (ВЛ / ИП Шерстов) с 3+ точками → фура;
# остальные наши заявки → «развоз» груза с тем же названием груза в той же сложной (не нашёлся — в примечание).
# Повторный запуск не задваивает: метка «[УЛ №сложной/№заявки]» в примечании.
# Запуск: python app-sklad/import_ul.py "<отчёт.mxl>" [--udalit-primer]
#   --udalit-primer — сначала убрать пример С534НХ03 (Г-0001…Г-0010 из seed_c534.py)
import difflib
import json
import re
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / 'tools' / 'slozhnye_ul'))
import server  # noqa: E402
import mxl  # noqa: E402

NASHI = ('ВОСТОЧНАЯ ЛОГИСТИКА', 'ШЕРСТОВ')
ORG = {'ООО "Восточная Логистика"': 'ООО ВЛ', 'Шерстов Андрей Витальевич': 'ИП Шерстов'}
SKLAD_MO = ('Щербинка', 'Щёлково')  # склады, где грузится фура
PRIMER = [f'Г-{i:04d}' for i in range(1, 11)]


def lines(v):
    return [x.strip() for x in (v or '').replace('\r', '').split('\n') if x.strip()]


def num(v):
    v = (v or '').replace('\xa0', '').replace(' ', '').replace(',', '.')
    try:
        return float(v)
    except ValueError:
        return None


def iso(d):
    try:
        return datetime.strptime(d, '%d.%m.%Y').date().isoformat()
    except (ValueError, TypeError):
        return ''


def gorod(s):
    return (s or '').replace('Щелково', 'Щёлково')


def read_report(path):
    cells = mxl.read(path)
    slozh, cur = [], None
    for r in sorted({r for r, _ in cells}):
        g = lambda k: cells.get((r, k), '')
        a = lines(g(0))
        if not a:
            continue
        if re.match(r'№\s*\d', a[0]):
            cur = {'n': int(re.sub(r'\D', '', a[0])), 'z': []}
            slozh.append(cur)
        elif a[0].startswith('Заявка') and cur:
            mesta = [gorod(x) for x in lines(g(2))]
            daty = lines(g(3))
            ves = [num(x) for x in lines(g(4))]
            obem = [num(x) for x in lines(g(5))]
            cur['z'].append({
                'nomer': a[0].replace('Заявка', '').strip(), 'mesta': mesta, 'daty': daty,
                't': next((x for x in ves if x), None), 'm3': next((x for x in obem if x), None),
                'gruz': g(6), 'zakazchik': g(7), 'perevozchik': g(8), 'ts': g(9),
                'st_k': num(g(10)), 'st_p': num(g(11)), 'org': g(13), 'menedzher': g(14)})
    return slozh


def podobrat(gruzy, name, client=''):
    # груз той же сложной с похожим названием (в УЛ бывают опечатки: «Кондитерсие»); сначала — ещё без развоза,
    # а если заявка от клиента — его же груз
    if not name:
        return None
    best, score = None, 0.0
    for g in gruzy:
        r = difflib.SequenceMatcher(None, g[1], name).ratio() - (0.05 if g[2] else 0) + (0.5 if client and g[3] == client else 0)
        if r > score:
            best, score = g, r
    return best if score >= 0.6 else None


def udalit_primer(con):
    ids = [r[0] for r in con.execute(
        f'SELECT id FROM gruz WHERE nomer IN ({",".join("?" * len(PRIMER))})', PRIMER)]
    for t in ('leg', 'log', 'reys', 'oplata'):
        con.execute(f'DELETE FROM {t} WHERE gruz_id IN ({",".join("?" * len(ids))})', ids)
    con.execute(f'DELETE FROM gruz WHERE id IN ({",".join("?" * len(ids))})', ids)
    f = con.execute("SELECT id FROM fura WHERE nomer_ts='С534НХ03' AND zayavka='0000000002'").fetchone()
    if f and not con.execute('SELECT 1 FROM reys WHERE fura_id=?', (f[0],)).fetchone():
        con.execute('DELETE FROM fura WHERE id=?', (f[0],))
    print(f'Пример убран: грузов {len(ids)}, фура С534НХ03 {"да" if f else "не найдена"}.')


def main():
    src = sys.argv[1]
    server.init_db()
    con = server.connect()
    if '--udalit-primer' in sys.argv:
        udalit_primer(con)
    sklady = {r['name']: r['id'] for r in con.execute('SELECT id, name FROM sklad')}
    est = {m for (n,) in con.execute('SELECT note FROM gruz UNION ALL SELECT note FROM fura')
           for m in re.findall(r'\[УЛ [^\]]+\]', n or '')}
    stat = {'zabor': 0, 'gruz': 0, 'fura': 0, 'razvoz': 0, 'ne_priv': 0, 'propusk': 0}

    for s in read_report(src):
        metka = lambda z: f"[УЛ {s['n']}/{z['nomer']}]"
        nashi = [z for z in s['z'] if any(k in z['zakazchik'].upper() for k in NASHI)]
        # заявка клиента без ставки клиенту, со склада города — это развоз его груза, а не новый груз
        razv_k = [z for z in s['z'] if z not in nashi and not z['st_k'] and z['mesta']
                  and z['mesta'][0] in sklady and z['mesta'][0] not in SKLAD_MO]
        klienty = [z for z in s['z'] if z not in nashi and z not in razv_k]
        # фура: 3+ точки или прямой рейс со склада МО на дальний склад
        fury = [z for z in nashi if len(z['mesta']) >= 3 or
                (len(z['mesta']) == 2 and z['mesta'][0] in SKLAD_MO and z['mesta'][1] in sklady
                 and z['mesta'][1] not in SKLAD_MO)]
        prochie = razv_k + [z for z in nashi if z not in fury]

        fura_ids = []
        for z in fury:
            if metka(z) in est:
                stat['propusk'] += 1
                continue
            route = [sklady[m] for m in z['mesta'][1:] if m in sklady]
            route = list(dict.fromkeys(route))
            fid = con.execute(
                'INSERT INTO fura(nomer_ts, carrier, zayavka, dt_out, sklad_from, route, rate, status, note) '
                'VALUES (?,?,?,?,?,?,?,?,?)',
                (z['ts'], z['perevozchik'], z['nomer'], iso(z['daty'][0] if z['daty'] else ''),
                 sklady.get(z['mesta'][0]), json.dumps(route), z['st_p'], 'прибыла',
                 f"{metka(z)} Сложная №{s['n']}. Маршрут в УЛ: {' → '.join(z['mesta'])}.")).lastrowid
            fura_ids.append(fid)
            stat['fura'] += 1
        fid = fura_ids[0] if fura_ids else None

        gruzy = []  # (id, название груза, есть ли развоз)
        for z in klienty:
            if metka(z) in est:
                stat['propusk'] += 1
                continue
            m = z['mesta']
            na_sklad = sklady.get(m[-1]) if m else None
            note = f"{metka(z)} Сложная №{s['n']}, заявка УЛ {z['nomer']}."
            if z['menedzher']:
                note += f" Менеджер в УЛ: {z['menedzher']}."
            cur = con.execute(
                'INSERT INTO gruz(created, client, company, cargo, kg, m3, from_addr, to_addr, rate_client, '
                'sklad_from, status, note) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                (iso(z['daty'][0] if z['daty'] else ''), z['zakazchik'], ORG.get(z['org'], z['org']), z['gruz'],
                 z['t'] * 1000 if z['t'] else None, z['m3'], m[0] if m else '', m[-1] if m else '',
                 z['st_k'], na_sklad, 'доставлен', note))
            gid = cur.lastrowid
            con.execute('UPDATE gruz SET nomer=? WHERE id=?', (f'Г-{gid:04d}', gid))
            con.execute('INSERT INTO leg(gruz_id, kind, zayavka, dt, from_addr, to_addr, carrier, rate) '
                        'VALUES (?,?,?,?,?,?,?,?)',
                        (gid, 'zabor', z['nomer'], iso(z['daty'][0] if z['daty'] else ''),
                         m[0] if m else '', m[-1] if m else '', z['perevozchik'], z['st_p']))
            if na_sklad:
                server.add_log(con, gid, iso(z['daty'][-1]), 'принят на склад', na_sklad)
            if fid:
                con.execute('INSERT INTO reys(gruz_id, fura_id, point) VALUES (?,?,?)', (gid, fid, None))
            gruzy.append([gid, z['gruz'].strip().lower(), False, z['zakazchik']])
            stat['gruz'] += 1

        ne_priv = []
        for z in prochie:
            if metka(z) in est:
                stat['propusk'] += 1
                continue
            name = z['gruz'].strip().lower()
            m = z['mesta']
            g = podobrat(gruzy, name, '' if z in nashi else z['zakazchik'])
            if g and m and m[-1] in SKLAD_MO:  # наш забор до склада МО — уточняет забор груза
                leg = con.execute("SELECT id, rate FROM leg WHERE gruz_id=? AND kind='zabor'", (g[0],)).fetchone()
                if leg and (leg['rate'] or 0) <= 1:
                    con.execute('UPDATE leg SET zayavka=?, from_addr=?, carrier=?, rate=? WHERE id=?',
                                (z['nomer'], m[0], z['perevozchik'], z['st_p'], leg['id']))
                    con.execute('UPDATE gruz SET note=note||? WHERE id=?', (f' {metka(z)} — забор.', g[0]))
                    stat['zabor'] += 1
                    continue
                g = None
            if g and g[2]:
                g = None
            if not g:
                ne_priv.append(f"{metka(z)} {' → '.join(m)}, {z['gruz']}, {z['perevozchik']}, "
                               f"{int(z['st_p']) if z['st_p'] else 0} ₽")
                stat['ne_priv'] += 1
                continue
            g[2] = True
            sklad_to = sklady.get(m[0]) if m else None
            con.execute('INSERT INTO leg(gruz_id, kind, zayavka, dt, from_addr, to_addr, carrier, rate) '
                        'VALUES (?,?,?,?,?,?,?,?)',
                        (g[0], 'razvoz', z['nomer'], iso(z['daty'][-1] if z['daty'] else ''),
                         m[0] if m else '', m[-1] if m else '', z['perevozchik'], z['st_p']))
            con.execute('UPDATE gruz SET sklad_to=?, to_addr=?, note=note||? WHERE id=?',
                        (sklad_to, m[-1] if m else '', f' {metka(z)} — развоз.', g[0]))
            con.execute('UPDATE reys SET point=? WHERE gruz_id=?', (sklad_to, g[0]))
            server.add_log(con, g[0], iso(z['daty'][-1] if z['daty'] else ''), 'выдан на развоз / доставлен', sklad_to)
            stat['razvoz'] += 1
        if ne_priv:
            text = ' Не привязано к грузам: ' + '; '.join(ne_priv) + '.'
            if fid:
                con.execute('UPDATE fura SET note=note||? WHERE id=?', (text, fid))
            elif gruzy:
                con.execute('UPDATE gruz SET note=note||? WHERE id=?', (text, gruzy[0][0]))
            else:
                print(f"Сложная №{s['n']}: некуда записать — {text}")
    con.commit()
    print(f"Загружено: грузов {stat['gruz']}, фур {stat['fura']}, развозов {stat['razvoz']}, заборов уточнено {stat['zabor']}, "
          f"не привязано {stat['ne_priv']}, уже были {stat['propusk']}.")


if __name__ == '__main__':
    main()
