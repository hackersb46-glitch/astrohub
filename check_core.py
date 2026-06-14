#!/usr/bin/env python
"""Check PTZManager from core"""
import sys
sys.path.insert(0, 'D:/py_app/astro_hub')

from src.ptz.core import PTZManager
print(f'PTZManager: {PTZManager}')
mgr = PTZManager()
print(f'Instance: {mgr}')
has_method = hasattr(mgr, 'list_stored_devices')
print(f'Has list_stored_devices: {has_method}')