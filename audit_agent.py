from __future__ import annotations

from dataclasses import dataclass
import json
import os
from urllib.request import Request, urlopen

import pandas as pd

from audit_engine import PaymentAuditEngine


@dataclass
class AuditRun:
    payments: pd.DataFrame
    findings: pd.DataFrame
    summary: str
    summary_mode: str
    steps: list[str]


class AuditAgent:
    """Orchestrateur léger : les étapes sont explicites et auditables."""

    def __init__(self, engine: PaymentAuditEngine | None = None) -> None:
        self.engine = engine or PaymentAuditEngine()

    def run(self, payments: pd.DataFrame, use_generative_ai: bool = False) -> AuditRun:
        steps = [f"1. Chargement et validation de {len(payments)} paiements"]
        findings = self.engine.run(payments)
        steps.append(f"2. Exécution de 8 familles de contrôles — {len(findings)} constats")
        steps.append("3. Classement des constats par criticité et score de risque")
        if use_generative_ai and os.getenv("OPENAI_API_KEY"):
            try:
                summary = self._openai_summary(payments, findings)
                mode = "Synthèse générative — aucun contrôle délégué à l’IA"
            except Exception as exc:  # Le contrôle reste disponible en cas d'indisponibilité externe.
                summary = self._local_summary(payments, findings)
                mode = f"Synthèse structurée locale — service IA indisponible ({type(exc).__name__})"
        else:
            summary = self._local_summary(payments, findings)
            mode = "Synthèse structurée locale — activer l’IA générative avec OPENAI_API_KEY"
        steps.append("4. Production d’une synthèse et de recommandations prioritaires")
        return AuditRun(payments, findings, summary, mode, steps)

    def _local_summary(self, payments: pd.DataFrame, findings: pd.DataFrame) -> str:
        if findings.empty:
            return (
                "Aucune anomalie n’a été relevée par les règles paramétrées. "
                "Cette conclusion ne constitue pas une assurance exhaustive : un contrôle par sondage reste recommandé."
            )
        counts = findings["risk_level"].value_counts()
        high = int(counts.get("Élevé", 0))
        medium = int(counts.get("Moyen", 0))
        top_types = findings.groupby("anomaly_type").size().sort_values(ascending=False).head(3)
        themes = ", ".join(f"{name} ({count})" for name, count in top_types.items())
        exposure = findings.drop_duplicates("payment_id")["amount"].sum()
        exposure_text = f"{exposure:,.0f}".replace(",", " ")
        return (
            f"Les contrôles ont analysé {len(payments)} paiements et relevé {len(findings)} constats, "
            f"dont {high} de niveau élevé et {medium} de niveau moyen. Les thèmes dominants sont : {themes}. "
            f"Le montant indicatif associé aux opérations signalées est de {exposure_text} € ; il ne représente pas "
            "nécessairement une perte. Priorité recommandée : sécuriser les doublons et écarts de montant, puis "
            "documenter les validations des nouveaux fournisseurs et opérations proches du seuil."
        )

    def _openai_summary(self, payments: pd.DataFrame, findings: pd.DataFrame) -> str:
        compact = findings[["anomaly_type", "risk_level", "rule", "recommendation"]].value_counts().reset_index(name="count")
        prompt = (
            "Tu es un assistant de rédaction d'audit interne. À partir de constats déjà établis par des règles, "
            "rédige en français une synthèse factuelle de 120 mots maximum : périmètre, risques prioritaires, "
            "limite de l'analyse et trois actions. N'invente aucune entité ni conclusion de fraude. Données : "
            + json.dumps({"payments": len(payments), "findings": compact.to_dict("records")}, ensure_ascii=False)
        )
        payload = json.dumps({
            "model": os.getenv("OPENAI_MODEL", "gpt-5-mini"),
            "input": prompt,
        }).encode("utf-8")
        request = Request(
            "https://api.openai.com/v1/responses",
            data=payload,
            headers={
                "Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urlopen(request, timeout=25) as response:
            data = json.loads(response.read().decode("utf-8"))
        for item in data.get("output", []):
            for content in item.get("content", []):
                if content.get("type") == "output_text":
                    return content["text"].strip()
        raise RuntimeError("Réponse IA sans texte exploitable")
