# 修复计划 v9.0

## 任务概要
用户反馈4个问题，需要查找资料并提交修复计划。

---

## 📌 任务1：web 版本号仍为 8.39

### 问题诊断
1. **前台显示**：`index.html` 第 210 行显示 `<span class="version" id="version-display">...</span>`
2. **加载方式**：`index.html` 第 2386 行使用 `fetch('/api/v1/version')` 获取版本信息
3. **后端接口**：`router.py` 第 274-278 行提供了 `/api/v1/version` 接口

### 代码分析
```python
# constants.py
VERSION = "v8.39"
VERSION_NUM = "8.13"

# router.py
@api_router.get("/version")
async def get_version() -> dict:
    return {"version": VERSION, "version_num": VERSION_NUM}
```

### 根本原因
- **constants.py 的版本号已经过期**，需要更新为当前版本（根据 `HEARTBEAT.md`，当前为 v8.42）
- 前端通过 API 加载，但后端返回的是旧版本号

### 修复方案
```python
# astrohub/src/main/constants.py
VERSION = "v8.42"
VERSION_NUM = "8.15"
```

### 执行方法
1. 打开 `astrohub/src/main/constants.py`
2. 第 8-9 行：
   - `VERSION = "v8.42"`
   - `VERSION_NUM = "8.15"`
3. API 会自动返回新版本号

---

## 📌 任务2：预置点列表包含设备自带预置点

### 问题诊断
1. **获取方式**：`ptz.py` 第 286-313 行的 `list_presets()` 方法调用 `GET /ISAPI/PTZCtrl/channels/1/presets`
2. **渲染逻辑**：`index.html` 第 2325-2333 行的 `loadPresetList()` 函数渲染所有返回的预置点

### 代码分析
```python
# ptz.py
def list_presets(self) -> list[dict]:
    result = self.client.get("/PTZCtrl/channels/1/presets")
    if result.status_code != 200:
        return []
    # 解析 XML，返回所有预置点：[{"id": int, "name": str}, ...]
    for p in root.findall(".//PTZPreset"):
        preset_id = (p.findtext("id") or "").strip()
        preset_name = (p.findtext("presetName") or "").strip()
        presets.append({"id": int(preset_id), "name": preset_name or f"Preset {preset_id}"})
    return presets
```

前端渲染：
```javascript
// index.html
resp.presets.forEach(function(p) {
    var opt = document.createElement('option');
    opt.value = p.id;
    opt.textContent = p.name ? ('P' + p.id + ' - ' + p.name) : '预置点 ' + p.id;
    sel.appendChild(opt);
});
```

### 根本原因
- **`GET /ISAPI/PTZCtrl/channels/1/presets` 返回所有预置点**（包括设备自带的）
- 没有区分设备预设 vs 用户预设的过滤逻辑
- 前端无过滤机制

### 修复方案（方案A：隐藏设备预设）
1. **识别设备预设规则**（根据 Hikvision 通用模式）：
   - 设备预设通常有固定的名称（如 `HOME`, `NAME_1`, `NAME_2` 等）
   - 设备预设的 ID 范围通常较小（如 1-10）
   - 用户预设通常是用户自定义的名称

2. **后端过滤**：
   ```python
   # ptz.py
   def list_presets(self) -> list[dict]:
       presets = ...  # 获取所有预置点
       filtered_presets = []
       preset_names = {"HOME", "NAME_1", "NAME_2"}  # 常见设备预设名称

       for p in presets:
           # 方式1: 按名称过滤（推荐）
           if p.name and p.name in preset_names:
               continue  # 跳过设备预设

           # 方式2: 按ID过滤（备选）
           # if p.id <= 10:  # 假设设备预设是ID 1-10
           #     continue

           filtered_presets.append(po froz
       return filtered_presets
   ```

3. **前端渲染**（无需改动，直接过滤后渲染）

### 执行方法
1. 打开 `astrohub/src/ptz/isapi/ptz.py`
2. 第 286-313 行的 `list_presets()` 方法
3. 在返回前增加过滤逻辑
4. 重启服务测试

---

## 📌 任务3：媒体信息与操作日志刷新顺序不一致

### 问题诊断
1. **媒体信息（`mediaLogBox`）**：`index.html` 第 2736 行
2. **操作日志（`operationLogBox`）**：`index.html` 第 199-206 行

### 代码对比

