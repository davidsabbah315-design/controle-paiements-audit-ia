from __future__ import annotations

from datetime import datetime
from html import escape
from io import BytesIO, StringIO
from pathlib import Path

import pandas as pd
from openpyxl import Workbook
from openpyxl.formatting.rule import FormulaRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.worksheet.table import Table, TableStyleInfo


def load_csv(source: str | Path | BytesIO) -> pd.DataFrame:
    """Charge un CSV virgule ou point-virgule, y compris les formats Excel français."""
    if isinstance(source, (str, Path)):
        raw = Path(source).read_bytes()
    elif hasattr(source, "getvalue"):
        raw = source.getvalue()
    else:
        raw = source.read()

    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("cp1252")

    df = pd.read_csv(StringIO(text), sep=None, engine="python")
    df.columns = [str(column).strip().lstrip("\ufeff") for column in df.columns]
    for column in ("expected_amount", "paid_amount"):
        if column in df.columns and df[column].dtype == object:
            cleaned = (
                df[column].astype(str)
                .str.replace("\u202f", "", regex=False)
                .str.replace("\xa0", "", regex=False)
                .str.replace(" ", "", regex=False)
                .str.replace(",", ".", regex=False)
            )
            df[column] = pd.to_numeric(cleaned, errors="coerce")
    return df


def findings_to_csv(findings: pd.DataFrame) -> bytes:
    return findings.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig")


def payments_template_csv(payments: pd.DataFrame) -> bytes:
    """Modèle compatible avec les paramètres régionaux d'Excel en français."""
    return payments_to_csv(payments.head(8))


def payments_to_csv(payments: pd.DataFrame) -> bytes:
    """Exporte exactement le jeu de paiements actuellement contrôlé."""
    return payments.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig")


