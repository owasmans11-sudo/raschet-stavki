"""Решаем, является ли текст заявкой на перевозку, где наша компания перевозчик."""

import re

# Латинские буквы, которые OCR путает с русскими
_HOMO = str.maketrans("aceopxyAKBEHMOPCTXk", "асеорхуаквенморстхк")

TRANSPORT = [  # (регулярное выражение, вес, подпись)
    (r"заявк\w*\s+(?:№\s*\S+\s+)?(?:на\s+)?(?:перевозк|транспортн|грузоперевоз|оказание\s+транспорт|организаци\w+\s+перевоз)", 6, "заявка на перевозку"),
    (r"договор\w*[\s\-–]*заявк", 6, "договор-заявка"),
    (r"заявк", 2, "слово «заявка»"),
    (r"перевозчик", 2, "перевозчик"),
    (r"грузоотправител", 1, "грузоотправитель"),
    (r"грузополучател", 1, "грузополучатель"),
    (r"погрузк|загрузк", 1, "погрузка"),
    (r"выгрузк|разгрузк", 1, "выгрузка"),
    (r"водител", 1, "водитель"),
    (r"гос\.?\s*(?:рег\.?\s*)?номер|госномер|\bг/н\b|\bгрз\b", 1, "госномер"),
    (r"тягач|полуприцеп|прицеп|\bтс\b|транспортн\w+\s+средств|\bа/м\b|автомобил", 1, "транспорт"),
    (r"маршрут", 1, "маршрут"),
    (r"ставк|стоимость\s+(?:перевозки|услуг)|фрахт|сумма\s+оплаты", 1, "ставка"),
    (r"наименование\s+груза|характер\s+груза|вес\s+груза|\bгруз\b|тонн|паллет|\bм3\b|куб", 1, "груз"),
    (r"дата\s+(?:и\s+время\s+)?(?:погрузки|подачи|загрузки)", 1, "дата подачи"),
    (r"экспедитор", 0.5, "экспедитор"),
]

# Сопутствующие документы: тоже про перевозку, но это не заявка
OTHER_DOCS = [
    (r"сч[её]т[\s\-–]*фактур", "счёт-фактура"),
    (r"универсальн\w+\s+передаточн|\bупд\b", "УПД"),
    (r"акт\w*\s+(?:№\s*\S+\s+)?(?:от\s+\S+\s+)?(?:выполненных|оказанных|об\s+оказании|сдачи)", "акт"),
    (r"акт\s+сверки", "акт сверки"),
    (r"транспортн\w+\s+накладн|товарно[\s\-–]*транспортн|\bттн\b", "транспортная накладная"),
    (r"сч[её]т\s+на\s+оплату|сч[её]т\s+№", "счёт"),
    (r"доверенност", "доверенность"),
    (r"претензи", "претензия"),
]

CARRIER_ROLE = r"перевозчик\w*|исполнител\w*"
CLIENT_ROLE = r"заказчик\w*|клиент\w*|экспедитор\w*|грузоотправител\w*"


def normalize(text):
    t = text.lower().replace("ё", "е")
    t = t.translate(_HOMO)
    t = re.sub(r"[ \t ]+", " ", t)
    return t


def company_regex(names):
    """«Восточная логистика» → допускаем разные окончания, кавычки, переносы и ошибки OCR."""
    alts = []
    for name in names:
        words = [w for w in re.split(r"[\s\"«»'ʼ]+", normalize(name)) if w]
        if not words:
            continue
        if re.fullmatch(r"\d{10}|\d{12}", words[0]):        # ИНН
            alts.append(words[0])
            continue
        stems = [re.escape(w[:max(4, len(w) - 2)]) + r"\w{0,4}" for w in words]
        alts.append(r"[\s\"«»'\-]{0,4}".join(stems))
    return re.compile("|".join(alts)) if alts else None


def find_role(t, comp_re):
    """Какая роль у нашей компании в документе: перевозчик, заказчик, просто упомянута, нет."""
    if comp_re is None:
        return "нет"
    hits = list(comp_re.finditer(t))
    if not hits:
        return "нет"
    carrier = client = 0
    for m in hits:
        before = t[max(0, m.start() - 160):m.start()]
        roles = list(re.finditer(rf"{CARRIER_ROLE}|{CLIENT_ROLE}", before))
        if roles:
            last = roles[-1].group(0)
            if re.match(CARRIER_ROLE, last):
                carrier += 1
            else:
                client += 1
    # Подпись внизу заявки: «Перевозчик: ____ /Иванов/ ООО Восточная логистика»
    if carrier > client:
        return "перевозчик"
    if client > carrier:
        return "заказчик"
    return "упомянута"


def classify(text, filename, company_names):
    t = normalize(text)
    fn = normalize(filename)
    score, found = 0.0, []
    for rx, w, label in TRANSPORT:
        if re.search(rx, t):
            score += w
            found.append(label)
    if re.search(r"заявк", fn):
        score += 3
        found.append("«заявка» в имени файла")
    other = [label for rx, label in OTHER_DOCS if re.search(rx, t[:1500])]
    strong = "заявка на перевозку" in found or "договор-заявка" in found
    if other and not strong:
        score -= 3

    role = find_role(t, company_regex(company_names))
    if role == "нет" and company_regex(company_names) is not None:
        if company_regex(company_names).search(fn):
            role = "упомянута"

    if score >= 6 and role == "перевозчик":
        verdict = "Заявка"
    elif score >= 6 and role == "упомянута":
        verdict = "Проверить"
    elif score >= 8 and role == "нет":
        verdict = "Проверить"               # заявка на перевозку, но нас не нашли (часто плохой скан)
    elif score >= 6 and role == "заказчик":
        verdict = "Мы заказчик"
    elif score >= 4 and role == "перевозчик":
        verdict = "Проверить"
    else:
        verdict = "Не заявка"
    return {
        "verdict": verdict, "score": round(score, 1), "role": role,
        "found": ", ".join(found), "other": ", ".join(other),
        "snippet": snippet(text),
    }


def snippet(text):
    m = re.search(r"заявк", text, re.I)
    start = max(0, m.start() - 40) if m else 0
    s = re.sub(r"\s+", " ", text[start:start + 300]).strip()
    return s
