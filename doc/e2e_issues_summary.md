# E2E 测试问题清单

> 生成日期: 2026-05-07

## 问题 1: psutil 兼容性 — /api/v1/system/nics 报错
- **现象:** `GET /api/v1/system/nics` 返回 `{'success':false, 'message': "'snicstats' object has no attribute 'isloopback'"}`
- **文件:** `src/core/system_info.py`
- **修复:** 用 hasattr/try-except 兼容新旧 psutil API

## 问题 2: 硬编码 IP 地址
- `src/core/sadp_discovery.py` — `192.168.5.107`, `192.168.5.201`, `192.168.5.1`
- `src/core/m1_flow.py` — `192.168.1.1`
- `src/m1_ptz_astro/core/network.py` — `192.168.1.100`
- `src/m3_stream_service/api/router.py` — `192.168.1.100`
- **修复:** 从 config 读取，SADP 改为 .64 默认+冲突检测+自动递增

## 问题 3: M12 模块不完整
- 缺失: `api/`, `core/config_merger.py`, `core/health_aggregator.py`

## 问题 4: SPA fallback 路由
- 部分不存在路径返回 404 而非 index.html
