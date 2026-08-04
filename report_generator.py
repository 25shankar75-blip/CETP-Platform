# report_generator.py
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
import io

def generate_pdf_report(project_data, results):
    """Generates an automated executive engineering proposal."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()
    elements = []
    
    elements.append(Paragraph(f"CETP Executive Summary: {project_data['project_name']}", styles['Title']))
    elements.append(Spacer(1, 12))
    
    elements.append(Paragraph(f"Location: {project_data['location']} | Scope: {project_data['scope']}", styles['Normal']))
    elements.append(Spacer(1, 12))
    
    data = [["Configuration", "Chiller (TR)", "TES (TRh)", "Annual OPEX"]]
    for key, val in results.items():
        data.append([key, f"{val['Capacity_TR']:,.0f}", f"{val['TES_TRh']:,.0f}", f"{val['Total_Opex']:,.2f}"])
        
    table = Table(data, colWidths=[120, 100, 100, 120])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#4F81BD")),
        ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('GRID', (0,0), (-1,-1), 1, colors.black)
    ]))
    
    elements.append(table)
    doc.build(elements)
    buffer.seek(0)
    return buffer