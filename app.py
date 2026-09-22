from __future__ import annotations

from html import escape
from pathlib import Path
import os

import pandas as pd
import streamlit as st

from audit_agent import AuditAgent
from connectors import audit_report_html, findings_to_xlsx, load_csv, payments_template_csv, payments_to_csv
from data_generator import generate_payments


ROOT = Path(__file__).parent
DEMO_PATH = ROOT / "data" / "paiements_demo.csv"
RISK_COLORS = {"Élevé": "#B33A3A", "Moyen": "#C98220", "Faible": "#4D6C76"}

st.set_page_config(
    page_title="Contrôle automatisé des paiements — Audit & IA",
    page_icon="✓",
    layout="wide",
)

st.markdown("""
<style>
    .stApp { background: #f5f7f8; }
    .block-container { max-width: 1280px; padding-top: 1.8rem; padding-bottom: 3rem; }
    h1, h2, h3 { color: #17313d !important; letter-spacing: -.02em; }
    h1 { font-size: 2.15rem !important; margin-bottom: .2rem !important; }
    [data-testid="stMetric"] { background:white; border:1px solid #dce3e6; border-top:3px solid #bd7a2a; padding:1rem; }
    [data-testid="stMetricLabel"], [data-testid="stMetricValue"] { color:#17313d !important; }
    [data-testid="stSidebar"] h2 { color:#F4F7F8 !important; }
    .eyebrow { color:#9a611e; font-weight:700; text-transform:uppercase; letter-spacing:.11em; font-size:.78rem; }
    .lede { color:#4d626d; font-size:1.03rem; max-width:850px; margin-bottom:1.25rem; }
    .scope { background:#e9f0f1; border-left:4px solid #275965; padding:.8rem 1rem; color:#29424b; }
    .summary-box { background:#e4f1f7; border:1px solid #bed7e2; border-radius:6px; padding:1rem 1.1rem; color:#17313d; line-height:1.55; }
    .risk-row { display:grid; grid-template-columns:72px 1fr 28px; gap:10px; align-items:center; margin:.8rem 0; color:#17313d; }
    .risk-track { height:18px; background:#dfe6e9; border-radius:2px; overflow:hidden; }
    .risk-fill { height:100%; background:#b8752c; }
    .risk-high { color:#9f2f2f; font-weight:700; }
    div[data-testid="stDownloadButton"] button { width:100%; }
</style>
""", unsafe_allow_html=True)


def get_payments() -> tuple[pd.DataFrame, str, bool]:
    with st.sidebar:
        st.header("Périmètre du contrôle")
        st.caption("Le fichier importé remplace le jeu fictif et relance tous les contrôles.")
        uploaded = st.file_uploader("Importer des paiements (CSV)", type="csv", help="CSV virgule ou point-virgule, 10 Mo maximum.")
        demo = load_csv(str(DEMO_PATH)) if DEMO_PATH.exists() else generate_payments()
        st.download_button(
            "Télécharger le modèle CSV",
            payments_template_csv(demo),
            "modele_paiements.csv",
            "text/csv",
            width="stretch",
        )
        if uploaded:
            selected_payments = load_csv(uploaded)
            source_name = uploaded.name
            is_uploaded = True
        else:
            selected_payments = demo
            source_name = "paiements_demo.csv"
            is_uploaded = False
            st.caption("Aucun fichier importé : le jeu fictif reproductible est utilisé.")
        st.download_button(
            "Télécharger les données analysées",
            payments_to_csv(selected_payments),
            "paiements_analyses.csv",
            "text/csv",
            width="stretch",
            help="Fichier source complet correspondant exactement au contrôle affiché.",
        )
        return selected_payments, source_name, is_uploaded


