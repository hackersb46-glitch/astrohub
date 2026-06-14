# AstroHub v7.12 代码架构完整分析

## 一、项目概述

**AstroHub** 是一个海康威视 PTZ 摄像机控制平台，专为天文观测设计。

- **版本**: v7.12
- **作者**: 雅痞张@南方天文
- **入口**: `src/main/main.py`
- **端口**: 10280

---

## 二、目录结构

```
astrohub/
├── src/
│   ├── main/           # 主程序入口
│   ├── api/            # API 路由聚合
│   ├── core/           # 核心管理器
│   ├── advanced/       # 高级测试功能
│   ├── ptz/            # PTZ 控制模块
│   ├── device/         # 设备管理模块
│   ├── stream/         # 流媒体模块
│   ├── database/       # 数据库模块
│   ├── websocket/      # WebSocket 模块
│   ├── webui/          # Web UI 模块
│   ├── ascom/          # ASCOM 望远镜驱动
│   ├── calibration/    # 校准模块
│   ├── integration/    # 集成模块
│   ├── deployment/     # 部署模块
│   ├── rest_api/       # REST API 模块
│   ├── web/            # 前端文件
│   └── scripts/        # 脚本工具
├── data/               # 运行时数据
├── config/             # 配置文件
├── log/                # 日志文件
└── doc/                # 文档
```

---

## 三、核心模块详解

### 1. 主入口 (src/main/)

#### `main.py` - 程序入口
```
作用: FastAPI 应用入口，启动 Web 服务
关键:
- 创建 FastAPI 应用
- 注册路由 (api_router, health_router)
- ISAPI 代理 (/ISAPI/*)
- WebSocket 代理 (/ws, /{channel}/webSocketVideoCtrlProxy)
- 启动时: SADP 设备发现，管理器初始化

依赖:
- src/api/router.py (API 路由)
- src/core/ptz_manager.py (PTZ 管理)
- src/core/device_manager.py (设备管理)
- src/core/stream_manager.py (流管理)
```

#### `constants.py` - 全局常量
```
作用: 版本号、项目名、模块顺序定义
关键:
- VERSION = "v7.12"
- PROJECT_NAME = "MAIN"
- MODULE_ORDER = [ptz, device, stream, ...]
```

#### `core/orchestrator.py` - 编排器
```
作用: 模块生命周期管理
关键:
- start(): 启动所有模块
- stop(): 停止所有模块
- 健康检查
```

---

### 2. API 路由 (src/api/)

#### `router.py` - 统一 API 路由
```
作用: 整合所有 API 端点到 /api/v1/

端点分类:
┌─────────────────────────────────────────────────────┐
│ 健康检查                                              │
│   GET  /api/v1/health          - 全局健康检查          │
├─────────────────────────────────────────────────────┤
│ 设备发现                                              │
│   GET  /api/v1/discovery/sadp  - SADP 设备发现        │
├─────────────────────────────────────────────────────┤
│ 设备管理                                              │
│   GET    /api/v1/devices            - 设备列表         │
│   POST   /api/v1/devices            - 注册设备         │
│   GET    /api/v1/devices/active     - 上次连接设备     │
│   POST   /api/v1/devices/{id}/connect   - 连接设备    │
│   POST   /api/v1/devices/{id}/disconnect - 断开设备   │
│   DELETE /api/v1/devices/{id}      - 删除设备         │
│   GET    /api/v1/devices/{id}/info - 设备信息         │
├─────────────────────────────────────────────────────┤
│ PTZ 控制                                              │
│   POST /api/v1/ptz/{id}/move      - 方向移动          │
│   POST /api/v1/ptz/{id}/stop      - 停止              │
│   POST /api/v1/ptz/{id}/home      - 归位              │
│   POST /api/v1/ptz/{id}/absolute  - 绝对移动          │
│   GET  /api/v1/ptz/{id}/position  - 获取位置          │
│   GET  /api/v1/ptz/{id}/presets   - 预置点列表        │
│   POST /api/v1/ptz/{id}/preset/{n}    - 前往预置点    │
│   POST /api/v1/ptz/{id}/preset/{n}/set - 保存预置点   │
├─────────────────────────────────────────────────────┤
│ OSD 控制                                              │
│   POST /api/v1/ptz/{id}/osd/ptz   - PTZ 坐标 OSD      │
│   POST /api/v1/ptz/{id}/osd/info  - 信息 OSD          │
├─────────────────────────────────────────────────────┤
│ 图像控制                                              │
│   GET  /api/v1/ptz/{id}/image/settings - 获取画面参数  │
│   PUT  /api/v1/ptz/{id}/image/settings - 更新画面参数  │
├─────────────────────────────────────────────────────┤
│ 高级功能                                              │
│   POST /api/v1/advanced/function/run    - 功能探测    │
│   POST /api/v1/advanced/limit/run       - 限位测试    │
│   POST /api/v1/advanced/speed/run       - 速度测试    │
├─────────────────────────────────────────────────────┤
│ SADP 操作                                             │
│   POST /api/v1/sadp/{mac}/modify-ip  - 修改 IP        │
│   POST /api/v1/sadp/auto-reconnect   - 自动重连       │
├─────────────────────────────────────────────────────┤
│ 系统信息                                              │
│   GET /api/v1/system/info   - 系统硬件信息            │
│   GET /api/v1/system/nics   - 网络接口列表            │
│   GET /api/v1/system/default-ip - 推荐目标 IP         │
└─────────────────────────────────────────────────────┘
```