#### 媒体信息（从下到上，新内容在底部）
```javascript
// index.html 第 2736-2751 行
function mediaLog(msg, type) {
    var box = document.getElementById('mediaLogBox');
    if (!box) return;
    var entry = document.createElement('div');
    entry.style.cssText = 'color:' + color + ';font-size:11px;font-family:monospace;line-height:1.4;margin-bottom:2px';
    entry.textContent = msg;
    box.appendChild(entry);  // 追加到末尾
    while (box.children.length > 100) box.removeChild(box.firstChild);  // 移除最早的
    box.scrollTop = box.scrollHeight;  // 自动滚动到底部
}

function addLog(level, msg) {
    var c = document.getElementById('logContainer');
    if (!c) return;
    var d = document.createElement('div');
    d.className = 'log-entry ' + level;
    d.textContent = '[' + new Date().toLocaleTimeString() + '] ' + msg;
    c.insert
    if (c.children.length > 50) c.removeChild(c.lastChild);
}
```

#### 操作日志（从上到下，新内容在顶部）
```javascript
// index.html 第 2391 行
function operationLog(msg, type='info') {
    const box = document.getElementById('operationLogBox');
    if (!box) { console.warn('[operationLog] operationLogBox not found'); return; }
    const entry = document.createElement('div');
    entry.style.cssText = 'color:' + color + ';margin:1px 0;padding:1px 6px;font-size:11px;font-family:monospace;line-height:1.3';
    entry.textContent = '[' + time + '] ' + icon + ' ' + msg;
    box.insertBefore(entry, box.firstChild);  // 插入到开头
    if (box.children.length > 50) box.removeChild(box.lastChild);
}
```

### 根本原因
- **媒体信息**：使用 `appendChild()` 追加到末尾，最旧的在底部 → 新内容在顶部 → 需要 `scrollTop = box.scrollHeight` 自动滚动
- **操作日志**：使用 `insertBefore(entry, box.firstChild)` 插入到开头 → 最新的在顶部
- **刷新方向不同**：一个最新在顶部，一个最新在底部

### 修复方案
**统一为"媒体信息"风格"（最新在底部，从上到下查阅）**：

#### 方案1：修改操作日志（推荐）
将 `operationLog()` 改为使用 `appendChild()`：

```javascript
function operationLog(msg, type='info') {
    const box = document.getElementById('operationLogBox');
    if (!box) return;

    const entry = document.createElement('div');
    entry.style.cssText = 'color:' + color + ';margin:1px 0;padding:1px 6px;font-size:11px;font-family:monospace;line-height:1.3';
    entry.textContent = '[' + time + '] ' + icon + ' ' + msg;

    box.appendChild(entry);  // 改为 appendChild
    if (box.children.length > 50) box.removeChild(box.firstChild);  // 移除最早的（最底部）
}
```

#### 方案2：修改媒体信息（备选）
改为使用 `insertBefore()`：
```javascript
function mediaLog(msg, type) {
    var box = document.getElementById('mediaLogBox');
    if (!box) return;
    var entry = document.createElement('div');
    entry.style.cssText = 'color:' + color + ';font-size:11px;font-family:monospace;line-height:1.4;margin-bottom:2px';
    entry.textContent = msg;
    box.insertBefore(entry, box.firstChild);  // 改为 insertBefore
    while (box.children.length > 100) box.removeChild(box.lastChild);
}
```

### 推荐方案
**方案1**：统一使用 appendChild，因为：
- 最新的日志通常在最底部，符合数据流方向（新数据在末尾）
- 无需修改滚动逻辑
- 操作日志增加记录时，更自然的阅读顺序

### 执行方法
1. 打开 `astrohub/src/web/index.html`
2. 搜索 `function operationLog(`（约第 2391 行）
3. 将 `box.insertBefore(entry, box.firstChild);` 改为 `box.appendChild(entry);`
4. 将 `box.removeChild(box.lastChild);` 改为 `box.removeChild(box.firstChild);`（移除最早的）
5. 重启前端服务测试

---

## 📌 任务4：滤镜与日夜模式 ISAPI 控制

### 老板要求
1. 找到 ISAPI 控制端点
2. 提供强制启动/关闭滤镜的方法
3. 说明切换条件
4. 说明如何长期固定模式

### ISAPI 资料整理（Hikvision 标准规范）

#### 1. 图像配置主端点
**GET/PUT** `GET /ISAPI/Image/channels/{channel}`
```bash
GET http://<ip>/ISAPI/Image/channels/1
```

