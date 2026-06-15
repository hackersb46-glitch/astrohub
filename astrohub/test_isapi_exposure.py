"""测试 ISAPI 曝光模式端点"""
import requests
from requests.auth import HTTPDigestAuth
import xml.etree.ElementTree as ET

IP = '192.168.5.72'
PORT = 80
USER = 'admin'
PASS = 'Nftw1357'
BASE_URL = f'http://{IP}:{PORT}'

def test_isapi(endpoint):
    """测试 ISAPI 端点"""
    url = BASE_URL + endpoint
    print(f'\n=== 测试: {endpoint} ===')
    try:
        r = requests.get(url, auth=HTTPDigestAuth(USER, PASS), timeout=10)
        print(f'状态码: {r.status_code}')
        if r.status_code == 200:
            print(f'响应: {r.text[:500]}')
            return r.text
        else:
            print(f'错误: {r.text[:200]}')
            return None
    except Exception as e:
        print(f'异常: {e}')
        return None

def main():
    # 1. 测试曝光模式端点
    print('========================================')
    print('测试曝光模式 ISAPI 端点')
    print('========================================')
    
    # 常见曝光模式端点
    endpoints = [
        '/ISAPI/Image/channels/1/exposure',
        '/ISAPI/Image/channels/1/Exposure',
        '/ISAPI/Image/channels/1/capabilities',
    ]
    
    for ep in endpoints:
        xml = test_isapi(ep)
        if xml and 'ExposureType' in xml:
            print('\n--- 解析 ExposureType ---')
            try:
                root = ET.fromstring(xml)
                for elem in root.iter():
                    local_name = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
                    if local_name == 'ExposureType':
                        opt = elem.get('opt')
                        current = elem.text
                        print(f'ExposureType opt: {opt}')
                        print(f'ExposureType current: {current}')
            except:
                pass

if __name__ == '__main__':
    main()