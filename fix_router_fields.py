# Fix router.py ISAPI field name mismatch
# 实际 ISAPI 字段: IrcutFilterType (不是 irCutFilter)
# dayNightMode 字段在 ISAPI 中不存在

import os

router_path = os.path.join(os.path.dirname(__file__), 'astrohub', 'src', 'api', 'router.py')

with open(router_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

output = []
i = 0
while i < len(lines):
    line = lines[i]
    
    # Fix 1: GET parsing - 将 dayNightMode/irCutFilter 解析改为 IrcutFilterType
    if '            if tag == "dayNightMode":' in line:
        # Skip dayNightMode block (2 lines)
        i += 1  # skip day_night = ...
        # Now at elif tag == "irCutFilter"
        if i < len(lines) and 'elif tag == "irCutFilter"' in lines[i]:
            lines[i] = lines[i].replace('elif', 'if').replace('irCutFilter', 'IrcutFilterType')
        continue
    
    # Fix 2: PUT regex - 删除 dayNightMode regex，修改 irCutFilter regex
    if '        if day_night:' in line and i+1 < len(lines) and 'dayNightMode' in lines[i+1]:
        # Skip entire day_night block (5 lines)
        i += 5
        continue
    
    if "r'(<irCutFilter>)[^<]*(</irCutFilter>)'" in line:
        line = line.replace('irCutFilter', 'IrcutFilterType')
    
    output.append(line)
    i += 1

with open(router_path, 'w', encoding='utf-8') as f:
    f.writelines(output)

print(f'Fixed {router_path}')
print(f'Original lines: {len(lines)}, New lines: {len(output)}')
