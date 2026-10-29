import pdfplumber
import sys

caminho = sys.argv[1] if len(sys.argv) > 1 else "samples/fatura.pdf"

with pdfplumber.open(caminho) as pdf:
    print(f"Páginas: {len(pdf.pages)}")
    page = pdf.pages[3] #pagina 4
    print("===== PÁGINA 4 =====")
    print(page.extract_text())