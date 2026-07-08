"""查询设备 ISAPI 实际响应"""
import requests
from requests.auth import HTTPDigestAuth
import xml.etree.ElementTree as ET

# 设备信息
device_ip = "192.168.1.64"  # 需要替换为实际设备IP
username = "admin"
password = "hik12345"  # 需要替换为实际密码

# 创建会话
auth = HTTPDigestAuth(username, password)
base_url = f"http://{device_ip}/ISAPI"

print("=" * 60)
print("1. 查询 Image/channels/1 (日夜模式和IR滤镜)")
print("=" * 60)
try:
    resp = requests.get(f"{base_url}/Image/channels/1", auth=auth, timeout=10)
    print(f"状态码: {resp.status_code}")
    if resp.status_code == 200:
        print("\nXML 响应:")
        print(resp.text[:2000])
        
        # 解析关键值
        root = ET.fromstring(resp.text)
        for elem in root.iter():
            tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
            if tag in ["dayNightMode", "irCutFilter"]:
                print(f"\n{tag} = {elem.text}")
    else:
        print(f"错误: {resp.text}")
except Exception as e:
    print(f"异常: {e}")

print("\n" + "=" * 60)
print("2. 查询 Image/channels/1/DSS (慢快门)")
print("=" * 60)
try:
    resp = requests.get(f"{base_url}/Image/channels/1/DSS", auth=auth, timeout=10)
    print(f"状态码: {resp.status_code}")
    if resp.status_code == 200:
        print("\nXML 响应:")
        print(resp.text)
        
        # 解析关键值
        root = ET.fromstring(resp.text)
        for elem in root.iter():
            tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
            if tag in ["enabled", "DSSLevel"]:
                print(f"\n{tag} = {elem.text}")
    else:
        print(f"错误: {resp.text}")
except Exception as e:
    print(f"异常: {e}")

print("\n" + "=" * 60)
print("3. 查询 Image/channels/1/Color (色彩配置，可能包含IR)")
print("=" * 60)
try:
    resp = requests.get(f"{base_url}/Image/channels/1/Color", auth=auth, timeout=10)
    print(f"状态码: {resp.status_code}")
    if resp.status_code == 200:
        print("\nXML 响应:")
        print(resp.text[:2000])
    else:
        print(f"错误: {resp.text}")
except Exception as e:
    print(f"异常: {e}")