**返回示例**：
```xml
<ImageChannelEntity xmlns="http://www.hikvision.com/ver20/XMLSchema">
  <video3DMode>disabled</video3DMode>
  <examplesCount>0</examplesCount>
  <imageAnimation>false</imageAnimation>
  <exposureMode>manual</exposureMode>
  <exposureTime>4000</exposureTime>
  <exposureProgram>auto</exposureProgram>
  <exposureCompensation>0</exposureCompensation>
  <imagesPerSecond>15</imagesPerSecond>
  <backlightCompensation>false</backlightCompensation>
  <dayNightMode>auto</dayNightMode>
  <irCutFilter>auto</irCutFilter>
</ImageChannelEntity>
```

#### 2. 关键参数

| 参数 | 值 | 说明 |
|------|-----|------|
| `dayNightMode` | `day` / `night` / `manual` | 日夜模式 |
| `irCutFilter` | `on` / `off` / `auto` | IRCut 滤镜开关 |
| `backlightCompensation` | `true` / `false` | 背光补偿（bLC） |

#### 3. 额端点（可选）

| 端点 | 用途 |
|------|------|
| `GET/PUT /ISAPI/Image/channels/1/Color` | 颜色增强配置（可选，用于白天/夜间的色彩调整） |

### API 端点设计

#### 方案1：统一入口（推荐）

**GET** `/api/v1/ptz/{device_id}/image/filter` - 获取滤镜/日夜模式
```python
# 返回示例
{
    "success": true,
    "data": {
        "dayNightMode": "auto",      # auto / day / night
        "irCutFilter": "auto",       # on / off / auto
        "backlightCompensation": false
    }
}
```

**PUT** `/api/v1/ptz/{device_id}/image/filter` - 设置滤镜/日夜模式
```python
{
    "success": true,
    "message": "滤镜设置成功"
}

# 请求体示例
{
    "dayNightMode": "night",       # 手动切换到夜间模式
    "irCutFilter": "off",          # 强制关闭 IRCut 滤镜
    "backlightCompensation": true  # 打开背光补偿
}
```

#### 方案2：分端点（备选）

- `GET/PUT /api/v1/ptz/{device_id}/image/day-night` - 日夜模式
- `GET/PUT /api/v1/ptz/{device_id}/image/ircut` - IRCut 滤镜
- `GET/PUT /api/v1/ptz/{device_id}/image/bcl` - 背光补偿

**推荐方案1**：统一入口，减少端点数量。

### 切换条件说明

#### dayNightMode 参数
| 值 | 说明 | 触发条件（自动模式） |
|----|------|---------------------|
| `manual` | 手动模式 | 用户手动设置 |
| `auto` | 自动日夜判断 | 根据环境光线自动切换 |
| `day` | 白天模式 | 用户强制白天 |
| `night` | 夜间模式 | 用户强制夜间 |

#### irCutFilter 参数
| 值 | 说明 |
|----|------|
| `on` | 闭合 IRCut 滤镜（白天） |
| `off` | 断开 IRCut 滤鉴（夜间） |
| `auto` | 自动切换 |

#### 常见自动切换逻辑（厂商默认策略）
1. 设备根据 **环境亮度（ILLUMINANCE）** 自动判断：
   - 亮度 > 阈值 → 白天（irCutFilter=on, night2dayColor=high）
   - 亮度 < 阈值 → 夜间（irCutFilter=off, night2dayColor=low）
2. **背光补偿（bLC）** 影响切换：
   - bLC=true, ILLUMINANCE 适中 → 白天
   - bLC=false, ILLUMINANCE 低 → 夜间

### 如何长期固定模式

#### 方法1：手动设置（推荐）
用户在 web 界面设置后，无需关心自动切换：
```python
# 设置为夜间模式，强制关闭 IRCut 滤架
apiPut('/api/v1/ptz/{device_id}/image/filter', {
    "dayNightMode": "night",
    "irCutFilter": "off",
    "backlightCompensation": false
})
```

#### 方法2：禁用自动切换（可选）
设备通常有 `autond2d` 参数（自动日夜切换）：
```python
# 禁用自动日夜切换
apiPut('/ISAPI/Image/channels/1', f'''
<?xml version="1.0" encoding="UTF-8"?>
<ImageChannelEntity xmlns="http://www.hikvision.com/ver20/XMLSchema">
  <autond2d>false</autond2d>
  <dayNightMode>night</dayNightMode>
  <irCutFilter>off</irCutFilter>
</ImageChannelEntity>
''')
```

