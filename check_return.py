#!/usr/bin/env python
"""Check what orchestrator returns"""
import sys
import asyncio
sys.path.insert(0, 'D:/py_app/astro_hub')

from src.main.core.orchestrator import Orchestrator

async def check():
    orch = Orchestrator()
    await orch.start()
    
    for name in ['ptz', 'device', 'stream', 'calibration']:
        mod = orch.get_module(name)
        print(f'{name}: {type(mod)} - {mod}')
        if hasattr(mod, 'list_stored_devices'):
            print(f'  has list_stored_devices')
    
    await orch.stop()

asyncio.run(check())