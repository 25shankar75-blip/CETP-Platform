"""
CETP Digital Twin - Report Generator
File: report_generator.py
"""
import io
from financial_engine import format_currency

def generate_pdf_report(p_name, loc, ind, scope, curr, df_comp, load, tar, res):
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib import colors
        
        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=letter)
        styles = getSampleStyleSheet()
        story = []
        
        story.append(Paragraph(f"<b>CETP Digital Twin Report: {p_name}</b>", styles['Heading1']))
        story.append(Paragraph(f"Location: {loc} | Scope: {scope} | Industry: {ind}", styles['Normal']))
        story.append(Spacer(1, 12))
        
        data = [
            ["Metric", "Conventional Baseline", "PCM TES Optimum", "Stratified TES Optimum"],
            ["TES Capacity", "0 TRh", f"{res['p']['tes_trh']:.0f} TRh", f"{res['s']['tes_trh']:.0f} TRh"],
            ["Total CAPEX", format_currency(res['c']['capex'], curr), format_currency(res['p']['capex'], curr), format_currency(res['s']['capex'], curr)],
            ["Annual OPEX", format_currency(res['c']['opex'], curr), format_currency(res['p']['opex'], curr), format_currency(res['s']['opex'], curr)],
            ["Annual Savings", "-", format_currency(res['p']['sav'], curr), format_currency(res['s']['sav'], curr)],
            ["Simple Payback", "-", f"{res['p']['pb']:.2f} Years", f"{res['s']['pb']:.2f} Years"]
        ]
        
        t = Table(data)
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.darkblue),
            ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
            ('GRID', (0,0), (-1,-1), 1, colors.black),
            ('ALIGN', (0,0), (-1,-1), 'CENTER')
        ]))
        story.append(t)
        doc.build(story)
        buf.seek(0)
        return buf.getvalue()
    except ImportError:
        return b"PDF Generation requires 'reportlab' to be installed."

def generate_word_report(p_name, loc, ind, scope, curr, df_comp, load, tar, res):
    try:
        from docx import Document
        doc = Document()
        doc.add_heading(f'CETP Report: {p_name}', 0)
        buf = io.BytesIO()
        doc.save(buf)
        buf.seek(0)
        return buf.getvalue()
    except ImportError:
        return b"Word Generation requires 'python-docx' to be installed."