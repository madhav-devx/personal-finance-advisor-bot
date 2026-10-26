"""PDF generation for the monthly report (reportlab)."""
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.calculations import format_money, pct
from app.constants import CATEGORY_LABELS, DISCLAIMER


def _sym(snap):
    # Built-in PDF fonts have no rupee glyph, so print "Rs." instead.
    return "Rs. " if snap["currency"] == "₹" else snap["currency"]


def _table(data, widths, header=True):
    table = Table(data, colWidths=widths, repeatRows=1 if header else 0)
    style = [("FONTSIZE", (0, 0), (-1, -1), 9), ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#d1d5db")),
             ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
             ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]
    if header:
        style += [("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#059669")),
                  ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold")]
    table.setStyle(TableStyle(style))
    return table


def build_report_pdf(snap, extras, user_name):
    """Return PDF bytes for a monthly report. ``snap``/``extras`` come from services/engine."""
    s = _sym(snap)
    money = lambda v: format_money(v, s, 2, indian=(snap["currency"] == "₹"))
    styles = getSampleStyleSheet()
    small = ParagraphStyle("small", parent=styles["BodyText"], fontSize=8, textColor=colors.HexColor("#6b7280"))
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm,
                            bottomMargin=16 * mm, title=f"Monthly report - {snap['label']}")
    story = [Paragraph(f"Monthly Financial Report - {escape(snap['label'])}", styles["Title"]),
             Paragraph(f"Prepared for {escape(user_name)}", styles["Normal"]), Spacer(1, 8)]

    rate = snap["savings_rate"]
    story.append(_table([
        ["Measure", "Amount"],
        ["Total income", money(snap["income_total"])],
        ["Total expenses", money(snap["expense_total"])],
        ["Remaining balance / net savings", money(snap["balance"])],
        ["Savings rate", "n/a" if rate is None else f"{rate:.1f}%"],
        ["Saved to goals this month", money(snap["contributions_month"])],
    ], [100 * mm, 60 * mm]))
    story.append(Spacer(1, 10))
    story.append(Paragraph(escape(extras["summary"]["text"]), styles["BodyText"]))

    story += [Spacer(1, 8), Paragraph("Expenses by category", styles["Heading2"])]
    rows = [["Category", "Spent", "Share of spending"]]
    for cat, value in snap["category_totals"].items():
        share = pct(value, snap["expense_total"])
        rows.append([CATEGORY_LABELS.get(cat, cat), money(value), "-" if share is None else f"{share:.0f}%"])
    if len(rows) == 1:
        rows.append(["No expenses recorded", "-", "-"])
    story.append(_table(rows, [70 * mm, 50 * mm, 40 * mm]))

    story += [Spacer(1, 8), Paragraph("Budget versus actual", styles["Heading2"])]
    rows = [["Category", "Budget", "Actual", "Used"]]
    for r in extras["budget_rows"]:
        if r["limit"] is not None:
            rows.append([r["label"], money(r["limit"]), money(r["spent"]), f"{r['percent']:.0f}%"])
    if len(rows) == 1:
        rows.append(["No budgets set for this month", "-", "-", "-"])
    story.append(_table(rows, [60 * mm, 40 * mm, 40 * mm, 20 * mm]))

    comparison = extras["comparison"]
    if comparison:
        story += [Spacer(1, 8), Paragraph("Compared with previous month", styles["Heading2"]),
                  _table([["Measure", "Previous", "Change"],
                          ["Income", money(comparison["prev_income"]), money(comparison["income_change"])],
                          ["Expenses", money(comparison["prev_expense"]), money(comparison["expense_change"])],
                          ["Balance", money(comparison["prev_balance"]), money(comparison["balance_change"])]],
                         [60 * mm, 50 * mm, 50 * mm])]

    story += [Spacer(1, 8), Paragraph("Observations", styles["Heading2"])]
    for item in extras["observations"]:
        story.append(Paragraph(f"&bull; <b>{escape(item['title'])}</b>: {escape(item['message'].replace('₹', 'Rs. '))}",
                               styles["BodyText"]))
    story += [Spacer(1, 12), Paragraph(escape(DISCLAIMER), small)]
    doc.build(story)
    return buffer.getvalue()
