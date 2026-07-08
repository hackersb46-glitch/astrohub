import sys
files = {
    'console.html': open('src/web/includes/console.html', encoding='utf-8').read(),
    'brightness.py': open('src/controlpanel/brightness.py', encoding='utf-8').read(),
    'router.py': open('src/api/router.py', encoding='utf-8').read(),
}

checks = [
    ('console.html', 'gainLabel id', 'id="gainLabel"'),
    ('console.html', 'gainEnabled=true', 'var gainEnabled = true'),
    ('console.html', 'payload.gain_limit', 'payload.gain_limit'),
    ('console.html', 'localGainLimit init', 'window.localGainLimit = '),
    ('console.html', 'gain_max uses localGainLimit', 'window.localGainLimit || 100'),
    ('console.html', 'label dynamic update', 'gainLabel.innerHTML'),
    ('brightness.py', 'gain_limit param', 'gain_limit'),
    ('router.py', 'gain_limit param', 'gain_limit'),
]

ok = True
for fname, name, pattern in checks:
    found = pattern in files[fname]
    mark = 'OK' if found else 'FAIL'
    print(f'  [{mark}] {fname}: {name}')
    if not found:
        ok = False

print()
print('ALL PASS' if ok else 'SOME FAILED')
