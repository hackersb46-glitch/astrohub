from src.main.main import app

# 检查所有路由
print('=== All Routes ===')
for r in app.routes:
    if hasattr(r, 'path'):
        endpoint_name = r.endpoint.__name__ if hasattr(r.endpoint, '__name__') else str(r.endpoint)
        print(f'Path: {r.path}, Endpoint: {endpoint_name}')
