"""ASTAP 截图解析端点"""
from fastapi import APIRouter
from pydantic import BaseModel
import subprocess, os, time, datetime

router = APIRouter()

ASTAP_EXE = os.environ.get("ASTAP_EXE", r"C:\Program Files\astap\astap.exe")
from pathlib import Path
APP_DIR = Path(__file__).resolve().parent.parent
LOG_FILE = str(APP_DIR / 'data' / 'astap_log.md')

class SolveRequest(BaseModel):
    filepath: str

@router.post("/astap/solve")
async def astap_solve(req: SolveRequest):
    """调用 ASTAP 解析天文图像"""
    filepath = req.filepath
    if not os.path.exists(filepath):
        return {"success": False, "error": f"文件不存在: {filepath}"}
    
    log_entry = f"## ASTAP 解析 - {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
    log_entry += f"- 文件: {filepath}\n"
    
    try:
        result = subprocess.run(
            [ASTAP_EXE, "-f", filepath, "-i", "5"],
            capture_output=True, text=True, timeout=60
        )
        
        ra, dec, fov = None, None, None
        for line in result.stdout.split("\n"):
            if "RA:" in line:
                parts = line.split("RA:")[1].strip().split()
                if parts: ra = parts[0]
            if "DEC:" in line:
                parts = line.split("DEC:")[1].strip().split()
                if parts: dec = parts[0]
            if "FoV:" in line:
                parts = line.split("FoV:")[1].strip().split()
                if parts: fov = parts[0]
        
        log_entry += f"- RA: {ra}\n- DEC: {dec}\n- FoV: {fov}\n"
        log_entry += f"- 状态: {'成功' if ra else '失败'}\n\n"
        
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(log_entry)
        
        if ra:
            return {"success": True, "ra": ra, "dec": dec, "fov": fov}
        else:
            return {"success": False, "error": "ASTAP 解析失败", "stdout": result.stdout[:500], "stderr": result.stderr[:500]}
    
    except FileNotFoundError:
        log_entry += f"- 错误: ASTAP 可执行文件不存在 ({ASTAP_EXE})\n\n"
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(log_entry)
        return {"success": False, "error": f"ASTAP 未安装: {ASTAP_EXE}"}
    except subprocess.TimeoutExpired:
        log_entry += "- 错误: 超时\n\n"
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(log_entry)
        return {"success": False, "error": "ASTAP 解析超时 (60s)"}
    except Exception as e:
        log_entry += f"- 错误: {str(e)}\n\n"
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(log_entry)
        return {"success": False, "error": str(e)}

