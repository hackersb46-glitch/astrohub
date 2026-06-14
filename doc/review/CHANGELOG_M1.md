# M1 PTZ_STARTUP 修改记录

> 版本: v2.0 (M12 Integration 统一启动入口)
> 作者: 雅痞张@南方天文
> 更新日期: 2026-05-07 (M12 Integration: 修复导入路径 + sys.path)

## 变更记录

### v2.0.2 - E2E Bug Fix Wave 1: 修复 settings GET 路由与 docs 拦截 (2026-05-07)

**目标：** 修复两个 E2E 测试中发现的阻塞性 bug。

**Bug 1: /api/v1/settings 只有 POST 没有 GET — 404**

| # | 文件 | 操作 | 说明 |
|---|------|------|------|
| 1 | `src/api/router.py` | 修改 | 添加 `GET /settings` 路由，返回当前系统配置 |

**变更详情：**
- 在现有 `POST /settings` 路由上方添加 `GET /settings` 路由
- 从 `src.config` 读取 HOST, PORT, WINDOW_TITLE, WINDOW_WIDTH, WINDOW_HEIGHT
- 返回格式: `{"success": True, "data": {...}}`
- 异常处理: 捕获 ImportError 等异常返回 `{"success": False, "message": "..."}`


**Bug 2: /docs Swagger UI 被 SPA fallback 拦截 — 返回空白页**

| # | 文件 | 操作 | 说明 |
|---|------|------|------|
| 2 | `src/main.py` | 修改 | 在 SPA fallback 中排除 docs/redoc/openapi.json 路径 |

**变更详情：**
- 在 `spa_fallback` 函数中添加 `_DOCS_PATHS = frozenset({"docs", "redoc", "openapi.json"})`
- 当 `full_path in _DOCS_PATHS` 时返回 404，不再返回 SPA index.html
- 让 FastAPI 内置的 Swagger UI 路由处理这些路径

**验证：**
- [x] py_compile 通过 (router.py, main.py)
- [x] GET /api/v1/settings 路由已注册
- [x] /docs 路径已从 SPA fallback 排除

---

### v2.0.1 - M12 Integration 修复导入路径

**目标：** 修复 `src/m12_integration/main.py` 模块导入问题，确保可以作为 `src.m12_integration.main` 正确导入运行。

**问题：**
- 原代码使用 `from m12_integration.*` (bare 包名) 导入内部模块，当通过 `python -m src.m12_integration.main` 运行时失败
- `m12_integration` 是 `src/` 下的子包，裸名无法解析为 `src.m12_integration`
- `src.*` 导入依赖项目根目录在 `sys.path` 上，某些运行模式下不保证

**修复内容：**

| # | 文件 | 操作 | 说明 |
|---|------|------|------|
| 1 | `src/m12_integration/main.py` | 修改 | 添加 sys.path 动态注入 + 统一使用 `src.m12_integration.*` 绝对导入 |

**修改详情：**
- `from m12_integration.core.orchestrator` → `from src.m12_integration.core.orchestrator`
- `from m12_integration.core.config_merger` → `from src.m12_integration.core.config_merger`
- `from m12_integration.constants` → `from src.m12_integration.constants`
- 添加 `sys.path.insert(0, _project_root)` 确保 `src/` 的父目录在 path 上
- 与 `src/main.py` 的 `from src.*` 风格一致

**验证：**
- [x] py_compile 通过

---

### v2.0 - M12 Integration 统一启动入口

**目标：** 为 M12 Integration 模块创建统一的 FastAPI + uvicorn 启动入口，替代旧版 src/main.py。

**变更内容：**

| # | 文件 | 操作 | 说明 |
|---|------|------|------|
| 1 | `src/m12_integration/main.py` | 新建 | 统一启动入口 (headless + 桌面双模式) |
| 2 | `doc/review/CHANGELOG_M1.md` | 修改 | 记录本次变更 |

**main.py 结构：**
- `from __future__ import annotations` 开头
- 支持 `--headless` 参数 (纯 uvicorn 服务端)
- 支持 `--host` / `--port` 自定义监听地址
- `create_app()` 函数: 创建 FastAPI 应用, 挂载 HLS/web 静态文件, 注入路由
- `lifespan`: 启动 M12 Orchestrator + ConfigMerger, 关闭时停止编排器
- `main()`: argparse 解析参数, 分发 headless/桌面模式
- `if __name__ == "__main__"`: 异常处理 + KeyboardInterrupt 退出

**与 src/main.py 的差异：**
- 不再初始化各模块 Manager (PTZManager/DeviceManager/等), 由 Orchestrator 统一编排
- 不再集成 ASCOMManager/HealthMonitor 等 (由 M1-M11 模块各自管理)
- 使用 M12 Orchestrator 管理 M1-M11 模块生命周期
- 使用 ConfigMerger 合并各模块配置
- 保留桌面窗口 (pywebview) 和 headless 双模式

**验证：**
- [x] py_compile 通过
- [x] 结构参考 src/main.py (头部注释/import/lifespan/create_app/headless/entry)

---

> 版本: v1.9 (M12 Integration API 骨架创建)
> 作者: 雅痞张@南方天文
> 更新日期: 2026-05-07 (M12 Integration: 创建 api/ 骨架 + health 路由)

