"""快速搜索ISAPI PDF - 用PyPDF2extractText"""
import PyPDF2
import sys

pdf_path = r'D:\SDK\HIK SDK\ISAPI开发指南\ISAPI开发指南_球型网络摄像机_DF球机w.pdf'

keywords = ['DSS', 'IrcutFilter', 'dayNight']

reader = PyPDF2.PdfReader(pdf_path)
total = len(reader.pages)
print(f'Total pages: {total}')

for i in range(total):
    if i % 100 == 0:
        print(f'Scanning page {i+1}/{total}...', file=sys.stderr)
    text = reader.pages[i].extract_text() or ''
    for kw in keywords:
        if kw in text:
            print(f'\n=== Page {i+1}: keyword "{kw}" ===')
            lines = text.split('\n')
            for j, line in enumerate(lines):
                if kw in line:
                    start = max(0, j-3)
                    end = min(len(lines), j+15)
                    for k in range(start, end):
                        if lines[k].strip():
                            print(f'  {lines[k].strip()[:200]}')
                    print('  ...')
                    break
            break
