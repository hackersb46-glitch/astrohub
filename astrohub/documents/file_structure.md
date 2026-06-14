# AstroHub v7.12 最终文件结构

## 一、总览

```
总文件数: 252
├── Python 源码:   116 个
├── HTML 页面:       7 个
├── WASM SDK:       35 个
├── 配置/文档:      64 个
├── 日志文件:       11 个
└── 其他:           19 个
```

---

## 二、目录结构

```
astrohub/
│
├── src/                          # 源码目录
│   ├── main/                     # 主入口 (4 Python)
│   │   ├── main.py               # ★ 程序入口
│   │   ├── constants.py          # ★ 版本号、常量
│   │   ├── api/__init__.py
│   │   ├── api/router.py
│   │   └── core/
│   │       ├── __init__.py
│   │       ├── orchestrator.py   # 模块编排器
│   │       ├── config_merger.py
│   │       └── health_aggregator.py
│   │
│   ├── api/                      # API 路由 (4 Python)
│   │   ├── __init__.py
│   │   ├── router.py             # ★ 统一 API 路由
│   │   └── astap_solve.py        # ASTAP 求解
│   │
│   ├── core/                     # 核心管理器 (15 Python)
│   │   ├── __init__.py
│   │   ├── ptz_manager.py        # ★ PTZ 核心管理器
│   │   ├── device_manager.py     # 设备管理器
│   │   ├── stream_manager.py     # 流管理器
│   │   ├── calibration_manager.py # 校准管理器
│   │   ├── auth.py               # 认证管理
│   │   ├── ws_manager.py         # WebSocket 管理
│   │   ├── ascom_manager.py      # ASCOM 管理
│   │   ├── health_monitor.py     # 健康监控
│   │   ├── orchestrator.py       # 编排器
│   │   ├── sadp_discovery.py     # SADP 设备发现
│   │   ├── net_detector.py       # 网络检测
│   │   ├── file_naming.py        # 文件命名
│   │   ├── nic_selector.py       # 网卡选择
│   │   └── service_manager.py    # 服务管理
│   │
│   ├── ptz/                      # PTZ 控制模块 (22 Python)
│   │   ├── __init__.py
│   │   ├── constants.py          # PTZ 常量
│   │   ├── core/
│   │   │   ├── __init__.py
│   │   │   ├── config.py         # PTZ 配置
│   │   │   ├── logger.py         # PTZ 日志
│   │   │   ├── network.py        # 网络工具
│   │   │   ├── recorder.py       # 录像
│   │   │   ├── system_info.py    # 系统信息
│   │   │   └── ui.py             # UI 工具
│   │   ├── isapi/
│   │   │   ├── __init__.py
│   │   │   ├── client.py         # ★ ISAPI HTTP 客户端
│   │   │   ├── ptz.py            # ★ PTZ 控制 ISAPI
│   │   │   └── capabilities.py   # 设备能力查询
│   │   ├── ptz/
│   │   │   ├── __init__.py
│   │   │   ├── limits.py         # 限位计算
│   │   │   └── motion.py         # 运动控制
│   │   ├── sadp/
│   │   │   ├── __init__.py
│   │   │   ├── discovery.py      # SADP 发现
│   │   │   └── ip_manager.py     # IP 管理
│   │   └── report/
│   │       ├── __init__.py
│   │       ├── generator.py      # 报告生成
│   │       └── packager.py       # 打包
│   │
│   ├── advanced/                 # 高级功能 (8 Python)
│   │   ├── __init__.py
│   │   ├── function.py           # ★ 功能探测 (P4.1-P4.21)
│   │   ├── limit.py              # ★ 限位测试 (P6.0-P6.6)
│   │   ├── speed.py              # ★ 速度测试
│   │   ├── device_path.py        # 设备路径管理
│   │   ├── device_config.py      # 设备配置
│   │   ├── config_writer.py      # 配置写入
│   │   └── onboarding.py         # 设备引导
│   │
│   ├── stream/                   # 流媒体模块 (15 Python)
│   │   ├── __init__.py
│   │   ├── constants.py
│   │   ├── core/
│   │   │   ├── __init__.py
│   │   │   ├── stream_manager.py # 流管理器
│   │   │   ├── stream.py         # 流控制
│   │   │   ├── distributor.py    # 分发器
│   │   │   ├── preview.py        # 预览
│   │   │   ├── recorder.py       # 录像
│   │   │   ├── transcoder.py     # 转码
│   │   │   ├── stream_monitor.py # 监控
│   │   │   └── logger.py
│   │   └── api/
│   │       ├── __init__.py
│   │       ├── router.py
│   │       └── models.py
│   │
│   ├── websocket/                # WebSocket 模块 (12 Python)
│   │   ├── __init__.py
│   │   ├── constants.py
│   │   ├── handlers.py
│   │   ├── server.py
│   │   ├── core/
│   │   │   ├── __init__.py
│   │   │   ├── ws_manager.py     # WebSocket 管理器
│   │   │   ├── auth.py           # 认证
│   │   │   ├── broadcast.py      # 广播
│   │   │   ├── message_handler.py # 消息处理
│   │   │   └── monitor.py        # 监控
│   │   └── api/
│   │       ├── __init__.py
│   │       └── router.py
│   │
│   ├── ascom/                    # ASCOM 驱动 (16 Python)
│   │   ├── __init__.py
│   │   ├── constants.py
│   │   ├── main.py
│   │   ├── alpaca/
│   │   ├── api/
│   │   └── core/
│   │
│   ├── storage/                  # 存储模块 (2 Python)
│   │   ├── __init__.py
│   │   └── store.py
│   │
│   ├── scripts/                  # 脚本工具 (3 Python)
│   │   ├── __init__.py
│   │   ├── start_server.py
│   │   └── stop_server.py
│   │
│   ├── web/                      # 前端
│   │   ├── index.html            # ★ 主页面
│   │   ├── includes/
│   │   │   ├── console.html      # 主控台
│   │   │   ├── devices.html      # 设备管理
│   │   │   ├── advanced.html     # 高级功能
│   │   │   ├── dashboard.html    # 仪表盘
│   │   │   ├── observation.html  # 观测计划
│   │   │   └── replay.html       # 回放
│   │   └── static/
│   │       └── websdk/wasm/      # WASM SDK (35 files)
│   │
│   ├── config.py                 # 全局配置
│   ├── config_paths.py           # 路径配置
│   ├── logger.py                 # 全局日志
│   ├── operation_logger.py       # 操作日志
│   └── __init__.py
│
├── data/                         # 运行时数据
│   ├── config/                   # 配置文件
│   ├── devices/                  # 设备数据
│   ├── logs/                     # 日志
│   └── records/                  # 录像
│
├── documents/                    # 文档
│   ├── ARCHITECTURE.md           # 架构文档
│   ├── FILE_ANALYSIS.md          # 文件分析
│   └── CODE_REUSE_ANALYSIS.md    # 复用分析
│
├── log/                          # 运行日志
├── config/                       # 配置目录
│
├── test_e2e.py                   # E2E 测试
├── verify_modules.py             # 模块验证
└── deep_dependency_analysis.py   # 依赖分析
```

