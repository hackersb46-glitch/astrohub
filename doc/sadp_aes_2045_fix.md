# SADP AES 加密失败 2045 修复任务

## 目标
修复 `src/core/sadp_discovery.py` 中 `SADP_ModifyDeviceNetParam_V40` 返回错误 2045 (AES 加密失败)

## 已确认事实
1. MAC 格式已修复：小写+横杠 `24-0f-9b-76-41-93`，通过参数校验 ✅
2. 密码编码已改为 cp936/GBK，仍 2045 ❌
3. 官方 SADP.exe 能成功修改 → 设备/密码/网络都正常
4. DLL 版本与 SDK libs 完全一致（2022/5/17）
5. 错误码 2045 = SADP_AES_ENCRYPT_ERROR（来自 Sadp.h）

## 必须读取的文档
| 文件 | 路径 |
|------|------|
| 头文件 | `D:\ASTRO PY\Astro_hub\ref\HIK SDK\HCSadpSDKV4.2.8.10_build20220517_Win64_ZH_20231201161210\HCSadpSDKV4.2.8.10_build20220517_Win64_ZH\incCN\Sadp.h` |
| C demo | `...\demo\DlgHikSadp.cpp` — 重点读 `OnButtonSafe` 函数 |
| SDK 文档 | `...\doc\SADPSDK_开发指南_V4.4_20231130.pdf` |

## 排查方向
1. C demo 中 `m_spsw` 的密码获取和编码方式（CString，MFC 项目是 Unicode 还是 Multi-Byte？）
2. Sadp.dll 内部 AES 加密是否需要 OpenSSL 初始化函数调用？
3. Python ctypes 传入密码是否需要 null 终止？
4. DLL 加载顺序和路径是否正确？

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

## 当前代码位置
`sadp_discovery.py` 中 `modify_device_network()` 方法，约第 680-820 行
