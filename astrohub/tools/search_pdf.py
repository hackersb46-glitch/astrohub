"""搜索ISAPI开发指南PDF中的DSS和IrcutFilter相关内容"""
import pdfplumber
import sys

pdf_path = r'D:\SDK\HIK SDK\ISAPI开发指南\ISAPI开发指南_球型网络摄像机_DF球机w.pdf'

keywords = ['DSS', 'IrcutFilter', 'dayNight', '慢快门', '日夜', 'IR滤镜', 'Ircut']

with pdfplumber.open(pdf_path) as pdf:
    total = len(pdf.pages)
    print(f'Total pages: {total}')
    
    for i, page in enumerate(pdf.pages):
        if i % 50 == 0:
            print(f'Scanning page {i+1}/{total}...', file=sys.stderr)
        text = page.extract_text() or ''
        for kw in keywords:
            if kw in text:
                print(f'\n=== Page {i+1}: keyword "{kw}" ===')
                # 打印包含关键词的行及上下文
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
                break  # 每页只打印第一个匹配的关键词