---

## 三、核心文件清单

### 必需文件 (不可删除)

| 文件 | 作用 |
|------|------|
| `src/main/main.py` | 程序入口 |
| `src/main/constants.py` | 版本号、常量 |
| `src/api/router.py` | API 路由聚合 |
| `src/config.py` | 全局配置 |
| `src/config_paths.py` | 路径管理 |
| `src/logger.py` | 日志工具 |
| `src/core/ptz_manager.py` | PTZ 核心管理 |
| `src/ptz/isapi/client.py` | ISAPI 客户端 |
| `src/ptz/isapi/ptz.py` | PTZ 控制 |
| `src/advanced/function.py` | 功能探测 |
| `src/advanced/limit.py` | 限位测试 |
| `src/advanced/speed.py` | 速度测试 |
| `src/web/index.html` | 主页面 |

### 模块统计

| 模块 | Python 文件 | 作用 |
|------|-------------|------|
| src/main | 4 | 程序入口 |
| src/api | 4 | API 路由 |
| src/core | 15 | 核心管理器 |
| src/ptz | 22 | PTZ 控制 |
| src/advanced | 8 | 高级功能 |
| src/stream | 15 | 流媒体 |
| src/websocket | 12 | WebSocket |
| src/ascom | 16 | ASCOM 驱动 |
| src/storage | 2 | 存储 |
| src/scripts | 3 | 脚本工具 |
| **总计** | **101** | |

---

## 四、WASM SDK (35 文件)

```
src/web/static/websdk/wasm/
├── jsPlugin-3.0.0.min.js     # SDK 主文件
├── webVideoCtrl.js           # 视频控制
├── wasmplayer.min.js         # WASM 播放器
├── encryption/               # 加密模块
│   ├── AES.js
│   ├── crypto-3.1.2.min.js
│   ├── cryptico.min.js
│   └── encryption.js
├── jsPlugin/
│   ├── playctrl/             # 播放控制
│   └── transform/            # 转换
└── playctrl/                 # 播放器
```

---

## 五、精简历史

| 阶段 | 文件数 | 删除 |
|------|--------|------|
| 原始 | 702 | - |
| 第一轮清理 | 383 | 319 |
| 第二轮清理 | 289 | 94 |
| **最终** | **252** | **450 (64%)** |

---

**生成时间**: 2026-06-15
**代码版本**: v7.12
