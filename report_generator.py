"""
Cooling Energy Transition Platform (CETP) - Executive PDF & Word Export Engine
File: report_generator.py
"""
import io
from financial_engine import format_currency

def generate_pdf_report(p_name, loc, scope, curr, res):
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib import colors
        
        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=letter)
        styles = getSampleStyleSheet()
        story = []
        
        safe_name = p_name if p_name else "Unnamed Project"
        safe_loc = loc if loc else "Unknown Location"
        
        story.append(Paragraph(f"<b>CETP Digital Twin Report: {safe_name}</b>", styles['Heading1']))
        story.append(Paragraph(f"Location: {safe_loc} | Scope: {scope}", styles['Normal']))
        story.append(Spacer(1, 12))
        
        data = [
            ["Metric", "Conventional Baseline", "PCM TES Optimum", "Stratified TES Optimum"],
            ["Status", "BASELINE", res['p']['status'], res['s']['status']],
            ["TES Capacity", "0 TRh", f"{res['p']['tes_trh']:.0f} TRh", f"{res['s']['tes_trh']:.0f} TRh"],
            ["Total CAPEX", format_currency(res['c']['capex'], curr), format_currency(res['p']['cap']['Total CAPEX'], curr), format_currency(res['s']['cap']['Total CAPEX'], curr)],
            ["Annual OPEX", format_currency(res['c']['opex'], curr), format_currency(res['p']['opex'], curr), format_currency(res['s']['opex'], curr)],
            ["Simple Payback", "-", f"{res['p']['payback']:.2f} Years", f"{res['s']['payback']:.2f} Years"]
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
    except Exception:
        return b"PDF Generation failed. Ensure 'reportlab' is installed on the deployment server."

def generate_word_report(p_name, loc, scope, curr, res):
    try:
        from docx import Document
        doc = Document()
        safe_name = p_name if p_name else "Unnamed Project"
        doc.add_heading(f'CETP Report: {safe_name}', 0)
        buf = io.BytesIO()
        doc.save(buf)
        buf.seek(0)
        return buf.getvalue()
    except Exception:
        return b"Word Generation failed. Ensure 'python-docx' is installed on the deployment server."