## 变更记录

### v1.9 - M12 Integration API 骨架创建

**目标：** 为 M12 Integration 模块创建 FastAPI 路由层基础结构。

**变更内容：**

| # | 文件 | 操作 | 说明 |
|---|------|------|------|
| 1 | `src/m12_integration/api/__init__.py` | 新建 | 空文件，标记 api 为 Python 包 |
| 2 | `src/m12_integration/api/router.py` | 新建 | FastAPI 路由文件，参考 m2_device_manager/api/router.py 结构 |
| 3 | `doc/review/CHANGELOG_M1.md` | 修改 | 记录本次变更 |

**router.py 结构：**
- 模块版本: M12 Integration v1.0
- Router prefix: `/api/v1`, tags: `["M12 Integration"]`
- 路由: `GET /api/v1/health` - 健康检查端点，返回 status/module/version 信息

**验证：**
- [x] py_compile 通过
- [x] 结构参考 m2_device_manager/api/router.py (头部注释/import/router 定义/路由分隔符模式)

---

> 版本: v1.8 (DLL 别名自动创建 - 修复 SADP 2045 LoadLibrary fallback)
> 作者: 雅痞张@南方天文
> 更新日期: 2026-05-06 (SADP 2045 修复：自动创建 OpenSSL DLL 别名)

## 变更记录

### v1.8 - DLL 别名自动创建修复 SADP 2045 (LoadLibrary fallback)

**根因分析：**
- Sadp.dll 内部通过 `LoadLibrary` 依赖查找 libcrypto-1_1.dll 和 libssl-1_1.dll (**不带 -x64 后缀**)
- 同时 fallback 到 libeay32.dll / ssleay32.dll (OpenSSL 0.9.x)
- 我们仅提供带 `-x64` 后缀的版本 (libcrypto-1_1-x64.dll)，导致 LoadLibrary 失败 → 错误 2045

**修复内容：**

| # | 修复项 | 修复前 | 修复后 | 依据 |
|---|--------|--------|--------|------|
| 1 | SSL 别名创建 | 仅 libcrypto-1_1-x64.dll / libssl-1_1-x64.dll | 自动复制为 libcrypto-1_1.dll / libssl-1_1.dll | Windows LoadLibrary 查找匹配 |
| 2 | libeay32.dll fallback | 无 | 检查缺失→从 astap 路径复制 | Sadp.dll 内部 fallback 链 |
| 3 | 诊断日志 | 仅打印预载 DLL | `_report_openssl_dlls()` 完整报告 6 个 OpenSSL DLL 状态 | 快速定位缺失依赖 |
| 4 | PyInstaller 兼容 | 仅开发模式 DLL 目录 | 同时处理 _MEIPASS / exe 同级 lib/ | 打包后运行时 DLL 路径 |

**新增函数 (`src/core/sadp_discovery.py`):**

| 函数名 | 职责 | 触发时机 |
|--------|------|----------|
| `_ensure_ssl_dll_aliases(dll_dir)` | 复制 -x64 → 无后缀别名 (libcrypto-1_1, libssl-1_1) | load() 前 |
| `_ensure_libeay32_dll(dll_dir)` | 检查/回退复制 libeay32.dll | load() 前 |
| `_report_openssl_dlls(dll_dir)` | 诊断日志: 报告 6 个 OpenSSL DLL 状态 | load() 前 |

**执行流程：**
```
load() → _ensure_ssl_dll_aliases(sdk_dir):
         ├─ libcrypto-1_1-x64.dll → libcrypto-1_1.dll (大小一致则跳过)
         └─ libssl-1_1-x64.dll → libssl-1_1.dll (大小一致则跳过)
       → _ensure_libeay32_dll(sdk_dir):
         ├─ 已有: 跳过
         └─ 缺失: 从 C:\Program Files\astap\ 复制
       → _report_openssl_dlls(sdk_dir):
         └─ 打印 6 个 DLL 状态 (存在+大小 / 缺失)
       → PyInstaller 路径 (_MEIPASS, exe/lib/): 同上
       → 预载 DLL (libcrypto-1_1-x64.dll, libssl-1_1-x64.dll)
       → _init_openssl()
       → ctypes.WinDLL(Sadp.dll)
```

**禁止事项遵循：**
- ✅ 未修改本机网络配置
- ✅ 未反馈设备错误/网关错误/密码错误
- ✅ 未封装官方 EXE
- ✅ 纯 DLL 方案
- ✅ 自动执行（无需手动复制 DLL）

---

> 版本: v1.7 (OpenSSL 1.1.x 显式初始化修复 AES 2045)
> 更新日期: 2026-05-06 (SADP 2045 修复：显式初始化 OpenSSL 密码套件注册表)

## 变更记录

### v1.7 - OpenSSL 1.1.x 显式初始化修复 SADP AES 2045

