# AstroHub v7.12 文件引用分析报告

## 一、总览

```
总文件数: 702 (含 WASM/SDK)
代码文件: 247 (Python/HTML/JS/CSS, 排除 WASM/SDK)

活跃文件: ~80 个 (被实际引用)
未使用文件: ~160 个 (过期/备用)
```

---

## 二、活跃模块 (正在使用)

### 1. 核心模块 ✅ 必需

| 文件 | 作用 | 被引用次数 |
|------|------|-----------|
| `src/main/main.py` | 程序入口 | 1 |
| `src/main/constants.py` | 版本号、常量 | 2 |
| `src/main/core/orchestrator.py` | 模块编排 | 2 |
| `src/api/router.py` | API 路由聚合 | 1 |
| `src/config.py` | 全局配置 | 2 |
| `src/config_paths.py` | 路径管理 | 多处 |
| `src/logger.py` | 日志工具 | 多处 |
| `src/operation_logger.py` | 操作日志 | 多处 |

### 2. PTZ 核心模块 ✅ 必需

| 文件 | 作用 | 被引用次数 |
|------|------|-----------|
| `src/core/ptz_manager.py` | PTZ 管理器核心 | 2 |
| `src/core/sadp_discovery.py` | SADP 设备发现 | 多处 |
| `src/ptz/isapi/client.py` | ISAPI HTTP 客户端 | 63+ |
| `src/ptz/isapi/ptz.py` | PTZ 控制 ISAPI | 多处 |
| `src/ptz/isapi/capabilities.py` | 设备能力查询 | 少 |
| `src/ptz/constants.py` | PTZ 常量 | 多处 |
| `src/ptz/core/logger.py` | PTZ 日志 | 多处 |
| `src/ptz/core/config.py` | PTZ 配置 | 少 |

### 3. 设备管理模块 ✅ 必需

| 文件 | 作用 | 被引用次数 |
|------|------|-----------|
| `src/core/device_manager.py` | 设备管理器 | 2 |
| `src/core/stream_manager.py` | 流管理器 | 2 |
| `src/core/calibration_manager.py` | 校准管理器 | 2 |
| `src/core/auth.py` | 认证管理 | 2 |
| `src/core/ws_manager.py` | WebSocket 管理 | 2 |
| `src/core/ascom_manager.py` | ASCOM 管理 | 2 |
| `src/core/health_monitor.py` | 健康监控 | 2 |
| `src/core/orchestrator.py` | 编排器 | 2 |
| `src/core/net_detector.py` | 网络检测 | 多处 |
| `src/core/file_naming.py` | 文件命名 | 多处 |

### 4. 高级功能模块 ✅ 必需

| 文件 | 作用 | 被引用次数 |
|------|------|-----------|
| `src/advanced/function.py` | 功能探测 (P4.1-P4.21) | 5+ |
| `src/advanced/limit.py` | 限位测试 (P6.0-P6.6) | 5+ |
| `src/advanced/speed.py` | 速度测试 | 5+ |
| `src/advanced/device_path.py` | 设备路径管理 | 多处 |
| `src/advanced/onboarding.py` | 设备引导 | 少 |
| `src/advanced/device_config.py` | 设备配置 | 少 |

### 5. 前端模块 ✅ 必需

| 文件 | 作用 |
|------|------|
| `src/web/index.html` | 主页面 SPA |
| `src/web/includes/console.html` | PTZ 控制面板 |
| `src/web/includes/devices.html` | 设备管理页面 |
| `src/web/includes/advanced.html` | 高级功能页面 |
| `src/web/includes/dashboard.html` | 仪表盘 |
| `src/web/includes/observation.html` | 观测计划 |
| `src/web/includes/replay.html` | 回放页面 |

### 6. WASM SDK ✅ 必需

| 目录 | 作用 |
|------|------|
| `src/web/static/websdk/wasm/` | 海康 WASM 视频播放器 |
| `jsPlugin-3.0.0.min.js` | SDK 主文件 |
| `wasmplayer.min.js` | WASM 解码器 |
| `webVideoCtrl.js` | 视频控制 |

---

## 三、未使用模块 (可清理)

### 1. 部署模块 ❌ 未使用
```
src/deployment/           - 0 外部引用
├── api/router.py
├── core/docker_builder.py
├── core/deployment_config.py
├── core/env_verify.py
├── core/health_monitor.py
├── core/log_collector.py
├── core/rollback.py
└── core/service_manager.py
```

### 2. 设备模块 (重复) ❌ 未使用
```
src/device/               - 0 外部引用
├── api/router.py
├── core/device_manager.py   # 与 src/core/device_manager.py 重复
├── core/sadp_discovery.py   # 与 src/core/sadp_discovery.py 重复
├── isapi/client.py          # 与 src/ptz/isapi/client.py 重复
└── ...
```

