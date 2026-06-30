# AstroHub 系统架构文档

**版本**: v7.59  
**更新日期**: 2026-06-18  
**作者**: 开发工厂

---

## 目录

1. [系统概述](#系统概述)
2. [目录结构](#目录结构)
3. [核心模块](#核心模块)
4. [模块依赖关系](#模块依赖关系)
5. [API 路由结构](#api-路由结构)
6. [前端架构](#前端架构)
7. [数据流](#数据流)
8. [日志系统](#日志系统)

---

## 系统概述

AstroHub 是一个 PTZ（云台）设备管理系统，主要用于：
- 海康威视 PTZ 设备的发现、连接和控制
- 实时视频流管理（WASM SDK）
- 设备功能测试（限位、速度、功能探测）
- ASCOM 望远镜控制集成
- 图像参数调节（白平衡、曝光、光圈等）

**技术栈**:
- 后端: Python 3.10+, FastAPI, uvicorn
- 前端: HTML5, JavaScript (原生)
- 视频: 海康 WASM SDK (WebVideoCtrl)
- 通信: ISAPI (HTTP), WebSocket

---

## 目录结构

```
astrohub/
├── src/                          # 源代码目录
│   ├── main/                     # 主程序入口
│   │   ├── main.py              # 应用启动入口
│   │   ├── constants.py         # 全局常量 (VERSION等)
│   │   └── core/                # 主程序核心
│   │       ├── orchestrator.py  # 启动编排器
│   │       ├── config_merger.py # 配置合并
│   │       └── health_aggregator.py # 健康检查聚合
│   │
│   ├── api/                      # API 路由层
│   │   ├── router.py            # 主路由 (所有API端点)
│   │   └── astap_solve.py       # ASTAP 天文板解算
│   │
│   ├── core/                     # 核心业务逻辑
│   │   ├── ptz_controller.py    # PTZ 设备控制器 (核心)
│   │   ├── device_manager.py    # 设备管理器
│   │   ├── stream_manager.py    # 流管理器
│   │   ├── auth.py              # 认证管理
│   │   ├── calibration_manager.py # 校准管理
│   │   ├── health_monitor.py    # 健康监控
│   │   ├── orchestrator.py      # 编排器
│   │   ├── ws_manager.py        # WebSocket 管理
│   │   ├── ascom_manager.py     # ASCOM 设备管理
│   │   ├── sadp_discovery.py    # SADP 设备发现
│   │   ├── net_detector.py      # 网络检测
│   │   ├── nic_selector.py      # 网卡选择
│   │   ├── file_naming.py       # 文件命名
│   │   └── service_manager.py   # 服务管理
│   │
│   ├── advanced/                 # 高级功能
│   │   ├── function.py          # 功能探测
│   │   ├── limit.py             # 限位测试
│   │   ├── speed.py             # 速度测试
│   │   ├── onboarding.py        # 设备引导
│   │   ├── startup.py           # 启动信息收集
│   │   ├── config_writer.py     # 配置写入
│   │   ├── device_config.py     # 设备配置
│   │   └── device_path.py       # 设备路径管理
│   │
│   ├── ptz/                      # PTZ 底层实现
│   │   ├── constants.py         # PTZ 常量
│   │   ├── core/                # PTZ 核心
│   │   │   ├── config.py        # 配置
│   │   │   ├── logger.py        # 日志
│   │   │   ├── network.py       # 网络
│   │   │   ├── system_info.py   # 系统信息
│   │   │   └── ui.py            # UI 辅助
│   │   ├── isapi/               # ISAPI 协议实现
│   │   │   ├── client.py        # ISAPI 客户端
│   │   │   ├── ptz.py           # PTZ 控制
│   │   │   └── capabilities.py  # 能力查询
│   │   ├── sadp/                # SADP 发现
│   │   │   └── discovery.py     # 发现实现
│   │   └── report/              # 报告生成
│   │       └── report.py        # 报告
│   │
│   ├── stream/                   # 流媒体管理
│   │   ├── constants.py         # 流常量
│   │   ├── core.py              # 流核心
│   │   ├── stream_wasm.py       # WASM 流
│   │   ├── api/                 # 流 API
│   │   │   ├── router.py        # 流路由
│   │   │   └── models.py        # 数据模型
│   │   └── core/                # 流核心模块
│   │       ├── stream.py        # 流管理
│   │       ├── stream_manager.py # 流管理器
│   │       ├── stream_monitor.py # 流监控
│   │       ├── distributor.py   # 分发器
│   │       ├── recorder.py      # 录制器
│   │       ├── preview.py       # 预览
│   │       ├── transcoder.py    # 转码器
│   │       └── logger.py        # 日志
│   │
│   ├── websocket/                # WebSocket 实现
│   │   ├── constants.py         # WS 常量
│   │   ├── server.py            # WS 服务器
│   │   ├── handlers.py          # 消息处理器
│   │   ├── api/                 # WS API
│   │   │   └── router.py        # WS 路由
│   │   └── core/                # WS 核心
│   │       ├── ws_manager.py    # WS 管理器
│   │       ├── auth.py          # 认证
│   │       ├── broadcast.py     # 广播
│   │       ├── message_handler.py # 消息处理
│   │       └── monitor.py       # 监控
│   │
│   ├── ascom/                    # ASCOM 望远镜集成
│   │   ├── constants.py         # ASCOM 常量
│   │   ├── main.py              # ASCOM 主程序
│   │   ├── api/                 # ASCOM API
│   │   │   └── router.py        # ASCOM 路由
│   │   ├── alpaca/              # Alpaca 协议
│   │   │   ├── server.py        # Alpaca 服务器
│   │   │   └── telescope.py     # 望远镜实现
│   │   └── core/                # ASCOM 核心
│   │       ├── driver_manager.py # 驱动管理
│   │       ├── telescope_driver.py # 望远镜驱动
│   │       ├── dome_driver.py   # 圆顶驱动
│   │       ├── focuser_driver.py # 调焦器驱动
│   │       ├── filter_wheel.py  # 滤镜轮
│   │       ├── weather_station.py # 气象站
│   │       └── platform_detect.py # 平台检测
│   │
│   ├── storage/                  # 存储管理
│   │   └── store.py             # 数据存储
│   │
│   ├── web/                      # 前端文件
│   │   ├── index.html           # 主页面 (包含所有JS逻辑)
│   │   └── includes/            # 页面组件
│   │       ├── console.html     # 主控台页面
│   │       ├── advanced.html    # 高级功能页面
│   │       ├── devices.html     # 设备管理页面
│   │       ├── dashboard.html   # 仪表盘页面
│   │       ├── observation.html # 观测页面
│   │       └── replay.html      # 回放页面
│   │
│   ├── config.py                 # 配置管理
│   ├── config_paths.py           # 配置路径
│   ├── database.py               # 数据库
│   ├── logger.py                 # 日志系统
│   ├── operation_logger.py       # 操作日志系统
│   └── env_check.py              # 环境检查
│
├── data/                         # 数据目录
│   ├── devices/                  # 设备数据
│   ├── config/                   # 配置文件
│   ├── logs/                     # 日志文件
│   └── reports/                  # 报告文件
│
├── logs/                         # 运行时日志
│   ├── astrohub_*.log           # 系统日志
│   └── operation_*.log          # 操作日志
│
├── backup_*/                     # 备份目录
└── documents/                    # 文档目录
    └── ARCHITECTURE.md          # 本文档
```

---

## 核心模块

### 1. PTZController (核心控制器)

**文件**: `src/core/ptz_controller.py`

**职责**:
- 设备发现 (SADP)
- 设备连接/断开
- PTZ 移动控制
- 预置点管理
- 图像参数控制
- OSD 控制
- 截图/录像

**依赖**:
- `src.ptz.isapi.client` - ISAPI 通信
- `src.ptz.isapi.ptz` - PTZ 控制
- `src.ptz.sadp.discovery` - 设备发现
- `src.core.file_naming` - 文件命名
- `src.core.net_detector` - 网络检测

### 2. DeviceManager (设备管理器)

**文件**: `src/core/device_manager.py`

**职责**:
- 设备注册/注销
- 设备状态管理
- 设备列表维护

### 3. StreamManager (流管理器)

**文件**: `src/core/stream_manager.py`

**职责**:
- 视频流管理
- 流分发
- 流监控

### 4. AuthManager (认证管理器)

**文件**: `src/core/auth.py`

**职责**:
- 设备凭据管理
- Token 生成/验证

### 5. OperationLogger (操作日志)

**文件**: `src/operation_logger.py`

**职责**:
- 记录所有用户操作
- 写入日志文件 (`logs/operation_*.log`)
- 提供日志查询 API

**日志格式**:
```
[2026-06-18 05:33:11.992] [INFO   ] [operation_logger] [image] exposure: {"device": "192.168.5.72", "mode": "auto"}
```

---

## 模块依赖关系

### 核心依赖链

```
main.py
├── api/router.py (所有API端点)
│   ├── core/ptz_controller.py (核心控制器)
│   │   ├── ptz/isapi/client.py (ISAPI通信)
│   │   ├── ptz/isapi/ptz.py (PTZ控制)
│   │   └── ptz/sadp/discovery.py (设备发现)
│   ├── core/device_manager.py
│   ├── core/stream_manager.py
│   ├── core/auth.py
│   └── operation_logger.py
├── config.py (配置)
├── logger.py (日志)
└── main/constants.py (常量)
```

### 高级功能依赖链

```
advanced/function.py (功能探测)
├── advanced/device_path.py
├── ptz/constants.py
└── ptz/isapi/client.py

advanced/limit.py (限位测试)
├── advanced/device_path.py
├── ptz/constants.py
├── ptz/core/logger.py
├── ptz/isapi/client.py
└── ptz/isapi/ptz.py

advanced/speed.py (速度测试)
└── advanced/device_path.py

advanced/onboarding.py (设备引导)
├── advanced/config_writer.py
└── config_paths.py
```

### 流媒体依赖链

```
stream/core/stream.py
├── stream/constants.py
└── stream/core/logger.py

stream/core/recorder.py
├── stream/constants.py
└── stream/core/logger.py

stream/stream_wasm.py
└── (WASM SDK 集成)
```

### WebSocket 依赖链

```
websocket/server.py
├── websocket/constants.py
├── websocket/core/ws_manager.py
├── websocket/core/auth.py
├── websocket/core/broadcast.py
├── websocket/core/message_handler.py
├── websocket/core/monitor.py
└── websocket/handlers.py
```

### ASCOM 依赖链

```
ascom/api/router.py
├── ascom/constants.py
└── ascom/core/driver_manager.py
    ├── ascom/core/telescope_driver.py
    ├── ascom/core/dome_driver.py
    ├── ascom/core/focuser_driver.py
    ├── ascom/core/filter_wheel.py
    └── ascom/core/weather_station.py
```

---

## API 路由结构

### 系统端点

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | `/api/v1/health` | 全局健康检查 |
| GET | `/api/v1/version` | 获取版本号 |
| GET | `/api/v1/localhost` | 本机信息 |
| GET | `/api/v1/system/info` | 系统硬件信息 |
| GET | `/api/v1/system/nics` | 网络接口列表 |
| GET | `/api/v1/system/default-ip` | 推荐目标IP |
| GET | `/api/v1/system/operations` | 操作日志(内存) |
| GET | `/api/v1/log/operations/file` | 操作日志(文件) |
| POST | `/api/v1/log/operation` | 记录操作日志 |

### 设备发现端点

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | `/api/v1/discovery/sadp` | SADP 设备发现 |
| POST | `/api/v1/sadp/{mac}/modify-ip` | SADP 修改设备IP |
| POST | `/api/v1/sadp/auto-reconnect` | 已知设备重连 |
| GET | `/api/v1/sadp/error-codes` | 错误代码参考 |

### 设备管理端点

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | `/api/v1/devices` | 设备列表 |
| GET | `/api/v1/devices/active` | 获取上次连接设备 |
| POST | `/api/v1/devices/active` | 设置上次连接设备 |
| POST | `/api/v1/devices` | 注册设备 |
| POST | `/api/v1/devices/{device_id}/connect` | 连接设备 |
| POST | `/api/v1/devices/{device_id}/disconnect` | 断开设备 |
| DELETE | `/api/v1/devices/{device_id}` | 删除设备 |
| GET | `/api/v1/devices/{device_id}/info` | 设备详细信息 |
| PUT | `/api/v1/devices/{device_id}/network` | 修改网络配置 |

### PTZ 控制端点

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | `/api/v1/ptz/connected` | 获取已连接设备状态 |
| POST | `/api/v1/ptz/{device_id}/move` | PTZ 移动 |
| POST | `/api/v1/ptz/{device_id}/home` | PTZ 归位 |
| POST | `/api/v1/ptz/{device_id}/stop` | PTZ 停止 |
| POST | `/api/v1/ptz/{device_id}/focus/mode` | 设置对焦模式 |
| GET | `/api/v1/ptz/{device_id}/focus/mode` | 获取对焦模式 |
| GET | `/api/v1/ptz/{device_id}/presets` | 获取预置点列表 |
| POST | `/api/v1/ptz/{device_id}/preset/{preset_id}` | 预置位前往 |
| POST | `/api/v1/ptz/{device_id}/preset/{preset_id}/set` | 设置预置位 |
| POST | `/api/v1/ptz/{device_id}/absolute` | 绝对位置移动 |
| GET | `/api/v1/ptz/{device_id}/position` | 获取PTZ位置 |
| POST | `/api/v1/ptz/{device_id}/osd/toggle` | 切换OSD显示 |
| POST | `/api/v1/ptz/{device_id}/osd/ptz` | 切换PTZ OSD |
| POST | `/api/v1/ptz/{device_id}/osd/info` | 切换Info OSD |
| POST | `/api/v1/ptz/{device_id}/capture` | 截图 |
| POST | `/api/v1/ptz/{device_id}/record/start` | 开始录像 |
| POST | `/api/v1/ptz/{device_id}/record/stop` | 停止录像 |

### 图像控制端点

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | `/api/v1/ptz/{device_id}/image/settings` | 获取图像设置 |
| PUT | `/api/v1/ptz/{device_id}/image/settings` | 更新图像设置 |
| GET | `/api/v1/ptz/{device_id}/image/whitebalance` | 获取白平衡 |
| POST | `/api/v1/ptz/{device_id}/image/whitebalance` | 设置白平衡 |
| GET | `/api/v1/ptz/{device_id}/image/exposure` | 获取曝光模式 |
| POST | `/api/v1/ptz/{device_id}/image/exposure` | 设置曝光模式 |
| GET | `/api/v1/ptz/{device_id}/image/shutter` | 获取快门 |
| POST | `/api/v1/ptz/{device_id}/image/shutter` | 设置快门 |
| GET | `/api/v1/ptz/{device_id}/image/iris` | 获取光圈 |
| POST | `/api/v1/ptz/{device_id}/image/iris` | 设置光圈 |
| GET | `/api/v1/ptz/{device_id}/image/gain` | 获取增益 |
| POST | `/api/v1/ptz/{device_id}/image/gain` | 设置增益 |
| GET | `/api/v1/ptz/{device_id}/image/sharpness` | 获取锐度 |
| POST | `/api/v1/ptz/{device_id}/image/sharpness` | 设置锐度 |
| GET | `/api/v1/ptz/{device_id}/image/noisereduce` | 获取降噪 |
| POST | `/api/v1/ptz/{device_id}/image/noisereduce` | 设置降噪 |
| POST | `/api/v1/ptz/{device_id}/image/reset` | 重置图像设置 |

### 高级功能端点

| 方法 | 路径 | 描述 |
|------|------|------|
| POST | `/api/v1/advanced/function/run` | 功能探测 |
| POST | `/api/v1/advanced/limit/run` | 限位测试 |
| POST | `/api/v1/advanced/speed/run` | 速度测试 |
| POST | `/api/v1/advanced/onboarding/start` | 开始引导 |
| POST | `/api/v1/advanced/onboarding/complete` | 完成引导 |
| POST | `/api/v1/advanced/onboarding/reset` | 重置引导 |
| POST | `/api/v1/advanced/onboarding/run` | 完整执行引导 |

### ASCOM 端点

| 方法 | 路径 | 描述 |
|------|------|------|
| POST | `/api/v1/ascom/{ascom_type}/connect` | 连接ASCOM设备 |
| POST | `/api/v1/ascom/telescope/slew` | 望远镜Slew |
| POST | `/api/v1/ascom/telescope/tracking` | 设置跟踪模式 |
| POST | `/api/v1/ascom/telescope/disconnect` | 断开望远镜 |
| GET | `/api/v1/ascom/telescope/position` | 查询望远镜位置 |
| POST | `/api/v1/ascom/telescope/abort` | 取消Slew |

### WebSocket 端点

| 方法 | 路径 | 描述 |
|------|------|------|
| WS | `/ws` | WebSocket 连接 |
| GET | `/api/v1/ws/stats` | WebSocket 连接统计 |
| GET | `/api/v1/ws/connections` | WebSocket 连接列表 |

---

## 前端架构

### 主页面结构

**文件**: `src/web/index.html`

```
index.html
├── 头部 (header)
│   ├── Logo
│   ├── 状态栏 (ISAPI/WASM状态)
│   └── 时钟
├── 导航栏 (nav)
│   ├── 主控台
│   ├── 设备管理
│   ├── 高级功能
│   ├── 观测
│   └── 回放
├── 页面容器
│   ├── console.html (主控台)
│   ├── devices.html (设备管理)
│   ├── advanced.html (高级功能)
│   ├── observation.html (观测)
│   └── replay.html (回放)
└── JavaScript 逻辑
    ├── 全局函数
    ├── API 调用
    ├── WASM SDK 集成
    ├── operationLog() (用户操作日志)
    └── mediaLog() (媒体/连接日志)
```

### 主控台页面 (console.html)

```
console.html
├── 左侧 (console-left)
│   ├── 运动控制 (ptzControlSection)
│   │   ├── 方向控制 (9个按钮)
│   │   ├── 速度滑块
│   │   ├── 光圈/快门/R/B/降噪 显示
│   │   ├── P/T/Z 显示
│   │   ├── 预置点选择
│   │   └── 变焦/对焦控制
│   └── 媒体信息 (mediaLogSection)
│       └── mediaLogBox (连接/登录/码流日志)
├── 中间 (console-center)
│   ├── 视频区域 (divPlugin - WASM)
│   ├── 媒体操作 (mediaControlSection)
│   │   ├── 码流选择
│   │   ├── 截图/录像
│   │   └── Live Stack
│   └── 跟踪控制 (trackControlSection)
│       └── 恒星/月球/太阳/关闭跟踪
└── 右侧 (console-right)
    ├── 操作日志 (logControlSection)
    │   └── operationLogBox (用户操作日志)
    └── 画面控制 (imageControlSection)
        ├── 亮度/对比度/饱和度/锐度
        ├── 白平衡模式/R/B增益
        ├── 降噪(空域/时域)
        ├── 曝光模式/快门/光圈/增益
        └── 颜色(亮度/对比度/饱和度)
```

### 前端函数分类

#### 全局函数 (index.html)

| 函数 | 描述 |
|------|------|
| `init()` | 初始化 |
| `connectDevice(ip)` | 连接设备 |
| `disconnectDevice(ip)` | 断开设备 |
| `deleteDevice(id)` | 删除设备 |
| `operationLog(msg, type)` | 记录用户操作日志 |
| `mediaLog(msg, type)` | 记录媒体/连接日志 |
| `clickLogin2()` | WASM SDK 登录 |
| `clickStartRealPlay(options)` | 开始播放 |
| `changeStreamType(streamType)` | 切换码流 |
| `setTracking(mode)` | 设置跟踪模式 |
| `consoleSnapshot()` | 截图 |
| `consoleRecordStart()` | 开始录像 |
| `consoleRecordStop()` | 停止录像 |
| `ptzGotoSelectedPreset()` | 前往预置点 |
| `ptzSetSelectedPreset()` | 保存预置点 |
| `ptzHome()` | 归位 |
| `setFocusMode(mode)` | 设置对焦模式 |
| `adjustImage(param, value)` | 调整图像参数 |
| `togglePtzOsd(enabled)` | 切换PTZ OSD |
| `toggleInfoOsd(enabled)` | 切换Info OSD |

#### 画面控制函数 (console.html)

| 函数 | 描述 |
|------|------|
| `setWhiteBalanceMode(mode)` | 设置白平衡模式 |
| `setWhiteBalanceGain(channel, value)` | 设置白平衡增益 |
| `setNoiseReduce(type, value)` | 设置降噪 |
| `setExposureMode(mode)` | 设置曝光模式 |
| `setShutterSpeed(value)` | 设置快门 |
| `setIris(value)` | 设置光圈 |
| `setGain(value)` | 设置增益 |
| `setSharpness(value)` | 设置锐度 |
| `resetImageControls()` | 重置图像控制 |
| `loadDeviceImageParams(deviceIp)` | 加载设备图像参数 |
| `loadAllImageParams(deviceIp)` | 加载所有图像参数 |

#### 高级功能函数 (advanced.html)

| 函数 | 描述 |
|------|------|
| `selectAdvTest(test)` | 选择测试 |
| `runAdvTest()` | 运行测试 |
| `stopAdvTest()` | 停止测试 |
| `renderAdvResult(result)` | 渲染测试结果 |
| `startAstroCalibration()` | 开始天文校准 |

---

## 数据流

### 设备连接流程

```
前端                    后端                      设备
 │                       │                         │
 ├── POST /connect ─────>│                         │
 │                       ├── ISAPI Login ─────────>│
 │                       │<── 登录成功 ────────────│
 │                       ├── 保存凭据              │
 │                       ├── 更新状态              │
 │<── 连接成功 ──────────│                         │
 │                       │                         │
 ├── WASM Login ────────>│                         │
 │                       ├── WebSocket 代理        │
 │<── 视频播放 ──────────│<── 视频流 ──────────────│
```

### 操作日志流程

```
用户操作
   │
   ├──> 前端函数 (如 setExposureMode)
   │       │
   │       ├──> API 调用 (POST /image/exposure)
   │       │       │
   │       │       └──> 后端处理 + log_info()
   │       │               │
   │       │               └──> 写入 logs/operation_*.log
   │       │
   │       └──> operationLog() / mediaLog()
   │               │
   │               └──> 显示在前端面板
```

### 图像参数设置流程

```
前端                     后端                      设备
 │                        │                         │
 ├── POST /image/exposure ─>│                        │
 │    {mode: "auto"}       │                         │
 │                        ├── log_info("image", "exposure", ...)
 │                        │                         │
 │                        ├── PUT /Image/channels/1/exposure ─>│
 │                        │                         │
 │                        │<── 200 OK ──────────────│
 │                        │                         │
 │<── {success: true} ────│                         │
 │                        │                         │
 └── operationLog("曝光: 自动")                      │
```

---

## 日志系统

### 系统日志

**文件**: `logs/astrohub_*.log`

**格式**:
```
[2026-06-18 05:33:08] [INFO   ] [src.api.router] 设备已连接: 192.168.5.72
```

**配置**: `src/logger.py`

### 操作日志

**文件**: `logs/operation_*.log`

**格式**:
```
[2026-06-18 05:33:11.992] [INFO   ] [operation_logger] [image] exposure: {"device": "192.168.5.72", "mode": "auto"}
```

**配置**: `src/operation_logger.py`

**记录内容**:
- 设备连接/断开
- PTZ 操作 (归位、预置点、OSD)
- 图像参数设置 (白平衡、曝光、光圈等)
- 截图/录像
- ASCOM 操作

### 前端日志显示

| 面板 | 函数 | 显示内容 |
|------|------|----------|
| 操作日志 (右侧) | `operationLog()` | 用户主动操作 |
| 媒体信息 (左侧) | `mediaLog()` | 连接/登录/码流事件 |

---

## 附录

### 配置文件位置

| 文件 | 路径 | 描述 |
|------|------|------|
| 系统配置 | `data/config/config.json` | 全局配置 |
| 设备配置 | `data/devices/{mac}/config.json` | 设备配置 |
| 功能探测 | `data/devices/{mac}/function.json` | 功能探测结果 |
| 限位测试 | `data/devices/{mac}/limit.json` | 限位测试结果 |
| 速度测试 | `data/devices/{mac}/speed.json` | 速度测试结果 |

### 数据目录结构

```
data/
├── config/
│   └── config.json          # 全局配置
├── devices/
│   └── {mac}/
│       ├── config.json      # 设备配置
│       ├── function.json    # 功能探测
│       ├── limit.json       # 限位测试
│       ├── limit.csv        # 限位详细数据
│       ├── speed.json       # 速度测试
│       └── speed.csv        # 速度详细数据
├── logs/                    # 系统日志
├── reports/                 # 报告
└── captures/                # 截图
```

---

**文档结束**
