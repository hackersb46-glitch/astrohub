# 模块重命名重构计划

## 映射表

| 旧名称 | 新名称 | 说明 |
|--------|--------|------|
| m1_ptz_astro | ptz | 云台控制 |
| m2_device_manager | device | 设备管理 |
| m3_stream_service | stream | 视频流 |
| m4_calibration | calibration | 标定 |
| m5_database | database | 数据库 |
| m6_webui | webui | Web界面 |
| m7_rest_api | rest_api | 独立REST网关 |
| m8_websocket | websocket | WebSocket |
| m9_ascom | ascom | ASCOM驱动 |
| m10_integration | integration | 模块集成 |
| m11_deployment | deployment | 部署 |
| m12_integration | main | 主入口 |

## 执行步骤

### Step 1: 重命名目录
在 src/ 下 mv 旧目录 → 新目录，顺序避免冲突：

```
m1_ptz_astro      → ptz
m2_device_manager → device
m3_stream_service → stream
m4_calibration    → calibration
m5_database       → database
m6_webui          → webui
m7_rest_api       → rest_api（避免与 api/ 冲突）
m8_websocket      → websocket
m9_ascom          → ascom
m10_integration   → integration
m11_deployment    → deployment
m12_integration   → main（最后执行）
```

### Step 2: 更新 Python import 语句
替换模式：
- `from src.m\d+_[a-z_]+` → `from src.<新名>`
- `from m\d+_[a-z_]+` → `from <新名>`（模块内部）
- `import src.m\d+_[a-z_]+` → `import src.<新名>`

涉及约 100+ 处，分批处理：
- Batch A: m1_ptz_astro → ptz
- Batch B: m2_device_manager → device
- Batch C: m3_stream_service → stream
- Batch D: m4_calibration → calibration
- Batch E: m5_database → database
- Batch F: m7_rest_api → rest_api
- Batch G: m8_websocket → websocket
- Batch H: m9_ascom → ascom
- Batch I: m10_integration → integration
- Batch J: m11_deployment → deployment
- Batch K: m12_integration → main

### Step 3: 更新入口点
- start.py:85 `src.m12_integration.main` → `src.main.main`

### Step 4: 更新字符串引用
- constants.py 中 MODULE_ORDER 列表
- __init__.py 导出
- 注释、文档中的模块名

### Step 5: 更新 HTML/JS 链接
- 导航按钮 href
- API 路径

### Step 6: 清理 __pycache__
删除所有 src/**/__pycache__ 避免 .pyc 缓存干扰

### Step 7: 验证
- grep 确认无残留 `m\d+_` 引用
- `python -c "from src.main import create_app"` 测试导入

## 风险与处理
- 目录冲突：m7 → rest_api（避免 api/）
- main 与 main.py：m12_integration 是包目录，不冲突
- import 失败：逐步验证，出错立即回退