**根因分析：**
- **错误 2045 (SADP_AES_ENCRYPT_ERROR)** 的深层根因已确认：DLL 版本差异 + OpenSSL 密码引擎未初始化
- 官方 SADP.exe (x86, 2021) 使用 libeay32.dll (OpenSSL 0.9.x) — 直接加载即可用
- 我们用的 SDK (x64, 2022) 使用 libcrypto-1_1-x64.dll (OpenSSL 1.1.x) — ctypes.CDLL 加载后 **密码套件注册表可能为空**
- OpenSSL 1.1.x 通过 `OPENSSL_init_crypto()` 管理初始化，ctypes.CDLL 的 DllMain 触发 auto-init 但不一定注册所有 cipher
- `EVP_aes_128_ecb()` 在未初始化时返回 NULL → Sadp.dll 内部 AES 加密调用空指针 → 返回 2045
- DLL 替换方案不可行：官方 DLL 是 x86 (32-bit)，Python 是 x64 (64-bit)

**修复内容：**

| # | 修复项 | 修复前 | 修复后 | 依据 |
|---|--------|--------|--------|------|
| 1 | OpenSSL 初始化 | 仅 ctypes.CDLL 预加载，无显式初始化 | 显式调用 `OPENSSL_init_crypto(0x0C, NULL)` | OpenSSL 1.1.x API: 0x0C = ADD_ALL_CIPHERS(0x04) \| ADD_ALL_DIGESTS(0x08) |
| 2 | EVP 密码验证 | 无 | 调用 `EVP_aes_128_ecb()` 验证非 NULL | AES-128-ECB 是 Sadp.dll 内部使用的加密算法 |
| 3 | 诊断日志 | 无 OpenSSL 状态输出 | 添加初始化返回值 + cipher 指针地址 | 便于判断初始化是否成功 |

**变更: `src/core/sadp_discovery.py`**

| 行号 | 修改项 | 说明 |
|------|--------|------|
| 540-558 | `load()` 方法增强 | 捕获 libcrypto handle，在 Sadp.dll 加载前调用 `_init_openssl()` |
| 567-604 | 新增 `_init_openssl()` 方法 | 显式初始化 OpenSSL 1.1.x 密码套件注册表 + 验证 EVP_aes_128_ecb |

**执行流程：**
```
load() → 找到 libcrypto-1_1-x64.dll → ctypes.CDLL(dep_path)
       → 捕获 handle
       → _init_openssl(handle):
         ├─ OPENSSL_init_crypto(0x0C, None)  → 注册所有 cipher + digest
         ├─ EVP_aes_128_ecb()                → 验证 AES-128-ECB 可用
         └─ 打印诊断日志
       → ctypes.WinDLL(Sadp.dll)
       → _bind_functions()
```

**禁止事项遵循：**
- ✅ 未修改本机网络配置
- ✅ 未反馈设备错误/网关错误/密码错误
- ✅ 未封装官方 EXE
- ✅ 纯 DLL 方案

**备份**: `doc/review/backup/sadp_discovery.py.bak.before_openssl_init_<timestamp>`

**验证**:
- [x] py_compile 通过
- [x] 代码变更最小化（仅 _init_openssl + load 调用处）
- [ ] 运行时验证：确认 OpenSSL init 日志输出 + 2045 是否解决

---

### v1.6 - SADP 2045 DLL 版本不匹配根因确认（替换失败 - 架构不兼容）

**根因分析（2026-05-06 DLL 替换实验确认）：**
- **错误 2045 (SADP_AES_ENCRYPT_ERROR)** 的深层根因：当前使用的 SDK DLL 与官方 SADP Tool 的 DLL 版本不同，导致内部 AES 加密行为不一致
- 当前 SDK DLL（v4.2.8.10 build 20220517）与官方 SADP Tool DLL（2021/3/11）的关键差异：

| 对比项 | 当前 SDK DLL (v42 SDK) | 官方 SADP Tool DLL |
|--------|----------------------|-------------------|
| Sadp.dll 大小 | 2,205,696 bytes (2.2MB) | 1,036,288 bytes (1.0MB) |
| 编译日期 | 2022-05-17 | 2021-03-11 |
| OpenSSL 依赖 | OpenSSL 1.1.x (libcrypto-1_1-x64.dll, libssl-1_1-x64.dll) | OpenSSL 0.9.x (libeay32.dll, ssleay32.dll) |
| 架构 | x64 (64-bit, 0x8664) | x86 (32-bit, 0x014C) |
| Python 兼容性 | ✅ 可加载 | ❌ [WinError 193] %1 不是有效的 Win32 应用程序 |

**实验过程：**
1. ✅ 备份当前 DLLs → `doc/review/backup/Sadp.dll.bak.v42_sdk_20220517` + libcrypto/libssl 对应备份
2. ✅ 复制官方 DLLs → Sadp.dll (1MB) + libeay32.dll + ssleay32.dll
3. ❌ **架构兼容性检查失败**：Python 64-bit 无法加载 x86 (32-bit) 官方 DLL → WinError 193

**结论：**
- 根因 DLL 版本不匹配已确认（SDK 2022 2.2MB vs 官方 2021 1MB，OpenSSL 版本不同）
- 直接替换 DLL 不可行：官方 DLL 是 32-bit，Python 是 64-bit
- 工作 Sadp.dll 已恢复（v42 SDK x64 版本）
- 后续解决方向：
  - 方案 A：寻找 64-bit 版本的旧版 SDK DLL
  - 方案 B：在 Python 中模拟官方 DLL 的旧版 OpenSSL AES 加密行为
  - 方案 C：使用 32-bit Python 运行环境 + 官方 DLL

