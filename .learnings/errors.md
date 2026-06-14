# ERRORS.md - 错误记录

## ERROR-20260611-001: JS 语法错误 - 重复代码块

**时间**: 2026-06-11
**优先级**: HIGH
**状态**: FIXED
**文件**: `src/web/index.html`

### 问题描述

修改 `window.clickLogin2()` 调用时，留下重复的代码块，导致 JavaScript 语法错误。

### 错误信息

```
SyntaxError: missing ) after argument list
    at line 83
```

### 表现

- 所有 IIFE 内函数无法执行
- `refreshDevices is not defined`
- 页面加载后所有功能失效

### 定位方法

使用 `node --check` 验证提取的 JS 脚本：

```python
import re, subprocess
scripts = re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL)
with open('temp.js', 'w') as f: f.write(scripts[0])
subprocess.run(['node', '--check', 'temp.js'])
```

### 修复

删除第 255-260 行的重复代码：

```javascript
// 删除前：
if (window.connectedDevice && window.clickLogin2) {
    window.clickLogin2();
}
    window.clickLogin2();  // 重复！
}                           // 多余！

// 删除后：
if (window.connectedDevice && window.clickLogin2) {
    window.clickLogin2();
}
```

### 教训

1. 编辑代码后必须检查语法
2. 大量编辑后运行 `python tests/check_js.py`
3. 注意 `edit` 工具不会自动检测语法错误

### 建议行动

- 创建 pre-commit hook 检查 JS 语法
- 每次修改 index.html 后自动运行 `check_js.py`

---

## ERROR-20260611-002: 函数未暴露到全局

**时间**: 2026-06-11
**优先级**: MEDIUM
**状态**: FIXED
**文件**: `src/web/index.html`

### 问题描述

重命名 `toggleOsd` 为 `togglePtzOsd`/`toggleInfoOsd`，但忘记更新 `_expose` 数组。

### 错误信息

```
toggleOsd is not defined
```

### 修复

更新 `_expose` 数组：

```javascript
var _expose = [
    // ... 其他函数
    togglePtzOsd, toggleInfoOsd,  // 替换 toggleOsd
    setFocusMode,                  // 新增
    showToast, addLog,             // 新增工具函数
];
```

### 教训

1. 重命名函数时必须同步更新 `_expose`
2. 添加新函数时检查是否需要全局暴露
3. IIFE 内的函数必须显式暴露才能被 HTML onclick 调用

---

## ERROR-20260611-003: 自动恢复触发时机错误

**时间**: 2026-06-11
**优先级**: HIGH
**状态**: FIXED
**文件**: `src/web/index.html`

### 问题描述

自动恢复代码在主控台页面切换回调中，而非 `refreshDevices` 回调中。

### 表现

- 页面加载时不会自动恢复
- 只有点击"主控台"按钮才触发自动恢复
- 右上角状态显示"未连接"

### 修复

移动到 `refreshDevices` 成功回调内：

```javascript
// 修改前：在页面切换回调中
if (btn.getAttribute('data-page') === 'console') {
    // 自动恢复代码
}

// 修改后：在 refreshDevices 回调中
function refreshDevices() {
    return apiGet('/api/v1/devices').then(function(result) {
        allDevices = result.data || [];
        renderDevices(allDevices);
        // 自动恢复代码
        var targetDev = allDevices.find(function(d) { return d.has_credentials; });
        if (targetDev) { /* 连接 */ }
    });
}
```

### 教训

1. 页面加载时的逻辑应该在初始化/数据加载回调中
2. 不要假设用户会切换页面
3. 分析代码执行时机，确保在正确的时机触发
