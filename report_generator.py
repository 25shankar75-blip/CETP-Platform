# report_generator.py
import io
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from reportlab.lib.pagesizes import landscape, letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

def generate_graphs(load_24, tar_24, res_p, res_s, sym):
    graphs = {}
    hrs = np.arange(24)
    
    fig, ax1 = plt.subplots(figsize=(8, 4))
    ax2 = ax1.twinx()
    ax1.bar(hrs, load_24, color='#1e3d59', label='Cooling Load (TR)', alpha=0.7)
    ax2.plot(hrs, tar_24, color='#ff6f69', marker='o', label=f'Tariff ({sym})', linewidth=2)
    ax1.set_xlabel('Hour of Day')
    ax1.set_ylabel('Cooling Load (TR)')
    ax2.set_ylabel(f'Tariff ({sym})')
    plt.title('24-Hour Cooling Load & Tariff Profile')
    fig.legend(loc='upper right', bbox_to_anchor=(0.9, 0.9))
    buf1 = io.BytesIO()
    plt.savefig(buf1, format='png', bbox_inches='tight', dpi=150)
    buf1.seek(0)
    graphs['load'] = buf1
    plt.close(fig)

    fig, ax1 = plt.subplots(figsize=(8, 4))
    ax2 = ax1.twinx()
    ax1.plot(hrs, load_24, color='black', linestyle='--', label='Required Load', linewidth=2)
    ax1.bar(hrs, res_p['data']['kw_comp'][:24]/0.58, color='#1e3d59', label='Base Chiller Generation', alpha=0.7)
    ax1.bar(hrs, res_p['data']['charge'][:24], color='#438a5e', label='TES Charging (TR)')
    ax1.bar(hrs, res_p['data']['discharge'][:24], color='#ffc13b', label='TES Discharging (TR)')
    ax2.plot(hrs, tar_24, color='#ff6f69', marker='x')
    ax1.set_xlabel('Hour of Day')
    ax1.set_ylabel('Operating Capacity (TR)')
    plt.title('PCM TES Operational Dispatch vs Tariff')
    fig.legend(loc='upper right', bbox_to_anchor=(0.9, 0.9))
    buf2 = io.BytesIO()
    plt.savefig(buf2, format='png', bbox_inches='tight', dpi=150)
    buf2.seek(0)
    graphs['pcm'] = buf2
    plt.close(fig)

    return graphs

def generate_pdf_report(proj_name: str, location: str, industry: str, proj_type: str, currency: str, comp_df: pd.DataFrame, load_24: list, tar_24: list, res: dict, sym: str) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(letter), rightMargin=20, leftMargin=20, topMargin=20, bottomMargin=20)
    story = []
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('DocTitle', parent=styles['Heading1'], fontSize=16, leading=20, textColor=colors.HexColor('#1e3d59'), spaceAfter=4)
    
    story.append(Paragraph(f"Cooling Energy Transition Platform (CETP) - {proj_name}", title_style))
    story.append(Paragraph(f"Location: {location} | Scope: {proj_type} | Currency: {currency}"))
    story.append(Spacer(1, 10))
    
    t = Table([list(comp_df.columns)] + comp_df.values.tolist(), colWidths=[180, 140, 140, 140])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#1e3d59')), ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'), ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,-1), 7), ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#dee2e6')),
    ]))
    story.append(t)
    story.append(Spacer(1, 15))
    
    graphs = generate_graphs(load_24, tar_24, res['p'], res['s'], sym)
    story.append(Image(graphs['load'], width=400, height=200))
    story.append(Spacer(1, 10))
    story.append(Image(graphs['pcm'], width=400, height=200))
    
    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()

def generate_word_report(proj_name: str, location: str, industry: str, proj_type: str, currency: str, comp_df: pd.DataFrame, load_24: list, tar_24: list, res: dict, sym: str) -> bytes:
    try:
        import docx
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.shared import Inches
    except ImportError: return None
        
    doc = docx.Document()
    section = doc.sections[0]
    section.page_width, section.page_height = section.page_height, section.page_width
    
    title = doc.add_heading(f'CETP Executive Proposal: {proj_name}', level=1)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.add_paragraph(f"Location: {location} | Scope: {proj_type} | Currency: {currency}")
    
    table = doc.add_table(rows=1, cols=len(comp_df.columns))
    table.style = 'Table Grid'
    hdr_cells = table.rows[0].cells
    for i, col in enumerate(comp_df.columns): hdr_cells[i].text = col
    for index, row in comp_df.iterrows():
        row_cells = table.add_row().cells
        for i, value in enumerate(row): row_cells[i].text = str(value)
            
    doc.add_heading('Equipment Energy & Cost Breakdown', level=2)
    eq_table = doc.add_table(rows=1, cols=7)
    eq_table.style = 'Table Grid'
    eq_hdrs = ["Equipment", "Conv. kWh", f"Conv. {sym}", "PCM kWh", f"PCM {sym}", "Strat kWh", f"Strat {sym}"]
    for i, col in enumerate(eq_hdrs): eq_table.rows[0].cells[i].text = col
    
    eq_list = ["Base Chiller", "Brine Chiller", "CHW Pumps", "CW Pumps", "CT Fans"]
    for eq in eq_list:
        row = eq_table.add_row().cells
        row[0].text = eq
        row[1].text = f"{res['c']['data']['breakdown'][eq]['kwh']:,.0f}"
        row[2].text = f"{res['c']['data']['breakdown'][eq]['cost']:,.0f}"
        row[3].text = f"{res['p']['data']['breakdown'][eq]['kwh']:,.0f}"
        row[4].text = f"{res['p']['data']['breakdown'][eq]['cost']:,.0f}"
        row[5].text = f"{res['s']['data']['breakdown'][eq]['kwh']:,.0f}"
        row[6].text = f"{res['s']['data']['breakdown'][eq]['cost']:,.0f}"

    graphs = generate_graphs(load_24, tar_24, res['p'], res['s'], sym)
    doc.add_heading('Operational Dispatch Visualizations', level=2)
    doc.add_picture(graphs['load'], width=Inches(6.0))
    doc.add_picture(graphs['pcm'], width=Inches(6.0))
    
    buffer = io.BytesIO()
    doc.save(buffer)
    return buffer.getvalue()