---

### 3. 核心管理器 (src/core/)

#### `ptz_manager.py` - PTZ 管理器 ⭐核心
```
作用: PTZ 设备控制的核心管理器
功能:
- SADP 设备发现 (discover_devices)
- ISAPI 连接/认证 (connect_device, disconnect_device)
- PTZ 控制 (ptz_move, ptz_stop, ptz_home, ptz_preset)
- 图像参数 (get_image_params, set_image_params)
- 凭据管理 (save_credentials, get_credentials)
- 设备信息 (get_device_info)

关键类:
- PTZManager: 主管理器
- ConfigManager: 配置管理
- Controller: 设备控制器

依赖:
- src/core/sadp_discovery.py (SADP 发现)
- src/ptz/isapi/client.py (ISAPI 客户端)
- src/ptz/isapi/ptz.py (PTZ 控制)
```

#### `device_manager.py` - 设备管理器
```
作用: 设备注册、状态追踪、分组管理
功能:
- register_device() - 注册设备
- unregister_device() - 注销设备
- get_device() - 获取设备信息
- list_devices() - 设备列表
- update_status() - 更新状态
- heartbeat() - 心跳检测

数据存储: data/devices/{mac}/info.json
```

#### `stream_manager.py` - 流管理器
```
作用: 视频流管理
功能:
- start_stream() - 启动流
- stop_stream() - 停止流
- get_stream_url() - 获取流地址
```

#### `sadp_discovery.py` - SADP 发现
```
作用: 海康威视 SADP 协议设备发现
功能:
- discover_devices() - 多播发现设备
- modify_ip() - 修改设备 IP
- 检测海康 MAC (HIKVISION_MAC_OUI)

协议:
- 多播地址: 239.255.255.250:37020
- 超时: 3000ms
```

#### `orchestrator.py` - 模块编排器
```
作用: 管理所有模块的生命周期
功能:
- start() - 启动所有模块
- stop() - 停止所有模块
- health_check() - 健康检查
```

---

### 4. 高级功能模块 (src/advanced/)

#### `function.py` - 功能探测 ⭐重要
```
作用: 探测设备支持的 ISAPI 功能 (P4.1-P4.21)
功能:
- verify_home_preset() - 验证 HOME 预置点
- run_function_detection() - 执行功能探测
- 18 项功能探测:
  P4.1  - IrLED 红外补光
  P4.2  - 白平衡
  P4.3  - Gain 模拟增益
  P4.4  - Focus 聚焦
  P4.5  - 快门速度
  P4.6  - 慢快门
  P4.7  - 光圈 Iris
  P4.9  - 数字降噪-时域
  P4.10 - 数字降噪-空域
  ... 等

输出: data/devices/{mac}/function.json
```

#### `limit.py` - 限位测试 ⭐重要
```
作用: 测试 PTZ 轴限位 (P6.0-P6.6)
功能:
- check_ptz_support() - P6.0 检查轴支持
- test_pan_limit() - P6.3 P 轴限位
- test_tilt_limit() - P6.4 T 轴限位/翻转
- test_zoom_limit() - P6.5 Z 轴限位
- restore_device() - P6.6 设备还原

输出: data/devices/{mac}/limit.json, limit.csv
```

