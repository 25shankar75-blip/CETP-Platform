import io
import matplotlib.pyplot as plt

def generate_pdf_report(project_data, results):
    return b"%PDF-1.4 Mock PDF Output - Full reportlab payload goes here"

def generate_docx_report(project_data, results):
    return b"PK\x03\x04 Mock DOCX Output - Full python-docx payload goes here"

def plot_dispatch_overlay(load_profile, tariff_profile, tes_schedule):
    fig, ax1 = plt.subplots(figsize=(10, 5))
    ax2 = ax1.twinx()
    
    hours = list(range(24))
    ax1.plot(hours, load_profile, 'b-', linewidth=2, label='Cooling Load (TR)')
    ax2.step(hours, tariff_profile, 'r-', where='post', alpha=0.6, label='Tariff / DG Cost')
    
    for i, s in enumerate(tes_schedule):
        if s['charge']: ax1.axvspan(i, i+1, color='blue', alpha=0.15)
        if s['discharge']: ax1.axvspan(i, i+1, color='green', alpha=0.15)
        
    ax1.set_xlabel("Hour of Day")
    ax1.set_ylabel("Cooling Load (TR)", color='b')
    ax2.set_ylabel("Tariff/Cost", color='r')
    plt.title("24-Hour Dispatch & Cost Overlay")
    plt.grid(True, alpha=0.3)
    
    buf = io.BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight')
    buf.seek(0)
    plt.close()
    return buf