# Вход в приложение «Склад»: одна учётная запись (владелец: «поставь пока что на меня одного»).
# Пароль хранится только хешем (PBKDF2); открытым текстом — лишь в блокноте на рабочем столе (просьба владельца).
# Забыли пароль / удалили блокнот: python app-sklad/server.py --reset-password — новый пароль запишется в блокнот.
import hashlib
import hmac
import os
import secrets
import time
from pathlib import Path

LOGIN = 'andrey'
CRED_FILE = Path(os.environ.get('SKLAD_CRED_FILE') or Path.home() / 'Desktop' / 'Склад ВЛ — вход.txt')
SESSION_DAYS = 30
ITER = 200_000

SCHEMA = """
CREATE TABLE IF NOT EXISTS auth(login TEXT PRIMARY KEY, pass_hash TEXT, changed TEXT);
CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, login TEXT, created REAL);
"""


def _hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), ITER).hex()
    return f'pbkdf2${ITER}${salt}${h}'


def _verify(password, stored):
    try:
        _, it, salt, h = stored.split('$')
        calc = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), int(it)).hex()
        return hmac.compare_digest(calc, h)
    except Exception:
        return False


def _new_password():
    abc = 'abcdefghjkmnpqrstuvwxyz23456789'  # без похожих символов (l/1, o/0)
    return '-'.join(''.join(secrets.choice(abc) for _ in range(5)) for _ in range(2))


def _write_note(password, port):
    CRED_FILE.write_text(
        'Склад ВЛ — вход в приложение\n\n'
        f'Адрес:  http://127.0.0.1:{port}\n'
        f'Логин:  {LOGIN}\n'
        f'Пароль: {password}\n\n'
        'Сменить пароль: вкладка «Справочники» → «Вход в приложение». После смены этот файл обновится сам.\n'
        'Не пересылайте этот файл и не кладите его в общие папки.\n', encoding='utf-8')


def set_password(con, password, port):
    con.execute('INSERT INTO auth(login, pass_hash, changed) VALUES (?,?,?) '
                'ON CONFLICT(login) DO UPDATE SET pass_hash=excluded.pass_hash, changed=excluded.changed',
                (LOGIN, _hash(password), time.strftime('%Y-%m-%d %H:%M')))
    con.execute('DELETE FROM sessions')  # после смены пароля — войти заново везде
    _write_note(password, port)


def init(con, port, reset=False):
    """Таблицы входа; при первом запуске (или --reset-password) — новый пароль в блокнот на рабочем столе."""
    con.executescript(SCHEMA)
    if reset or not con.execute('SELECT 1 FROM auth').fetchone():
        set_password(con, _new_password(), port)
        return True
    return False


def login(con, user, password):
    row = con.execute('SELECT pass_hash FROM auth WHERE login=?', ((user or '').strip().lower(),)).fetchone()
    if not row or not _verify(password or '', row[0]):
        time.sleep(1)  # медленно на неверном пароле — против подбора
        return None
    token = secrets.token_urlsafe(32)
    con.execute('INSERT INTO sessions(token, login, created) VALUES (?,?,?)', (token, LOGIN, time.time()))
    return token


def check(con, token):
    if not token:
        return False
    row = con.execute('SELECT created FROM sessions WHERE token=?', (token,)).fetchone()
    return bool(row) and time.time() - row[0] < SESSION_DAYS * 86400


def logout(con, token):
    con.execute('DELETE FROM sessions WHERE token=?', (token,))


def change(con, old, new, port):
    row = con.execute('SELECT pass_hash FROM auth WHERE login=?', (LOGIN,)).fetchone()
    if not row or not _verify(old or '', row[0]):
        time.sleep(1)
        return 'Старый пароль неверный'
    if len(new or '') < 8:
        return 'Новый пароль — не короче 8 символов'
    set_password(con, new, port)
    return ''
