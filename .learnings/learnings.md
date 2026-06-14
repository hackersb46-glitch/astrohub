# 开发教训 - 2026-06-14

## LRN-20260614-001: ISAPI XML 格式必须与 GET 响应一致

**问题**: 白平衡 R/B 设置 PUT 返回 400 Invalid XML Content

**原因**: 
- 代码使用首字母大写 `Manual`/`Auto`
- ISAPI 实际要求小写 `manual`/`auto`

**解决方法**: 
1. 先 GET 当前值
2. 对比 GET 响应格式
3. PUT XML 格式必须与 GET 完全一致（包括大小写）

**验证**: 连续5次设置不同值，每次等待1秒，全部 PUT=200 + GET 验证值正确

**代码位置**: `src/api/router.py` set_whitebalance 函数

---

## LRN-20260614-002: 降噪 XML 需完整结构

**问题**: 降噪设置 XML 格式不完整

**原因**: 缺少 `<mode>general</mode>` 和 `<GeneralMode>` 包装节点

**正确格式**:
```xml
<NoiseReduce version="2.0" xmlns="http://www.hikvision.com/ver20/XMLSchema">
<mode>general</mode>
<GeneralMode>
<generalLevel>{level}</generalLevel>
</GeneralMode>
</NoiseReduce>
```

**验证**: 连续5次设置不同值，全部通过

**代码位置**: `src/api/router.py` set_noisereduce 函数

---

## LRN-20260614-003: ISAPI 端点验证流程

**流程**:
1. 直接测试 ISAPI 端点（GET）确认端点可用
2. 对比 GET 响应格式确定正确 XML 结构
3. 直接 PUT 测试验证格式正确性
4. 连续5次测试确保稳定性

**关键点**:
- ISAPI 错误响应会给出具体类型（如 `badXmlContent`）
- GET 响应就是 PUT 应用的正确格式模板