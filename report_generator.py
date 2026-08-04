# report_generator.py
import io
import pandas as pd
from reportlab.lib.pagesizes import landscape, letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

def generate_pdf_report(proj_name: str, location: str, industry: str, proj_type: str, currency: str, comp_df: pd.DataFrame) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(letter), rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
    story = []
    
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('DocTitle', parent=styles['Heading1'], fontSize=18, leading=22, textColor=colors.HexColor('#1e3d59'), spaceAfter=4)
    subtitle_style = ParagraphStyle('DocSubTitle', parent=styles['Normal'], fontSize=10, leading=13, textColor=colors.HexColor('#438a5e'), spaceAfter=12)
    
    story.append(Paragraph(f"Cooling Energy Transition Platform (CETP) - {proj_name}", title_style))
    story.append(Paragraph(f"Location: {location} | Industry: {industry} | Scope: {proj_type} | Currency: {currency}", subtitle_style))
    story.append(Spacer(1, 6))
    
    table_data = [list(comp_df.columns)] + comp_df.values.tolist()
    t = Table(table_data, colWidths=[90, 60, 60, 60, 60, 60, 65, 75, 75, 75, 75, 60])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#1e3d59')),
        ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,0), 7.5),
        ('BOTTOMPADDING', (0,0), (-1,0), 5),
        ('BACKGROUND', (0,1), (-1,-1), colors.HexColor('#f8f9fa')),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#dee2e6')),
        ('FONTSIZE', (0,1), (-1,-1), 7)
    ]))
    
    story.append(t)
    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()