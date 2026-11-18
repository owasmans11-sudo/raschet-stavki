import csv, sys
from pathlib import Path
def norm(s):
    return s.casefold().replace("ё", "е").strip()
with (Path(__file__).resolve().parents[1]/"references/mo-distances.csv").open(encoding="utf-8-sig") as f:
    rows = list(csv.DictReader(f, delimiter=";"))
matches = [r for r in rows if norm(r["Откуда"]) == norm(sys.argv[1]) and norm(r["Куда"]) == norm(sys.argv[2])]
if not matches:
    raise SystemExit("Пара отсутствует в справочнике")
for r in matches:
    print(r["Откуда"], "→", r["Куда"], r["Км"], "км;", r["Профиль"], r["Дата"])
