from __future__ import annotations

from dataclasses import dataclass, asdict
from itertools import count
from typing import Callable

import pandas as pd


REQUIRED_COLUMNS = {
    "payment_id", "supplier_id", "supplier_name", "invoice_number",
    "invoice_date", "due_date", "payment_date", "expected_amount",
    "paid_amount", "invoice_available", "is_new_supplier",
}

RISK_ORDER = {"Élevé": 3, "Moyen": 2, "Faible": 1}


@dataclass(frozen=True)
class Finding:
    anomaly_id: str
    payment_id: str
    supplier_name: str
    anomaly_type: str
    risk_level: str
    risk_score: int
    rule: str
    explanation: str
    recommendation: str
    amount: float
    payment_date: str


class PaymentAuditEngine:
    """Moteur transparent : une règle de contrôle produit un constat traçable."""

    HIGH_AMOUNT = 50_000.0
    APPROVAL_THRESHOLD = 10_000.0
    VARIANCE_RATE = 0.01
    VARIANCE_MIN = 50.0
    NEW_SUPPLIER_REVIEW = 7_500.0

    def __init__(self) -> None:
        self._ids = count(1)

    def run(self, source: pd.DataFrame) -> pd.DataFrame:
        self._ids = count(1)
        df = self._prepare(source)
        checks: list[Callable[[pd.DataFrame], list[Finding]]] = [
            self._duplicate_invoices,
            self._high_amounts,
            self._inconsistent_dates,
            self._amount_variances,
            self._split_payments,
            self._new_suppliers,
            self._calendar_anomalies,
            self._missing_documents,
        ]
        findings = [finding for check in checks for finding in check(df)]
        columns = list(Finding.__dataclass_fields__)
        result = pd.DataFrame([asdict(item) for item in findings], columns=columns)
        if result.empty:
            return result
        return result.sort_values(
            ["risk_score", "payment_date"], ascending=[False, False]
        ).reset_index(drop=True)

    def _prepare(self, source: pd.DataFrame) -> pd.DataFrame:
        missing = REQUIRED_COLUMNS.difference(source.columns)
        if missing:
            raise ValueError("Colonnes manquantes : " + ", ".join(sorted(missing)))
        df = source.copy()
        for column in ("invoice_date", "due_date", "payment_date"):
            df[column] = pd.to_datetime(df[column], errors="coerce")
        for column in ("expected_amount", "paid_amount"):
            df[column] = pd.to_numeric(df[column], errors="coerce")
        if df[["invoice_date", "due_date", "payment_date", "expected_amount", "paid_amount"]].isna().any().any():
            raise ValueError("Le fichier contient des dates ou montants non exploitables.")
        df["invoice_available"] = df["invoice_available"].map(_as_bool)
        df["is_new_supplier"] = df["is_new_supplier"].map(_as_bool)
        return df

    def _finding(self, row: pd.Series, kind: str, risk: str, score: int, rule: str, explanation: str, recommendation: str, payment_id: str | None = None, amount: float | None = None) -> Finding:
        return Finding(
            anomaly_id=f"A-{next(self._ids):03d}",
            payment_id=payment_id or str(row.payment_id),
            supplier_name=str(row.supplier_name),
            anomaly_type=kind,
            risk_level=risk,
            risk_score=score,
            rule=rule,
            explanation=explanation,
            recommendation=recommendation,
            amount=float(row.paid_amount if amount is None else amount),
            payment_date=row.payment_date.date().isoformat(),
        )

    def _duplicate_invoices(self, df: pd.DataFrame) -> list[Finding]:
        mask = df.duplicated(["supplier_id", "invoice_number"], keep=False)
        return [
            self._finding(
                row, "Doublon de facture", "Élevé", 95,
                "Même fournisseur + même numéro de facture sur plusieurs paiements.",
                f"La facture {row.invoice_number} apparaît plusieurs fois pour {row.supplier_name}.",
                "Bloquer le paiement suivant et rapprocher facture, bon à payer et historique bancaire.",
            )
            for _, row in df[mask].iterrows()
        ]

    def _high_amounts(self, df: pd.DataFrame) -> list[Finding]:
        supplier_median = df.groupby("supplier_id")["paid_amount"].transform("median")
        mask = (df["paid_amount"] >= self.HIGH_AMOUNT) | (df["paid_amount"] >= 4 * supplier_median)
        return [
            self._finding(
                row, "Montant inhabituellement élevé", "Élevé", 85,
                "Montant ≥ 50 000 € ou ≥ 4 fois la médiane du fournisseur.",
                f"Le paiement de {row.paid_amount:,.2f} € dépasse le profil habituel du fournisseur.",
                "Obtenir une seconde approbation et rapprocher contrat, facture et réception du service.",
            )
            for _, row in df[mask].iterrows()
        ]

    def _inconsistent_dates(self, df: pd.DataFrame) -> list[Finding]:
        mask = (df["due_date"] < df["invoice_date"]) | (df["payment_date"] < df["invoice_date"]) | (df["payment_date"] > df["due_date"] + pd.Timedelta(days=30))
        results = []
        for _, row in df[mask].iterrows():
            if row.payment_date < row.invoice_date:
                reason = "paiement antérieur à la facture"
            elif row.due_date < row.invoice_date:
                reason = "échéance antérieure à la facture"
            else:
                reason = "retard supérieur à 30 jours"
            results.append(self._finding(
                row, "Échéance incohérente", "Moyen", 65,
                "Chronologie facture–échéance–paiement incohérente ou retard > 30 jours.",
                f"La chronologie est atypique : {reason}.",
                "Vérifier les dates sources, l’autorisation de paiement et la cause opérationnelle.",
            ))
        return results

    def _amount_variances(self, df: pd.DataFrame) -> list[Finding]:
        delta = (df["paid_amount"] - df["expected_amount"]).abs()
        limit = (df["expected_amount"] * self.VARIANCE_RATE).clip(lower=self.VARIANCE_MIN)
        return [
            self._finding(
                row, "Écart montant attendu / payé", "Élevé", 90,
                "Écart absolu > max(50 €, 1 % du montant attendu).",
                f"Montant attendu : {row.expected_amount:,.2f} € ; payé : {row.paid_amount:,.2f} €.",
                "Suspendre l’écart et rapprocher facture, avoir, taxes et ordre de virement.",
            )
            for idx, row in df[(delta > limit)].iterrows()
        ]

    def _split_payments(self, df: pd.DataFrame) -> list[Finding]:
        candidates = df[
            (df["paid_amount"] < self.APPROVAL_THRESHOLD)
            & (df["paid_amount"] >= self.APPROVAL_THRESHOLD * 0.4)
        ].sort_values("payment_date")
        results: list[Finding] = []
        seen: set[tuple[str, tuple[str, ...]]] = set()
        for group_key, group in candidates.groupby(["supplier_id", "invoice_date", "due_date"]):
            for _, anchor in group.iterrows():
                window = group[(group.payment_date >= anchor.payment_date) & (group.payment_date <= anchor.payment_date + pd.Timedelta(days=3))]
                total = float(window.paid_amount.sum())
                if len(window) >= 2 and self.APPROVAL_THRESHOLD <= total <= self.APPROVAL_THRESHOLD * 1.25:
                    ids = tuple(sorted(window.payment_id.astype(str)))
                    key = (str(group_key), ids)
                    if key in seen:
                        continue
                    seen.add(key)
                    results.append(self._finding(
                        anchor, "Paiements fractionnés", "Élevé", 92,
                        "Même fournisseur et mêmes dates de facture/échéance : au moins 2 paiements de 4 000 à 9 999 € totalisant 10 000 à 12 500 € sur 3 jours.",
                        f"{len(window)} paiements totalisent {total:,.2f} € autour du seuil d’approbation.",
                        "Regrouper les opérations, vérifier l’unicité de la prestation et faire valider au niveau requis.",
                        payment_id=" · ".join(ids), amount=total,
                    ))
        return results

    def _new_suppliers(self, df: pd.DataFrame) -> list[Finding]:
        mask = df["is_new_supplier"] & (df["paid_amount"] >= self.NEW_SUPPLIER_REVIEW)
        return [
            self._finding(
                row, "Nouveau fournisseur sensible", "Moyen", 70,
                "Premier paiement fournisseur ≥ 7 500 €.",
                f"Premier paiement de {row.paid_amount:,.2f} € à un fournisseur nouvellement créé.",
                "Contrôler création du tiers, identité, coordonnées bancaires et validation indépendante.",
            )
            for _, row in df[mask].iterrows()
        ]

    def _calendar_anomalies(self, df: pd.DataFrame) -> list[Finding]:
        weekend = df["payment_date"].dt.dayofweek >= 5
        daily_count = df.groupby(["supplier_id", "payment_date"])["payment_id"].transform("count")
        mask = weekend | (daily_count >= 5)
        return [
            self._finding(
                row, "Anomalie de calendrier / fréquence", "Faible", 40,
                "Paiement un week-end ou ≥ 5 paiements au même fournisseur le même jour.",
                "La date ou la fréquence de paiement sort du calendrier opérationnel attendu.",
                "Confirmer le calendrier de traitement et examiner le journal des validations.",
            )
            for _, row in df[mask].iterrows()
        ]

    def _missing_documents(self, df: pd.DataFrame) -> list[Finding]:
        return [
            self._finding(
                row, "Pièce justificative absente", "Élevé", 88,
                "Aucune facture disponible pour le paiement.",
                "Le paiement ne dispose pas de pièce justificative dans le dossier de contrôle.",
                "Bloquer ou régulariser le dossier, obtenir la facture et documenter l’approbation.",
            )
            for _, row in df[~df["invoice_available"]].iterrows()
        ]


def _as_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes", "oui", "vrai"}
