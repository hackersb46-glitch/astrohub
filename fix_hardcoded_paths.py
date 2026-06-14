import os
import re

workspace = r"C:\Users\admin\.openclaw\agents\dev-factory\astrohub"

files_to_fix = [
    os.path.join(workspace, "src", "main", "main.py"),
]

for filepath in files_to_fix:
    if not os.path.exists(filepath):
        print("File not found:", filepath)
        continue
    
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    
    if "D:\\py_app\\astro_hub" in content or "D:\\astro_py\\astro_hub" in content:
        print("Fixing:", filepath)
        
        if "APP_DIR = Path" not in content:
            if "from pathlib import Path" not in content:
                content = "from pathlib import Path\nAPP_DIR = Path(__file__).resolve().parent.parent\n\n" + content
            else:
                content = content.replace("from pathlib import Path", "from pathlib import Path\nAPP_DIR = Path(__file__).resolve().parent.parent")
        
        # 替换硬编码路径
        content = content.replace("D:\\py_app\\astro_hub\\logs", "str(APP_DIR / \"logs\")")
        content = content.replace("D:\\astro_py\\astro_hub\\data", "str(APP_DIR / \"data\")")
        
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        
        print("Fixed:", filepath)
    else:
        print("No hardcoded paths in:", filepath)

print("Done")