#### `speed.py` - 速度测试 ⭐重要
```
作用: 测试 PTZ 运动速度
功能:
- measure_speed_single() - 单点速度测量
- run_all_tests() - 完整测试流程
- 支持 lite/medium/full 三种测试配置

输出: data/devices/{mac}/speed.json, speed.csv
```

#### `device_path.py` - 设备路径管理
```
作用: 统一管理设备数据路径
功能:
- get_device_info() - 获取设备信息
- get_data_path_read() - 读取路径
- get_data_path_write() - 写入路径
- get_devices_dir() - 设备目录

路径规则: data/devices/{mac}/{model_short}/
```

#### `device_config.py` - 设备配置
```
作用: 设备配置读写
功能:
- get_current_device() - 获取当前设备
- set_current_device() - 设置当前设备
- load_config() / save_config() - 配置 IO
```

#### `onboarding.py` - 设备引导
```
作用: 新设备引导流程
功能:
- 自动发现、连接、测试
```

---

### 5. PTZ 模块 (src/ptz/)

#### `isapi/client.py` - ISAPI 客户端
```
作用: 海康威视 ISAPI HTTP 客户端
功能:
- get(endpoint) - GET 请求
- put(endpoint, xml) - PUT 请求
- post(endpoint, xml) - POST 请求
- Digest Auth 认证
- 错误码解析

关键类:
- ISAPIClient: HTTP 客户端
- ISAPIResponse: 响应封装
```

#### `isapi/ptz.py` - PTZ 控制器
```
作用: PTZ 运动 ISAPI 实现
功能:
- continuous_move() - 连续移动
- absolute_move() - 绝对移动
- get_position() - 获取位置
- goto_preset() - 前往预置点
- set_preset() - 保存预置点
- stop() - 停止

关键类:
- PTZController: PTZ 控制器
```

#### `isapi/capabilities.py` - 能力查询
```
作用: 查询设备 ISAPI 能力
功能:
- 获取支持的端点
- 获取参数范围
```

#### `sadp/discovery.py` - SADP 发现
```
作用: SADP 协议实现
功能:
- discover_devices() - 多播发现
- modify_ip() - 修改 IP
```

#### `core/config.py` - PTZ 配置
```
作用: PTZ 配置管理
```

#### `core/logger.py` - PTZ 日志
```
作用: PTZ 模块日志
```

---

### 6. 设备模块 (src/device/)

#### `core/device_manager.py` - 设备管理核心
```
作用: 设备管理业务逻辑
```

#### `isapi/client.py` - 设备 ISAPI 客户端
```
作用: 设备 ISAPI 操作
```

#### `core/sadp_discovery.py` - 设备 SADP 发现
```
作用: 设备发现逻辑
```

---

### 7. 前端 (src/web/)

#### `index.html` - 主页面 ⭐核心前端
```
作用: 单页应用主页面
功能:
- 导航 (仪表盘/设备管理/主控台/高级功能/回放)
- PTZ 控制 UI
- 设备管理 UI
- 高级功能 UI
- WASM 视频播放器

包含 JavaScript:
- apiGet/apiPost - API 封装
- ptzMove/ptzStop/ptzPreset - PTZ 控制
- loadShutter/loadIris/loadGain - 参数加载
- connectDevice/disconnectDevice - 设备连接
- showToast - 消息提示
```

#### `includes/console.html` - 主控台页面
```
作用: PTZ 控制面板
功能:
- PTZ 方向控制 (9 方向按钮)
- 预置点管理
- 变焦/对焦控制
- 跟踪控制 (恒星/月球/太阳)
- 媒体操作 (截图/录像/Live Stack)
- 画面控制 (亮度/对比度/白平衡/曝光/降噪)
```

#### `includes/devices.html` - 设备管理页面
```
作用: 设备列表和管理
功能:
- 设备表格
- 发现设备按钮
- 快速连接开关
- 设备连接/断开
```

#### `includes/advanced.html` - 高级功能页面
```
作用: 测试项目页面
功能:
- 功能测试
- 限位测试
- 速度测试
- 推流/存储
- 天文校准
```

