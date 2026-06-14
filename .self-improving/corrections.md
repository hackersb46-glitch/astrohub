# 纠正记录

## COR-20260519-001 — 三大红线重复违反
**日期**: 2026-05-19
**严重性**: Critical
**触发**: 老板明确指出

**错误行为**:
1. 直接 exec python 代码（几十次）
2. 直接 edit/write src/ 下文件
3. Stop-Process 杀进程

**必须执行的行为**:
- 所有开发 → opencode run --dir "D:\astro_py\astro_hub" "/ulw-loop <任务>"
- 所有代码修改 → 通过 opencode
- 服务启停 → 老板操作，不碰
- 网关 → 绝对不碰，一个字都不能执行

**教训**: 宁可没有产出，不可流程错误。
