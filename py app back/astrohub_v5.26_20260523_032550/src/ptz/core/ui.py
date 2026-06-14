"""
PTZ_ASTRO v1.1 - 交互式 CLI 界面模块
提供数字序号选择、密码掩码输入、按键控制（Q 退出/Enter 确认/Esc 清空）。

Author: 雅痞张@南方天文
"""

import sys
from .logger import LOG
from ptz.constants import VERSION, AUTHOR


def clear_screen() -> None:
    """清屏。"""
    import os
    os.system("cls" if os.name == "nt" else "clear")


def print_header() -> None:
    """打印软件头部信息。"""
    print("=" * 60)
    print(f"  PTZ_ASTRO {VERSION} - PTZ 设备启动模块")
    print(f"  软件作者: {AUTHOR}")
    print("=" * 60)
    print()


def print_phase(phase_num: str, phase_name: str) -> None:
    """打印当前阶段。"""
    print()
    print("-" * 60)
    print(f"  >>> 阶段 P{phase_num}: {phase_name}")
    print("-" * 60)
    print()


def print_progress(current: int, total: int, message: str = "") -> None:
    """打印进度信息。"""
    pct = (current / total * 100) if total > 0 else 0
    bar_len = 30
    filled = int(bar_len * current / total) if total > 0 else 0
    bar = "█" * filled + "░" * (bar_len - filled)
    status = f"[{bar}] {pct:.0f}%"
    if message:
        status += f"  {message}"
    print(f"  {status}")


def print_done(message: str) -> None:
    """打印完成信息。"""
    print(f"  ✓ [DONE] {message}")


def print_error(message: str) -> None:
    """打印错误信息。"""
    print(f"  ✗ [ERROR] {message}")


def print_warning(message: str) -> None:
    """打印警告信息。"""
    print(f"  ! [WARNING] {message}")


def input_with_mask(prompt_text: str, visible_chars: int = 2) -> str:
    """密码掩码输入。

    只显示首尾少数几个字符，其余用 * 代替。
    """
    try:
        import msvcrt
    except ImportError:
        # fallback for non-Windows
        import getpass
        return getpass.getpass(prompt_text)

    print(prompt_text, end="", flush=True)
    password = []
    while True:
        ch = msvcrt.getch()
        if ch in (b"\r", b"\n"):  # Enter
            print()
            break
        elif ch == b"\x1b":  # Esc
            password.clear()
            print("\r" + " " * (len(prompt_text) + 40) + "\r", end="")
            print(prompt_text, end="", flush=True)
            continue
        elif ch == b"\x08" or ch == b"\x7f":  # Backspace
            if password:
                password.pop()
                # 回退并覆盖
                print("\b \b", end="", flush=True)
        elif ch == b"q" or ch == b"Q":
            print("\n用户取消输入")
            return ""
        else:
            password.append(ch.decode("utf-8", errors="ignore"))
            # 显示掩码
            if len(password) <= visible_chars:
                print("*", end="", flush=True)
            else:
                print("*", end="", flush=True)

    result = "".join(password)
    return result


def input_number(prompt_text: str, default: str = "", allow_q: bool = True) -> str | None:
    """数字序号输入。

    返回:
        用户输入的字符串
        None = 用户按 Q
    """
    print(prompt_text, end="", flush=True)
    buf = []

    try:
        import msvcrt
    except ImportError:
        raw = input(prompt_text).strip()
        if allow_q and raw.upper() == "Q":
            return None
        return raw if raw else default

    while True:
        ch = msvcrt.getch()

        if ch in (b"\r", b"\n"):  # Enter
            print()
            result = "".join(buf).strip()
            return result if result else default

        elif ch == b"\x1b":  # Esc - 清空
            buf.clear()
            print("\r" + " " * (len(prompt_text) + 40) + "\r", end="")
            print(prompt_text, end="", flush=True)
            continue

        elif ch == b"\x08" or ch == b"\x7f":  # Backspace
            if buf:
                buf.pop()
                print("\b \b", end="", flush=True)

        elif allow_q and ch in (b"q", b"Q"):
            print("Q")
            return None

        elif ch.decode("utf-8", errors="ignore").isdigit():
            buf.append(ch.decode("utf-8", errors="ignore"))
            print(buf[-1], end="", flush=True)


def confirm(prompt_text: str = "按 Enter 继续，Q 退出") -> bool:
    """确认提示。

    返回:
        True = 继续
        False = 用户按 Q
    """
    result = input_number(f"\n  {prompt_text}: ", allow_q=True)
    return result is not None


def select_from_list(items: list[str], title: str = "请选择", default: int = 1) -> int | None:
    """从列表中选择。

    参数:
        items: 选项列表
        title: 标题
        default: 默认选项序号（从 1 开始）

    返回:
        选中的序号（从 1 开始），或 None = Q
    """
    print(f"\n=== {title} ===")
    for i, item in enumerate(items, 1):
        print(f"  {i}. {item}")

    print(f"\n  输入序号选择（默认 {default}），Q 退出")

    while True:
        result = input_number(f"\n请选择 [{default}]: ", default=str(default), allow_q=True)
        if result is None:
            return None

        try:
            idx = int(result)
            if 1 <= idx <= len(items):
                LOG.log("done", f"用户选择: {items[idx-1]}")
                return idx
            else:
                print(f"  错误: 请输入 1-{len(items)} 的有效序号")
        except ValueError:
            print(f"  错误: 请输入有效序号 (1-{len(items)})")


def print_table(headers: list[str], rows: list[list[str]], col_widths: list[int]) -> None:
    """打印表格。"""
    # 表头
    header_line = "  ".join(h.ljust(w) for h, w in zip(headers, col_widths))
    print(f"  {header_line}")
    print("  " + "-" * len(header_line))

    # 数据行
    for row in rows:
        line = "  ".join(str(c).ljust(w) for c, w in zip(row, col_widths))
        print(f"  {line}")


def wait_for_enter(message: str = "按 Enter 继续") -> None:
    """等待 Enter 键。"""
    try:
        import msvcrt
        print(f"\n  {message}... ", end="", flush=True)
        while True:
            if msvcrt.kbhit():
                ch = msvcrt.getch()
                if ch in (b"\r", b"\n"):
                    print()
                    return
                elif ch == b"q" or ch == b"Q":
                    print("\n  用户退出")
                    sys.exit(0)
    except ImportError:
        input(f"\n  {message}... ")
