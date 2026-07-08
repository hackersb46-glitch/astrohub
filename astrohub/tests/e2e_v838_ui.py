"""
v8.38 Playwright E2E 验证脚本
验证主控台界面修改：
1. 左侧运动控制：PTZ OSD 开关存在，变焦/对焦区已移除
2. 右侧画面控制：布局顺序正确
3. 白平衡下拉：3选项（自动/手动/局部）
4. 白平衡手动模式：R/B滑动条显示
5. 白平衡局部模式：框选+定时显示
6. 对焦下拉：3选项（自动/手动/局部）
7. 对焦手动模式：焦点移动按钮显示
8. 对焦局部模式：框选+定时显示
9. 降噪位于饱和度/锐度下方
10. OSD控制区无PTZ开关（仅信息）
"""
import asyncio
import sys
import os

async def main():
    from playwright.async_api import async_playwright
    
    errors = []
    passed = []
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        # 拦截 console 错误
        console_errors = []
        page.on("console", lambda msg: console_errors.append(f"[{msg.type}] {msg.text}") if msg.type == "error" else None)
        
        # 拦截 request 失败
        request_errors = []
        page.on("requestfailed", lambda req: request_errors.append(f"{req.url} - {req.failure}"))
        
        # 导航到主控台页面
        await page.goto("http://127.0.0.1:10280/", wait_until="networkidle", timeout=15000)
        
        # 切换到主控台页面
        console_btn = page.locator('[data-page="console"]')
        if await console_btn.count() > 0:
            await console_btn.click()
            await page.wait_for_timeout(500)
        else:
            errors.append("无法找到主控台导航按钮")
        
        # ========== 测试1: 左侧运动控制 - PTZ OSD 开关存在 ==========
        try:
            ptz_osd_switch = page.locator('#ptzOsdSwitch')
            if await ptz_osd_switch.count() > 0:
                passed.append("[PASS] 测试1: 左侧面板 PTZ OSD 开关存在")
            else:
                errors.append("[FAIL] 测试1: 左侧面板未找到 PTZ OSD 开关 (ptzOsdSwitch)")
        except Exception as e:
            errors.append(f"[FAIL] 测试1异常: {e}")
        
        # ========== 测试2: 左侧运动控制 - 旧的变焦/对焦区已移除 ==========
        try:
            # 检查运动控制区内不应有 focusMode select（旧的）
            ptz_section = page.locator('#ptzControlSection')
            old_focus_select = ptz_section.locator('select#focusMode')
            if await old_focus_select.count() == 0:
                passed.append("[PASS] 测试2: 左侧面板变焦/对焦区已移除（无focusMode select）")
            else:
                errors.append("[FAIL] 测试2: 左侧面板仍存在 focusMode select")
        except Exception as e:
            errors.append(f"[FAIL] 测试2异常: {e}")
        
        # ========== 测试3: 左侧运动控制 - 旧的焦距按钮已移除 ==========
        try:
            ptz_section = page.locator('#ptzControlSection')
            # 检查不应该有 ptzZoom 调用（焦距按钮）
            zoom_btns = ptz_section.locator('button[onmousedown*="ptzZoom"]')
            if await zoom_btns.count() == 0:
                passed.append("[PASS] 测试3: 左侧面板焦距按钮已移除")
            else:
                errors.append(f"[FAIL] 测试3: 左侧面板仍存在 {await zoom_btns.count()} 个焦距按钮")
        except Exception as e:
            errors.append(f"[FAIL] 测试3异常: {e}")
        
        # ========== 测试4: 右侧画面控制 - 白平衡下拉3选项 ==========
        try:
            wb_select = page.locator('#wbMode')
            if await wb_select.count() > 0:
                options = await wb_select.locator('option').all()
                opt_values = []
                for opt in options:
                    opt_values.append(await opt.get_attribute('value'))
                
                expected = ['auto', 'manual', 'local']
                if opt_values == expected:
                    passed.append(f"[PASS] 测试4: 白平衡下拉选项正确: {opt_values}")
                else:
                    errors.append(f"[FAIL] 测试4: 白平衡下拉选项不符: 期望{expected}, 实际{opt_values}")
            else:
                errors.append("[FAIL] 测试4: 未找到白平衡下拉 (wbMode)")
        except Exception as e:
            errors.append(f"[FAIL] 测试4异常: {e}")
        
        # ========== 测试5: 白平衡 - R/B滑动条默认隐藏 ==========
        try:
            wb_manual = page.locator('#wbManualControls')
            if await wb_manual.count() > 0:
                display_val = await wb_manual.get_attribute('style')
                if 'display:none' in display_val or 'display: none' in display_val:
                    passed.append("[PASS] 测试5: 白平衡R/B滑动条默认隐藏")
                else:
                    errors.append(f"[FAIL] 测试5: 白平衡R/B滑动条未隐藏: style={display_val}")
            else:
                errors.append("[FAIL] 测试5: 未找到 wbManualControls")
        except Exception as e:
            errors.append(f"[FAIL] 测试5异常: {e}")
        
        # ========== 测试6: 白平衡 - 局部控制默认隐藏 ==========
        try:
            wb_local = page.locator('#wbLocalControls')
            if await wb_local.count() > 0:
                display_val = await wb_local.get_attribute('style')
                if 'display:none' in display_val or 'display: none' in display_val:
                    passed.append("[PASS] 测试6: 白平衡局部控制默认隐藏")
                else:
                    errors.append(f"[FAIL] 测试6: 白平衡局部控制未隐藏: style={display_val}")
            else:
                errors.append("[FAIL] 测试6: 未找到 wbLocalControls")
        except Exception as e:
            errors.append(f"[FAIL] 测试6异常: {e}")
        
        # ========== 测试7: 白平衡 - 切换到手动模式，R/B显示 ==========
        try:
            await page.select_option('#wbMode', 'manual')
            await page.wait_for_timeout(300)
            
            wb_manual = page.locator('#wbManualControls')
            display_val = await wb_manual.get_attribute('style')
            if 'display:none' not in display_val and 'display: none' not in display_val:
                passed.append("[PASS] 测试7: 白平衡手动模式 → R/B滑动条显示")
            else:
                errors.append(f"[FAIL] 测试7: 白平衡手动模式 R/B仍未显示: style={display_val}")
            
            # 同时验证局部控制隐藏
            wb_local = page.locator('#wbLocalControls')
            local_display = await wb_local.get_attribute('style')
            if 'display:none' in local_display or 'display: none' in local_display:
                pass  # 正确：局部应隐藏
            else:
                errors.append(f"[FAIL] 测试7b: 白平衡手动模式 → 局部控制未隐藏")
        except Exception as e:
            errors.append(f"[FAIL] 测试7异常: {e}")
        
        # ========== 测试8: 白平衡 - 切换到局部模式 ==========
        try:
            await page.select_option('#wbMode', 'local')
            await page.wait_for_timeout(300)
            
            wb_local = page.locator('#wbLocalControls')
            local_display = await wb_local.get_attribute('style')
            if 'display:none' not in local_display and 'display: none' not in local_display:
                passed.append("[PASS] 测试8: 白平衡局部模式 → 局部控制显示")
            else:
                errors.append(f"[FAIL] 测试8: 白平衡局部模式 控制未显示: style={local_display}")
            
            # R/B 应隐藏
            wb_manual = page.locator('#wbManualControls')
            manual_display = await wb_manual.get_attribute('style')
            if 'display:none' in manual_display or 'display: none' in manual_display:
                pass  # 正确
            else:
                errors.append(f"[FAIL] 测试8b: 白平衡局部模式 → R/B未隐藏")
            
            # 验证框选按钮存在
            btn_wb_region = page.locator('#btnWbRegionSelect')
            if await btn_wb_region.count() > 0:
                btn_text = await btn_wb_region.text_content()
                if '🔲' in btn_text:
                    pass  # v8.41: emoji按钮
                else:
                    errors.append(f"[FAIL] 测试8c: 白平衡框选按钮文字错误: '{btn_text}'")
            else:
                errors.append("[FAIL] 测试8c: 未找到白平衡框选按钮")
            
            # 验证定时输入框存在
            wb_timer = page.locator('#wbTimerInput')
            if await wb_timer.count() > 0:
                timer_val = await wb_timer.get_attribute('value')
                if timer_val == '0':
                    pass  # 正确：默认0
                else:
                    errors.append(f"[FAIL] 测试8d: 白平衡定时默认值错误: {timer_val}")
            else:
                errors.append("[FAIL] 测试8d: 未找到白平衡定时输入框")
            
            # v8.41: 验证停止按钮存在且默认禁用
            wb_stop = page.locator('#btnWbLocalStop')
            if await wb_stop.count() > 0:
                is_disabled = await wb_stop.is_disabled()
                if is_disabled:
                    pass  # 正确：默认禁用
                else:
                    errors.append(f"[FAIL] 测试8e: 白平衡停止按钮未禁用")
            else:
                errors.append("[FAIL] 测试8e: 未找到白平衡停止按钮")
                
        except Exception as e:
            errors.append(f"[FAIL] 测试8异常: {e}")
        
        # ========== 测试9: 白平衡 - 切回自动，所有附加控件隐藏 ==========
        try:
            await page.select_option('#wbMode', 'auto')
            await page.wait_for_timeout(300)
            
            wb_manual = page.locator('#wbManualControls')
            manual_display = await wb_manual.get_attribute('style')
            wb_local = page.locator('#wbLocalControls')
            local_display = await wb_local.get_attribute('style')
            
            if ('display:none' in manual_display or 'display: none' in manual_display) and \
               ('display:none' in local_display or 'display: none' in local_display):
                passed.append("[PASS] 测试9: 白平衡自动模式 → 所有附加控件隐藏")
            else:
                errors.append(f"[FAIL] 测试9: 白平衡自动模式 控件未全部隐藏")
        except Exception as e:
            errors.append(f"[FAIL] 测试9异常: {e}")
        
        # ========== 测试10: 对焦下拉3选项 ==========
        try:
            focus_select = page.locator('#focusMode')
            if await focus_select.count() > 0:
                options = await focus_select.locator('option').all()
                opt_values = []
                for opt in options:
                    opt_values.append(await opt.get_attribute('value'))
                
                expected = ['auto', 'manual', 'local']
                if opt_values == expected:
                    passed.append(f"[PASS] 测试10: 对焦下拉选项正确: {opt_values}")
                else:
                    errors.append(f"[FAIL] 测试10: 对焦下拉选项不符: 期望{expected}, 实际{opt_values}")
            else:
                errors.append("[FAIL] 测试10: 未找到对焦下拉 (focusMode)")
        except Exception as e:
            errors.append(f"[FAIL] 测试10异常: {e}")
        
        # ========== 测试11: 对焦 - 焦点移动按钮默认隐藏 ==========
        try:
            focus_move = page.locator('#focusMoveControls')
            if await focus_move.count() > 0:
                display_val = await focus_move.get_attribute('style')
                if 'display:none' in display_val or 'display: none' in display_val:
                    passed.append("[PASS] 测试11: 对焦焦点移动按钮默认隐藏")
                else:
                    errors.append(f"[FAIL] 测试11: 焦点移动按钮未隐藏: style={display_val}")
            else:
                errors.append("[FAIL] 测试11: 未找到 focusMoveControls")
        except Exception as e:
            errors.append(f"[FAIL] 测试11异常: {e}")
        
        # ========== 测试12: 对焦 - 切换到手动模式，焦点按钮显示 ==========
        try:
            await page.select_option('#focusMode', 'manual')
            await page.wait_for_timeout(300)
            
            focus_move = page.locator('#focusMoveControls')
            display_val = await focus_move.get_attribute('style')
            if 'display:none' not in display_val and 'display: none' not in display_val:
                passed.append("[PASS] 测试12: 对焦手动模式 → 焦点移动按钮显示")
            else:
                errors.append(f"[FAIL] 测试12: 对焦手动模式 焦点按钮未显示: style={display_val}")
            
            # 验证按钮文字
            far_btn = page.locator('#focusMoveControls button:has-text("远")')
            near_btn = page.locator('#focusMoveControls button:has-text("近")')
            if await far_btn.count() > 0 and await near_btn.count() > 0:
                pass  # 正确
            else:
                errors.append("[FAIL] 测试12b: 焦点移动按钮文字不正确（远/近）")
            
            # 局部控制应隐藏
            focus_local = page.locator('#focusLocalControls')
            local_display = await focus_local.get_attribute('style')
            if 'display:none' in local_display or 'display: none' in local_display:
                pass
            else:
                errors.append(f"[FAIL] 测试12c: 对焦手动模式 → 局部控制未隐藏")
        except Exception as e:
            errors.append(f"[FAIL] 测试12异常: {e}")
        
        # ========== 测试13: 对焦 - 切换到局部模式 ==========
        try:
            await page.select_option('#focusMode', 'local')
            await page.wait_for_timeout(300)
            
            focus_local = page.locator('#focusLocalControls')
            local_display = await focus_local.get_attribute('style')
            if 'display:none' not in local_display and 'display: none' not in local_display:
                passed.append("[PASS] 测试13: 对焦局部模式 → 局部控制显示")
            else:
                errors.append(f"[FAIL] 测试13: 对焦局部模式 控制未显示: style={local_display}")
            
            # 焦点移动应隐藏
            focus_move = page.locator('#focusMoveControls')
            move_display = await focus_move.get_attribute('style')
            if 'display:none' in move_display or 'display: none' in move_display:
                pass
            else:
                errors.append(f"[FAIL] 测试13b: 对焦局部模式 → 焦点按钮未隐藏")
            
            # 验证框选按钮
            btn_focus_region = page.locator('#btnFocusRegionSelect')
            if await btn_focus_region.count() > 0:
                btn_text = await btn_focus_region.text_content()
                if '🔲' in btn_text:
                    pass  # v8.41: emoji按钮
                else:
                    errors.append(f"[FAIL] 测试13c: 对焦框选按钮文字错误: '{btn_text}'")
            else:
                errors.append("[FAIL] 测试13c: 未找到对焦框选按钮")
            
            # 验证定时输入框
            focus_timer = page.locator('#focusTimerInput')
            if await focus_timer.count() > 0:
                timer_val = await focus_timer.get_attribute('value')
                if timer_val == '0':
                    pass
                else:
                    errors.append(f"[FAIL] 测试13d: 对焦定时默认值错误: {timer_val}")
            else:
                errors.append("[FAIL] 测试13d: 未找到对焦定时输入框")
            
            # v8.41: 验证停止按钮存在且默认禁用
            focus_stop = page.locator('#btnFocusLocalStop')
            if await focus_stop.count() > 0:
                is_disabled = await focus_stop.is_disabled()
                if is_disabled:
                    pass  # 正确：默认禁用
                else:
                    errors.append(f"[FAIL] 测试13e: 对焦停止按钮未禁用")
            else:
                errors.append("[FAIL] 测试13e: 未找到对焦停止按钮")
                
        except Exception as e:
            errors.append(f"[FAIL] 测试13异常: {e}")
        
        # ========== 测试14: 对焦 - 切回自动 ==========
        try:
            await page.select_option('#focusMode', 'auto')
            await page.wait_for_timeout(300)
            
            focus_move = page.locator('#focusMoveControls')
            move_display = await focus_move.get_attribute('style')
            focus_local = page.locator('#focusLocalControls')
            local_display = await focus_local.get_attribute('style')
            
            if ('display:none' in move_display or 'display: none' in move_display) and \
               ('display:none' in local_display or 'display: none' in local_display):
                passed.append("[PASS] 测试14: 对焦自动模式 → 所有附加控件隐藏")
            else:
                errors.append(f"[FAIL] 测试14: 对焦自动模式 控件未全部隐藏")
        except Exception as e:
            errors.append(f"[FAIL] 测试14异常: {e}")
        
        # ========== 测试15: 降噪位于饱和度/锐度下方 ==========
        try:
            # 获取所有 section-subtitle 和关键元素的顺序
            image_section = page.locator('#imageControlSection .collapsible-content .card')
            
            # 获取饱和度、降噪、白平衡的Y坐标位置
            saturation = page.locator('#consoleSaturation')
            dnr_spatial = page.locator('#dnrSpatial')
            wb_mode = page.locator('#wbMode')
            
            if await saturation.count() > 0 and await dnr_spatial.count() > 0 and await wb_mode.count() > 0:
                sat_box = await saturation.bounding_box()
                dnr_box = await dnr_spatial.bounding_box()
                wb_box = await wb_mode.bounding_box()
                
                if sat_box and dnr_box and wb_box:
                    # 降噪Y坐标应大于饱和度Y坐标（在下方）
                    # 白平衡Y坐标应大于降噪Y坐标（在下方）
                    if dnr_box['y'] > sat_box['y'] and wb_box['y'] > dnr_box['y']:
                        passed.append("[PASS] 测试15: 降噪位于饱和度下方，白平衡位于降噪下方")
                    else:
                        errors.append(f"[FAIL] 测试15: 位置错误 - 饱和度Y={sat_box['y']:.0f}, 降噪Y={dnr_box['y']:.0f}, 白平衡Y={wb_box['y']:.0f}")
                else:
                    errors.append("[FAIL] 测试15: 无法获取元素位置")
            else:
                errors.append("[FAIL] 测试15: 关键元素不存在")
        except Exception as e:
            errors.append(f"[FAIL] 测试15异常: {e}")
        
        # ========== 测试16: OSD控制区无PTZ开关 ==========
        try:
            # 在画面控制区查找 ptzOsdSwitch（旧的ID，不应该存在）
            old_ptz_switch = page.locator('#imageControlSection #ptzOsdSwitch')
            if await old_ptz_switch.count() == 0:
                passed.append("[PASS] 测试16: 画面控制区已移除PTZ OSD开关")
            else:
                errors.append("[FAIL] 测试16: 画面控制区仍存在旧的ptzOsdSwitch")
        except Exception as e:
            errors.append(f"[FAIL] 测试16异常: {e}")
        
        # ========== 测试17: 右侧无OSD，左侧有OSD+PTZ ==========
        try:
            right_info = page.locator('#imageControlSection #infoOsdSwitch')
            left_info = page.locator('#ptzControlSection #infoOsdSwitch')
            left_ptz = page.locator('#ptzControlSection #ptzOsdSwitch')
            if await right_info.count() == 0 and await left_info.count() > 0 and await left_ptz.count() > 0:
                passed.append("[PASS] 测试17: 右侧无OSD开关，左侧有OSD+PTZ双开关")
            else:
                rc = await right_info.count()
                lc = await left_info.count()
                lp = await left_ptz.count()
                errors.append(f"[FAIL] 测试17: 右侧info={rc}, 左侧info={lc}, 左侧ptz={lp}")
        except Exception as e:
            errors.append(f"[FAIL] 测试17异常: {e}")
        
        # ========== 测试18: 右侧面板元素顺序完整验证 ==========
        try:
            # v8.40: 增益在自动曝光模式下隐藏，改用手动曝光模式测试
            await page.select_option('#exposureMode', 'manual')
            await page.wait_for_timeout(300)
            # 获取右侧画面控制区所有关键元素的Y坐标，验证顺序
            elements_to_check = [
                ('consoleBrightness', '亮度'),
                ('consoleSaturation', '饱和度'),
                ('dnrSpatial', '空域降噪'),
                ('wbMode', '白平衡模式'),
                ('focusMode', '对焦模式'),
                ('exposureMode', '曝光模式'),
                ('gainLevel', '增益'),
            ]
            
            prev_y = 0
            order_ok = True
            for elem_id, label in elements_to_check:
                elem = page.locator('#' + elem_id)
                if await elem.count() > 0:
                    box = await elem.bounding_box()
                    if box:
                        if box['y'] < prev_y - 5:  # 允许5px误差
                            errors.append(f"[FAIL] 测试18: {label}({elem_id}) Y={box['y']:.0f} 在前一个元素 Y={prev_y:.0f} 之上")
                            order_ok = False
                        prev_y = box['y']
                    else:
                        errors.append(f"[FAIL] 测试18: {label}({elem_id}) 无法获取位置")
                        order_ok = False
                else:
                    errors.append(f"[FAIL] 测试18: {label}({elem_id}) 不存在")
                    order_ok = False
            
            if order_ok:
                passed.append("[PASS] 测试18: 右侧面板元素顺序正确（亮度→饱和度→降噪→白平衡→对焦→曝光→增益）")
        except Exception as e:
            errors.append(f"[FAIL] 测试18异常: {e}")
        
        # ========== 测试19: 定时输入框可以修改值 ==========
        try:
            # 切到局部白平衡
            await page.select_option('#wbMode', 'local')
            await page.wait_for_timeout(300)
            
            wb_timer = page.locator('#wbTimerInput')
            await wb_timer.fill('5')
            val = await wb_timer.input_value()
            if val == '5':
                passed.append("[PASS] 测试19: 白平衡定时输入框可修改值（0→5）")
            else:
                errors.append(f"[FAIL] 测试19: 定时输入框值错误: 期望5, 实际{val}")
        except Exception as e:
            errors.append(f"[FAIL] 测试19异常: {e}")
        
        # ========== 测试20: 白平衡定时输入框 type=text ==========
        try:
            wb_timer = page.locator('#wbTimerInput')
            input_type = await wb_timer.get_attribute('type')
            if input_type == 'text':
                passed.append("[PASS] 测试20: 白平衡定时输入框 type=text（无上下箭头）")
            else:
                errors.append(f"[FAIL] 测试20: 定时输入框 type={input_type}（应为text）")
        except Exception as e:
            errors.append(f"[FAIL] 测试20异常: {e}")
        
        # ========== 测试21: 对焦定时输入框 ==========
        try:
            await page.select_option('#focusMode', 'local')
            await page.wait_for_timeout(300)
            
            focus_timer = page.locator('#focusTimerInput')
            await focus_timer.fill('10')
            val = await focus_timer.input_value()
            input_type = await focus_timer.get_attribute('type')
            
            if val == '10' and input_type == 'text':
                passed.append("[PASS] 测试21: 对焦定时输入框可修改值且type=text")
            else:
                errors.append(f"[FAIL] 测试21: 对焦定时 val={val}, type={input_type}")
        except Exception as e:
            errors.append(f"[FAIL] 测试21异常: {e}")
        
        # ========== 测试22: JS函数存在性检查 ==========
        try:
            functions_check = await page.evaluate("""() => {
                return {
                    onWbModeChange: typeof onWbModeChange === 'function',
                    onFocusModeChange: typeof onFocusModeChange === 'function',
                    stopAutoWhiteBalance: typeof stopAutoWhiteBalance === 'function',
                    stopAutoFocus: typeof stopAutoFocus === 'function',
                    togglePtzOsdSwitch: typeof togglePtzOsdSwitch === 'function',
                    toggleRegionMode: typeof toggleRegionMode === 'function',
                    confirmWbTimer: typeof confirmWbTimer === 'function',
                    confirmFocusTimer: typeof confirmFocusTimer === 'function',
                    stopWbTimer: typeof stopWbTimer === 'function',
                    stopFocusTimer: typeof stopFocusTimer === 'function'
                };
            }""")
            
            missing = [k for k, v in functions_check.items() if not v]
            if len(missing) == 0:
                passed.append("[PASS] 测试22: 所有JS函数已定义")
            else:
                errors.append(f"[FAIL] 测试22: 缺失JS函数: {missing}")
        except Exception as e:
            errors.append(f"[FAIL] 测试22异常: {e}")
        
        # ========== 输出结果 ==========
        print("\n" + "=" * 60)
        print("Playwright E2E - v8.38 UI Test")
        print("=" * 60)
        print(f"\nPASS: {len(passed)}")
        for p_item in passed:
            print(f"  {p_item}")
        
        print(f"\nFAIL: {len(errors)}")
        for e_item in errors:
            print(f"  {e_item}")
        
        if console_errors:
            print(f"\n[WARN] Console错误 ({len(console_errors)}):")
            for ce in console_errors[:5]:
                print(f"  {ce}")
        
        print(f"\nTotal: {len(passed)} passed / {len(errors)} failed")
        print("=" * 60)
        
        await browser.close()
        
        # 退出码
        sys.exit(0 if len(errors) == 0 else 1)

if __name__ == '__main__':
    # v8.41: Windows GBK 编码兼容
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    asyncio.run(main())
