"""PDF generation engine for MedBalance documents.

Supports WeasyPrint HTML/CSS rendering with seamless fallback to ReportLab
when native GTK/Pango libraries are not present (e.g. Windows host environments).
Renders:
1. Drug Transfer Advice (DTA) vouchers with scannable QR code. (Never "Form 19").
2. Cold-Chain Consignment & Telemetry Logs.
3. Financial Inter-Facility Credit Memos.
"""

import base64
from datetime import date, datetime
import io
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
import jinja2
from PIL import Image
import qrcode

# ReportLab imports for pure-python PDF fallback
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage, KeepTogether, HRFlowable
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
jinja_env = jinja2.Environment(
    loader=jinja2.FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=jinja2.select_autoescape(["html", "xml"]),
)


def generate_qr_image_bytes(data: str) -> bytes:
    """Generate PNG bytes of a QR code encoding `data`."""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=5,
        border=2,
    )
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def generate_qr_code_base64(data: str) -> str:
    """Generate base64 encoded PNG for direct HTML inline embedding."""
    img_bytes = generate_qr_image_bytes(data)
    return base64.b64encode(img_bytes).decode("ascii")


def _is_near_expiry(expiry_val: Any, as_of_date: Optional[Any] = None) -> bool:
    """Return True if residual shelf life is < 90 days."""
    try:
        if isinstance(expiry_val, str):
            exp_date = datetime.strptime(expiry_val[:10], "%Y-%m-%d").date()
        elif isinstance(expiry_val, (date, datetime)):
            exp_date = expiry_val.date() if isinstance(expiry_val, datetime) else expiry_val
        else:
            return False

        if as_of_date is None:
            today_date = date.today()
        elif isinstance(as_of_date, str):
            today_date = datetime.strptime(as_of_date[:10], "%Y-%m-%d").date()
        elif isinstance(as_of_date, (date, datetime)):
            today_date = as_of_date.date() if isinstance(as_of_date, datetime) else as_of_date
        else:
            today_date = date.today()

        days = (exp_date - today_date).days
        return days < 90
    except Exception:
        return False


# =====================================================================
# HTML Template Rendering
# =====================================================================

def render_dta_html(data: Dict[str, Any]) -> str:
    """Render Drug Transfer Advice (DTA) HTML template."""
    qr_token = data.get("qr_token", "tok-default")
    qr_url = f"/scan/{qr_token}"
    qr_b64 = generate_qr_code_base64(qr_url)

    ctx = dict(data)
    ctx["qr_code_base64"] = qr_b64
    ctx["qr_url"] = qr_url
    ctx["is_near_expiry"] = _is_near_expiry(data.get("expiry_date"), data.get("date"))
    template = jinja_env.get_template("dta_voucher.html")
    return template.render(ctx)


def render_coldchain_html(data: Dict[str, Any]) -> str:
    """Render Cold-Chain Consignment Log HTML template."""
    template = jinja_env.get_template("coldchain_log.html")
    return template.render(data)


def render_credit_memo_html(data: Dict[str, Any]) -> str:
    """Render Financial Credit Memo HTML template."""
    template = jinja_env.get_template("credit_memo.html")
    return template.render(data)


# =====================================================================
# ReportLab Native Fallback Builders
# =====================================================================