#### 方法3：设置环境参数使模式固定
如果设备仍有自动切换但用户希望固定模式：
1. 停止自动日夜切换
2. 强制设置滤镜方向
3. 手动调整 bLC（背光补偿）到合适值，防止设备误判

### Web 界面设计

#### 新增 UI 模块（画面控制区或新增区块）
```html
<div class="collapsible-section" id="filterControlSection">
    <div class="collapsible-header">
        <h3>🎨 滤镜与日夜设置</h3>
        <span class="collapse-icon">▼</span>
    </div>
    <div class="collapsible-content">
        <div class="card">
            <!-- 日夜模式 -->
            <label style="font-size:11px;color:#8b949e">日夜模式</label>
            <select id="dayNightMode" onchange="setDayNightMode(this.value)">
                <option value="auto">自动</option>
                <option value="day">白天</option>
                <option value="night">夜间</option>
            </select>

            <!-- IRCut 滤镜开关 -->
            <label style="font-size:11px;color:#8b949e;margin-top:8px">IRCut 滤镜</label>
            <select id="irCutFilter" onchange="setIRCutFilter(this.value)">
                <option value="auto">自动</option>
                <option value="on">开启（白天）</option>
                <option value="off">关闭（夜间）</option>
            </select>

            <!-- 背光补偿 -->
            <label style="font-size:11px;color:#8b949e;margin-top:8px">背光补偿</label>
            <label class="switch">
                <input type="checkbox" id="backlightCompensation" onchange="setBacklightCompensation(this.checked)">
                <span class="slider"></span>
            </label>

            <!-- 当前状态显示 -->
            <div style="font-size:11px;color:#58a6ff;margin-top:12px">
                当前: {{mode}} / {{filter}} / {{blc}}
            </div>
        </div>
    </div>
</div>
```

#### JavaScript 函数
```javascript
// 设置日夜模式
function setDayNightMode(mode) {
    apiPut('/api/v1/ptz/' + deviceIp + '/image/filter', {
        dayNightMode: mode
    }).then(r => {
        if (r && r.success) {
            showToast('success', '日夜模式: ' + mode);
            operationLog('日夜模式: ' + mode, 'success');
        }
    });
}

// 设置 IRCut 滤关
function setIRCutFilter(filter) {
    apiPut('/api/v1/ptz/' + deviceIp + '/image/filter', {
        irCutFilter: filter
    }).then(r => {
        if (r && r.success) {
            showToast('success', '滤镜: ' + filter);
            operationLog('IRCut 滤持: ' + filter, 'success');
        }
    });
}

// 设置背光补偿
function setBacklightCompensation(enabled) {
    apiPut('/api/v1/ptz/' + deviceIp + '/image/filter', {
        backlightCompensation: enabled
    }).then(r => {
        if (r && r.success) {
            showToast('success', '背光补偿: ' + (enabled ? '开启' : '关闭'));
        }
    });
}

// 初始化加载滤镜状态
function loadFilterStatus(deviceIp) {
    apiGet('/api/v1/ptz/' + deviceIp + '/image/filter').then(r => {
        if (r && r.success && r.data) {
            var data = r.data;
            document.getElementById('dayNightMode').value = data.dayNightMode || 'auto';
            document.getElementById('irCutFilter').value = data.irCutFilter || 'auto';
            document.getElementById('backlightCompensation').checked = data.backlightCompensation || false;
        }
    });
}
```

### 执行优先级版本计划

#### v9.1（高优先级）
1. 更新版本号（constants.py）
2. 修复操作日志刷新顺序（统一为 appendChild）

#### v9.2（中优先级）
3. 预置点过滤（识别并隐藏设备预设）

#### v9.3（低优先级）
4. 滤镜/日夜模式 ISAPI 控制（需要资料收集和前端设计）

### 总结

**任务1（版本号）**：更新 `constants.py` 第 8-9 行
**任务2（预置点）**：在 `list_presets()` 方法增加名称过滤逻辑
**任务3（刷新顺序）**：修改 `operationLog()` 函数，改为 `appendChild()` 追加
**任务4（滤镜控制）**：
    - ISAPI 端点：`/ISAPI/Image/channels/1`，参数 `dayNightMode`、`irCutFilter`
    - 控制 API：`/api/v1/ptz/{device_id}/image/filter`（GET/PUT）
    - 切换条件：根据环境光线、背光补偿自动判断
    - 长期固定：手动设置参数 + 禁用 `autond2d`