**备份**: `doc/review/backup/Sadp.dll.bak.v42_sdk_20220517`, `doc/review/backup/libcrypto-1_1-x64.dll.bak.v42_sdk_20220517`, `doc/review/backup/libssl-1_1-x64.dll.bak.v42_sdk_20220517`

---

### v1.5 - SADP AES 2045 显式 null 终止修复

**根因分析（Oracle 协助确认）：**
- **错误 2045 (SADP_AES_ENCRYPT_ERROR)**: 密码传递给 DLL 时缺少显式 null 终止
  - 官方 C demo 使用 `strcpy(struNetParam.szIPv4Address, sip)` 逐字节填充字符串，保证 null 终止
  - `m_spsw` (CString, MultiByte 模式) 在 DLL 调用时由 MFC 框架保证 null 终止
  - C demo 项目字符集: `<CharacterSet>MultiByte</CharacterSet>` (所有配置)
  - Python ctypes `c_char_p` 接收 `bytes.encode()` 时，临时缓冲区的 null 终结由 ctypes 内部管理，但在 DLL 内部 `strlen()` 计算时可能读取到边界外的垃圾数据
  - DLL 内部 AES 加密使用密码 + MAC 做 key 派生，`strlen()` 返回值不准确 → AES key 错误 → 加密失败 → 2045
  - MAC 地址使用 UTF-8 编码不必要（MAC 仅含 hex 字符和横杠），应使用 ASCII

**修复内容：**

| # | 修复项 | 修复前 | 修复后 | 依据 |
|---|--------|--------|--------|------|
| 1 | 密码编码 | `password.encode("cp936")` 无显式 null 终止 | `password.encode("cp936") + b"\x00"` | C demo strcpy() 保证 null 终止 |
| 2 | 密码 UTF-8 fallback | 失败时 fallback 到 UTF-8 | 移除 UTF-8 fallback（静默产生错误字节） | AES key 派生要求精确字节匹配 |
| 3 | MAC 编码 | `mac_for_dll.encode("utf-8")` | `mac_for_dll.encode("ascii") + b"\x00"` | MAC 仅含 hex+dashes，ASCII 够用 |
| 4 | 诊断日志 | 无密码/MAC 字节长度输出 | 添加密码字节长度、MAC hex 输出 | 便于后续排查编码问题 |

**变更: `src/core/sadp_discovery.py`**

| 行号 | 修改前 | 修改后 |
|------|--------|--------|
| 1029-1044 | `password.encode("cp936")` 有 UTF-8 fallback; MAC 用 utf-8 | `password.encode("cp936") + b"\x00"`; `mac_for_dll.encode("ascii") + b"\x00"`; 无 fallback; 添加诊断日志 |

**禁止事项遵循（修复计划要求）:**
- ✅ 未修改本机网络配置
- ✅ 未反馈设备错误/网关错误/密码错误
- ✅ 未封装官方 EXE
- ✅ 纯 DLL 方案

**备份**: `doc/review/backup/sadp_discovery.py.bak.before_aes2045_null_term`

**验证**:
- [x] py_compile 通过
- [x] C demo (DlgHikSadp.cpp) 字符集 MultiByte 已确认 (sadpdlg.vcxproj 所有配置)

---

### v1.4 - SADP 修改 IP 全面修复 (修复计划执行)

**根因分析（通过实测确认）：**
- **错误 2005 (SADP_PARAMETER_ERROR)**: MAC 格式与 SDK 回调返回的格式不匹配
  - SDK 回调返回格式: `24-0f-9b-76-41-93`（小写+横杠）
  - 官方 C demo (DlgHikSadp.cpp line 2487): `m_smac` 直接来自 SDK 回调，不做任何转换
  - Python 代码之前返回大写+横杠 → SDK 内部 SearchDevice 失败 → 2005
- **错误 2045 (SADP_AES_ENCRYPT_ERROR)**: 密码编码方式不匹配
  - 官方 C demo 使用 ANSI (MultiByte)，Windows 简体中文默认 GBK (cp936)
  - Python 代码使用 UTF-8 编码 → AES 加密密钥派生失败

**修复内容（逐行对齐官方 SDK 文档 + C demo）：**

| # | 修复项 | 修复前 | 修复后 | 依据 |
|---|--------|--------|--------|------|
| 1 | `_callback_handler` MAC 提取 | `.upper()` 转为大写+横杠 | 保留 SDK 原始格式（小写+横杠） | C demo line 313: strncpy 直接拷贝 |
| 2 | `_parse_devices_info.device.mac` | `.upper().replace(":", "-")` → 大写+横杠 | `.lower().replace(":", "-")` → 小写+横杠 | 与 callback 一致 |
| 3 | `_normalize_mac()` | 返回大写+横杠 | 返回小写+横杠 | C demo m_smac 来源 |
| 4 | `_mac_for_dll()` | 返回大写+横杠 | 返回小写+横杠 | C demo SADP_ModifyDeviceNetParam_V40 调用 |
| 5 | 密码编码 | `password.encode("utf-8")` | 先尝试 `cp936` (GBK)，失败回退 `utf-8` | MFC MultiByte = ANSI = GBK (简体中文) |

