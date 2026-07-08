"""Find IR cut switch and dayNight switch in console.html"""
with open('src/web/includes/console.html', 'r', encoding='utf-8') as f:
    lines = f.readlines()

print('=== IR cut switch (irCutSwitch) ===')
for i, line in enumerate(lines):
    if 'irCutSwitch' in line or 'irCut' in line.lower() and 'switch' in line.lower():
        print(f'{i+1}: {line.rstrip()[:120]}')

print('\n=== dayNightSwitch ===')
for i, line in enumerate(lines):
    if 'dayNightSwitch' in line or 'dayNight' in line and ('Switch' in line or 'switch' in line):
        print(f'{i+1}: {line.rstrip()[:120]}')

print('\n=== setIRCutFilter / setDayNightMode ===')
for i, line in enumerate(lines):
    if 'setIRCutFilter' in line or 'setDayNightMode' in line:
        print(f'{i+1}: {line.rstrip()[:120]}')

print('\n=== loadFilterStatus ===')
for i, line in enumerate(lines):
    if 'loadFilterStatus' in line:
        print(f'{i+1}: {line.rstrip()[:120]}')

print('\n=== moveVideoTo ===')
for i, line in enumerate(lines):
    if 'moveVideoTo' in line:
        print(f'{i+1}: {line.rstrip()[:120]}')
