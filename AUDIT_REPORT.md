# AstroHub 三大模块逐行校验报告

**校验日期**: 2026-05-08
**校验依据**: doc/review/M1_method.csv + M1_speed_method.csv
**校验文件**: function.py (738行) / limit.py (585行) / speed.py (234行)

---

## 通过标准（不可绕过）

**所有 P4.x 功能探测**：GET 解析范围 → PUT 测试值 → GET 确认值在范围内 → PUT 恢复原值
**HTTP 状态码 ≠ 通过，supported 字段 ≠ 通过**

---

## P5: PTZ运动控制

### P5.0 设置HOME位置
**CSV要求**: 预置点编号和坐标正确；gotohome指令可用，无报错，预置点必须是10号，不得额外生成预置点，不得覆盖原有预置点，预置点位置精准0偏差。

**当前代码检查**:
- goto_home() 方法 → 使用 preset 10 ✅
- 验证逻辑 → 持续采样20点/严格等于预置点坐标 ✅ (已修复)
- 不覆盖预置点 → 检查 set_preset(10) 是否会覆盖 → 需要确认
- 0偏差 → 20点全部严格匹配 ✅

### P5.1 Continuous Move
**CSV要求**: 设备支持Continuous Move并能正确执行，返回HOME成功

**当前代码检查**:
- continuous_move() API 是否存在
- 执行后调用 goto_home 验证

### P5.2 Absolute Move
**CSV要求**: 设备支持Absolute Move并能正确执行，评审阶段要求必须实现

**当前代码检查**:
- absolute_move() 方法是否存在

### P5.4 Pan速度控制
**CSV要求**: 得出正确控制速度的方法，是否支持速度变化，测试阶段设备明确有速度变化

### P5.5 ZOOM范围
**CSV要求**: 得出设备是否支持zoom，测试设计中Z明确支持

---

## P6: 限位测试

### P6.0 预设方法与文件
**CSV要求**: 创建方法成功，记录方法可用

### P6.3 P轴限位
**CSV要求**: 测试阶段本设备无限位，如结论不同则评审不通过

**当前代码检查**:
- 限位检测逻辑 → 连续移动直到跳变或20点同值
- 无限位判定 → 需要确认代码是否正确处理无限位

### P6.4 T限位/翻转
**CSV要求**: 自动翻转，上限记录为900，下限-200

### P6.5 Z限位
**CSV要求**: 上限为320，下限为10

---

## P5-P8: 速度测试

### P5 通用采样与后处理
**CSV要求**: continuous_move → 每0.1秒采样 → 丢弃前后各5样本 → post_process_csv计算 → 速度值4位小数

**当前代码检查**:
- 采样间隔 → 检查是否为 0.1s
- 丢弃逻辑 → samples[5:-5]
- 速度公式 → \|end-start\| × 0.1° / 10.0s (不是100.0)
- 小数位数 → round(..., 4)

### P6 Pan轴
**CSV要求**: 
- 有限位：absolute_move(azimuth=P_max/P_min) → wait_stable → continuous_move
- 无限位：preset_goto(10) → sleep(3) → wait_stable → continuous_move

### P7 Tilt轴
**CSV要求**: 
- 正向：absolute_move(el=T_max=900) → wait_stable → continuous_move(tilt=speed)
- 负向：absolute_move(el=T_min=-200) → wait_stable → continuous_move(tilt=-speed)

### P8 三档Zoom影响
**CSV要求**: Zoom循环：absolute_move_zoom(Z_min) → wait(2s) → 测试P+T → 回HOME → absolute_move_zoom(Z_mid) → wait(2s) → 测试P+T → 回HOME → absolute_move_zoom(Z_max) → wait(2s) → 测试P+T

### P8.1 档位切换返回HOME
**CSV要求**: preset_goto(10) → sleep(3) → 验证HOME(az≈1800, el≈450) → absolute_move_zoom(next)

---

## P4: 功能探测（强制验证流程）

| P# | CSV要求 | 当前代码状态 | 是否符合 |
|---|---------|-------------|---------|
| P4.1 | IrLED上下限 1~100 | 需逐行检查 _test_value 逻辑 | 待确认 |
| P4.2 | 白光上下限 1~255 | 需逐行检查 _test_value 逻辑 | 待确认 |
| P4.3 | Gain上下限 1~100 | 需逐行检查 _test_value 逻辑 | 待确认 |
| P4.4-P4.20 | 操作指令正确 | 需逐行检查端点+PUT验证 | 待确认 |
| P4.21 | 还原成功 | restore_all() 方法 | 待确认 |

**_test_value 强制流程**:
1. GET 原始值
2. PUT 测试值
3. GET 再次确认值已改变且在范围内 ← 这是通过的关键
4. PUT 恢复原值
5. GET 确认恢复成功
