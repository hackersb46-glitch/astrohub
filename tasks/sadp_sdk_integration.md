# SADP SDK 集成 + 全链路实机测试任务

> 创建时间: 2026-05-06

## 当前问题
- SADP 发现返回 0 设备
- 官方 SADP 工具可以正常发现设备
- 纯 Python 多播实现不工作
- **必须使用官方 SDK DLL**

## 官方 SDK 资源
```
D:\ASTRO PY\Astro_hub\ref\HIK SDK\
├── HCSadpSDKV4.2.8.10_build20220517_Win64_ZH_20231201161210/  ← SADP 官方 SDK
│   ├── HeaderFiles/  ← C 头文件（API 定义）
│   ├── Doc/          ← 文档
│   ├── Demo/         ← C/C# 示例代码
│   └── Libs/         ← DLL + .lib
├── HIKVISION ISAPI_2.0-IPMD Service\  ← ISAPI 协议文档
│   └── HIKVISION ISAPI_2.0-IPMD Service.pdf
└── VideoSDK_Win64_20250326095740\VideoSDK_Win64\  ← 视频 SDK
```

## 项目现状
- 项目根目录: D:\astro_py\astro_hub
- 现有 SADP 实现: src\core\ptz_manager.py 中的 scan_for_devices() — 纯 Python 多播，**不工作**
- 已有 ISAPI 客户端: src\core\ptz_manager.py 中的 ISAPIClient 类
- API 路由: src\api\router.py（已对接 PTZManager）
- 前端: src\web\index.html（已改造为真实后端）
- 可执行文件: dist\AstroHub\AstroHub.exe
- 测试凭据: admin / Nftw1357

## 绝对红线
1. **绝对禁止全网段 IP 扫描**
2. **绝对禁止修改本机网络配置**（不新增网卡、不改IP、不改网关）
3. **绝对禁止封装/调用官方 exe 程序**（不用 subprocess 调 SADP.exe）
4. **网络操作只允许**: SADP DLL 发现 + ping 单个已发现的 IP
5. **必须使用官方 SDK DLL**（ctypes 调用 HCSadpSDK）
6. 测试环境硬件/网络/账号密码全部正常

## 必须完成的工作

### Step 1: 读取 SADP SDK 文档和头文件
读取 HCSadpSDKV4.2.8.10 目录中的所有 .h 文件和文档
找到设备发现的 API 函数签名和回调机制

### Step 2: ctypes 封装 SADP SDK
- 创建 src\core\sadp_sdk.py
- 用 ctypes 加载 SADP DLL
- 实现设备发现函数
- 返回设备列表

### Step 3: 替换 ptz_manager.py 的 SADP 实现
- 修改 scan_for_devices() 改为调用 SADP SDK

### Step 4: 重新打包 + 实机测试
- 打包时包含 SADP SDK DLL
- 启动 AstroHub.exe --headless
- 调用 /api/v1/discovery/sadp → 应发现真实设备
- 连接设备 → PTZ 控制

## 约束
- 自己直接写文件，不委托子代理
- 每步报告进度
- 所有 py_compile 验证
