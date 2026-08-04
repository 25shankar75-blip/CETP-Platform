# report_generator.py
import io
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from financial_engine import format_currency

def generate_pdf_report(project_data, results):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=30, leftMargin=30)
    elements = []
    curr = project_data['currency']
    
    elements.append(Paragraph(f"<b>CETP Executive Digital Twin Output: {project_data['project_name']}</b>", getSampleStyleSheet()['Title']))
    elements.append(Spacer(1, 10))
    
    matrix = [["Metric", "Conventional", "PCM TES", "Stratified TES"]]
    matrix.append(["Base Chiller (TR)", f"{results['Conventional N+1']['Base_TR']:,.0f}", f"{results['PCM TES']['Base_TR']:,.0f}", f"{results['Stratified TES']['Base_TR']:,.0f}"])
    matrix.append(["TES Storage (TRh)", "0", f"{results['PCM TES']['TES_TRh']:,.0f}", f"{results['Stratified TES']['TES_TRh']:,.0f}"])
    matrix.append(["Substation (kVA)", f"{results['Conventional N+1']['Sub_kVA']:,.0f}", f"{results['PCM TES']['Sub_kVA']:,.0f}", f"{results['Stratified TES']['Sub_kVA']:,.0f}"])
    matrix.append(["Total CAPEX", format_currency(results['Conventional N+1']['CAPEX']['Total_CAPEX'], curr), format_currency(results['PCM TES']['CAPEX']['Total_CAPEX'], curr), format_currency(results['Stratified TES']['CAPEX']['Total_CAPEX'], curr)])
    matrix.append(["Total OPEX", format_currency(results['Conventional N+1']['Tot_OPEX'], curr), format_currency(results['PCM TES']['Tot_OPEX'], curr), format_currency(results['Stratified TES']['Tot_OPEX'], curr)])
    matrix.append(["Simple Payback", "Baseline", f"{results['PCM TES'].get('Payback',0):.2f} Yrs", f"{results['Stratified TES'].get('Payback',0):.2f} Yrs"])

    t = Table(matrix, colWidths=[130, 110, 110, 110])
    t.setStyle(TableStyle([('BACKGROUND', (0,0), (-1,0), colors.HexColor('#1E3A8A')),('TEXTCOLOR', (0,0), (-1,0), colors.white),('GRID', (0,0), (-1,-1), 0.5, colors.grey)]))
    elements.append(t)
    
    doc.build(elements)
    buffer.seek(0)
    return buffer