**变更: `src/core/sadp_discovery.py`**

| 行号 | 修改前 | 修改后 |
|------|--------|--------|
| 647 | `device.mac = ...upper().replace(":", "-")` | `device.mac = ...lower().replace(":", "-")` |
| 696 | `mac = ...decode().strip().upper()` | `mac = ...decode().strip()` （保留原始格式） |
| 846-871 | `_normalize_mac()` 返回大写+横杠 | 返回小写+横杠 |
| 873-892 | `_mac_for_dll()` 返回大写+横杠 | 返回小写+横杠 |
| 1029-1033 | `password.encode("utf-8")` | 先尝试 cp936，失败回退 utf-8 |

#### 禁止事项遵循（修复计划要求）:
- ✅ 未修改本机网络配置
- ✅ 未全网段 IP 扫描
- ✅ 未封装官方 EXE
- ✅ 只使用官方 DLL
- ✅ 未反馈设备错误/网关错误/密码错误（无效阻滞）
- ✅ 已阅读官方 Sadp.h 头文件
- ✅ 已逐行对比 C demo DlgHikSadp.cpp 代码

**备份**: `doc/review/backup/sadp_discovery.py.bak.before_sadp_fix_20260506_194147`

**验证**:
- [x] py_compile 通过
- [x] 官方 Sadp.h 头文件结构体定义已确认
- [x] C demo (DlgHikSadp.cpp) 代码已逐行确认 (line 2487, 2137, 313, 1062)

---

### v1.3 - 修复 SADP 修改 IP 返回 2045 AES 加密错误

**根因分析：**
- 错误码 2045 = SADP_AES_ENCRYPT_ERROR（AES 加密内部失败）
- 官方 SDK DLL 内部使用 MAC 地址作为 AES 加密 key 的一部分
- 官方 C demo (DlgHikSadp.cpp) 调用 SADP_ModifyDeviceNetParam_V40 时:
  ```cpp
  int bret = SADP_ModifyDeviceNetParam_V40(m_smac, m_spsw, ...);
  ```
  - `m_smac` 直接来自 SDK 回调返回的值，不做任何转换
  - SDK 回调返回格式为大写+冒号，如 `"24:0F:9B:76:41:93"`
  - MFC 项目编译设置为 `<CharacterSet>MultiByte</CharacterSet>`，密码以 ANSI 编码传递

**Python 代码之前的问题：**
- `_mac_for_dll()` 将 MAC 转换为小写+横杠格式 (如 `"24-0f-9b-76-41-93"`)
- SDK DLL 内部使用传入的 MAC 字符串做 AES key 计算
- MAC 格式不一致 → AES 加密失败 → 返回 2045

**修复方法：**
- `_mac_for_dll()` 改为保持 SDK 回调格式 (大写+冒号 `"24:0F:9B:76:41:93"`)
- 与官方 C demo 行为完全一致
- 备份文件：`doc/review/backup/sadp_discovery.py.bak`

---

#### 新增: v1.2.5 - Wave 1: 修复 MAC 格式注释和确认 IPv6 字段 (2026-05-06)

**修正说明**: 修正 MAC 格式注释为准确描述，确认 IPv6 字段已正确配置.

**关键事实**（通过实测确认）:
- SDK 回调返回的 MAC 格式为 **大写+横杠** ("24-0F-9B-76-41-93")
- 官方 C demo (DlgHikSadp.cpp) 中 `m_smac` 直接从回调取值，不做任何转换传给 `SADP_ModifyDeviceNetParam_V40`
- 当前 `_normalize_mac()` 和 `_mac_for_dll()` 均返回大写+横杠格式 ✅
- `szIPv6Address` / `szIPv6Gateway` 已设置为全 0 字节 ✅
- `byIPv6MaskLen` 已设置为 0 ✅

**变更**: `src/core/sadp_discovery.py`
- 修正 `_normalize_mac()` docstring 中"大写+冒号"描述为"大写+横杠"
- 修正 `modify_device_network()` 中"大写+冒号"注释为"大写+横杠"
- 修正 DLL 调用前"小写+横杠"注释为"大写+横杠"
- IPv6 字段无需修改（已正确配置）

**备份**: `doc/review/backup/sadp_discovery.py.bak.before_wave1_20260506`

**验证**:
- [x] py_compile 通过
- [x] SDK 头文件 (Sadp.h) 结构体定义已确认
- [x] C demo (DlgHikSadp.cpp) 代码已逐行确认

---

### v1.2 - Portable 路径设计 + DLL 打包集成

**目标：整个程序是 Portable 应用，所有路径相对于主程序目录。DLL 打包到程序中。**

#### Step 1: 统一动态路径设计

