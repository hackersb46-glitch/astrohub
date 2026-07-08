import glob, os

base = r"D:\SDK\HIK SDK"
pdf_files = glob.glob(os.path.join(base, "**", "*.pdf"), recursive=True)
target = [f for f in pdf_files if "ISAPI" in f and "球" in f and f.endswith(".pdf")]

if not target:
    with open("read_pdf_result.txt", "w", encoding="utf-8") as f:
        f.write("PDF not found!")
    exit(1)

pdf_path = target[0]

import pdfplumber

keywords = [
    "DSS", "DayNight", "dayNight", "ircutFilter", "ircut", "IRCut",
    "日夜", "慢快门", "滤镜", "ir_cut", "/DSS", "Image/channels"
]

results = []

with pdfplumber.open(pdf_path) as pdf:
    for page_num, page in enumerate(pdf.pages):
        text = page.extract_text()
        if not text:
            continue
        
        found_keywords = []
        for kw in keywords:
            if kw.lower() in text.lower():
                found_keywords.append(kw)
        
        if found_keywords:
            results.append({
                "page": page_num + 1,
                "keywords": found_keywords,
                "text": text
            })

with open("read_pdf_result.txt", "w", encoding="utf-8") as out:
    out.write(f"Found {len(results)} relevant pages\n\n")
    for r in results:
        out.write(f"\n{'='*80}\n")
        out.write(f"PAGE {r['page']} | Keywords: {', '.join(r['keywords'])}\n")
        out.write(f"{'='*80}\n")
        out.write(r["text"][:5000])
        out.write(f"\n...[total {len(r['text'])} chars]\n")

with open("read_pdf_result.txt", "r", encoding="utf-8") as f:
    content = f.read()
    print(content[:15000])
