#!/usr/bin/env python
"""Analyze HTML file relationships"""
import re

with open('D:/py_app/astro_hub/src/web/index.html', 'r', encoding='utf-8') as f:
    idx = f.read()

with open('D:/py_app/astro_hub/src/web/base.html', 'r', encoding='utf-8') as f:
    base = f.read()

with open('D:/py_app/astro_hub/src/web/includes/console.html', 'r', encoding='utf-8') as f:
    console = f.read()

# Check includes in index.html
includes = re.findall(r'{% include "([^"]+)"', idx)
print('index.html includes:')
for inc in includes:
    print(f'  - {inc}')

# Check if base.html is used
base_has_includes = '{% include' in base
print(f'\nbase.html has includes: {base_has_includes}')

# Check if index extends base
idx_extends = '{% extends' in idx
print(f'index.html extends base: {idx_extends}')

# Check console.html
print(f'\nconsole.html length: {len(console)}')
print(f'console.html has divPlugin: {"divPlugin" in console}')

# Check if index and base are similar
idx_wasm = 'webVideoCtrl.js' in idx
base_wasm = 'webVideoCtrl.js' in base
print(f'\nindex.html has WASM: {idx_wasm}')
print(f'base.html has WASM: {base_wasm}')

# Check Jinja2 in index
idx_jinja_blocks = len(re.findall(r'{% block [^%]+ %}', idx))
base_jinja_blocks = len(re.findall(r'{% block [^%]+ %}', base))
print(f'\nindex.html Jinja2 blocks: {idx_jinja_blocks}')
print(f'base.html Jinja2 blocks: {base_jinja_blocks}')