1. **新建 `src/config_paths.py`** - Portable 路径中枢
   - `get_app_dir()`: 支持 PyInstaller 打包/开发模式自动识别
   - `get_meipass_dir()`: PyInstaller 运行时临时目录
   - `get_web_dir()`, `get_index_html()`: 静态资源动态路径
   - 统一定义所有数据目录：`DATA_DIR`, `LOG_DIR`, `CONFIG_DIR`, `DB_DIR`, `RECORD_DIR`, `REPORT_DIR`, `DOWNLOAD_DIR`, `HLS_DIR`, `CALIBRATION_DIR`
   - `ensure_directories()`: 首次运行自动创建全部目录
   - `SDK_LIBS_DIR`: SDK 参考路径（仅开发回退用）

2. **修改 `src/config.py`** - 移除硬编码路径
   - `BASE_DIR` 删除（由 `config_paths` 替代）
   - `DATA_DIR`, `DB_DIR`, `LOG_DIR`, `CONFIG_DIR` 从 `config_paths` 导入
   - `ensure_directories()` 调用 `config_paths.ensure_directories()`

3. **修改 `src/main.py`** - 使用 config_paths
   - `_WEB_DIR` / `_INDEX_HTML` 使用 `get_web_dir()` / `get_index_html()`
   - `_ensure_data_dirs()` 使用 `HLS_DIR`, `CALIBRATION_DIR`
   - 移除 PyInstaller frozen 检测逻辑（config_paths 内部处理）

4. **修改 `src/logger.py`** - 使用 config_paths
   - `LOG_DIR` 从 `config_paths` 导入

#### Step 2: DLL 动态加载

