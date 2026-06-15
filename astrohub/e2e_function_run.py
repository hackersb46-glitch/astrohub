"""E2E 测试 - 运行功能探测并检查 function.json"""
from playwright.sync_api import sync_playwright
import requests
import json
import time
import os

API_BASE = 'http://localhost:10280/api/v1'

def test_function_detection():
    """测试功能探测"""
    ip = '192.168.5.72'
    
    print('\n=== 步骤1: 检查当前 function.json 状态 ===')
    r = requests.get(f'{API_BASE}/ptz/{ip}/function', timeout=10)
    data = r.json()
    print(f'function.json 存在: {data.get("success")}')
    
    print('\n=== 步骤2: 运行功能探测 API ===')
    # 直接调用 API 运行功能探测
    r = requests.post(f'{API_BASE}/advanced/function/run', json={'device_ip': ip}, timeout=120)
    print(f'状态码: {r.status_code}')
    
    try:
        result = r.json()
        print(f'成功: {result.get("success")}')
        if result.get('total_functions'):
            print(f'总功能数: {result.get("total_functions")}')
            print(f'支持数: {result.get("supported_count")}')
        
        # 打印部分结果
        if result.get('functions'):
            for key, val in list(result['functions'].items())[:5]:
                print(f'  {key}: supported={val.get("supported")}, opt_values={val.get("opt_values", [])[:3] if val.get("opt_values") else "无"}')
    except Exception as e:
        print(f'解析响应错误: {e}')
        print(f'响应内容: {r.text[:500]}')
    
    print('\n=== 步骤3: 检查 function.json 文件 ===')
    # 检查文件是否存在
    device_dir = 'C:/Users/admin/.openclaw/agents/dev-factory/astrohub/data/devices/240f9b764193'
    func_file = f'{device_dir}/function.json'
    
    if os.path.exists(func_file):
        print(f'文件存在: {func_file}')
        with open(func_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 检查 shutter 和 iris
        if data.get('functions'):
            print('\n--- Shutter ---')
            shutter = data['functions'].get('shutter', {})
            print(f'  supported: {shutter.get("supported")}')
            print(f'  opt_values: {shutter.get("opt_values", [])[:5]}...')
            
            print('\n--- Iris ---')
            iris = data['functions'].get('iris', {})
            print(f'  supported: {iris.get("supported")}')
            print(f'  opt_values: {iris.get("opt_values", [])[:5]}...')
    else:
        print(f'文件不存在: {func_file}')
        # 列出目录内容
        if os.path.exists(device_dir):
            print(f'目录内容: {os.listdir(device_dir)}')
        else:
            print(f'目录不存在: {device_dir}')
    
    print('\n=== 步骤4: 通过 API 再次检查 ===')
    r = requests.get(f'{API_BASE}/ptz/{ip}/function', timeout=10)
    data = r.json()
    print(f'成功: {data.get("success")}')
    if data.get('function_detection'):
        print(f'探测时间: {data.get("detected_at", "未知")}')

if __name__ == '__main__':
    test_function_detection()