# AstroHub v7.12 最终文件清单

## 文件统计

```
Python 源码:   109 个
HTML 页面:       7 个
JavaScript:     16 个
WASM:            4 个
DLL:             7 个
配置/文档:      ~15 个
────────────────────
总计:          ~158 个
```

## 目录结构

```
astrohub/
├── src/
│   ├── main/                        (3 Python)
│   │   ├── __init__.py
│   │   ├── constants.py             # 版本号、常量
│   │   ├── main.py                  # ★ 程序入口
│   │   ├── api/
│   │   │   ├── __init__.py
│   │   │   └── router.py
│   │   └── core/
│   │       ├── __init__.py
│   │       ├── config_merger.py
│   │       ├── health_aggregator.py
│   │       └── orchestrator.py      # 模块编排器
│   │
│   ├── api/                         (3 Python)
│   │   ├── __init__.py
│   │   ├── astap_solve.py           # ASTAP 求解
│   │   └── router.py                # ★ API 路由聚合
│   │
│   ├── core/                       (15 Python + 7 DLL)
│   │   ├── __init__.py
│   │   ├── ptz_manager.py          # ★ PTZ 核心管理器 (122KB)
│   │   ├── device_manager.py       # 设备管理
│   │   ├── stream_manager.py       # 流管理
│   │   ├── calibration_manager.py  # 校准管理
│   │   ├── ascom_manager.py        # ASCOM 管理
│   │   ├── auth.py                 # 认证
│   │   ├── ws_manager.py           # WebSocket 管理
│   │   ├── health_monitor.py       # 健康监控
│   │   ├── orchestrator.py         # 编排器
│   │   ├── sadp_discovery.py       # SADP 发现
│   │   ├── net_detector.py         # 网络检测
│   │   ├── file_naming.py          # 文件命名
│   │   ├── nic_selector.py         # 网卡选择
│   │   ├── service_manager.py      # 服务管理
│   │   └── *.dll                   # SADP/OpenSSL DLLs
│   │
│   ├── ptz/                        (22 Python)
│   │   ├── __init__.py
│   │   ├── constants.py
│   │   ├── core/
│   │   │   ├── config.py           # PTZ 配置
│   │   │   ├── logger.py           # PTZ 日志
│   │   │   ├── network.py          # 网络工具
│   │   │   ├── recorder.py         # 录像
│   │   │   ├── system_info.py      # 系统信息
│   │   │   └── ui.py               # UI 工具
│   │   ├── isapi/
│   │   │   ├── client.py           # ★ ISAPI HTTP 客户端
│   │   │   ├── ptz.py              # ★ PTZ 控制
│   │   │   └── capabilities.py     # 设备能力
│   │   ├── ptz/
│   │   │   ├── limits.py           # 限位计算
│   │   │   └── motion.py           # 运动控制
│   │   ├── sadp/
│   │   │   ├── discovery.py        # SADP 发现
│   │   │   └── ip_manager.py       # IP 管理
│   │   └── report/
│   │       ├── generator.py        # 报告生成
│   │       └── packager.py         # 打包
│   │
│   ├── advanced/                    (8 Python)
│   │   ├── __init__.py
│   │   ├── function.py             # ★ 功能探测 (P4.1-P4.21)
│   │   ├── limit.py                # ★ 限位测试 (P6.0-P6.6)
│   │   ├── speed.py                # ★ 速度测试
│   │   ├── device_path.py          # 设备路径
│   │   ├── device_config.py        # 设备配置
│   │   ├── config_writer.py        # 配置写入
│   │   └── onboarding.py           # 设备引导
│   │
│   ├── stream/                     (12 Python)
│   │   ├── __init__.py
│   │   ├── constants.py
│   │   ├── core.py
│   │   ├── api/
│   │   │   ├── models.py
│   │   │   └── router.py
│   │   └── core/
│   │       ├── stream.py           # 流控制
│   │       ├── stream_manager.py   # 流管理器
│   │       ├── distributor.py      # 分发器
│   │       ├── preview.py          # 预览
│   │       ├── recorder.py         # 录像
│   │       ├── transcoder.py       # 转码
│   │       ├── stream_monitor.py   # 监控
│   │       └── logger.py
│   │
│   ├── websocket/                  (12 Python)
│   │   ├── __init__.py
│   │   ├── constants.py
│   │   ├── handlers.py
│   │   ├── server.py
│   │   ├── api/router.py
│   │   └── core/
│   │       ├── ws_manager.py       # WebSocket 管理器
│   │       ├── auth.py
│   │       ├── broadcast.py        # 广播
│   │       ├── message_handler.py  # 消息处理
│   │       └── monitor.py
│   │
│   ├── ascom/                      (16 Python)
│   │   ├── __init__.py
│   │   ├── constants.py
│   │   ├── main.py
│   │   ├── alpaca/
│   │   │   ├── server.py           # Alpaca 服务器
│   │   │   └── telescope.py        # 望远镜驱动
│   │   ├── api/router.py
│   │   └── core/
│   │       ├── driver_manager.py   # 驱动管理
│   │       ├── telescope_driver.py # 望远镜驱动
│   │       ├── dome_driver.py      # 圆顶驱动
│   │       ├── focuser_driver.py   # 调焦驱动
│   │       ├── filter_wheel.py     # 滤镜轮
│   │       ├── weather_station.py  # 气象站
│   │       └── platform_detect.py  # 平台检测
│   │
│   ├── storage/                     (2 Python)
│   │   ├── __init__.py
│   │   └── store.py
│   │
│   └── web/                         (7 HTML + WASM SDK)
│       ├── index.html               # ★ 主页面 (158KB)
│       └── includes/
│           ├── console.html         # 主控台
│           ├── devices.html         # 设备管理
│           ├── advanced.html        # 高级功能
│           ├── dashboard.html       # 仪表盘
│           ├── observation.html     # 观测计划
│           └── replay.html          # 回放
│       └── static/websdk/wasm/      # WASM SDK (20 files)
│           ├── jquery.min.js
│           ├── jsPlugin-3.0.0.min.js
│           ├── webVideoCtrl.js
│           ├── encryption/          (4 files)
│           ├── playctrl/            (10 files)
│           └── transform/           (3 files)
│
├── data/                            # 运行时数据
│   ├── config/
│   ├── devices/
│   └── ...
│
├── log/                             # 运行日志
│
├── documents/                       # 文档
│   ├── ARCHITECTURE.md
│   ├── FILE_ANALYSIS.md
│   ├── FILE_STRUCTURE.md
│   ├── CODE_REUSE_ANALYSIS.md
│   └── CLEANUP_REPORT.md
│
├── config/                          # 配置目录
│
├── requirements.txt                 # Python 依赖
└── test_e2e.py                      # E2E 测试
```

