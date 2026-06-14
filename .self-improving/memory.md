# 自我改进记忆 (HOT 层)

## 🔴 铁律（违反=立即停止）

### 1. 进程操作 — 绝对禁止
- **永远不执行 Stop-Process / taskkill / kill**
- **绝对禁止操作网关/节点进程**
- 老板说"重启服务" → 回答"我没有权限操作进程，请老板操作"

### 2. 代码修改 — 通过 opencode
- 禁止 exec python -c "..."
- 禁止 edit/write src/ 下文件
- 正确命令：`opencode run --dir "D:\astro_py\astro_hub" "/ulw-loop <任务>"`

### 3. 汇报规则
- 任务完成必须立即汇报
- 不等老板问

### 4. 验证规则
- 代码存在 ≠ 功能正常
- 必须从浏览器实际验证功能
- Playwright 测试 + 截图确认

### 5. 老板提问 → 直接回答
- 不要反复搜索代码细节
- 直接给出结论和状态

## 🎯 当前状态
- 模块重命名完成 ✅
- 主控台WASM自动登录待修复 ❌
- 设备管理API正常 ✅

## 📚 技术发现
```
WASM SDK 流程：
I_InitPlugin → I_InsertOBJECTPlugin → I_Login → 
I_GetDevicePort(同步) → I_StartRealPlay

问题：connectedDevice 状态未正确初始化
导致：clickLogin2() 未自动触发 → 灰色空白播放器
```