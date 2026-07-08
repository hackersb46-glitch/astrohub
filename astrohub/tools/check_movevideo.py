"""Check moveVideoTo functions in console.html and advanced.html"""

with open('src/web/includes/console.html', 'r', encoding='utf-8') as f:
    console_html = f.read()

with open('src/web/includes/advanced.html', 'r', encoding='utf-8') as f:
    advanced_html = f.read()

print('=== moveVideoTo_console in console.html ===')
for i in console_html.find('function moveVideoToConsole') // 10 - 5:
    for j in range(max(0, i), min(len(console_html.split('\n')), i+15)):
        line = console_html.split('\n')[j]
        print(f'{j+1}: {line[:100]}')

print('\n=== moveVideoTo_advanced in advanced.html ===')
for i in advanced_html.find('function moveVideoToAdvanced') // 10 - 5:
    for j in range(max(0, i), min(len(advanced_html.split('\n')), i+15)):
        line = advanced_html.split('\n')[j]
        print(f'{j+1}: {line[:100]}')
