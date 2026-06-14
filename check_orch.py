#!/usr/bin/env python
"""Check orchestrator"""
import sys
sys.path.insert(0, 'D:/py_app/astro_hub')

from src.main.core.orchestrator import Orchestrator

orch = Orchestrator()
attrs = [a for a in dir(orch) if not a.startswith('_')]
print(f'Attributes: {attrs}')