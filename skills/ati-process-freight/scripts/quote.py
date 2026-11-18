"""Calculate a quote using the ATI freight tariff."""
import argparse
import json
import sys
from decimal import Decimal, ROUND_CEILING
from pathlib import Path

RATES = {"krasnoyarsk": 32, "irkutsk": 35, "ulan-ude": 38, "chita": 40}
WAREHOUSES = ("shchyolkovo", *RATES)
DELIVERY_MODES = ("warehouse", "city", "outside")
REQUIRED_FIELDS = {"kg", "m3", "pickup_km", "warehouse", "delivery"}
OPTIONAL_FIELDS = dict.fromkeys(("delivery_km", "width_m", "height_m", "ati_price"))
OPTIONAL_FIELDS["ati_comparable"] = False


def number(value):
    result = Decimal(str(value).replace(",", "."))
    if not result.is_finite() or result < 0:
        raise ValueError("Measurements and prices must be finite and nonnegative")
    return result


def steps(value, included, step):
    return (max(value - included, Decimal(0)) / step).to_integral_value(rounding=ROUND_CEILING)


def grid(km, kg, volume):
    return 6000 + 1000 * steps(km, 50, 80) + 2000 * steps(kg, 1000, 1000) + 2000 * steps(volume, 3, 3)


def calculate(args):
    if args.warehouse not in WAREHOUSES or args.delivery not in DELIVERY_MODES:
        raise ValueError("Unknown warehouse or delivery mode")
    if type(args.ati_comparable) is not bool:
        raise ValueError("ati_comparable must be true or false")
    kg = number(args.kg)
    volume = number(args.m3) * Decimal("1.10")
    billable_kg = max(kg, volume * 200)
    pickup = grid(number(args.pickup_km), kg, volume)

    if args.warehouse == "shchyolkovo" and args.delivery != "warehouse":
        raise ValueError("A Shchyolkovo-only trip ends at the warehouse")
    if (args.delivery == "outside") != (args.delivery_km is not None):
        raise ValueError("Provide delivery distance exactly when delivery is outside the city")

    interwarehouse = billable_kg * RATES.get(args.warehouse, 0)
    delivery = Decimal(0)
    if args.delivery == "city":
        delivery = Decimal(5000 if kg < 3000 else 7000 if kg < 5000 else 10000)
    elif args.delivery == "outside":
        delivery = grid(number(args.delivery_km), kg, volume)

    width = number(args.width_m) if args.width_m is not None else None
    height = number(args.height_m) if args.height_m is not None else None
    oversize = (width is not None and width > Decimal("2.20")) or (
        height is not None and height > Decimal("2.30")
    )
    base = pickup + interwarehouse + delivery
    uplift = base * Decimal("0.20") if base > 60000 else Decimal(0)
    size_fee = Decimal(7000 if oversize else 0)
    total = base + uplift + size_fee
    ati_price = number(args.ati_price) if args.ati_price is not None else None
    if args.ati_comparable and ati_price is None:
        raise ValueError("A comparable ATI price must be supplied")
    use_ati = args.ati_comparable and ati_price >= total
    comment = ati_price * Decimal("1.10") if use_ati else total

    return {
        "calculated_m3": volume, "billable_kg": billable_kg, "pickup_rub": pickup,
        "interwarehouse_rub": interwarehouse, "delivery_rub": delivery,
        "base_rub": base, "uplift_rub": uplift, "size_fee_rub": size_fee,
        "total_rub": total, "comment_rub": comment, "used_ati_price": use_ati,
        "width_missing": width is None, "height_missing": height is None,
    }


def calculate_batch(rows):
    if not isinstance(rows, list):
        raise ValueError("The batch must be a JSON array of freight records")

    results = []
    for index, row in enumerate(rows, start=1):
        entry = {"row": index}
        try:
            if not isinstance(row, dict):
                raise ValueError("The record must be a JSON object")
            identifiers = {key: row[key] for key in ("id", "account") if key in row}
            entry.update(identifiers)
            values = {key: value for key, value in row.items() if key not in identifiers}
            missing = REQUIRED_FIELDS - values.keys()
            unknown = values.keys() - REQUIRED_FIELDS - OPTIONAL_FIELDS.keys()
            if missing:
                raise ValueError("Missing fields: " + ", ".join(sorted(missing)))
            if unknown:
                raise ValueError("Unknown fields: " + ", ".join(sorted(unknown)))
            quote = calculate(argparse.Namespace(**(OPTIONAL_FIELDS | values)))
            rubles = format(quote["comment_rub"], ",f").replace(",", " ")
            if "." in rubles:
                rubles = rubles.rstrip("0").rstrip(".").replace(".", ",")
            entry.update(quote)
            entry["comment"] = f"Андрей ({rubles} ₽)"
        except (ArithmeticError, ValueError) as error:
            entry["error"] = "Invalid numeric value" if isinstance(error, ArithmeticError) else str(error)
        results.append(entry)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", metavar="JSON", help="Read an array of records from a file or '-' for stdin")
    parser.add_argument("--kg")
    parser.add_argument("--m3")
    parser.add_argument("--pickup-km")
    parser.add_argument("--warehouse", choices=WAREHOUSES)
    parser.add_argument("--delivery", choices=DELIVERY_MODES)
    parser.add_argument("--delivery-km")
    parser.add_argument("--width-m", help="Largest known width of a single piece")
    parser.add_argument("--height-m", help="Largest known height of a single piece")
    parser.add_argument("--ati-price")
    parser.add_argument("--ati-comparable", action="store_true")
    args = parser.parse_args()
    try:
        if args.batch is not None:
            if any(getattr(args, key) is not None for key in REQUIRED_FIELDS) or any(
                getattr(args, key) != default for key, default in OPTIONAL_FIELDS.items()
            ):
                parser.error("--batch cannot be combined with individual freight arguments")
            source = sys.stdin.read() if args.batch == "-" else Path(args.batch).read_text(encoding="utf-8-sig")
            result = calculate_batch(json.loads(source, parse_float=Decimal))
        else:
            missing = sorted(key for key in REQUIRED_FIELDS if getattr(args, key) is None)
            if missing:
                parser.error("required arguments: " + ", ".join("--" + key.replace("_", "-") for key in missing))
            result = calculate(args)
    except (ArithmeticError, OSError, ValueError) as error:
        parser.error(str(error))
    print(json.dumps(result, default=lambda value: format(value, "f")))


if __name__ == "__main__":
    main()