### 3. 集成模块 ❌ 未使用
```
src/integration/          - 0 外部引用
├── api/router.py
├── core/device_orchestrator.py
├── core/event_bus.py
├── core/pipeline.py
└── core/task_scheduler.py
```

### 4. REST API 模块 (重复) ❌ 未使用
```
src/rest_api/             - 0 外部引用
├── api/router.py           # 与 src/api/router.py 重复
├── core/api_gateway.py
├── core/auth.py
└── core/middleware.py
```

### 5. WebUI 模块 (重复) ❌ 未使用
```
src/webui/                - 0 外部引用
├── api/router.py
├── core/web_server.py
└── core/dashboard.py
```

### 6. 数据库模块 ⚠️ 部分使用
```
src/database/             - 24 外部引用
├── core/db_manager.py       # 被引用
├── core/device_repo.py      # 可能使用
└── core/operation_log.py    # 可能使用
```

### 7. 校准模块 (旧版) ⚠️ 部分使用
```
src/calibration/          - 17 外部引用
├── core/calibration_manager.py  # 与 src/core/ 重复
├── core/position_calibration.py
└── core/speed_mapping.py
```

### 8. WebSocket 模块 ⚠️ 部分使用
```
src/websocket/            - 28 外部引用
├── core/ws_manager.py       # 被引用
├── server.py
└── handlers.py
```

### 9. 流模块 ⚠️ 部分使用
```
src/stream/               - 27 外部引用
├── core/stream_manager.py   # 被引用
├── core/stream.py
└── core/recorder.py
```

---

## 四、过期文件 (可直接删除)

### 1. 旧版本文件
```
src/web/versions/         - 历史版本备份
├── advanced_v5.30.html
├── console_v5.15.html
├── index_v5.15.html ~ v5.29.html
└── function_v5.29.py, v5.30.py

src/web/includes/
├── advanced_v2.html      - 旧版本
├── advanced_v5.31.html   - 旧版本
└── advanced.html         - 当前版本 ✅

src/web/static/css/
└── advanced_v2.css       - 旧版样式
```

### 2. 文档源码 (可保留但非必需)
```
doc/
├── PTZ_FUNCTION_source.py
├── PTZ_LIMIT_source.py
├── ptzhelper_source.py
├── step4_probe_source.py
└── step5_function_source.py
```

### 3. 测试脚本 (开发用)
```
test_e2e.py              - E2E 测试
test_e2e_full.py         - 完整 E2E 测试
analyze_files.py         - 分析脚本
check_duplicates.py      - 查重脚本
start.py                 - 启动脚本 (与 main.py 重复)
```

---

## 五、建议清理列表

### 可安全删除 (0 引用)
```
src/deployment/          # 整个目录
src/integration/         # 整个目录
src/rest_api/            # 整个目录
src/webui/               # 整个目录
src/web/versions/        # 历史版本
src/web/includes/advanced_v2.html
src/web/includes/advanced_v5.31.html
src/web/static/css/advanced_v2.css
```

### 需验证后删除 (重复)
```
src/device/              # 与 src/core/ 和 src/ptz/ 重复
src/calibration/core/    # 与 src/core/calibration_manager.py 重复
```

### 保留但低优先级
```
src/database/            # 部分使用
src/websocket/           # 部分使用
src/stream/              # 部分使用
src/ascom/               # ASCOM 驱动 (未来功能)
```

---

## 六、精简后结构

```
astrohub/
├── src/
│   ├── main/
│   │   ├── main.py           # 入口
│   │   ├── constants.py      # 常量
│   │   └── core/orchestrator.py
│   ├── api/
│   │   └── router.py         # API 路由
│   ├── core/
│   │   ├── ptz_manager.py    # PTZ 核心
│   │   ├── device_manager.py
│   │   ├── stream_manager.py
│   │   ├── sadp_discovery.py
│   │   └── ...
│   ├── advanced/
│   │   ├── function.py       # 功能探测
│   │   ├── limit.py          # 限位测试
│   │   ├── speed.py          # 速度测试
│   │   └── device_path.py
│   ├── ptz/
│   │   ├── isapi/client.py   # ISAPI 客户端
│   │   ├── isapi/ptz.py      # PTZ 控制
│   │   └── constants.py
│   └── web/
│       ├── index.html
│       └── includes/         # 页面组件
├── data/                     # 运行时数据
├── config/                   # 配置
└── documents/                # 文档
```

---

## 七、清理收益

| 类别 | 文件数 | 大小估算 |
|------|--------|---------|
| 删除未使用模块 | ~60 文件 | ~500KB |
| 删除历史版本 | ~15 文件 | ~200KB |
| 删除重复代码 | ~40 文件 | ~400KB |
| **总计** | **~115 文件** | **~1.1MB** |

精简后代码文件: **~130 个** (从 247 减少到 130)

---

**分析时间**: 2026-06-15
**代码版本**: v7.12
