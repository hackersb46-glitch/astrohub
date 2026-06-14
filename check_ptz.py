#!/usr/bin/env python
"""Check PTZ module"""
import sys
sys.path.insert(0, 'D:/py_app/astro_hub')

from src.ptz import PTZManager
mgr = PTZManager()
print(f'PTZManager: {mgr}')
attrs = [a for a in dir(mgr) if not a.startswith('_')]
print(f'Attrs: {attrs}')