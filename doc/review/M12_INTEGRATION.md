# M12_INTEGRATION.md - 统一集成与打包规范

> **版本:** v2.0 | **作者:** 雅痞张@南方天文 | **日期:** 2026-05-05

---

## 背景

现有 M1-M11 是 11 个独立的 FastAPI 微服务，各自有独立的 main.py/constants.py/logger。
用户需要**一个完整的 Web 应用**，最终封装为单个 AstroHub.exe。

**产品形态：**
- 双击 AstroHub.exe → 自检环境 → 启动服务端 → 自动打开浏览器窗口（默认 1600x900）
- 支持服务模式：启动后可通过 IP 地址访问
- 所有模块集成在同一个 FastAPI 进程中
- **Portable 应用**：免安装，解压/复制即用
- **跨平台**：Windows (.exe) + macOS (.app)

---

## P0: 统一项目结构

### P0.1 目录结构
删除 M1-M11 的 m*/ 分散结构，整合为统一项目：

`
astro_hub/
├── src/
│   ├── __init__.py              # 包元信息
│   ├── main.py                  # 唯一入口 (FastAPI + pywebview)
│   ├── config.py                # 统一配置 (端口/路径/密钥)
│   ├── database.py              # 统一数据库层 (复用 M5 db_manager)
│   ├── logger.py                # 统一日志 (单例)
│   ├── env_check.py             # 环境自检 + 自动修复
│   ├── core/                    # 业务核心
│   │   ├── ptz_manager.py       # M1 → 云台控制
│   │   ├── device_manager.py    # M2 → 设备管理
│   │   ├── stream_manager.py    # M3 → 流服务
│   │   ├── calibration_manager.py # M4 → 校准
│   │   ├── device_repo.py       # M5 → 数据仓库
│   │   ├── auth.py              # M7 → 认证
│   │   ├── ws_manager.py        # M8 → WebSocket
│   │   ├── ascom_manager.py     # M9 → ASCOM 驱动
│   │   ├── orchestrator.py      # M10 → 编排
│   │   └── health_monitor.py    # M11 → 健康监控
│   ├── api/                     # 统一路由
│   │   ├── __init__.py
│   │   └── router.py            # 聚合所有路由
│   └── web/                     # 前端静态文件
│       └── index.html           # SPA 入口
├── deps/                        # 运行时依赖（DLL 等）
│   ├── windows/
│   │   ├── *.dll                # ASCOM 平台 DLL
│   │   └── redistributables/    # VC++ 等
│   └── macos/
│       └── *.dylib              # macOS 动态库
├── runtime/                     # 嵌入式 Python（Portable）
│   ├── windows/
│   │   └── python/              # Windows Embedded Python
│   └── macos/
│       └── python/              # macOS Python
├── data/                        # 运行时数据（自动创建）
│   ├── db/                      # SQLite 数据库
│   ├── logs/                    # 日志文件
│   └── config/                  # 用户配置
├── doc/review/
│   └── M12_INTEGRATION.md       # 本文件
├── requirements.txt             # 统一依赖
├── build.spec                   # PyInstaller 配置
├── build-macos.spec             # macOS 打包配置
├── build.bat                    # Windows 构建脚本
├── build.sh                     # macOS 构建脚本
├── AstroHub.exe                 # Windows 最终产出
└── AstroHub.app                 # macOS 最终产出
`

### P0.2 统一依赖
合并所有 M1-M11 的依赖到 requirements.txt：
- FastAPI + uvicorn
- SQLAlchemy + aiosqlite
- pywebview (桌面窗口)
- PyInstaller (打包)
- requests (ISAPI/SADP)
- pydantic (数据验证)
- psutil (系统监控)
- python-multipart (文件上传)

### P0.3 统一配置
src/config.py：
- 服务端端口（默认 8080）
- 数据库路径（data/db/astrohub.db）
- 日志配置（data/logs/）
- 认证密钥
- WebSocket 端口
- 窗口默认尺寸（1600x900）

### P0.4 统一日志
单例 Logger，按模块分区，文件轮转。

---

## P1: 代码迁移与整合

