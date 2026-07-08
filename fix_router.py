"""Replace slow_shutter API in router.py to use DSS endpoint"""
path = r'astrohub\src\api\router.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

start = content.find('# === 慢快门 (v8.44) ===')
end = content.find('@api_router.get("/ptz/{device_id}/osd/ptz"')

print(f'start={start}, end={end}')

new = """# === 慢快门 DSS (v8.45) ===

@api_router.get("/ptz/{device_id}/image/slow-shutter", summary="获取慢快门设置", tags=["Image"])
async def get_slow_shutter(device_id: str) -> dict:
    mgr = _managers.get("ptz_controller")
    if not mgr:
        return {"success": False, "message": "PTZDeviceController未初始化"}
    target_ip = _resolve_device_id_to_ip(mgr, device_id)
    if not target_ip:
        return {"success": False, "message": f"无法解析设备标识: {device_id}"}
    ctrl, err = mgr._get_controller(target_ip)
    if err:
        return {"success": False, "message": err}
    client = ctrl.client
    try:
        resp = client.get("/Image/channels/1/DSS")
        if resp.status_code != 200:
            return {"success": False, "message": f"获取DSS失败: HTTP {resp.status_code}"}
        import xml.etree.ElementTree as ET
        root = ET.fromstring(resp.xml)
        enabled = False
        dss_level = ""
        for elem in root.iter():
            tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
            if tag == "enabled":
                enabled = (elem.text or "").strip().lower() == "true"
            elif tag == "DSSLevel":
                dss_level = (elem.text or "").strip()
        return {"success": True, "data": {"supported": True, "enabled": enabled, "dss_level": dss_level}}
    except Exception as e:
        return {"success": False, "message": f"获取DSS异常: {e}"}

@api_router.put("/ptz/{device_id}/image/slow-shutter", summary="设置慢快门", tags=["Image"])
async def set_slow_shutter(device_id: str, body: dict) -> dict:
    mgr = _managers.get("ptz_controller")
    if not mgr:
        return {"success": False, "message": "PTZDeviceController未初始化"}
    target_ip = _resolve_device_id_to_ip(mgr, device_id)
    if not target_ip:
        return {"success": False, "message": f"无法解析设备标识: {device_id}"}
    ctrl, err = mgr._get_controller(target_ip)
    if err:
        return {"success": False, "message": err}
    client = ctrl.client
    dss_level = body.get("dss_level", "")
    try:
        if dss_level == "off":
            enabled = "false"
            level_str = "*1"
        else:
            enabled = "true"
            level_str = dss_level
        xml_str = '<?xml version="1.0" encoding="UTF-8"?>' + chr(10) + '<DSS version="2.0" xmlns="http://www.hikvision.com/ver20/XMLSchema">' + chr(10) + '  <enabled>' + enabled + '</enabled>' + chr(10) + '  <DSSLevel>' + level_str + '</DSSLevel>' + chr(10) + '</DSS>'
        put_resp = client.put("/Image/channels/1/DSS", xml_str)
        if put_resp.status_code == 200:
            log_info("image", "dss", {"device": device_id, "level": dss_level})
            return {"success": True, "message": "慢快门: " + ("关闭" if dss_level == "off" else dss_level)}
        return {"success": False, "message": f"设置失败: HTTP {put_resp.status_code}"}
    except Exception as e:
        return {"success": False, "message": f"设置DSS异常: {e}"}

"""

content = content[:start] + new + content[end:]
with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
print('router.py DSS API replaced')
