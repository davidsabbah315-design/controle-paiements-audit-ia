from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
import random

import pandas as pd


SUPPLIERS = [
    ("F001", "Atlas Conseil"),
    ("F002", "Buro Services"),
    ("F003", "Cloud Horizon"),
    ("F004", "Delta Maintenance"),
    ("F005", "Énergie Locale"),
    ("F006", "France Logistique"),
    ("F007", "Graphik Studio"),
    ("F008", "Hôtel République"),
]


def generate_payments(seed: int = 42, normal_count: int = 72) -> pd.DataFrame:
    """Crée un échantillon fictif reproductible, avec anomalies documentées."""
    rng = random.Random(seed)
    rows: list[dict] = []
    base = date(2026, 4, 1)

    for i in range(normal_count):
        supplier_id, supplier_name = rng.choice(SUPPLIERS)
        invoice_date = base + timedelta(days=rng.randint(0, 110))
        due_date = invoice_date + timedelta(days=rng.choice([30, 45, 60]))
        expected = round(rng.uniform(380, 8_500), 2)
        payment_date = _next_business_day(due_date + timedelta(days=rng.randint(-8, 12)))
        rows.append(
            _row(
                f"PAY-{i + 1:04d}", supplier_id, supplier_name,
                f"{supplier_id}-2026-{i + 1:04d}", invoice_date, due_date,
                payment_date, expected, expected,
            )
        )

    # Cas volontairement injectés : ils rendent chaque règle démontrable.
    rows.extend(
        [
            _row("PAY-9001", "F002", "Buro Services", "BS-8841", date(2026, 6, 2), date(2026, 7, 2), date(2026, 6, 28), 4_280, 4_280),
            _row("PAY-9002", "F002", "Buro Services", "BS-8841", date(2026, 6, 2), date(2026, 7, 2), date(2026, 6, 29), 4_280, 4_280),
            _row("PAY-9003", "F003", "Cloud Horizon", "CH-7712", date(2026, 6, 6), date(2026, 7, 6), date(2026, 7, 4), 72_500, 72_500),
            _row("PAY-9004", "F004", "Delta Maintenance", "DM-2047", date(2026, 7, 10), date(2026, 8, 9), date(2026, 7, 4), 6_200, 6_200),
            _row("PAY-9005", "F005", "Énergie Locale", "EL-9821", date(2026, 5, 12), date(2026, 6, 11), date(2026, 6, 10), 9_800, 10_760),
            _row("PAY-9006", "F006", "France Logistique", "FL-5101", date(2026, 7, 1), date(2026, 7, 31), date(2026, 7, 8), 6_100, 6_100),
            _row("PAY-9007", "F006", "France Logistique", "FL-5102", date(2026, 7, 1), date(2026, 7, 31), date(2026, 7, 9), 5_400, 5_400),
            _row("PAY-9008", "F009", "Nova Facilities", "NF-0001", date(2026, 7, 3), date(2026, 8, 2), date(2026, 7, 10), 18_400, 18_400, is_new=True),
            _row("PAY-9009", "F007", "Graphik Studio", "GS-1108", date(2026, 7, 2), date(2026, 8, 1), date(2026, 7, 12), 3_250, 3_250),
            _row("PAY-9010", "F001", "Atlas Conseil", "AC-6680", date(2026, 7, 4), date(2026, 8, 3), date(2026, 7, 7), 7_900, 7_900, invoice_available=False),
        ]
    )
    return pd.DataFrame(rows).sort_values("payment_date").reset_index(drop=True)


def _row(
    payment_id: str,
    supplier_id: str,
    supplier_name: str,
    invoice_number: str,
    invoice_date: date,
    due_date: date,
    payment_date: date,
    expected_amount: float,
    paid_amount: float,
    *,
    is_new: bool = False,
    invoice_available: bool = True,
) -> dict:
    return {
        "payment_id": payment_id,
        "supplier_id": supplier_id,
        "supplier_name": supplier_name,
        "invoice_number": invoice_number,
        "invoice_date": invoice_date.isoformat(),
        "due_date": due_date.isoformat(),
        "payment_date": payment_date.isoformat(),
        "expected_amount": expected_amount,
        "paid_amount": paid_amount,
        "currency": "EUR",
        "payment_method": "Virement",
        "approved_by": "Responsable finance",
        "invoice_available": invoice_available,
        "is_new_supplier": is_new,
    }


def _next_business_day(value: date) -> date:
    while value.weekday() >= 5:
        value += timedelta(days=1)
    return value


if __name__ == "__main__":
    target = Path(__file__).parent / "data" / "paiements_demo.csv"
    target.parent.mkdir(exist_ok=True)
    generate_payments().to_csv(target, index=False)
    print(f"{len(generate_payments())} paiements créés dans {target}")
