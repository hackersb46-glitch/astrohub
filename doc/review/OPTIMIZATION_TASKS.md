# AstroHub 优化任务清单

> **创建时间:** 2026-05-05 19:30
> **优先级:** P0(阻塞) → P1(重要) → P2(改进)

---

## P0: 修复所有 API 路由 404（阻塞）

### 问题
所有 /api/v1/* 路由返回 404。src/api/router.py 中所有路由是占位符（注释掉的）。health_router 前缀错误。

### 需要做的
1. **修复 src/api/router.py**：
   - 创建实际的 API 端点，返回 Manager 实例数据
   - /api/v1/health → 全局健康检查，返回所有模块状态
   - /api/v1/devices → GET 列表, POST 注册
   - /api/v1/ptz/{device_id}/move → POST PTZ 移动
   - /api/v1/ptz/{device_id}/home → POST 归位
   - /api/v1/ptz/{device_id}/stop → POST 停止
   - /api/v1/streams → GET 列表
   - /api/v1/calibration/{device_id}/{type} → POST 开始校准
   - /api/v1/ascom/{type}/connect → POST 连接
   - /api/v1/settings → POST 保存设置
   - 使用 set_managers() 注入模式，路由层获取 Manager 实例
   - 所有端点返回 mock/stub 数据（实际硬件未接入时返回示例数据）

2. **修复 health_router 前缀**：
   - 改为 APIRouter(prefix="/api/v1", tags=["System"]) 或在 main.py 挂载时指定
   - main.py: pp.include_router(health_router) → 确保路径是 /api/v1/health

3. **修复 WebSocket 端点**：
   - /ws 返回 200 但没有实际处理函数
   - 添加 WebSocket 端点，接收连接并通过 WSManager 管理

---

## P1: 数据目录自动创建

### 问题
启动时 data/db, data/logs, data/config, data/hls 等目录可能不存在。

### 需要做的
- main.py 启动时确保所有目录存在：
  `python
  for d in [DB_DIR, LOG_DIR, CONFIG_DIR, DATA_DIR / 'hls', DATA_DIR / 'calibration']:
      d.mkdir(parents=True, exist_ok=True)
  `

---

## P2: SPA 前端数据对接

### 问题
前端 SPA 通过 fetch 调用 API，但当前 API 都是 404。

### 需要做的
- P0 修复后前端自动可用（前端已写好所有 fetch 调用）
- 确认 WebSocket 实时数据推送正常

---

## P3: 打包体积优化

### 问题
总输出 135.8 MB。可优化项：
- 排除了 matplotlib/numpy/scipy 但 IPython 等开发工具仍被打包
- 可增加更多 excludes 减小体积

### 需要做的
- build.spec 排除：IPython, jupyter, pytest, setuptools, black, astroid, jedi, parso 等开发工具
- 测试打包后可正常运行

---

## P4: 日志输出到文件

### 问题
运行日志输出到 stderr，不持久化。

### 需要做的
- env_check.py 启动时初始化日志到 data/logs/astrohub_YYYYMMDD.log
- 日志轮转：10MB，保留 5 份
- --headless 模式日志输出到文件 + stderr

---

## P5: 图标和版本信息

### 需要做的
- 添加 AstroHub.ico 图标
- build.spec 添加 Windows 版本信息（ProductName, CompanyName, FileVersion）

---

## 执行顺序

1. **P0** → 修复所有 API 路由（最重要）
2. **P1** → 数据目录自动创建
3. **P2** → SPA 前端对接（P0 完成后自动可用）
4. **P3** → 打包体积优化
5. **P4** → 日志持久化
6. **P5** → 图标/版本（可选）

---

## 当前项目状态

- 172 Python 文件，全部 py_compile 通过
- 9 个 Manager 类已实现
- SPA 前端已完成（18KB HTML）
- 打包成功，exe 21.5MB，总输出 135.8MB
- --headless 模式可启动，HTTP 200 首页正常

## 项目根目录
D:\\astro_py\\astro_hub
