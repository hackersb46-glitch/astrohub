"""读取ISAPI PDF中关键页面的完整内容"""
import PyPDF2
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

pdf_path = r'D:\SDK\HIK SDK\ISAPI开发指南\ISAPI开发指南_球型网络摄像机_DF球机w.pdf'

reader = PyPDF2.PdfReader(pdf_path)

# 读取关键页面
for page_num in [404, 405, 406, 407, 408, 409, 410, 411, 412, 413, 414, 415]:
    text = reader.pages[page_num].extract_text() or ''
    if text.strip():
        print(f'\n{"="*60}')
        print(f'PAGE {page_num + 1}')
        print(f'{"="*60}')
        print(text[:3000])