def build_dta_pdf_reportlab(data: Dict[str, Any]) -> bytes:
    """Build official Drug Transfer Advice (DTA) voucher PDF using ReportLab."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=36,
        rightMargin=36,
        topMargin=36,
        bottomMargin=36,
    )
    styles = getSampleStyleSheet()

    # Custom styles
    title_style = ParagraphStyle(
        "DtaTitle",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=22,
        textColor=colors.HexColor("#0f766e"),
        spaceAfter=4,
    )
    subtitle_style = ParagraphStyle(
        "DtaSubtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#475569"),
        spaceAfter=14,
    )
    label_style = ParagraphStyle(
        "DtaLabel",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#64748b"),
    )
    val_style = ParagraphStyle(
        "DtaVal",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=10,
        leading=13,
        textColor=colors.HexColor("#0f172a"),
    )
    table_cell = ParagraphStyle(
        "TableCell",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8.5,
        leading=11,
    )
    table_cell_bold = ParagraphStyle(
        "TableCellBold",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8.5,
        leading=11,
    )
    table_cell_right = ParagraphStyle(
        "TableCellRight",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8.5,
        leading=11,
        alignment=TA_RIGHT,
    )
    footer_style = ParagraphStyle(
        "DtaFooter",
        parent=styles["Italic"],
        fontName="Helvetica-Oblique",
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#94a3b8"),
        alignment=TA_CENTER,
    )

    story = []

    # Title - strictly "Drug Transfer Advice" (Never Form 19)
    story.append(Paragraph("Drug Transfer Advice", title_style))
    story.append(Paragraph("Inter-Facility Redistribution Order &bull; MedBalance-Q Clinical Supply Network", subtitle_style))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#0f766e"), spaceAfter=12))

    # Metadata Grid Table
    order_id = data.get("order_id", "DTA/UNKNOWN")
    date_str = data.get("date", "2026-11-01")
    plan_id = data.get("plan_id", "PLAN-UNKNOWN")
    src_info = f"{data.get('source_facility_name', 'Source')} ({data.get('source_facility_id', 'H1')})"
    dst_info = f"{data.get('destination_facility_name', 'Dest')} ({data.get('destination_facility_id', 'H2')})"
    temp_req = data.get("temperature_requirement", "Ambient (15°C – 25°C)")
    veh_info = data.get("vehicle_info", "Standard Transport")

    meta_data = [
        [
            Paragraph("DTA VOUCHER NO", label_style),
            Paragraph(f"<b>{order_id}</b>", val_style),
            Paragraph("TRANSFERRING STORE (SOURCE)", label_style),
            Paragraph(src_info, val_style),
        ],
        [
            Paragraph("DATE OF ISSUE", label_style),
            Paragraph(date_str, val_style),
            Paragraph("RECEIVING STORE (DESTINATION)", label_style),
            Paragraph(dst_info, val_style),
        ],
        [
            Paragraph("OPTIMIZATION PLAN ID", label_style),
            Paragraph(plan_id, val_style),
            Paragraph("STORAGE & VEHICLE", label_style),
            Paragraph(f"{temp_req} &bull; {veh_info}", val_style),
        ],
    ]
    meta_table = Table(meta_data, colWidths=[100, 150, 120, 150])
    meta_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 14))

    # Drugs Table with Near-Expiry vs Normal Column
    is_near = _is_near_expiry(data.get("expiry_date"), data.get("date"))
    qty = data.get("quantity", 0)
    near_qty_str = f"<b>{qty}</b>" if is_near else "—"
    normal_qty_str = f"<b>{qty}</b>" if not is_near else "—"

    items_data = [
        [
            Paragraph("<b>#</b>", table_cell),
            Paragraph("<b>Drug Code</b>", table_cell),
            Paragraph("<b>Drug Description</b>", table_cell),
            Paragraph("<b>Batch No</b>", table_cell),
            Paragraph("<b>Expiry Date</b>", table_cell),
            Paragraph("<b>Near to Expiry<br/>(&lt;90 days)</b>", table_cell_right),
            Paragraph("<b>Normal<br/>(&ge;90 days)</b>", table_cell_right),
        ],
        [
            Paragraph("1", table_cell),
            Paragraph(f"<b>{data.get('drug_code', '')}</b>", table_cell),
            Paragraph(data.get("drug_name", ""), table_cell),
            Paragraph(f"<code>{data.get('batch_no', '')}</code>", table_cell),
            Paragraph(data.get("expiry_date", ""), table_cell),
            Paragraph(near_qty_str, table_cell_right),
            Paragraph(normal_qty_str, table_cell_right),
        ],
    ]
    items_table = Table(items_data, colWidths=[25, 80, 150, 85, 70, 60, 50])
    items_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f766e")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(items_table)
    story.append(Spacer(1, 14))

    # Clinical rationale narration if present
    narration = data.get("narration")
    if narration:
        rationale_p = [
            [Paragraph("<b>CLINICAL TRANSFER RATIONALE</b>", label_style)],
            [Paragraph(narration, val_style)],
        ]
        rat_table = Table(rationale_p, colWidths=[520])
        rat_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f0fdfa")),
            ("LINELEFT", (0, 0), (0, -1), 3.0, colors.HexColor("#0f766e")),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#ccfbf1")),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.append(rat_table)
        story.append(Spacer(1, 14))

    # QR Code & Audit section
    qr_token = data.get("qr_token", "tok-default")
    qr_url = f"/scan/{qr_token}"
    qr_bytes = generate_qr_image_bytes(qr_url)
    qr_img = RLImage(io.BytesIO(qr_bytes), width=85, height=85)

    approver = data.get("approver_name", "Dr. Ramesh (District Drug Officer)")
    approved_at = data.get("approved_at", "2026-11-01 08:45:00 IST")
    eta = data.get("eta", "2026-11-01 11:30 AM")
    audit_hash = data.get("audit_hash", "0" * 64)

    audit_cell_text = [
        Paragraph("APPROVING AUTHORITY & AUDIT RECORD", label_style),
        Paragraph(f"<b>{approver}</b>", val_style),
        Paragraph(f"Approved: {approved_at} &bull; ETA: {eta}", val_style),
        Spacer(1, 4),
        Paragraph("CRYPTOGRAPHIC AUDIT CHAIN HASH", label_style),
        Paragraph(f"<font face='Courier' size='7'>{audit_hash}</font>", val_style),
    ]

    qr_cell = [
        qr_img,
        Paragraph(f"<font face='Courier' size='7'>{qr_token}</font>", footer_style),
    ]

    audit_table = Table([[audit_cell_text, qr_cell]], colWidths=[420, 100])
    audit_table.setStyle(TableStyle([
        ("LINEABOVE", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(audit_table)
    story.append(Spacer(1, 20))

    # Footer
    story.append(Paragraph("Synthetic demo data &bull; MedBalance-Q Algorithmic Drug Rebalancing Platform", footer_style))

    doc.build(story)
    return buf.getvalue()


def build_coldchain_pdf_reportlab(data: Dict[str, Any]) -> bytes:
    """Build Cold-Chain Consignment Log PDF using ReportLab."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=36,
        rightMargin=36,
        topMargin=36,
        bottomMargin=36,
    )
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "CcTitle",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=17,
        leading=21,
        textColor=colors.HexColor("#0284c7"),
        spaceAfter=3,
    )
    subtitle_style = ParagraphStyle(
        "CcSubtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#475569"),
        spaceAfter=12,
    )
    val_style = ParagraphStyle("CcVal", parent=styles["Normal"], fontName="Helvetica", fontSize=9.5, leading=13)
    val_bold = ParagraphStyle("CcValBold", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=9.5, leading=13)
    card_label = ParagraphStyle("CcCardLabel", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=8, alignment=TA_CENTER, textColor=colors.HexColor("#64748b"))
    card_val = ParagraphStyle("CcCardVal", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=13, alignment=TA_CENTER, textColor=colors.HexColor("#0284c7"))
    footer_style = ParagraphStyle("CcFooter", parent=styles["Italic"], fontName="Helvetica-Oblique", fontSize=8, alignment=TA_CENTER, textColor=colors.HexColor("#94a3b8"))

    story = []
    story.append(Paragraph("Cold-Chain Consignment & Telemetry Log", title_style))
    story.append(Paragraph("Continuous IoT Thermal Compliance Record &bull; Standard 2°C – 8°C Protocol", subtitle_style))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#0284c7"), spaceAfter=10))

    order_id = data.get("order_id", "DTA/UNKNOWN")
    drug = f"{data.get('drug_name', 'Insulin')} ({data.get('drug_code', 'INS-REG')}) &bull; Qty: {data.get('quantity', 28)} units"
    route = f"{data.get('source_facility_id', 'H1')} &rarr; {data.get('destination_facility_id', 'H2')}"
    veh = data.get("vehicle_id", "KA-01-EA-1001")
    dev = data.get("device_id", "DEV-H1-01")

    meta_table = Table([
        [Paragraph(f"<b>Transfer Order:</b> {order_id}", val_style), Paragraph(f"<b>Route:</b> {route}", val_style)],
        [Paragraph(f"<b>Drug:</b> {drug}", val_style), Paragraph(f"<b>Vehicle:</b> {veh}", val_style)],
        [Paragraph(f"<b>Batch:</b> {data.get('batch_no', 'N/A')}", val_style), Paragraph(f"<b>Sensor Device:</b> {dev}", val_style)],
    ], colWidths=[260, 260])
    meta_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f0f9ff")),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#bae6fd")),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 10))

    # Summary Cards Table
    min_t = data.get("min_temp", 3.4)
    max_t = data.get("max_temp", 5.8)
    excursions = data.get("excursions", 0)
    status_str = "COMPLIANT" if excursions == 0 else "EXCURSION"
    status_color = colors.HexColor("#16a34a") if excursions == 0 else colors.HexColor("#dc2626")

    cards_data = [
        [Paragraph("ALLOWED RANGE", card_label), Paragraph("MIN OBSERVED", card_label), Paragraph("MAX OBSERVED", card_label), Paragraph("THERMAL STATUS", card_label)],
        [Paragraph("2.0 – 8.0 °C", card_val), Paragraph(f"{min_t} °C", card_val), Paragraph(f"{max_t} °C", card_val), Paragraph(f"<font color='{status_color.hexval()}'>{status_str}</font>", card_val)],
    ]
    cards_table = Table(cards_data, colWidths=[130, 130, 130, 130])
    cards_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(cards_table)
    story.append(Spacer(1, 12))

    # Telemetry Traces Table
    traces = data.get("traces", [
        {"timestamp": "2026-11-01 08:30:00", "device_id": dev, "temperature_c": 4.1, "battery_pct": 98, "signal_dbm": -68, "status": "NORMAL"},
        {"timestamp": "2026-11-01 08:45:00", "device_id": dev, "temperature_c": 4.3, "battery_pct": 97, "signal_dbm": -70, "status": "NORMAL"},
        {"timestamp": "2026-11-01 09:00:00", "device_id": dev, "temperature_c": 4.8, "battery_pct": 96, "signal_dbm": -69, "status": "NORMAL"},
        {"timestamp": "2026-11-01 09:15:00", "device_id": dev, "temperature_c": 5.2, "battery_pct": 96, "signal_dbm": -72, "status": "NORMAL"},
        {"timestamp": "2026-11-01 09:30:00", "device_id": dev, "temperature_c": 4.6, "battery_pct": 95, "signal_dbm": -71, "status": "NORMAL"},
        {"timestamp": "2026-11-01 09:45:00", "device_id": dev, "temperature_c": 3.9, "battery_pct": 94, "signal_dbm": -69, "status": "NORMAL"},
        {"timestamp": "2026-11-01 10:00:00", "device_id": dev, "temperature_c": 4.2, "battery_pct": 94, "signal_dbm": -70, "status": "NORMAL"},
    ])

    trace_rows = [
        [
            Paragraph("<b>Timestamp</b>", val_style),
            Paragraph("<b>Device ID</b>", val_style),
            Paragraph("<b>Temperature</b>", val_style),
            Paragraph("<b>Battery</b>", val_style),
            Paragraph("<b>Signal</b>", val_style),
            Paragraph("<b>Integrity</b>", val_style),
        ]
    ]
    for tr in traces:
        trace_rows.append([
            Paragraph(str(tr.get("timestamp", "")), val_style),
            Paragraph(f"<code>{tr.get('device_id', dev)}</code>", val_style),
            Paragraph(f"<b>{tr.get('temperature_c', '')} °C</b>", val_style),
            Paragraph(f"{tr.get('battery_pct', '')}%", val_style),
            Paragraph(f"{tr.get('signal_dbm', '')} dBm", val_style),
            Paragraph("<font color='#16a34a'><b>NORMAL</b></font>", val_style),
        ])

    trace_table = Table(trace_rows, colWidths=[140, 90, 80, 60, 70, 80])
    trace_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0284c7")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(trace_table)
    story.append(Spacer(1, 15))

    # Audit Sign-off
    verified_by = data.get("verified_by", "District Cold-Chain Logistics Officer")
    audit_hash = data.get("audit_hash", "0" * 64)
    story.append(Table([
        [Paragraph(f"<b>Verification Authority:</b> {verified_by}", val_style),
         Paragraph(f"<b>Audit Hash:</b> <font face='Courier' size='7'>{audit_hash[:32]}...</font>", val_style)]
    ], colWidths=[260, 260]))

    story.append(Spacer(1, 20))
    story.append(Paragraph("Synthetic demo data &bull; MedBalance-Q Continuous Cold-Chain Telemetry System", footer_style))

    doc.build(story)
    return buf.getvalue()


