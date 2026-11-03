# Пример для приложения: фура С534НХ03 (сложная перевозка №2 из «Умной логистики», июль 2026).
# Данные берём из tools/cepochka_fury/build.py (там они собраны вручную из УЛ), чтобы не дублировать.
# Запуск (только в пустую базу): python app-sklad/seed_c534.py
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import server  # noqa: E402

SRC = Path(__file__).resolve().parent.parent / 'tools' / 'cepochka_fury' / 'build.py'


def load_data():
    text = SRC.read_text(encoding='utf-8')
    part = text[text.index('NE = '):text.index('thin = ')]  # только блок с данными, без сборки Excel
    ns = {}
    exec(part, ns)
    return ns


def iso(d):
    return datetime.strptime(d, '%d.%m.%Y').date().isoformat() if d else ''


def main():
    server.init_db()
    con = server.connect()
    if con.execute('SELECT 1 FROM gruz').fetchone():
        print('В базе уже есть грузы — пример не загружаю.')
        return
    d = load_data()

    def sklad_id(name, address=''):
        r = con.execute('SELECT id FROM sklad WHERE name=?', (name,)).fetchone()
        if r:
            if address:
                con.execute("UPDATE sklad SET address=? WHERE id=? AND address=''", (address, r[0]))
            return r[0]
        return con.execute('INSERT INTO sklad(name, address) VALUES (?,?)', (name, address)).lastrowid

    # В июле 2026 фура грузилась в Щербинке (так в УЛ) — заводим её отдельным складом
    mo = sklad_id('Щербинка', d['SKLAD_MO'])
    city = {c: sklad_id(c, a) for c, a in d['SKLAD'].items()}
    uu = sklad_id('Улан-Удэ', 'ул. Покровская, 33а, 1 блок, Промышленный парк РБ')
    chita = sklad_id('Чита')

    out = '2026-07-06'
    fid = con.execute(
        'INSERT INTO fura(nomer_ts, carrier, zayavka, dt_out, sklad_from, route, cap_m3, cap_t, rate, status, note) '
        'VALUES (?,?,?,?,?,?,?,?,?,?,?)',
        ('С534НХ03', 'ГРАД-ЛОГИСТИК ООО', '0000000002', out, mo,
         json.dumps([city['Красноярск'], city['Иркутск'], uu, chita]), 82, 20, 510000, 'прибыла',
         'Пример из УЛ (сложная №2). Объём кузова в УЛ не указан — 82 м³ поставлено условно. '
         'Выгрузка в Улан-Удэ и Чите — чей груз, в УЛ не указано.')).lastrowid

    for g in d['G']:
        (kl, gr, w, v, st, org, zz, zd, zfrom, zper, zst, c, sd, dz, dd, dto, dper, dst, note) = g
        to = city.get(c)
        cur = con.execute(
            'INSERT INTO gruz(created, client, company, cargo, kg, m3, from_addr, to_addr, rate_client, '
            'sklad_from, sklad_to, status, fura_id, note) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
            (iso(zd), kl, org, gr, w * 1000 if w else None, v, zfrom, dto if dto != d['NE'] else '', st,
             mo, to, 'доставлен' if to else 'в фуре', None if to else fid, note))
        gid = cur.lastrowid
        con.execute('UPDATE gruz SET nomer=? WHERE id=?', (f'Г-{gid:04d}', gid))
        con.execute('INSERT INTO reys(gruz_id, fura_id, point) VALUES (?,?,?)', (gid, fid, to))
        con.execute('INSERT INTO leg(gruz_id, kind, zayavka, dt, from_addr, to_addr, carrier, rate) VALUES (?,?,?,?,?,?,?,?)',
                    (gid, 'zabor', zz, iso(zd), zfrom, d['SKLAD_MO'], zper, zst))
        server.add_log(con, gid, iso(d['PRIEM'].get(zz, zd)), 'принят на склад', mo)
        server.add_log(con, gid, out, 'погружен в фуру', mo, fid)
        server.add_log(con, gid, out, 'фура выехала', mo, fid)
        if to:
            con.execute('INSERT INTO leg(gruz_id, kind, zayavka, dt, from_addr, to_addr, carrier, rate) VALUES (?,?,?,?,?,?,?,?)',
                        (gid, 'razvoz', dz, iso(dd), d['SKLAD'][c], dto, dper, dst))
            server.add_log(con, gid, iso(sd), 'выгружен из фуры на склад', to, fid)
            server.add_log(con, gid, iso(dd), 'выдан на развоз / доставлен', to)
    con.commit()
    n = con.execute('SELECT COUNT(*) FROM gruz').fetchone()[0]
    print(f'Загружено: фура С534НХ03, грузов {n}.')


if __name__ == '__main__':
    main()