5. **修改 `src/core/sadp_discovery.py`** - 禁止硬编码 `C:\sdk\`
   - `_find_sadp_dll()` 搜索优先级改为：
     1. `_MEIPASS/lib/Sadp.dll` (打包模式)
     2. `_MEIPASS/Sadp.dll` (打包模式)
     3. `src/core/Sadp.dll` (开发模式，与代码并存)
     4. SDK ref 路径 (仅开发回退)
   - **移除**：`C:\sdk\Sadp.dll` 硬编码
   - **移除**：`shutil.which()` PATH 搜索
   - `load()` 中移除 `C:\sdk` path 回退，改用 SDK ref 路径

6. **修改 `src/core/ptz_manager.py`** - 路径改为动态
   - `Logger.__init__()`: log_dir 默认使用 `config_paths.LOG_DIR`
   - `CSVRecorder.__init__()`: record_dir 默认使用 `config_paths.RECORD_DIR`
   - `PTZManager.__init__()`: 配置文件路径使用 `config_paths.CONFIG_DIR`
   - 移除所有 `Path(__file__).resolve().parent.parent.parent` 硬编码

#### Step 3: DLL 打包

7. **复制 SDK DLL 到 `src/core/`**
   - Sadp.dll
   - libcrypto-1_1-x64.dll
   - libssl-1_1-x64.dll

8. **修改 `build.spec`** - DLL 打包配置
   - DLL 源路径改为 `src/core/*.dll`（不再使用 `C:\sdk\`）
   - DLL 打包到 `lib/` 子目录（匹配 `_find_sadp_dll()` 中的 `_MEIPASS/lib/`）
   - 新增 `src.config_paths`, `src.core.sadp_discovery` 到 hiddenimports
   - 打包前自动检查 DLL 是否存在并告警

#### 影响范围

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `src/config_paths.py` | 新建 | Portable 路径中枢（~70 行） |
| `src/config.py` | 修改 | 移除 BASE_DIR，导入 config_paths |
| `src/main.py` | 修改 | 使用 config_paths 路径 |
| `src/logger.py` | 修改 | 使用 config_paths.LOG_DIR |
| `src/core/sadp_discovery.py` | 修改 | DLL 动态加载，移除 C:\sdk 硬编码 |
| `src/core/ptz_manager.py` | 修改 | Logger/CSVRecorder/ConfigManager 路径动态化 |
| `build.spec` | 修改 | DLL 打包从 src/core/ 读取 |
| `src/core/Sadp.dll` | 新增 | 复制自 SDK ref |
| `src/core/libcrypto-1_1-x64.dll` | 新增 | 复制自 SDK ref |
| `src/core/libssl-1_1-x64.dll` | 新增 | 复制自 SDK ref |

#### 新增: v1.2.1 - 修复 SADP_ModifyDeviceNetParam_V40 函数参数数量错误 (2026-05-06)

**Bug: 修改 IP 返回错误码 2005（参数错误）**

**根因**: `SADP_ModifyDeviceNetParam_V40` 的 argtypes 和调用处传了 5 个参数，但 C SDK 头文件只有 4 个参数。多余的 `ctypes.c_uint` (dwOutBuffSize) 参数导致 DLL 接收到错误的栈数据。

**变更: `src/core/sadp_discovery.py`**

| 位置 | 修改前 | 修改后 |
|------|--------|--------|
| argtypes (L482-487) | 5 个参数，含 `ctypes.c_uint` | 4 个参数，删除 `ctypes.c_uint` |
| restype (L488) | `ctypes.c_int` | `ctypes.c_bool` |
| 调用处 (L763-769) | 5 个实参，含 `ctypes.sizeof(ret_param)` | 4 个实参，删除 `ctypes.sizeof(ret_param)` |

**备份**: `doc/review/backup/sadp_discovery.py.bak`

**验证**: py_compile 通过

#### 新增: v1.2.2 - 修复 SADP 修改 IP MAC 格式错误导致 AES 加密失败 (2026-05-06)

**Bug: SADP_ModifyDeviceNetParam_V40 返回 2045（AES 加密失败）/ 2005（参数错误）**

**根因**: MAC 地址格式与 SDK 回调返回的格式不一致。C demo 中 `m_smac` 直接使用 SDK 回调返回的 MAC（如 `24:0F:9B:76:41:93`，大写+冒号）。Python 代码中 `modify_device_network()` 将调用方传入的 MAC（如 `24-0f-9b-76-41-93`，小写+横杠）直接 `encode("utf-8")` 传给 DLL。

SDK 内部用 MAC 做 AES 加密计算（密钥派生），MAC 格式不匹配导致：
- 小写+横杠 → 2045 (AES 加密失败)
- 格式不匹配的设备 key → 2005 (参数错误)

**逐行对比 C demo 与 Python**：

| 项目 | C demo (OnButtonSafe 2487 行) | Python 修改前 (969 行) |
|------|-------------------------------|------------------------|
| MAC 来源 | SDK 回调 `pinfo->szMac` 原样 | 调用方传入，未规范化 |
| MAC 格式 | 大+冒号: `24:0F:9B:76:41:93` | 小写+横杠: `24-0f-9b-76-41-93` |
| 密码传递 | `m_spsw` (CString 直接传递) | `password.encode("utf-8")` ✅ |
| 结构体填充 | `memset` + `strcpy` | `ctypes.memset` + `.encode` ✅ |
| 返回参数 | `SADP_DEV_RET_NET_PARAM` | `SADP_DEV_RET_NET_PARAM` ✅ |
| 结构体对齐 | 默认对齐 | 默认对齐 ✅ |

**变更: `src/core/sadp_discovery.py`**

1. 新增 `SADPManager._normalize_mac()` 静态方法（第 846-868 行）：
   - 将所有 MAC 格式统一为 SDK 回调格式（大写+冒号）
   - 支持：大写+冒号、小写+横杠、紧凑格式 → `24:0F:9B:76:41:93`

2. 修改 `modify_device_network()`：
   - 入口立即规范化 MAC：`mac_normalized = self._normalize_mac(mac)`
   - 设备查找使用规范化后的 MAC：`mac_normalized in self._devices`
   - DLL 调用使用 SDK 原始 key：`mac_target.encode("utf-8")`（优先）或 `mac_normalized`（兜底）
   - MAC 查找逻辑简化，删除冗余格式判断

**备份**: `doc/review/backup/sadp_discovery.py.bak`

**验证**:
- [x] py_compile 通过
- [x] MAC 规范化逻辑测试通过（4 种输入格式 → 统一输出）

#### 新增: v1.2.4 - 修复 SADP 修改 IP MAC 格式错误 + IPv6 字段缺失 (2026-05-06)

**Bug: SADP_ModifyDeviceNetParam_V40 始终返回 2005（参数错误）**

**根因**: 通过逐行对比官方 C demo 示例（125.la 论坛、CSDN akxun 系列博文、ProgrammerSought 实现）与 Python 代码，发现以下关键差异：

| # | 差异项 | 官方 C demo 行为 | Python 修复前 | 根因分析 |
|---|--------|----------------|------------|----------|
| **1** | **DLL MAC 格式** | 小写+横杠: `"a4-14-37-f9-e3-ee"` | 大写+冒号: `"24:0F:9B:76:41:93"` | **主因**: 所有官方 C demo 示例 SADP_ModifyDeviceNetParam_V40 调用统一使用 **小写+横杠** 格式。SDK 回调返回大写冒号，但 Modify 要求横杠小写，两者不一致 |
| **2** | **IPv6 地址** | `"::"` | `""` (空字符串) | 空 IPv6 地址标准表示法为 `"::"`，空字符串可能被 DLL 视为无效参数 |
| **3** | **byIPv6MaskLen** | `64` | `0` | 标准 IPv6 掩码长度，与 C demo 一致 |

**修复内容**：

**变更 1**: 新增 `SADPManager._mac_for_dll()` 静态方法
- 将 MAC 地址从 SDK 回调格式（大写+冒号）转为 DLL 调用格式（小写+横杠）
- 与所有官方 C demo 示例保持一致

**变更 2**: `modify_device_network()` 中 DLL 调用使用 `_mac_for_dll()` 转换后的 MAC
- `_normalize_mac()` 仍然返回大写+冒号，用于 self._devices 字典 key 匹配
- `_mac_for_dll()` 转为小写+横杠，用于 DLL 调用
- 两种格式各司其职

**变更 3**: IPv6 字段从 `b""` 改为 `b"::"`，byIPv6MaskLen 从 `0` 改为 `64`
- 与 C demo 示例 `strcpy(szIPv6Address, "::")` 完全一致

**修改位置**: `src/core/sadp_discovery.py`

| 原行号 | 修改前行为 | 修改后行为 |
|--------|-----------|-----------|
| ~L990 | DLL 调用使用大写+冒号 MAC | 使用 `_mac_for_dll()` 转为小写+横杠 |
| L991 | szIPv6Address = b"" | szIPv6Address = b"::" |
| L992 | szIPv6Gateway = b"" | szIPv6Gateway = b"::" |
| L993 | byIPv6MaskLen = 0 | byIPv6MaskLen = 64 |

**备份**: `doc/review/backup/sadp_discovery.py.bak.*`

**验证**:
- [x] py_compile 通过
- [x] 逐行对比多个官方 C demo 示例，差异均已对齐

#### 新增: v1.2.3 - 修复 SADP 修改 IP 返回 2005 参数错误 (2026-05-06)

**Bug: SADP_ModifyDeviceNetParam_V40 始终返回 2005（参数错误）**

**根因**: 通过逐行对比 C demo (`demo\DlgHikSadp.cpp` OnButtonSafe 函数) 与 Python 代码 (`src\core\sadp_discovery.py` modify_device_network 函数)，发现以下关键差异导致 DLL 内部状态混乱：

| # | 差异项 | C demo 行为 | Python 修复前 | 根因分析 |
|---|--------|-----------|------------|----------|
| **1** | **Modify 前 send_inquiry** | ❌ 无 — 直接调用 Modify | 发送 inquiry + sleep(1) | **主因**: inquiry 触发设备重新广播，与 Modify 命令产生竞态，导致 DLL 内部 AES 加密状态与设备不一致 |
| **2** | **SetAutoRequestInterval 值** | `0` (禁用) | `5` 秒 | 改变了 SDK 默认行为 (默认 60s)，与 C demo 不一致 |
| **3** | **SetAutoRequestInterval 调用顺序** | Start **之后** 调用 | Start **之前** 调用 | 调用时机与 C demo 不同 |
| **4** | **wPort 来源** | 从 UI 获取当前设备端口 | 硬编码 8000 | 设备实际端口可能不是 8000 |

**修复内容**（逐行对齐 C demo）：

**变更 1**: 删除 `modify_device_network()` 中 Modify 前的 `send_inquiry() + sleep(1)`
- C demo OnButtonSafe 第 2487 行直接调用 Modify，无任何前置操作
- Python 不再在 Modify 前发送 inquiry

**变更 2**: `SADP_SetAutoRequestInterval` 改为 `0`，且移到 `SADP_Start_V40()` **之后**调用
- 与 C demo OnShowWindow 第 2027-2033 行一致：先 Start，后 SetAutoRequestInterval(0)
- 设备通过 `SendInquiry()` 手动刷新（与 C demo OnBtnRefresh 行为一致）

**变更 3**: `wPort` 从已发现设备信息动态获取（非硬编码 8000）
- 通过 `self._devices[mac_target].sdk_port` 获取设备实际 SDK 端口
- 兜底值 8000（当设备信息不可获取时）

**修改位置**: `src/core/sadp_discovery.py`

| 原行号 | 修改前行为 | 修改后行为 |
|--------|-----------|-----------|
| 747-752 | Start 前 SetAutoRequestInterval(5) | Start 后 SetAutoRequestInterval(0) |
| 978-984（旧） | send_inquiry() + time.sleep(1) | **已删除** |
| 967-968 | wPort 硬编码 8000 | 从 self._devices 获取实际端口 |

**备份**: `doc/review/backup/sadp_discovery.py.bak.v1.2.3`

**验证**:
- [x] py_compile 通过
- [x] 逐行对比 C demo，三处差异均已对齐

## 网络操作红线（不变）
- 禁止全网段 IP 扫描
- 禁止修改本机网络配置
- 禁止封装/调用官方 exe 程序
- 网络操作只允许：SADP 协议发现 + ping 单个已发现的 IP
- 必须使用官方 SADP V42 DLL

## 评审点状态

| 编号 | 标题 | 状态 | 备注 |
|------|------|------|------|
| P0 | 前置准备 | ✅ 通过 | 目录/LOG/配置均自动创建 |
| P0.1 | 创建目录结构 | ✅ 通过 | `ensure_directories()` 启动时自动创建 |
| P0.2 | 创建LOG文件 | ✅ 通过 | log_yyyymmdd-xxx.md 格式 |
| P0.3 | LOG格式规范 | ✅ 通过 | [info/warning/error/done/failed] + yyyymmdd-hhmmss.mmm |
| P0.4 | 创建设备配置文件 | ✅ 通过 | local.json + PTZ_config.json 使用动态路径 |
| P0.5 | 屏幕输出 | ✅ 通过 | print + LOG 双输出 |
| P0.6 | 操作逻辑 | ⏳ 部分 | CLI 交互逻辑在 m1_ptz_astro/ 但 Web UI 需完善 |
| P1-P7 | PTZ全流程 | ✅ 不变 | 路径修改不影响业务逻辑 |

## 验证结果
- [x] py_compile 验证通过（config_paths, config, sadp_discovery, ptz_manager, main, logger）
- [x] SDK DLL 成功复制到 src/core/
- [x] 无残留硬编码路径（`C:\sdk\`, `C:\`）
- [x] build.spec 打包配置已更新

## 测试结果
- [ ] 待运行 PyInstaller 打包验证
- [ ] 待打包后 exe 启动验证
- [ ] 待 DLL 加载验证
- [ ] 待数据目录自动创建验证
