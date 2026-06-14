# 完全重写main.py中的ISAPI代理部分
# 先读取文件找到正确的插入点

with open('D:/py_app/astro_hub/src/main/main.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# 找到app.include_router(api_router)的位置
router_idx = None
for i, line in enumerate(lines):
    if 'app.include_router(api_router)' in line and 'ISAPI' not in lines[i-1] if i > 0 else True:
        router_idx = i
        break

if router_idx:
    # 检查前面是否已经有ISAPI代理
    has_isapi = any('ISAPI' in lines[j] for j in range(router_idx-20, router_idx) if j >= 0)
    
    if not has_isapi:
        # 在router之前插入ISAPI代理
        isapi_code = '''
    # === ISAPI Proxy for WASM SDK ===
    import aiohttp
    _isapi_sessions = {}

    async def _handle_isapi(request, path):
        device_ip = request.query_params.get('ip', '192.168.5.72')
        url = f'http://{device_ip}:80/ISAPI/{path}'
        method = request.method
        body = await request.body() if method in ('POST', 'PUT') else None
        
        session = _isapi_sessions.get(device_ip)
        if not session or getattr(session, 'closed', False):
            session = aiohttp.ClientSession()
            _isapi_sessions[device_ip] = session
        
        headers = {'Content-Type': 'application/xml'} if method in ('POST', 'PUT') else {}
        
        try:
            if method == 'GET':
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as r:
                    return Response(content=await r.read(), status_code=r.status, media_type='application/xml')
            elif method == 'POST':
                async with session.post(url, data=body, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as r:
                    return Response(content=await r.read(), status_code=r.status, media_type='application/xml')
        except Exception as e:
            return Response(content=str(e).encode(), status_code=500)

    @app.api_route('/ISAPI/{path:path}', methods=['GET', 'POST', 'PUT', 'DELETE'])
    async def isapi_proxy(request: Request, path: str):
        return await _handle_isapi(request, path)

'''
        # 插入代码
        new_lines = lines[:router_idx] + isapi_code.splitlines(keepends=True) + lines[router_idx:]
        
        with open('D:/py_app/astro_hub/src/main/main.py', 'w', encoding='utf-8') as f:
            f.writelines(new_lines)
        
        print(f"Added ISAPI proxy before line {router_idx}")
    else:
        print("ISAPI proxy already exists")
else:
    print("Could not find router position")