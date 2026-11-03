"""Шаблоны от ИП Шерстов, которых не было: «до склада ИПШ» и «с клиентом ИПШ» (стиль «вариант 3»).
Условия — слово в слово из шаблонов ВЛ (владелец: «условия оставь прежние», 2026-11-02);
шапка и реквизиты ИП — из «Заявка с перевозчиком со склада ИПШ (новый дизайн).docx».
Запуск из корня проекта: python tools/build_templates_ipsh.py"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'app-sklad'))
from build_templates_v3 import P, carrier_from_legal, client_template  # noqa: E402
from pechat import parse_template  # noqa: E402

if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    ip = parse_template('Заявка с перевозчиком со склада ИПШ (новый дизайн).docx')
    co, own = ip['co'], ip['own']
    footer = f'{co["legal"]} · {co["email"]} · {co["phone"]}'
    postal = next(l.split(':', 1)[1].strip() for l in own if l.startswith('Почт. адрес'))

    do_vl = parse_template('Заявка с перевозчиком до склада ВЛ (новый дизайн).docx')
    n = carrier_from_legal(do_vl['legal'], P('Заявка с перевозчиком до склада ИПШ (новый дизайн).docx'), co, own, footer,
                           *do_vl['titles'])
    print('До склада ИПШ: абзацев условий', len(n))

    n = client_template(P('Заявка с клиентом ВЛ (вариант 3).docx'), P('Заявка с клиентом ИПШ (новый дизайн).docx'),
                        co, co['email'], postal, own, footer)
    print('С клиентом ИПШ: абзацев условий', len(n))