def findings_to_xlsx(payments: pd.DataFrame, findings: pd.DataFrame, summary: str) -> bytes:
    """Produit un rapport traçable avec synthèse, constats et paiements sources."""
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Constats d'audit"
    sheet.sheet_view.showGridLines = False
    sheet.freeze_panes = "A8"

    navy = "17313D"
    bronze = "B8752C"
    pale_blue = "EAF2F5"
    white = "FFFFFF"
    border_color = "D7E0E3"
    thin = Side(style="thin", color=border_color)

    sheet["A1"] = "Contrôle automatisé des paiements"
    sheet["A1"].font = Font(name="Aptos", size=16, bold=True, color=navy)
    sheet["A2"] = "Données fictives – les alertes orientent les travaux complémentaires et ne prouvent pas une fraude."
    sheet["A2"].font = Font(name="Aptos", size=10, italic=True, color="536872")

    risk_counts = findings["risk_level"].value_counts() if not findings.empty else {}
    amount_reviewed = round(float(payments["paid_amount"].sum()), 2)
    kpis = [
        ("Paiements analysés", len(payments)),
        ("Montant total contrôlé", amount_reviewed),
        ("Constats", len(findings)),
        ("Risques élevés", int(risk_counts.get("Élevé", 0))),
    ]
    kpi_columns = [(1, 2), (4, 5), (7, 8), (10, 10)]
    for index, (label, value) in enumerate(kpis):
        start_column, end_column = kpi_columns[index]
        if end_column > start_column:
            sheet.merge_cells(start_row=4, start_column=start_column, end_row=4, end_column=end_column)
            sheet.merge_cells(start_row=5, start_column=start_column, end_row=5, end_column=end_column)
        column = start_column
        label_cell = sheet.cell(4, column, label)
        value_cell = sheet.cell(5, column, value)
        label_cell.font = Font(name="Aptos", size=10, bold=True, color=white)
        label_cell.fill = PatternFill("solid", fgColor=navy)
        label_cell.alignment = Alignment(horizontal="center", vertical="center")
        value_cell.font = Font(name="Aptos", size=14, bold=True, color=navy)
        value_cell.fill = PatternFill("solid", fgColor=pale_blue)
        value_cell.alignment = Alignment(horizontal="center", vertical="center")
        if label == "Montant total contrôlé":
            value_cell.number_format = '#,##0.00 [$€-fr-FR]'
        for row in (4, 5):
            for merged_column in range(start_column, end_column + 1):
                sheet.cell(row, merged_column).border = Border(left=thin, right=thin, top=thin, bottom=thin)

    headers = [
        "Référence du constat", "Type d'anomalie", "Niveau de risque", "Score",
        "Fournisseur", "Paiement(s)", "Montant (€)", "Date de paiement",
        "Règle déclenchée", "Explication", "Recommandation de contrôle",
    ]
    header_row = 7
    sheet.append([])
    sheet.append([])
    # Les six premières lignes sont déjà utilisées ; écrire l'en-tête à la ligne 7.
    for col, header in enumerate(headers, 1):
        cell = sheet.cell(header_row, col, header)
        cell.font = Font(name="Aptos", size=10, bold=True, color=white)
        cell.fill = PatternFill("solid", fgColor=navy)
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = Border(left=Side(style="thin", color=white), right=Side(style="thin", color=white))

    for row_number, (_, finding) in enumerate(findings.iterrows(), header_row + 1):
        raw_date = str(finding.payment_date)
        try:
            payment_date = datetime.strptime(raw_date, "%Y-%m-%d").date()
        except ValueError:
            payment_date = raw_date
        values = [
            finding.anomaly_id, finding.anomaly_type, finding.risk_level,
            int(finding.risk_score), finding.supplier_name, finding.payment_id,
            float(finding.amount), payment_date, finding.rule,
            finding.explanation, finding.recommendation,
        ]
        for col, value in enumerate(values, 1):
            cell = sheet.cell(row_number, col, value)
            cell.font = Font(name="Aptos", size=10, color=navy)
            cell.alignment = Alignment(vertical="top", wrap_text=col in {2, 6, 9, 10, 11})
            cell.border = Border(bottom=thin)
        sheet.cell(row_number, 4).alignment = Alignment(horizontal="center", vertical="top")
        sheet.cell(row_number, 7).number_format = '#,##0.00 [$€-fr-FR]'
        sheet.cell(row_number, 8).number_format = "dd/mm/yyyy"
        sheet.row_dimensions[row_number].height = 42

    if not findings.empty:
        end_row = header_row + len(findings)
        table = Table(displayName="TableConstatsAudit", ref=f"A{header_row}:K{end_row}")
        table.tableStyleInfo = TableStyleInfo(
            name="TableStyleMedium2", showFirstColumn=False,
            showLastColumn=False, showRowStripes=True, showColumnStripes=False,
        )
        sheet.add_table(table)
        risk_range = f"C{header_row + 1}:C{end_row}"
        sheet.conditional_formatting.add(risk_range, FormulaRule(formula=[f'C{header_row + 1}="Élevé"'], fill=PatternFill("solid", fgColor="F4CCCC"), font=Font(color="9C0006", bold=True)))
        sheet.conditional_formatting.add(risk_range, FormulaRule(formula=[f'C{header_row + 1}="Moyen"'], fill=PatternFill("solid", fgColor="FCE5CD"), font=Font(color="9A5A00", bold=True)))
        sheet.conditional_formatting.add(risk_range, FormulaRule(formula=[f'C{header_row + 1}="Faible"'], fill=PatternFill("solid", fgColor="D9EAD3"), font=Font(color="356B2D", bold=True)))

    widths = [14, 28, 17, 9, 23, 24, 15, 17, 48, 55, 55]
    for index, width in enumerate(widths, 1):
        sheet.column_dimensions[chr(64 + index)].width = width
    sheet.row_dimensions[1].height = 24
    sheet.row_dimensions[2].height = 20
    sheet.row_dimensions[7].height = 30
    sheet.auto_filter.ref = f"A{header_row}:K{header_row + len(findings)}"
    sheet.print_title_rows = f"1:{header_row}"
    sheet.page_setup.orientation = "landscape"
    sheet.page_setup.fitToWidth = 1
    sheet.sheet_properties.pageSetUpPr.fitToPage = True

    source_sheet = workbook.create_sheet("Paiements analysés")
    source_sheet.sheet_view.showGridLines = False
    source_sheet.freeze_panes = "A2"
    source_headers = {
        "payment_id": "ID paiement",
        "supplier_id": "ID fournisseur",
        "supplier_name": "Fournisseur",
        "invoice_number": "N° de facture",
        "invoice_date": "Date de facture",
        "due_date": "Échéance",
        "payment_date": "Date de paiement",
        "expected_amount": "Montant attendu (€)",
        "paid_amount": "Montant payé (€)",
        "currency": "Devise",
        "payment_method": "Mode de paiement",
        "approved_by": "Approbateur",
        "invoice_available": "Facture disponible",
        "is_new_supplier": "Nouveau fournisseur",
    }
    ordered_columns = [column for column in source_headers if column in payments.columns]
    source_headers_row = [source_headers[column] for column in ordered_columns] + ["Constat(s) associé(s)"]
    finding_links: dict[str, list[str]] = {}
    for _, finding in findings.iterrows():
        for payment_id in str(finding.payment_id).replace("·", "|").split("|"):
            payment_id = payment_id.strip()
            if payment_id:
                finding_links.setdefault(payment_id, []).append(str(finding.anomaly_id))

    for col, header in enumerate(source_headers_row, 1):
        cell = source_sheet.cell(1, col, header)
        cell.font = Font(name="Aptos", size=10, bold=True, color=white)
        cell.fill = PatternFill("solid", fgColor=navy)
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    date_columns = {"invoice_date", "due_date", "payment_date"}
    amount_columns = {"expected_amount", "paid_amount"}
    boolean_columns = {"invoice_available", "is_new_supplier"}
    for row_number, (_, payment) in enumerate(payments.iterrows(), 2):
        for col, column in enumerate(ordered_columns, 1):
            value = payment[column]
            if column in date_columns:
                try:
                    value = datetime.strptime(str(value), "%Y-%m-%d").date()
                except ValueError:
                    pass
            elif column in amount_columns:
                value = float(value)
            elif column in boolean_columns:
                value = "Oui" if bool(value) else "Non"
            cell = source_sheet.cell(row_number, col, value)
            cell.font = Font(name="Aptos", size=10, color=navy)
            cell.border = Border(bottom=thin)
            if column in date_columns:
                cell.number_format = "dd/mm/yyyy"
            elif column in amount_columns:
                cell.number_format = '#,##0.00 [$€-fr-FR]'
        payment_id = str(payment["payment_id"])
        source_sheet.cell(row_number, len(source_headers_row), ", ".join(finding_links.get(payment_id, [])))
        source_sheet.cell(row_number, len(source_headers_row)).border = Border(bottom=thin)

    if not payments.empty:
        source_end_row = len(payments) + 1
        source_end_column = len(source_headers_row)
        source_table = Table(
            displayName="TablePaiementsAnalyses",
            ref=f"A1:{source_sheet.cell(1, source_end_column).column_letter}{source_end_row}",
        )
        source_table.tableStyleInfo = TableStyleInfo(
            name="TableStyleMedium2", showFirstColumn=False,
            showLastColumn=False, showRowStripes=True, showColumnStripes=False,
        )
        source_sheet.add_table(source_table)
    source_widths = [14, 14, 24, 20, 16, 16, 17, 20, 18, 10, 18, 22, 19, 20, 24]
    for index, width in enumerate(source_widths[:len(source_headers_row)], 1):
        source_sheet.column_dimensions[source_sheet.cell(1, index).column_letter].width = width
    source_sheet.row_dimensions[1].height = 32
    source_sheet.auto_filter.ref = f"A1:{source_sheet.cell(1, len(source_headers_row)).column_letter}{len(payments) + 1}"
    source_sheet.page_setup.orientation = "landscape"
    source_sheet.page_setup.fitToWidth = 1
    source_sheet.sheet_properties.pageSetUpPr.fitToPage = True

    # La synthèse complète reste disponible dans les propriétés du document sans alourdir le tableau.
    workbook.properties.subject = summary[:255]
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def audit_report_html(payments: pd.DataFrame, findings: pd.DataFrame, summary: str) -> bytes:
    counts = findings["risk_level"].value_counts() if not findings.empty else {}
    rows = "".join(
        "<tr>"
        f"<td>{escape(str(row.anomaly_id))}</td>"
        f"<td>{escape(str(row.anomaly_type))}</td>"
        f"<td>{escape(str(row.risk_level))}</td>"
        f"<td>{escape(str(row.supplier_name))}</td>"
        f"<td>{escape(str(row.explanation))}</td>"
        f"<td>{escape(str(row.recommendation))}</td>"
        "</tr>"
        for _, row in findings.iterrows()
    )
    html = f"""<!doctype html><html lang='fr'><meta charset='utf-8'>
    <title>Rapport de contrôle des paiements</title>
    <style>body{{font:15px Arial;color:#172635;margin:38px}}h1{{color:#123f4a}}.meta{{display:flex;gap:30px;background:#eef3f4;padding:16px}}table{{border-collapse:collapse;width:100%;margin-top:22px}}th,td{{border:1px solid #ccd5d8;padding:8px;text-align:left;vertical-align:top}}th{{background:#123f4a;color:white}}</style>
    <h1>Contrôle automatisé des paiements</h1>
    <div class='meta'><b>{len(payments)} paiements analysés</b><b>{payments['paid_amount'].sum():,.2f} € contrôlés</b><b>{len(findings)} constats</b><b>{int(counts.get('Élevé', 0))} risques élevés</b></div>
    <h2>Synthèse</h2><p>{escape(summary)}</p>
    <h2>Constats</h2><table><thead><tr><th>ID</th><th>Type</th><th>Risque</th><th>Fournisseur</th><th>Explication</th><th>Recommandation</th></tr></thead><tbody>{rows}</tbody></table>
    <p><small>Données fictives — démonstrateur de contrôle interne. Un signal constitue un point à examiner, pas une preuve de fraude.</small></p></html>"""
    return html.encode("utf-8")
