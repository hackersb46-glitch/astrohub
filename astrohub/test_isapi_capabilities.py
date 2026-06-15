"""测试 ISAPI capabilities 端点 - 获取光圈和快门的 opt_values"""
import requests
from requests.auth import HTTPDigestAuth
import xml.etree.ElementTree as ET

# 摄像头配置
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
            print(f'响应长度: {len(r.text)}')
            return r.text
        else:
            print(f'错误: {r.text[:200]}')
            return None
    except Exception as e:
        print(f'异常: {e}')
        return None

def parse_opt_values(xml_text, key):
    """解析 XML 中的 opt 值"""
    if not xml_text:
        return None
    try:
        root = ET.fromstring(xml_text)
        for elem in root.iter():
            local_name = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
            if local_name == key:
                opt_attr = elem.get('opt')
                if opt_attr:
                    values = [v.strip() for v in opt_attr.split(',')]
                    print(f'找到 {key} opt_values: {values[:5]}... (共 {len(values)} 个)')
                    return values
        print(f'未找到 {key} 的 opt 属性')
        return None
    except Exception as e:
        print(f'解析错误: {e}')
        return None

def main():
    print('========================================')
    print('测试 ISAPI capabilities 端点')
    print('========================================')
    
    # 1. 测试 capabilities 端点
    cap_xml = test_isapi('/ISAPI/Image/channels/1/capabilities')
    
    if cap_xml:
        print('\n--- 解析快门 opt_values ---')
        shutter_opts = parse_opt_values(cap_xml, 'ShutterLevel')
        
        print('\n--- 解析光圈 opt_values ---')
        iris_opts = parse_opt_values(cap_xml, 'IrisLevel')
        
        print('\n--- 解析其他字段 ---')
        # 查看所有有 opt 属性的元素
        root = ET.fromstring(cap_xml)
        for elem in root.iter():
            opt_attr = elem.get('opt')
            if opt_attr:
                local_name = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
                values = opt_attr.split(',')
                print(f'{local_name}: opt 值数量 = {len(values)}')
    
    # 2. 测试直接访问快门/光圈端点
    print('\n========================================')
    print('测试快门/光圈端点')
    print('========================================')
    
    shutter_xml = test_isapi('/ISAPI/Image/channels/1/Shutter')
    iris_xml = test_isapi('/ISAPI/Image/channels/1/Iris')
    
    if shutter_xml:
        print('\n--- 快门 XML 片段 ---')
        print(shutter_xml[:500])
    
    if iris_xml:
        print('\n--- 光圈 XML 片段 ---')
        print(iris_xml[:500])

if __name__ == '__main__':
    main()