st.markdown('<div class="eyebrow">Démonstrateur audit interne · Données 100 % fictives</div>', unsafe_allow_html=True)
st.title("Contrôle automatisé des paiements – Démonstrateur audit & IA")
st.markdown(
    '<div class="lede">Une revue ciblée du processus fournisseurs : règles traçables, priorisation des risques, '
    'piste d’audit et synthèse assistée. Aucun constat n’est une preuve de fraude.</div>',
    unsafe_allow_html=True,
)

try:
    payments, source_name, is_uploaded = get_payments()
    with st.sidebar:
        st.divider()
        st.write(f"**Source :** {source_name}")
        use_ai = st.toggle(
            "Synthèse IA générative",
            value=False,
            disabled=not bool(os.getenv("OPENAI_API_KEY")),
            help="Nécessite OPENAI_API_KEY. Les contrôles restent exécutés par le moteur de règles.",
        )
        st.caption("Agent : charger → contrôler → classer → synthétiser")
    run = AuditAgent().run(payments, use_generative_ai=use_ai)
    if is_uploaded:
        with st.sidebar:
            st.success(f"{len(payments)} paiements chargés et contrôlés.")
except Exception as exc:
    with st.sidebar:
        st.error("Import refusé. Corrige le fichier puis réessaie.")
    st.error(f"Le fichier ne peut pas être contrôlé : {exc}")
    st.stop()

findings = run.findings
counts = findings["risk_level"].value_counts() if not findings.empty else pd.Series(dtype=int)
amount_reviewed = payments["paid_amount"].sum()

col1, col2, col3, col4 = st.columns(4)
col1.metric("Paiements analysés", f"{len(payments)}")
col2.metric(
    "Montant contrôlé",
    f"{amount_reviewed / 1000:,.0f} k€".replace(",", " "),
    help="Somme des montants payés de tous les paiements du périmètre, et non montant des anomalies.",
)
col3.metric("Constats", f"{len(findings)}")
col4.metric("Risque élevé", f"{int(counts.get('Élevé', 0))}")

overview_tab, findings_tab, method_tab = st.tabs(["Synthèse de mission", "Constats détaillés", "Dispositif de contrôle"])

with overview_tab:
    left, right = st.columns([1.35, 1])
    with left:
        st.subheader("Synthèse d’audit")
        st.markdown(f'<div class="summary-box">{escape(run.summary)}</div>', unsafe_allow_html=True)
        st.caption(run.summary_mode)
        st.markdown('<div class="scope"><b>Lecture :</b> les alertes orientent les travaux complémentaires. Elles ne concluent ni à une erreur certaine, ni à une fraude.</div>', unsafe_allow_html=True)
    with right:
        st.subheader("Ventilation des risques")
        levels = [(label, int(counts.get(label, 0))) for label in ["Élevé", "Moyen", "Faible"]]
        scale = max((value for _, value in levels), default=1) or 1
        bars = "".join(
            f'<div class="risk-row"><span>{label}</span><div class="risk-track"><div class="risk-fill" style="width:{value / scale * 100:.0f}%"></div></div><b>{value}</b></div>'
            for label, value in levels
        )
        st.markdown(bars, unsafe_allow_html=True)
    st.subheader("Priorités de contrôle")
    if findings.empty:
        st.success("Aucun constat selon les paramètres actifs.")
    else:
        priorities = findings.sort_values("risk_score", ascending=False).head(5)[["anomaly_id", "anomaly_type", "supplier_name", "risk_level", "recommendation"]]
        st.dataframe(priorities, hide_index=True, width="stretch", column_config={"anomaly_id": "Réf. constat", "anomaly_type": "Anomalie", "supplier_name": "Fournisseur", "risk_level": "Risque", "recommendation": "Action recommandée"})