def build_credit_memo_pdf_reportlab(data: Dict[str, Any]) -> bytes:
    """Build Financial Credit Memo PDF using ReportLab."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=36,
        rightMargin=36,
        topMargin=36,
        bottomMargin=36,
    )
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "CmTitle",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=22,
        textColor=colors.HexColor("#b45309"),
        spaceAfter=4,
    )
    subtitle_style = ParagraphStyle(
        "CmSubtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#475569"),
        spaceAfter=14,
    )
    label_style = ParagraphStyle("CmLabel", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=8, textColor=colors.HexColor("#64748b"))
    val_style = ParagraphStyle("CmVal", parent=styles["Normal"], fontName="Helvetica", fontSize=9.5, leading=13)
    table_cell = ParagraphStyle("CmCell", parent=styles["Normal"], fontName="Helvetica", fontSize=9, leading=12)
    table_cell_right = ParagraphStyle("CmCellRight", parent=styles["Normal"], fontName="Helvetica", fontSize=9, leading=12, alignment=TA_RIGHT)
    memo_p_style = ParagraphStyle("CmMemoP", parent=styles["Normal"], fontName="Helvetica", fontSize=10, leading=15, textColor=colors.HexColor("#78350f"))
    footer_style = ParagraphStyle("CmFooter", parent=styles["Italic"], fontName="Helvetica-Oblique", fontSize=8, alignment=TA_CENTER, textColor=colors.HexColor("#94a3b8"))

    story = []
    story.append(Paragraph("Inter-Facility Credit Memo", title_style))
    story.append(Paragraph("District Health Society &bull; Financial Drug Reallocation Credit Note", subtitle_style))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#b45309"), spaceAfter=12))

    memo_id = data.get("memo_id", "CM/BLR-U/2026/000042")
    order_id = data.get("order_id", "DTA/BLR-U/2026/000101")
    issue_date = data.get("issue_date", "2026-11-01")
    creditor = f"{data.get('creditor_facility_name', 'District Hospital 1')} ({data.get('creditor_facility_id', 'H1')})"
    debtor = f"{data.get('debtor_facility_name', 'District Hospital 2')} ({data.get('debtor_facility_id', 'H2')})"
    auth_by = data.get("authorized_by", "District Financial Comptroller")

    meta_table = Table([
        [Paragraph("MEMO REFERENCE", label_style), Paragraph(f"<b>{memo_id}</b>", val_style), Paragraph("CREDITOR (DONOR STORE)", label_style), Paragraph(creditor, val_style)],
        [Paragraph("TRANSFER DTA", label_style), Paragraph(order_id, val_style), Paragraph("DEBTOR (RECIPIENT STORE)", label_style), Paragraph(debtor, val_style)],
        [Paragraph("ISSUE DATE", label_style), Paragraph(issue_date, val_style), Paragraph("AUTHORIZING AUTHORITY", label_style), Paragraph(auth_by, val_style)],
    ], colWidths=[100, 150, 130, 140])
    meta_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 14))

    # Financial Items Table
    qty = data.get("quantity", 28)
    unit_cost = float(data.get("unit_cost_inr", 145.50))
    total_val = float(data.get("total_credit_inr", qty * unit_cost))

    items = [
        [
            Paragraph("<b>Drug Code</b>", table_cell),
            Paragraph("<b>Description</b>", table_cell),
            Paragraph("<b>Quantity Transferred</b>", table_cell_right),
            Paragraph("<b>Unit Price (INR)</b>", table_cell_right),
            Paragraph("<b>Total Credit Value (INR)</b>", table_cell_right),
        ],
        [
            Paragraph(f"<b>{data.get('drug_code', 'INS-REG')}</b>", table_cell),
            Paragraph(data.get("drug_name", "Insulin Regular 40IU/ml"), table_cell),
            Paragraph(f"{qty} units", table_cell_right),
            Paragraph(f"Rs. {unit_cost:.2f}", table_cell_right),
            Paragraph(f"<b>Rs. {total_val:.2f}</b>", table_cell_right),
        ],
    ]
    items_table = Table(items, colWidths=[80, 160, 100, 90, 90])
    items_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#b45309")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(items_table)
    story.append(Spacer(1, 14))

    # Memo text paragraph
    memo_text = data.get("memo_text", "")
    memo_box = Table([
        [Paragraph("<b>OFFICIAL FINANCIAL RECONCILIATION RECOMMENDATION</b>", label_style)],
        [Paragraph(memo_text, memo_p_style)],
    ], colWidths=[520])
    memo_box.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fffbeb")),
        ("LINELEFT", (0, 0), (0, -1), 3.0, colors.HexColor("#b45309")),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#fef3c7")),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(memo_box)
    story.append(Spacer(1, 25))

    # Signatures
    sig_table = Table([
        [Paragraph("<br/><br/>___________________________________<br/><b>Transferring Medical Officer</b><br/>" + creditor, val_style),
         Paragraph("<br/><br/>___________________________________<br/><b>" + auth_by + "</b><br/>District Health Society", val_style)]
    ], colWidths=[260, 260])
    story.append(sig_table)

    story.append(Spacer(1, 20))
    story.append(Paragraph("Synthetic demo data &bull; District Health Accounting & Reallocation System", footer_style))

    doc.build(story)
    return buf.getvalue()


# =====================================================================
# Top-Level Document Exporters (WeasyPrint with ReportLab fallback)
# =====================================================================

def generate_dta_pdf(data: Dict[str, Any]) -> bytes:
    """Generate DTA voucher PDF using WeasyPrint with ReportLab fallback."""
    # Attempt WeasyPrint first
    try:
        import weasyprint
        html_str = render_dta_html(data)
        return weasyprint.HTML(string=html_str).write_pdf()
    except Exception as exc:
        logger.info(f"WeasyPrint unavailable ({exc}); falling back to ReportLab DTA builder")
        return build_dta_pdf_reportlab(data)


def generate_coldchain_pdf(data: Dict[str, Any]) -> bytes:
    """Generate Cold-Chain Consignment Log PDF using WeasyPrint with ReportLab fallback."""
    try:
        import weasyprint
        html_str = render_coldchain_html(data)
        return weasyprint.HTML(string=html_str).write_pdf()
    except Exception as exc:
        logger.info(f"WeasyPrint unavailable ({exc}); falling back to ReportLab Cold-Chain builder")
        return build_coldchain_pdf_reportlab(data)


def generate_credit_memo_pdf(data: Dict[str, Any]) -> bytes:
    """Generate Credit Memo PDF using WeasyPrint with ReportLab fallback."""
    try:
        import weasyprint
        html_str = render_credit_memo_html(data)
        return weasyprint.HTML(string=html_str).write_pdf()
    except Exception as exc:
        logger.info(f"WeasyPrint unavailable ({exc}); falling back to ReportLab Credit Memo builder")
        return build_credit_memo_pdf_reportlab(data)

