"""PDF bill with support for typed (custom) items."""
from io import BytesIO
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle


def generate_bill_pdf(invoice, items, cfg):
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18*mm, rightMargin=18*mm, topMargin=16*mm, bottomMargin=16*mm)
    st = getSampleStyleSheet()
    navy = colors.HexColor('#0b3d6b')
    story = [
        Paragraph(f"<b>{cfg.get('STORE_NAME', 'Optical Store')}</b>", st['Title']),
        Paragraph(f"{cfg.get('STORE_ADDRESS', '')}<br/>{cfg.get('STORE_PHONE', '')} &nbsp;|&nbsp; {cfg.get('STORE_EMAIL', '')}", st['Normal']),
        Spacer(1, 8*mm),
        Paragraph(f"<b>BILL</b> &nbsp; {invoice.invoice_number} &nbsp;&nbsp; Date: {invoice.invoice_date.strftime('%d %b %Y')}", st['Heading3']),
        Paragraph(f"<b>Customer:</b> {invoice.customer.name}<br/>Phone: {invoice.customer.phone or '-'}", st['Normal']),
        Spacer(1, 6*mm),
    ]
    rows = [['#', 'Item', 'Qty', 'Price (Rs.)', 'Amount (Rs.)']]
    for i, it in enumerate(items, 1):
        rows.append([i, Paragraph(it['description'], st['Normal']), it['quantity'],
                     f"{it['unit_price']:.2f}", f"{it['total']:.2f}"])
    t = Table(rows, colWidths=[10*mm, 82*mm, 15*mm, 30*mm, 35*mm], repeatRows=1)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), navy), ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (2, 0), (-1, -1), 'RIGHT'), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#cbd5e1')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f5f8fb')]),
    ]))
    story += [t, Spacer(1, 5*mm)]

    subtotal = sum(i['total'] for i in items)
    tot = [['Subtotal', f"{subtotal:.2f}"]]
    if invoice.discount:
        tot.append(['Discount', f"- {invoice.discount:.2f}"])
    if invoice.tax_rate:
        tot.append([f"Tax ({invoice.tax_rate:g}%)", f"{invoice.tax_amount:.2f}"])
    tot.append(['TOTAL', f"Rs. {invoice.total_amount:.2f}"])
    if invoice.balance_amount > 0:
        tot += [['Paid', f"{invoice.paid_amount:.2f}"], ['Balance due', f"{invoice.balance_amount:.2f}"]]
    tt = Table(tot, colWidths=[40*mm, 35*mm], hAlign='RIGHT')
    total_row = [r[0] for r in tot].index('TOTAL')
    tt.setStyle(TableStyle([
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('FONTNAME', (0, total_row), (-1, total_row), 'Helvetica-Bold'),
        ('LINEABOVE', (0, total_row), (-1, total_row), 0.8, navy),
    ]))
    story += [tt, Spacer(1, 10*mm)]
    if invoice.notes:
        story.append(Paragraph(f"<b>Notes:</b> {invoice.notes}", st['Normal']))
    story.append(Paragraph("<i>Thank you for shopping with us!</i>", st['Normal']))
    doc.build(story)
    return buf.getvalue()
