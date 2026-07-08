import glob, os, re

base = r"D:\SDK\HIK SDK"
pdf_files = glob.glob(os.path.join(base, "**", "*.pdf"), recursive=True)
target = [f for f in pdf_files if "ISAPI" in f and "球" in f and f.endswith(".pdf")]

if not target:
    print("PDF not found!")
    exit(1)

pdf_path = target[0]
print(f"Reading: {len(target[0])} char path")

import pdfplumber

keywords = [
    "DSS", "DayNight", "dayNight", "Daynight",
    "IRCut", "irCut", "ircut", "IR",
    "日夜", "慢快门", "滤镜", "ircutFilter",
    "Image/channels", "/DSS"
]

with pdfplumber.open(pdf_path) as pdf:
    print(f"Total pages: {len(pdf.pages)}")
    
    for page_num, page in enumerate(pdf.pages):
        text = page.extract_text()
        if not text:
            continue
        
        found = False
        for kw in keywords:
            if kw.lower() in text.lower():
                found = True
                break
        
        if found:
            print(f"\n{'='*80}")
            print(f"PAGE {page_num + 1}")
            print(f"{'='*80}")
            print(text[:3000])
            if len(text) > 3000:
                print(f"... [truncated, total {len(text)} chars]")
