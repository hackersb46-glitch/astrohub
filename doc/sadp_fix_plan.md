# SADP 修改 IP 修复计划

## 问题描述

SADP_ModifyDeviceNetParam_V40 始终返回错误，官方 SADP.exe 工具可以成功修改。

## 关键发现（已通过实测确认）

### 1. MAC 格式
- **SDK 回调返回的 MAC 格式**: `24-0f-9b-76-41-93`（**小写+横杠**）
- 大写+横杠 → 2005（参数错误）
- 大写/小写+冒号 → 2005（参数错误）
- **只有小写+横杠能通过参数校验** → 2045（AES 加密失败）

### 2. 2045 = AES 加密失败
- 小写 MAC 通过参数校验后，SDK 内部 AES 加密密码失败
- 官方工具能成功，说明不是密码本身的问题
- 可能原因：密码编码方式、libcrypto/libssl DLL 版本

### 3. SDK 日志关键错误
```
[ERR] [CSadpService::ModifyNetParamV40] SearchDevice failed [24-0F-9B-76-41-93]
```
- 当使用大写 MAC 时，SDK 内部搜索设备失败
- 使用小写 MAC 时能找到设备（但 AES 加密失败）

### 4. 官方 C demo 调用方式（DlgHikSadp.cpp 第 2487 行）
```cpp
int bret = SADP_ModifyDeviceNetParam_V40(m_smac, m_spsw, &struNetParam, &struDevRetNetParam, sizeof(struDevRetNetParam));
```
- `m_smac` 直接来自 SDK 回调原始值，**不做任何转换**
- 回调返回小写+横杠格式

### 5. 当前 Python 代码的问题
- `_normalize_mac()` 返回大写+横杠（错误！应该是小写+横杠）
- `_mac_for_dll()` 返回大写+横杠（错误！应该是小写+横杠）
- 导致 SDK 内部 SearchDevice 失败 → 2005

## 修复方案

### 修改 1: MAC 格式
- `_normalize_mac()` 和 `_mac_for_dll()` 都应返回**小写+横杠**格式
- 即 `24-0f-9b-76-41-93`

### 修改 2: 密码编码
- 尝试用 `cp936`（GBK）编码而不是 UTF-8
- C demo 使用 ANSI（MultiByte），Windows 简体中文默认 GBK

### 修改 3: SADP_Start_V40 参数
- 确保 `bInstallNPF=0`（不安装 NPF 驱动）
- SDK 官方示例代码直接调用 `SADP_Start_V40(callback)`

### 修改 4: 结构体确认
- SADP_DEV_NET_PARAM: sizeof=440 ✅ 正确
- SADP_DEV_RET_NET_PARAM: sizeof=128 ✅ 正确
- byIPv6MaskLen=0 ✅ 正确
- byDhcpEnable=0 ✅ 正确

## 官方文档路径（必须读取）

- SDK 根目录: `D:\ASTRO PY\Astro_hub\ref\HIK SDK\HCSadpSDKV4.2.8.10_build20220517_Win64_ZH_20231201161210\HCSadpSDKV4.2.8.10_build20220517_Win64_ZH\`
- 头文件: `incCN\Sadp.h`
- C demo: `demo\DlgHikSadp.cpp`
- SDK 文档: `doc\SADPSDK_开发指南_V4.4_20231130.pdf`

## 错误码定义

| 错误码 | 常量 | 含义 |
|--------|------|------|
| 2005 | SADP_PARAMETER_ERROR | 参数错误 |
| 2006 | SADP_OPEN_ADAPTER_FAIL_ERROR | 打开适配器失败 |
| 2045 | SADP_AES_ENCRYPT_ERROR | AES 加密失败 |

## 测试设备信息

- MAC: `24-0f-9b-76-41-93`（SDK 回调原始格式，小写+横杠）
- 当前 IP: `192.168.56.68`
- 目标 IP: `192.168.5.107`（已 PING 确认空闲）
- 目标网关: `192.168.5.1`
- 子网: `255.255.255.0`
- 账号: `admin` / 密码: `Nftw1357`

## 禁止事项（必须遵守）

1. **禁止修改本机网络配置**
2. **禁止全网段 IP 扫描**
3. **禁止封装官方 EXE**
4. **只允许使用官方 DLL**
5. **禁止反馈设备错误、网关错误、路由器问题、密码错误** — 这些都是无效阻滞，官方工具能成功说明设备没问题
6. **必须完整阅读 PDF 文档**
7. **必须逐行对比 C demo 代码**

## 执行步骤

1. 读取官方 SDK 文档和 C demo
2. 修复 `_normalize_mac()` 和 `_mac_for_dll()` 返回小写+横杠
3. 修复密码编码方式（尝试 GBK/cp936）
4. 备份原文件到 `doc/review/backup/`
5. 修改 `src\core\sadp_discovery.py`
6. py_compile 验证
7. 编写测试脚本并执行
8. 更新 `CHANGELOG_M1.md`
