# TOOLS.md - Local Notes

Skills define _how_ tools work. This file is for _your_ specifics — the stuff that's unique to your setup.

## 重要概念澄清

### 网关 (Gateway)
- **网关 = OpenClaw Gateway**：OpenClaw 的核心服务，负责消息路由、节点管理等
- **铁律：绝对禁止操作网关**：不执行 `openclaw gateway start/stop/restart/status` 等命令
- **网关进程**：`openclaw.exe`、`node.exe` 等 OpenClaw 相关进程

### AstroHub
- **AstroHub = 我开发的应用**：PTZ 设备管理、功能测试、限位测试等
- **可以操作**：启动、停止、重启 AstroHub 服务（端口 10280）
- **启动命令**：`cd astrohub && python -m src.main.main --headless`
- **进程名**：`python.exe`（运行 astrohub）

---

## What Goes Here

Things like:

- Camera names and locations
- SSH hosts and aliases
- Preferred voices for TTS
- Speaker/room names
- Device nicknames
- Anything environment-specific

## Examples

```markdown
### Cameras

- living-room → Main area, 180° wide angle
- front-door → Entrance, motion-triggered

### SSH

- home-server → 192.168.1.100, user: admin

### TTS

- Preferred voice: "Nova" (warm, slightly British)
- Default speaker: Kitchen HomePod
```

## Why Separate?

Skills are shared. Your setup is yours. Keeping them apart means you can update skills without losing your notes, and share skills without leaking your infrastructure.

---

Add whatever helps you do your job. This is your cheat sheet.

## 图片识别（Qwen3.7 Plus Vision）

### 唯一可用方法：Coding Plan Pro 端点

**端点**: `https://coding.dashscope.aliyuncs.com/apps/anthropic/v1/messages`
**格式**: Anthropic Messages API
**模型**: `qwen3.7-plus`（支持文本、图像、视频输入）
**API Key**: `sk-sp-438656a7e1b740cdbac3f4d0f5369df7`

```python
import base64, json, urllib.request

with open('image.png', 'rb') as f:
    img_b64 = base64.b64encode(f.read()).decode('utf-8')

data = {
    'model': 'qwen3.7-plus',
    'max_tokens': 1024,
    'messages': [{
        'role': 'user',
        'content': [
            {'type': 'image', 'source': {'type': 'base64', 'media_type': 'image/png', 'data': img_b64}},
            {'type': 'text', 'text': '请描述这个图片'}
        ]
    }]
}

req = urllib.request.Request(
    'https://coding.dashscope.aliyuncs.com/apps/anthropic/v1/messages',
    data=json.dumps(data).encode('utf-8'),
    headers={
        'Content-Type': 'application/json',
        'x-api-key': 'sk-sp-438656a7e1b740cdbac3f4d0f5369df7',
        'anthropic-version': '2023-06-01'
    }
)
with urllib.request.urlopen(req, timeout=60) as resp:
    result = json.loads(resp.read().decode('utf-8'))
    for block in result['content']:
        if block['type'] == 'text': print(block['text'])
```

### 不可用方法（禁止使用）

| 方法 | 原因 |
|------|------|
| `image` 工具 | Bug：provider 名转小写，无法匹配 models.json |
| `mmx vision` | MiniMax API 配额用完 |
| `unified-search --vision` | 依赖 minimax-multimodal 未安装 |
| `qwen-vision` 技能 | DashScope 原生端点拒绝 Coding Plan API key |
| 标准 DashScope 端点 | `dashscope.aliyuncs.com` 不接受 Coding Plan API key |

### 便捷脚本

```bash
# 单图分析
python astrohub/tools/vision.py <图片路径> "分析提示词"

# 多图分析（拼接多个 base64）
python astrohub/tools/vision.py screenshot.png "描述这个截图中的UI和状态"
```

脚本位置：`astrohub/tools/vision.py`

### 模型参数

- 输入：文本、图像、视频
- 最大像素/图：16M
- 最大图片数：2048
- 上下文：1M token
- Function Calling：支持

---

## 主动工具使用

- 优先安全内部工作：草稿、检查、准备下一步
- 下一步明确且可逆时，用工具推进工作
- 在求助前尝试多种方法和替代工具
- 用工具测试假设、验证机制、提前发现阻塞
- 涉及发送/花钱/删除/重排/联系时，停下来问老板
- 工具结果改变活跃工作时，更新 `~/proactivity/session-state.md`