#### `static/websdk/wasm/` - WASM SDK
```
作用: 海康威视 WASM 视频播放器
关键文件:
- jsPlugin-3.0.0.min.js - SDK 主文件
- wasmplayer.min.js - WASM 播放器
- webVideoCtrl.js - 视频控制
```

---

## 四、数据流

### 设备连接流程
```
1. 用户点击"发现设备"
   → GET /api/v1/discovery/sadp
   → SADPManager.discover_devices()
   → 返回设备列表

2. 用户点击"连接"
   → POST /api/v1/devices/{mac}/connect
   → PTZManager.connect_device(ip, username, password)
   → ISAPIClient 认证
   → 保存到 active_device
   → 返回成功

3. 前端加载设备参数
   → GET /api/v1/ptz/{ip}/function
   → 加载曝光/白平衡/增益等参数
   → 更新 UI 控件
```

### PTZ 控制流程
```
1. 用户点击方向按钮
   → onmousedown="ptzMove('up')"
   → POST /api/v1/ptz/{ip}/move
   → PTZManager.ptz_move(ip, direction='up', speed=4)
   → PTZController.continuous_move(pan=57, tilt=0)
   → ISAPI PUT /PTZCtrl/channels/1/continuous

2. 用户松开按钮
   → onmouseup="ptzStop()"
   → POST /api/v1/ptz/{ip}/stop
   → PTZController.continuous_move(0, 0, 0)
```

### 视频流流程
```
1. 用户点击"播放"
   → clickStartRealPlay()
   → WebVideoCtrl.I_StartRealPlay()
   → WebSocket 连接 /{channel}/webSocketVideoCtrlProxy
   → 服务端代理到 camera:7681
   → WASM 解码渲染
```

---

## 五、配置文件

### `data/config/local.json` - 本地配置
```json
{
  "hostname": "Astro-AIO",
  "cpu_model": "AMD Ryzen 9",
  "ram_gb": 64,
  "selected_nic": {
    "name": "以太网",
    "ip": "192.168.5.1"
  }
}
```

### `data/devices/{mac}/info.json` - 设备信息
```json
{
  "mac": "240f9b764193",
  "ip": "192.168.5.72",
  "model": "DS-2DC7423IW-D",
  "name": "主望远镜",
  "username": "admin",
  "password": "***"
}
```

### `data/registry.json` - 设备注册表
```json
{
  "active_device": "240f9b764193",
  "last_connected": "240f9b764193"
}
```

---

## 六、关键常量

```python
# PTZ 控制
SADP_MULTICAST_ADDR = "239.255.255.250"
SADP_PORT = 37020
ISAPI_CHANNEL = 1
DEFAULT_PTZ_PRESET = 10
HOME_COORDS = {"pan": 1800, "tilt": 450, "zoom": 10}

# 速度映射 (1-7 档 → ISAPI 值)
speed_map = {
    1: 14, 2: 28, 3: 43, 4: 57,
    5: 71, 6: 86, 7: 100
}

# ISAPI 端点
/Image/channels/1/exposure      # 曝光模式
/Image/channels/1/Shutter       # 快门
/Image/channels/1/Iris          # 光圈
/Image/channels/1/gain          # 增益
/Image/channels/1/whiteBalance  # 白平衡
/Image/channels/1/noiseReduce   # 降噪
/PTZCtrl/channels/1/continuous  # 连续移动
/PTZCtrl/channels/1/absolute    # 绝对移动
```

---

## 七、已删除模块

以下模块在 v7.12 中已删除（导入已注释）：

- `calibrate/` - 校准模块
- `stack/` - Live Stack 模块

---

## 八、运行命令

```bash
# 启动服务
cd astrohub
python -m src.main.main --headless

# 访问
http://localhost:10280

# 健康检查
curl http://localhost:10280/api/v1/health
```

---

## 九、依赖关系图

```
main.py
├── api/router.py
│   ├── core/ptz_manager.py
│   │   ├── core/sadp_discovery.py
│   │   ├── ptz/isapi/client.py
│   │   └── ptz/isapi/ptz.py
│   ├── core/device_manager.py
│   ├── core/stream_manager.py
│   ├── advanced/function.py
│   ├── advanced/limit.py
│   └── advanced/speed.py
├── core/orchestrator.py
└── web/index.html
```

---

**文档版本**: 2026-06-15
**代码版本**: v7.12
