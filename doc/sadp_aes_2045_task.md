# SADP AES 加密失败 2045 修复任务

## 目标
修复 `src/core/sadp_discovery.py` 中 `SADP_ModifyDeviceNetParam_V40` 返回错误 2045 (AES 加密失败)

## 已确认事实
1. MAC 格式已修复：小写+横杠 `24-0f-9b-76-41-93`，通过参数校验 ✅
2. 密码编码已改为 cp936/GBK + null 终止，仍 2045 ❌
3. 官方 SADP.exe 能成功修改 → 设备/密码/网络都正常
4. 错误码 2045 = SADP_AES_ENCRYPT_ERROR（来自 Sadp.h）

## 关键发现：DLL 版本差异
| 组件 | 官方 SADP 工具 (能成功) | 我们用的 SDK (2045 失败) |
|------|-------------------------|--------------------------|
| 路径 | `C:\Program Files\Hikvision Tools Manager\...\SADPTool\` | SDK libs/ |
| Sadp.dll | 1,036,288 bytes (2021/3/11) | 2,205,696 bytes (2022/5/17) |
| OpenSSL | libeay32.dll + ssleay32.dll (0.9.x) | libcrypto-1_1-x64.dll + libssl-1_1-x64.dll (1.1.x) |
| 架构 | x86 (32-bit) | x64 (64-bit) |

## 必须读取的文档
- 头文件: `D:\ASTRO PY\Astro_hub\ref\HIK SDK\HCSadpSDKV4.2.8.10_build20220517_Win64_ZH_20231201161210\HCSadpSDKV4.2.8.10_build20220517_Win64_ZH\incCN\Sadp.h`
- C demo: `...\demo\DlgHikSadp.cpp` — 重点读 `OnButtonSafe` 函数
- SDK 文档: `...\doc\SADPSDK_开发指南_V4.4_20231130.pdf`

## 排查方向
1. 官方旧版 DLL 用 libeay32.dll (OpenSSL 0.9.x)，新版用 libcrypto-1_1-x64.dll (OpenSSL 1.1.x)，AES 实现不同
2. 尝试复制官方 libeay32.dll + ssleay32.dll 到 src/core/，测试是否与新版 Sadp.dll 兼容
3. 检查 SDK 头文件中是否有 SADP_InitAES 或类似初始化函数
4. 在代码中显式加载 libeay32.dll 并初始化 OpenSSL

## 需要修改的文件
`D:\astro_py\astro_hub\src\core\sadp_discovery.py`

## 约束
- 禁止修改本机网络配置（IP、网关、网卡）
- 禁止反馈设备错误、网关错误、密码错误
- 禁止封装官方 EXE
- 纯 DLL 方案
- 修改前备份到 `doc/review/backup/`
- 修改后编写 `CHANGELOG_M1.md`
- 修改后 `py_compile` 验证