with findings_tab:
    st.subheader("Journal des anomalies")
    st.caption("Une référence A-xxx identifie un constat généré par les contrôles ; PAY-xxxx désigne le ou les paiements sources concernés.")
    if findings.empty:
        st.success("Aucune anomalie détectée.")
    else:
        risk_filter = st.multiselect("Niveau de risque", ["Élevé", "Moyen", "Faible"], default=["Élevé", "Moyen", "Faible"])
        visible = findings[findings.risk_level.isin(risk_filter)]
        st.dataframe(
            visible[["anomaly_id", "anomaly_type", "risk_level", "supplier_name", "payment_id", "amount", "payment_date"]],
            hide_index=True,
            width="stretch",
            column_config={
                "anomaly_id": "Réf. constat", "anomaly_type": "Type", "risk_level": "Risque",
                "supplier_name": "Fournisseur", "payment_id": "Paiement(s)",
                "amount": st.column_config.NumberColumn("Montant", format="%.2f €"), "payment_date": "Date",
            },
        )
        selected_id = st.selectbox("Ouvrir un constat", visible.anomaly_id, format_func=lambda value: f"{value} — {visible.loc[visible.anomaly_id == value, 'anomaly_type'].iloc[0]}")
        selected = visible.loc[visible.anomaly_id == selected_id].iloc[0]
        st.markdown(f"### {selected.anomaly_id} · {selected.anomaly_type}")
        d1, d2, d3 = st.columns(3)
        d1.write(f"**Risque**  \n{selected.risk_level} · score {selected.risk_score}/100")
        d2.write(f"**Fournisseur**  \n{selected.supplier_name}")
        d3.write(f"**Paiement(s)**  \n{selected.payment_id}")
        st.write(f"**Règle déclenchée**  \n{selected.rule}")
        st.write(f"**Constat**  \n{selected.explanation}")
        st.warning(f"**Recommandation de contrôle**  \n{selected.recommendation}")

with method_tab:
    st.subheader("Une architecture crédible et limitée")
    a, b, c = st.columns(3)
    a.markdown("**1 · Connecteur**\n\nImport CSV, validation du schéma et exports CSV/HTML.")
    b.markdown("**2 · Moteur de règles**\n\nHuit familles de tests déterministes, seuils lisibles et résultats reproductibles.")
    c.markdown("**3 · Agent de synthèse**\n\nOrchestration des étapes. L’IA rédige uniquement à partir de constats déjà établis.")
    st.markdown("#### Piste d’exécution de l’agent")
    for step in run.steps:
        st.write(f"✓ {step}")
    st.markdown("#### Référentiel des contrôles")
    controls = pd.DataFrame([
        ["Doublons", "Fournisseur + n° facture identiques", "Élevé"],
        ["Montants élevés", "≥ 50 k€ ou ≥ 4× médiane fournisseur", "Élevé"],
        ["Échéances", "Chronologie incohérente ou retard > 30 j", "Moyen"],
        ["Écarts", "> max(50 €, 1 % du montant attendu)", "Élevé"],
        ["Fractionnement", "Même fournisseur et dates ; 10 à 12,5 k€ sur 3 j", "Élevé"],
        ["Nouveau fournisseur", "Premier paiement ≥ 7,5 k€", "Moyen"],
        ["Calendrier / fréquence", "Week-end ou ≥ 5 opérations/jour", "Faible"],
        ["Pièce justificative", "Facture indisponible", "Élevé"],
    ], columns=["Risque couvert", "Paramètre", "Cotation"])
    st.dataframe(controls, hide_index=True, width="stretch")

st.divider()
download1, download2, note = st.columns([1, 1, 1.5])
download1.download_button(
    "Exporter le rapport d'audit (Excel)",
    findings_to_xlsx(payments, findings, run.summary),
    "constats_audit.xlsx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    help="Inclut les constats, le montant total contrôlé et les paiements sources avec leur référence de constat.",
)
download2.download_button("Exporter le rapport (HTML)", audit_report_html(payments, findings, run.summary), "rapport_audit.html", "text/html")
note.caption("Périmètre fictif · Seuils illustratifs à adapter à la politique de délégation réelle.")
