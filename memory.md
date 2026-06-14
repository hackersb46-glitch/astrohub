# AstroHub 开发关键规则

## ISAPI 接口规则

### 1. XML 格式必须与 GET 响应一致
- GET 响应就是 PUT 应用的正确格式模板
- 大小写敏感：`manual`/`auto`（小写），不是 `Manual`/`Auto`
- 完整结构：降噪需要 `<mode>general</mode><GeneralMode><generalLevel>`

### 2. 白平衡端点
- GET: `/ISAPI/Image/channels/1/whiteBalance`
- 返回字段：`WhiteBalanceStyle`, `WhiteBalanceRed`, `WhiteBalanceBlue`
- PUT 格式必须与 GET 一致

### 3. 降噪端点
- GET: `/ISAPI/Image/channels/1/noiseReduce`
- 返回字段：`mode`, `GeneralMode/generalLevel`
- PUT 需要完整 `<mode>general</mode><GeneralMode>` 结构

---

## 测试验证标准

### 连续5次测试
- 每次设置不同值
- 每次等待1秒
- ISAPI PUT 返回 200
- GET 验证值正确