## 模块统计

| 模块 | Python 文件 | 核心文件 |
|------|-------------|----------|
| src/main | 3 | main.py |
| src/api | 3 | router.py |
| src/core | 15 | ptz_manager.py |
| src/ptz | 22 | isapi/client.py, isapi/ptz.py |
| src/advanced | 8 | function.py, limit.py, speed.py |
| src/stream | 12 | stream.py, stream_manager.py |
| src/websocket | 12 | ws_manager.py |
| src/ascom | 16 | driver_manager.py |
| src/storage | 2 | store.py |
| src/web | 7 HTML | index.html |
| **总计** | **109** | |

## WASM SDK (20 文件)

```
src/web/static/websdk/wasm/
├── jquery.min.js               (87 KB)
├── jsPlugin-3.0.0.min.js       (1.0 MB)
├── webVideoCtrl.js             (77 KB)
├── encryption/
│   ├── AES.js                  (17 KB)
│   ├── cryptico.min.js         (44 KB)
│   ├── crypto-3.1.2.min.js     (13 KB)
│   └── encryption.js           (4 KB)
├── playctrl/PlayCtrlWasm/
│   ├── wasmplayer.min.js       (1.6 MB)
│   ├── playctrlV1/Decoder.js   (2.2 MB)
│   ├── playctrlV3/
│   │   ├── Decoder.js          (227 KB)
│   │   ├── Decoder.wasm        (3.5 MB)
│   │   └── Decoder.worker.js   (2 KB)
│   ├── playctrlV3_NoSIMD/
│   │   ├── Decoder.js          (227 KB)
│   │   ├── Decoder.wasm        (3.1 MB)
│   │   └── Decoder.worker.js   (2 KB)
│   └── playctrlV3_NoWorker/
│       ├── Decoder.js          (147 KB)
│       └── Decoder.wasm        (2.9 MB)
└── transform/
    ├── libSystemTransform.js   (301 KB)
    ├── libSystemTransform.wasm (834 KB)
    └── systemTransform-worker.js (10 KB)

总大小: ~15.7 MB
```

## 清理历史

| 阶段 | 文件数 | 减少 |
|------|--------|------|
| 原始备份 | 702 | - |
| 第一轮清理 | 383 | 319 |
| 第二轮清理 | 289 | 94 |
| WASM 清理 | 241 | 48 |
| 备份/日志清理 | 158 | 83 |
| **总减少** | - | **544 (78%)** |

## E2E 测试结果

```
[PASS] 60
[FAIL] 0
```

---

**生成时间**: 2026-06-15 02:48
**代码版本**: v7.12