### P1.1 核心业务迁移
将 M1-M11 的核心业务逻辑提取到 src/core/ 下的对应文件：
- M1 → ptz_manager.py (SADP/ISAPI/PTZ/运动控制)
- M2 → device_manager.py (设备注册/状态/分组/心跳/生命周期)
- M3 → stream_manager.py (RTSP/ONVIF/HLS/转码/监控)
- M4 → calibration_manager.py (自动对焦/色彩/速度/位置/恢复)
- M5 → device_repo.py (CRUD/配置存储/操作日志)
- M7 → auth.py (JWT/API Key/权限)
- M8 → ws_manager.py (连接管理/广播/订阅)
- M9 → ascom_manager.py (圆顶/调焦器/滤镜轮/气象站/望远镜)
- M10 → orchestrator.py (任务调度/事件总线/管道/错误处理)
- M11 → health_monitor.py (健康聚合/服务状态/回滚)

### P1.2 统一路由
src/api/router.py 聚合所有模块的路由：
- /api/v1/ptz/* - M1
- /api/v1/devices/* - M2
- /api/v1/streams/* - M3
- /api/v1/calibration/* - M4
- /api/v1/db/* - M5
- /api/v1/auth/* - M7
- /api/v1/ascom/* - M9
- /api/v1/system/* - M10/M11
- /ws - M8

### P1.3 数据库统一
- 使用 M5 的 SQLAlchemy async engine
- 所有模块共享同一个数据库实例
- 定义统一的表模型（设备、配置、日志、校准记录）

---

## P2: Web 前端

### P2.1 SPA 入口
src/web/index.html：
- 简洁的控制面板界面
- 显示设备状态、流状态、系统健康
- 通过 WebSocket 接收实时数据

### P2.2 基础功能页面
- 仪表盘（总览）
- 设备管理（列表/操作）
- PTZ 控制面板
- 校准工作台
- 系统设置

### P2.3 响应式
- 默认 1600x900
- 窗口缩放自适应
- 移动端基础适配

---

## P3: 桌面应用封装

### P3.1 pywebview 集成
main.py 中：
- 启动 uvicorn 服务端（后台线程）
- 创建 pywebview 窗口（1600x900, "AstroHub"）
- 加载 http://localhost:PORT
- 窗口关闭时优雅停止 uvicorn

### P3.2 多模式启动
- **桌面模式**（默认）：双击 exe → pywebview 窗口
- **服务模式**：astrohub.exe --headless → 仅服务端，IP 可访问

### P3.3 系统托盘
- Windows 系统托盘图标
- 右键菜单：打开浏览器 / 停止服务 / 退出

---

## P4: 环境自检与 Portable

### P4.1 环境自检 (env_check.py)
启动前检查：
- Python 版本 >= 3.11
- 核心依赖包是否安装（FastAPI/SQLAlchemy/uvicorn/pywebview 等）
- 运行时 DLL 是否存在（ASCOM/VC++ 等）
- 数据目录是否可写（data/db, data/logs, data/config）
- 端口是否被占用

### P4.2 自动修复
- **Python 缺失**：下载并安装嵌入式 Python（Windows: python.org embed zip, macOS: 系统 Python 或 brew）
- **依赖包缺失**：自动 pip install -r requirements.txt
- **DLL 缺失**：提示用户安装对应运行时（VC++ Redistributable / ASCOM Platform）
- **目录缺失**：自动创建

### P4.3 Portable 实现方案
**Windows:**
- 方案 A（推荐）：使用 PyInstaller 打包为单文件 exe，内置 Python 运行时
  - 所有依赖打包进 exe
  - DLL 随 exe 分发
  - 用户只需一个 AstroHub.exe
- 方案 B（备选）：便携式 Python + 预装依赖 + 启动脚本
  - 下载 Python embeddable zip
  - 预装所有依赖到 site-packages
  - 提供 run.bat 启动
  - 整体放在 AstroHub/ 文件夹

**macOS:**
- 使用 PyInstaller 打包为 .app bundle
  - 所有依赖打包进 app
  - 用户只需 AstroHub.app
- 备选：homebrew 依赖 + 启动脚本

### P4.4 DLL 与运行时依赖
**Windows DLL 清单：**
- ASCOM Platform DLL（望远镜/圆顶/调焦器等驱动）
- VC++ Redistributable（2015-2022）
- FFmpeg（流转码，可选）
- ONVIF 相关 DLL

**打包策略：**
- PyInstaller --add-data 将 DLL 打包进 exe
- 运行时释放到临时目录
- 检测 ASCOM Platform 是否已安装，未安装则提示下载

**macOS 动态库：**
- ASCOM 等效库（如 indi/astrodrivers）
- FFmpeg（brew install ffmpeg）
- 未安装时提示

---

## P5: 多平台打包

### P5.1 Windows 打包
build.bat：
- PyInstaller --onedir --windowed
- 包含所有静态文件 + DLL
- 输出 dist/AstroHub/ 文件夹（含 AstroHub.exe）
- 版本号注入

### P5.2 macOS 打包
build.sh：
- PyInstaller --onedir --windowed --osx-bundle-identifier com.astrohub.app
- 输出 dist/AstroHub.app
- 包含 Info.plist
- 代码签名（可选）

### P5.3 跨平台兼容处理
- 路径分隔符统一使用 pathlib
- DLL/dylib 动态加载
- pywebview 跨平台 API
- 系统托盘：Windows=pystray, macOS=内置

### P5.4 构建矩阵
| 平台 | 构建命令 | 输出 |
|------|----------|------|
| Windows x64 | build.bat | dist/AstroHub/AstroHub.exe |
| macOS ARM | build.sh (Apple Silicon) | dist/AstroHub.app |
| macOS x64 | build.sh (Intel) | dist/AstroHub.app |

---

## P6: 测试验证

### P6.1 功能完整性
- M1-M11 核心功能在集成后均可用
- API 路由无冲突
- 数据库正常读写
- WebSocket 正常连接

### P6.2 环境自检
- Python 缺失时自动安装
- 依赖缺失时自动 pip install
- DLL 缺失时给出清晰提示

### P6.3 桌面应用
- 双击 exe/app 正常启动
- 窗口尺寸 1600x900
- 标题栏显示 "AstroHub"
- 关闭按钮正常退出

### P6.4 服务模式
- --headless 参数正常启动
- http://IP:PORT 可访问
- 远程连接稳定

### P6.5 打包质量
- Windows exe 大小 < 150MB
- macOS app 大小 < 200MB
- 无缺失依赖
- 干净机器可运行
- Portable：无需安装，解压即用

---

## 评审标准

| 评审点 | 标准 | 验证方式 |
|--------|------|----------|
| P0.1 项目结构 | 统一目录，无 m*/ 分散 | 检查目录 |
| P0.2 依赖管理 | requirements.txt 完整 | pip install 成功 |
| P0.3 统一配置 | 单 config.py 管理所有 | 检查文件 |
| P0.4 统一日志 | 单例 Logger | 日志输出正常 |
| P1.1 代码迁移 | 核心功能保留 | 功能测试 |
| P1.2 路由统一 | 无路由冲突 | 启动无警告 |
| P1.3 数据库统一 | 所有模块共享 DB | CRUD 正常 |
| P2.1 SPA | 页面正常加载 | 浏览器访问 |
| P2.2 功能页面 | 仪表盘/设备/PTZ 可用 | 手动测试 |
| P3.1 pywebview | 窗口正常启动 | 双击 exe/app |
| P3.2 服务模式 | --headless 有效 | 命令行 |
| P4.1 环境自检 | Python/依赖/DLL 检测 | 模拟缺失环境 |
| P4.2 自动修复 | 自动安装缺失组件 | 模拟缺失环境 |
| P4.3 Portable | 解压即用，免安装 | 干净机器测试 |
| P4.4 DLL 打包 | 依赖 DLL 正确打包 | 干净机器运行 |
| P5.1 Windows 打包 | exe 生成成功 | build.bat |
| P5.2 macOS 打包 | app 生成成功 | build.sh |
| P5.3 跨平台 | 同代码双平台可用 | 双平台测试 |
| P6 功能验证 | 核心功能正常 | 全面测试 |

---

## 开发步骤

1. **M12-P0**：创建统一项目结构 + requirements.txt + config.py + logger.py + database.py
2. **M12-P1**：迁移核心代码 + 统一路由
3. **M12-P2**：Web 前端
4. **M12-P3**：pywebview 集成
5. **M12-P4**：环境自检 + Portable
6. **M12-P5**：多平台打包
7. **M12-P6**：测试验证
