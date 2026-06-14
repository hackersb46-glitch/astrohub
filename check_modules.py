#!/usr/bin/env python
"""Check orchestrator modules"""
import sys
sys.path.insert(0, 'D:/py_app/astro_hub')

from src.main.core.orchestrator import Orchestrator

orch = Orchestrator()
print(f'Orchestrator created')
print(f'Attrs: {[a for a in dir(orch) if not a.startswith("_")]}')

orch.start()
print(f'After start')

for name in ['ptz', 'device', 'stream', 'calibration']:
    mod = orch.get_module(name)
    print(f'  {name}: {mod}')

orch.stop()