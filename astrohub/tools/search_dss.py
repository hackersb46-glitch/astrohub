"""搜索ISAPI PDF中DSS端点的GET/PUT定义"""
import PyPDF2
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

pdf_path = r'D:\SDK\HIK SDK\ISAPI开发指南\ISAPI开发指南_球型网络摄像机_DF球机w.pdf'

reader = PyPDF2.PdfReader(pdf_path)

# 搜索包含 /DSS 或 DSS 端点定义的页面
for i in range(400, 420):
    text = reader.pages[i].extract_text() or ''
    if '/DSS' in text or 'DSS' in text:
        print(f'\n{"="*60}')
        print(f'PAGE {i+1}')
        print(f'{"="*60}')
        # 找到DSS相关行
        lines = text.split('\n')
        for j, line in enumerate(lines):
            if 'DSS' in line or '/DSS' in line:
                start = max(0, j-5)
                end = min(len(lines), j+20)
                for k in range(start, end):
                    if lines[k].strip():
                        print(f'  {lines[k].strip()[:200]}')
                print('  ...')
