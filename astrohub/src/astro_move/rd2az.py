"""
AstroHub v8.100 - RA/Dec → Alt/Az 天体坐标与跟踪解析
======================================================
从 calibration_3stars.py 抽取核心坐标转换和恒星查询功能，
新增 CelestialResolver 类，支持恒星/月球/行星/自定义天体识别和位置解析。

依赖: astropy (7.2.0+), Python 标准库
"""

import csv
import math
import os
from datetime import datetime, timezone, timedelta
from typing import Optional

import astropy.units as u
from astropy.coordinates import AltAz, EarthLocation, SkyCoord, get_body, solar_system_ephemeris
from astropy.time import Time

# ─── 模块路径 ───────────────────────────────────────────────────────────────
_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT = os.path.normpath(os.path.join(_HERE, "..", ".."))
_CATALOG_PATH = os.path.join(_PROJECT, "data", "hipparcos_bright.csv")


# ─── 矩阵工具（纯 Python） ──────────────────────────────────────────────────

def _transpose(m):
    """矩阵转置"""
    return list(map(list, zip(*m)))


def _mat_mul(a, b):
    """矩阵乘法 a @ b"""
    m, n = len(a), len(b[0])
    k = len(b)
    return [[sum(a[i][p] * b[p][j] for p in range(k)) for j in range(n)] for i in range(m)]


def _mat_inv_5x5(m):
    """
    5×5 矩阵求逆 (Gauss-Jordan 消元法)
    返回逆矩阵，不可逆时抛出 ValueError。
    """
    size = 5
    aug = [row[:] + [1.0 if i == j else 0.0 for j in range(size)] for i, row in enumerate(m)]

    for col in range(size):
        pivot = max(range(col, size), key=lambda r: abs(aug[r][col]))
        if abs(aug[pivot][col]) < 1e-15:
            raise ValueError("矩阵奇异，无法求逆")
        if pivot != col:
            aug[col], aug[pivot] = aug[pivot], aug[col]
        pivot_val = aug[col][col]
        for j in range(2 * size):
            aug[col][j] /= pivot_val
        for row in range(size):
            if row == col:
                continue
            factor = aug[row][col]
            if abs(factor) < 1e-15:
                continue
            for j in range(2 * size):
                aug[row][j] -= factor * aug[col][j]

    return [row[size:] for row in aug]


def _mat_vec_mul(a, v):
    """矩阵 × 向量"""
    return [sum(a[i][j] * v[j] for j in range(len(v))) for i in range(len(a))]


def _lsq_solve(A, b):
    """
    最小二乘法求解超定系统 A x = b
    A: m×n 矩阵, b: m 维向量, m >= n
    返回 n 维向量 x = (A^T A)^{-1} A^T b
    """
    At = _transpose(A)
    AtA = _mat_mul(At, A)
    Atb = _mat_vec_mul(At, b)
    AtA_inv = _mat_inv_5x5(AtA)
    return _mat_vec_mul(AtA_inv, Atb)


# ─── 星表加载与查询 ─────────────────────────────────────────────────────────

class StarCatalog:
    """
    依巴谷星表加载与查询
    数据来源: astrohub/data/hipparcos_bright.csv
    """

    def __init__(self, csv_path: str = _CATALOG_PATH):
        self._csv_path = csv_path
        self._stars = []
        self._loaded = False

    # ── 加载 ─────────────────────────────────────────────────────────────

    def load(self):
        """加载 CSV 到内存"""
        self._stars = []
        with open(self._csv_path, encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                hip_str = (row.get("HIP") or "0").strip()
                vmag_str = (row.get("Vmag") or "0").strip()
                try:
                    hip = int(hip_str)
                except ValueError:
                    continue
                try:
                    vmag = float(vmag_str)
                except ValueError:
                    vmag = 99.0
                self._stars.append({
                    "hip": hip,
                    "ra_deg": float((row.get("RA_deg") or "0").strip()),
                    "dec_deg": float((row.get("Dec_deg") or "0").strip()),
                    "vmag": vmag,
                    "bayer": row.get("bayer", "").strip(),
                    "constellation_cn": row.get("constellation_cn", "").strip(),
                    "constellation_en": row.get("constellation_en", "").strip(),
                    "name_cn": row.get("name_cn", "").strip(),
                    "name_en": row.get("name_en", "").strip(),
                    "display_name": row.get("display_name", "").strip(),
                })
        self._loaded = True
        return self

    # ── 查询 ─────────────────────────────────────────────────────────────

    def get_all(self):
        """返回全部星列表"""
        if not self._loaded:
            self.load()
        return list(self._stars)

    def get_by_hip(self, hip: int) -> Optional[dict]:
        """按 HIP 编号查询"""
        if not self._loaded:
            self.load()
        for star in self._stars:
            if star["hip"] == hip:
                return dict(star)
        return None

    def get_polaris(self) -> Optional[dict]:
        """返回北极星 (HIP 11767)"""
        return self.get_by_hip(11767)

    # ── 可见星筛选 ───────────────────────────────────────────────────────

    def get_visible(self, lat: float, lon: float, time_utc: datetime,
                    min_alt: float = 20.0, max_vmag: float = 4.0):
        """返回当前可见亮星，每颗含 alt/az 信息"""
        if not self._loaded:
            self.load()
        converter = CoordinateConverter()
        result = []
        for star in self._stars:
            if star["vmag"] > max_vmag:
                continue
            alt, az = converter.radec_to_altaz(star["ra_deg"], star["dec_deg"],
                                               lat, lon, time_utc)
            if alt >= min_alt:
                entry = dict(star)
                entry["alt"] = round(alt, 4)
                entry["az"] = round(az, 4)
                result.append(entry)
        return result

    # ── 推荐星 ───────────────────────────────────────────────────────────

    def get_recommended(self, lat: float, lon: float, time_utc: datetime,
                        exclude_hips: list = None, count: int = 3):
        """返回推荐星，按方位角均匀分布排序"""
        if exclude_hips is None:
            exclude_hips = []
        exclude_set = set(exclude_hips)

        visible = self.get_visible(lat, lon, time_utc, min_alt=20, max_vmag=3.5)
        visible = [s for s in visible if s["hip"] not in exclude_set]
        if not visible:
            visible = self.get_visible(lat, lon, time_utc, min_alt=15, max_vmag=4.5)
            visible = [s for s in visible if s["hip"] not in exclude_set]

        if not visible:
            return []

        sector_size = 360.0 / count
        sectors = [[] for _ in range(count)]
        for star in visible:
            idx = min(int(star["az"] / sector_size), count - 1)
            sectors[idx].append(star)

        result = []
        for sector in sectors:
            if not sector:
                continue
            sector.sort(key=lambda s: s["alt"] - 2 * s["vmag"], reverse=True)
            result.append(sector[0])

        remaining = [s for s in visible if s not in result]
        remaining.sort(key=lambda s: s["alt"] - 2 * s["vmag"], reverse=True)
        while len(result) < count and remaining:
            result.append(remaining.pop(0))

        return result[:count]


# ─── 坐标转换 ───────────────────────────────────────────────────────────────

class CoordinateConverter:
    """
    RA/Dec ↔ Alt/Az 坐标转换
    基于 astropy.coordinates
    """

    @staticmethod
    def radec_to_altaz(ra_deg: float, dec_deg: float, lat: float, lon: float,
                       time_utc: datetime):
        """
        (RA, Dec) → (高度角, 方位角)
        返回 (alt_deg, az_deg)
        """
        location = EarthLocation(lat=lat * u.deg, lon=lon * u.deg)
        obstime = Time(time_utc)
        coord = SkyCoord(ra=ra_deg * u.deg, dec=dec_deg * u.deg, frame="icrs")
        altaz = coord.transform_to(AltAz(obstime=obstime, location=location))
        return altaz.alt.deg, altaz.az.deg

    @staticmethod
    def altaz_to_radec(alt_deg: float, az_deg: float, lat: float, lon: float,
                       time_utc: datetime):
        """
        (高度角, 方位角) → (RA, Dec)
        返回 (ra_deg, dec_deg)
        """
        location = EarthLocation(lat=lat * u.deg, lon=lon * u.deg)
        obstime = Time(time_utc)
        altaz = SkyCoord(alt=alt_deg * u.deg, az=az_deg * u.deg,
                         frame=AltAz(obstime=obstime, location=location))
        icrs = altaz.transform_to("icrs")
        return icrs.ra.deg, icrs.dec.deg


# ─── 5参数校准求解 ──────────────────────────────────────────────────────────

class CalibrationSolver:
    """
    5参数 PTZ 校准模型:

    ΔAz = IA + NPAE×tan(Alt) − T_N×sin(Az)×tan(Alt) + T_E×cos(Az)×tan(Alt)
    ΔAlt = IE − T_N×cos(Az) − T_E×sin(Az)

    参数: [IA, IE, NPAE, T_N, T_E]
    """

    def __init__(self):
        self._points = []
        self._solved = False
        self._params = None
        self._az_rms = None
        self._alt_rms = None

    # ── 添加校准点 ───────────────────────────────────────────────────────

    def add_point(self, star_hip: int, star_ra: float, star_dec: float,
                  ptz_pan: float, ptz_tilt: float,
                  obs_lat: float, obs_lon: float, obs_time: datetime):
        """添加一个校准点"""
        self._points.append({
            "star_hip": star_hip,
            "star_ra": star_ra,
            "star_dec": star_dec,
            "ptz_pan": ptz_pan,
            "ptz_tilt": ptz_tilt,
            "obs_lat": obs_lat,
            "obs_lon": obs_lon,
            "obs_time": obs_time,
        })
        self._solved = False
        self._params = None
        self._az_rms = None
        self._alt_rms = None

    # ── 求解 ─────────────────────────────────────────────────────────────

    def solve(self):
        """渐进式建模求解"""
        n = len(self._points)
        if n < 2:
            self._solved = False
            return None
        if n == 2:
            return self._solve_2param()
        return self._solve_5param()

    def _solve_2param(self):
        """简化模型：仅解 IA, IE（零点偏移）"""
        converter = CoordinateConverter()
        daz_list = []
        dalt_list = []
        for pt in self._points:
            true_alt, true_az = converter.radec_to_altaz(
                pt["star_ra"], pt["star_dec"],
                pt["obs_lat"], pt["obs_lon"], pt["obs_time"],
            )
            daz = true_az - pt["ptz_pan"]
            dalt = true_alt - pt["ptz_tilt"]
            daz_list.append(daz)
            dalt_list.append(dalt)

        IA = sum(daz_list) / len(daz_list)
        IE = sum(dalt_list) / len(dalt_list)
        self._params = [IA, IE, 0.0, 0.0, 0.0]
        self._solved = True
        self._az_rms = math.sqrt(sum((d - IA) ** 2 for d in daz_list) / len(daz_list))
        self._alt_rms = math.sqrt(sum((d - IE) ** 2 for d in dalt_list) / len(dalt_list))
        return self._params

    def _solve_5param(self):
        """完整最小二乘法求解 5 参数"""
        converter = CoordinateConverter()
        rows = []
        targets = []
        for pt in self._points:
            true_alt, true_az = converter.radec_to_altaz(
                pt["star_ra"], pt["star_dec"],
                pt["obs_lat"], pt["obs_lon"], pt["obs_time"],
            )
            ptz_az = pt["ptz_pan"]
            ptz_alt = pt["ptz_tilt"]

            tan_alt = math.tan(math.radians(ptz_alt))
            sin_az = math.sin(math.radians(ptz_az))
            cos_az = math.cos(math.radians(ptz_az))

            daz = true_az - ptz_az
            dalt = true_alt - ptz_alt

            # Az 方程: IA + NPAE×tan(Alt) − T_N×sin(Az)×tan(Alt) + T_E×cos(Az)×tan(Alt)
            rows.append([1.0, 0.0, tan_alt, -sin_az * tan_alt, cos_az * tan_alt])
            targets.append(daz)

            # Alt 方程: IE − T_N×cos(Az) − T_E×sin(Az)
            rows.append([0.0, 1.0, 0.0, -cos_az, -sin_az])
            targets.append(dalt)

        self._params = _lsq_solve(rows, targets)

        residuals = []
        for r, t in zip(rows, targets):
            pred = sum(r[j] * self._params[j] for j in range(5))
            residuals.append(t - pred)

        n = len(self._points)
        az_residuals = [residuals[2 * i] for i in range(n)]
        alt_residuals = [residuals[2 * i + 1] for i in range(n)]
        self._az_rms = math.sqrt(sum(r * r for r in az_residuals) / n)
        self._alt_rms = math.sqrt(sum(r * r for r in alt_residuals) / n)
        self._solved = True
        return self._params

    # ── 结果查询 ─────────────────────────────────────────────────────────

    def get_rms(self) -> dict:
        """返回 RMS 残差 {az_rms, alt_rms}"""
        if not self._solved:
            return {"az_rms": None, "alt_rms": None}
        return {"az_rms": round(self._az_rms, 4), "alt_rms": round(self._alt_rms, 4)}

    def get_params(self) -> dict:
        """返回参数"""
        if not self._solved or self._params is None:
            return {}
        IA, IE, NPAE, T_N, T_E = self._params
        tilt_mag = math.sqrt(T_N ** 2 + T_E ** 2)
        tilt_dir = math.degrees(math.atan2(T_E, T_N))
        return {
            "IA": round(IA, 4),
            "IE": round(IE, 4),
            "NPAE": round(NPAE, 4),
            "T_N": round(T_N, 4),
            "T_E": round(T_E, 4),
            "tilt_magnitude": round(tilt_mag, 4),
            "tilt_direction": round(tilt_dir, 4),
        }

    def get_quality(self) -> str:
        """返回评级"""
        rms = self.get_rms()
        max_rms = max(rms["az_rms"] or 0, rms["alt_rms"] or 0)
        if max_rms < 0.1:
            return "优秀"
        if max_rms < 0.3:
            return "良好"
        if max_rms < 0.5:
            return "一般"
        return "差"

    # ── 正反向转换 ───────────────────────────────────────────────────────

    def ptz_to_true(self, ptz_az: float, ptz_alt: float):
        """将 PTZ 读数转为真实 Alt/Az"""
        if not self._solved or self._params is None:
            raise RuntimeError("尚未求解校准参数")
        IA, IE, NPAE, T_N, T_E = self._params
        rad_alt = math.radians(ptz_alt)
        rad_az = math.radians(ptz_az)
        tan_alt = math.tan(rad_alt)
        sin_az = math.sin(rad_az)
        cos_az = math.cos(rad_az)
        daz = IA + NPAE * tan_alt - T_N * sin_az * tan_alt + T_E * cos_az * tan_alt
        dalt = IE - T_N * cos_az - T_E * sin_az
        return ptz_az + daz, ptz_alt + dalt

    def true_to_ptz(self, true_az: float, true_alt: float, max_iter: int = 10,
                    tol: float = 1e-6):
        """将真实 Alt/Az 转为期望 PTZ 读数（迭代求解反函数）"""
        if not self._solved or self._params is None:
            raise RuntimeError("尚未求解校准参数")
        ptz_az, ptz_alt = true_az, true_alt
        for _ in range(max_iter):
            t_az, t_alt = self.ptz_to_true(ptz_az, ptz_alt)
            err_az = true_az - t_az
            err_alt = true_alt - t_alt
            ptz_az += err_az
            ptz_alt += err_alt
            if abs(err_az) < tol and abs(err_alt) < tol:
                break
        return ptz_az, ptz_alt

    # ── 管理 ─────────────────────────────────────────────────────────────

    def clear(self):
        """清空所有校准点"""
        self._points.clear()
        self._solved = False
        self._params = None
        self._az_rms = None
        self._alt_rms = None

    def status(self) -> dict:
        """返回状态"""
        has_polaris = any(pt["star_hip"] == 11767 for pt in self._points)
        return {
            "points_count": len(self._points),
            "has_polaris": has_polaris,
            "is_ready": len(self._points) >= 4,
        }


# ─── 天体识别与位置解析 ─────────────────────────────────────────────────────

class CelestialResolver:
    """
    天体识别与位置解析

    根据用户输入的目标规格，返回目标的:
    - RA/Dec（赤道坐标）
    - Alt/Az（地平坐标）
    - 类型
    - 推荐跟踪速率 (deg/s)

    支持的目标类型:
    - star: 恒星，通过 HIP 编号查询星表
    - moon: 月球（使用 astropy 内置星历）
    - planet: 行星（使用 astropy 内置星历）
    - custom: 自定义坐标（含自行的 RA/Dec）
    """

    # 内置行星名称映射
    _PLANET_NAMES = {
        "mercury": "水星", "venus": "金星", "mars": "火星",
        "jupiter": "木星", "saturn": "土星", "uranus": "天王星", "neptune": "海王星",
    }

    # 已知亮星名称速查（小写 -> HIP 编号）
    _NAMED_STARS = {
        "polaris": 11767, "北极星": 11767,
        "sirius": 32349, "天狼星": 32349,
        "vega": 91262, "织女星": 91262,
        "altair": 97649, "牛郎星": 97649,
        "rigel": 24436, "参宿七": 24436,
        "betelgeuse": 27989, "参宿四": 27989,
        "capella": 24608, "五车二": 24608,
        "arcturus": 69673, "大角星": 69673,
        "procyon": 37279, "南河三": 37279,
        "aldebaran": 21421, "毕宿五": 21421,
        "spica": 65474, "角宿一": 65474,
        "antares": 80763, "心宿二": 80763,
        "pollux": 37826, "北河三": 37826,
        "fomalhaut": 113368, "北落师门": 113368,
        "deneb": 102098, "天津四": 102098,
    }

    def __init__(self):
        self.catalog = StarCatalog()
        self.converter = CoordinateConverter()
        self._planet_cache = {}

    # ── 目标识别 ────────────────────────────────────────────────────────

    def identify_target(self, name: str) -> dict:
        """
        根据用户输入的名称识别目标类型和返回信息

        Args:
            name: 用户输入的名称（如 "HIP11767", "polaris", "mars", "北极星"）

        Returns:
            {
                "type": "star" | "moon" | "planet" | "unknown",
                "id": str,
                "name": str,
                "display_name": str,
                "ra_deg": float | None,
                "dec_deg": float | None,
                "found": bool,
                "message": str
            }
        """
        name_stripped = name.strip()
        name_lower = name_stripped.lower()

        # 1. 检查是否是 HIP 编号格式
        if name_lower.startswith("hip"):
            try:
                hip = int(name_lower.replace("hip", ""))
                star = self.catalog.get_by_hip(hip)
                if star:
                    return {
                        "type": "star",
                        "id": f"HIP{hip}",
                        "name": name_stripped,
                        "display_name": star.get("display_name") or f"HIP{hip}",
                        "ra_deg": star["ra_deg"],
                        "dec_deg": star["dec_deg"],
                        "found": True,
                        "message": f"恒星: {star.get('display_name') or 'HIP' + str(hip)}",
                    }
                return {"type": "unknown", "id": name_stripped, "found": False,
                        "message": f"未找到 HIP {hip}"}
            except ValueError:
                pass

        # 2. 检查是否是已知亮星名称
        if name_lower in self._NAMED_STARS:
            hip = self._NAMED_STARS[name_lower]
            star = self.catalog.get_by_hip(hip)
            if star:
                return {
                    "type": "star",
                    "id": f"HIP{hip}",
                    "name": name_stripped,
                    "display_name": star.get("display_name") or name_stripped,
                    "ra_deg": star["ra_deg"],
                    "dec_deg": star["dec_deg"],
                    "found": True,
                    "message": f"恒星: {star.get('display_name') or name_stripped}",
                }

        # 3. 检查是否是纯数字（HIP 编号）
        try:
            hip = int(name_stripped)
            star = self.catalog.get_by_hip(hip)
            if star:
                return {
                    "type": "star",
                    "id": f"HIP{hip}",
                    "name": name_stripped,
                    "display_name": star.get("display_name") or f"HIP{hip}",
                    "ra_deg": star["ra_deg"],
                    "dec_deg": star["dec_deg"],
                    "found": True,
                    "message": f"恒星: {star.get('display_name') or 'HIP' + str(hip)}",
                }
        except ValueError:
            pass

        # 4. 检查是否是月球
        if name_lower in ("moon", "月球", "月亮"):
            return {
                "type": "moon", "id": "moon", "name": name_stripped,
                "display_name": "月球", "ra_deg": None, "dec_deg": None,
                "found": True, "message": "月球",
            }

        # 5. 检查是否是行星
        if name_lower in self._PLANET_NAMES:
            cn_name = self._PLANET_NAMES[name_lower]
            return {
                "type": "planet", "id": name_lower, "name": name_stripped,
                "display_name": cn_name, "ra_deg": None, "dec_deg": None,
                "found": True, "message": f"行星: {cn_name} ({name_lower})",
            }

        # 6. 在星表中按英文/中文名称模糊查找
        if not self.catalog._loaded:
            self.catalog.load()
        for star in self.catalog._stars:
            if (star["name_en"] and name_lower == star["name_en"].lower()) or \
               (star["name_cn"] and name_lower == star["name_cn"].lower()) or \
               (star["display_name"] and name_lower == star["display_name"].lower()):
                return {
                    "type": "star",
                    "id": f"HIP{star['hip']}",
                    "name": name_stripped,
                    "display_name": star.get("display_name") or f"HIP{star['hip']}",
                    "ra_deg": star["ra_deg"],
                    "dec_deg": star["dec_deg"],
                    "found": True,
                    "message": f"恒星: {star.get('display_name') or star['name_en'] or 'HIP' + str(star['hip'])}",
                }

        # 7. 未识别
        return {"type": "unknown", "id": name_stripped, "found": False,
                "message": f"无法识别: {name_stripped}"}

    # ── 位置解析 ────────────────────────────────────────────────────────

    def resolve_target(self, target_spec: dict, lat: float, lon: float,
                       time_utc: datetime) -> dict:
        """
        根据目标规格返回天体位置信息

        Args:
            target_spec: {
                "type": "star" | "moon" | "planet" | "custom",
                "id": "HIP11767" | "mars",
                "custom_ra": float,       # 自定义 RA（度），仅 custom 类型
                "custom_dec": float,      # 自定义 Dec（度），仅 custom 类型
                "custom_dra": float,      # 自定义 RA 自行 ("/s)，仅 custom 类型
                "custom_ddec": float,     # 自定义 Dec 自行 ("/s)，仅 custom 类型
            }
            lat: 观测者纬度（度）
            lon: 观测者经度（度）
            time_utc: 观测时间 (UTC)

        Returns:
            {
                "success": bool,
                "type": str,
                "id": str,
                "display_name": str,
                "ra_deg": float,
                "dec_deg": float,
                "alt_deg": float,
                "az_deg": float,
                "rate_az_deg_per_s": float,   # Az 变化率
                "rate_alt_deg_per_s": float,  # Alt 变化率
                "message": str
            }
        """
        target_type = target_spec.get("type", "star")
        target_id = target_spec.get("id", "")

        try:
            # ── 恒星 ────────────────────────────────────────────────────
            if target_type == "star":
                # 解析 HIP 编号
                hip_str = target_id.replace("HIP", "").replace("hip", "")
                hip = int(hip_str)
                star = self.catalog.get_by_hip(hip)
                if not star:
                    return {"success": False, "message": f"未找到恒星 HIP {hip}"}

                ra_deg = star["ra_deg"]
                dec_deg = star["dec_deg"]
                display_name = star.get("display_name") or f"HIP{hip}"

                # 计算 Alt/Az
                alt_deg, az_deg = self.converter.radec_to_altaz(
                    ra_deg, dec_deg, lat, lon, time_utc
                )

                # 计算跟踪速率（取 t 和 t+1s 两个点的位置差）
                rate = self._compute_rate(ra_deg, dec_deg, lat, lon, time_utc)

                return {
                    "success": True,
                    "type": "star",
                    "id": f"HIP{hip}",
                    "display_name": display_name,
                    "ra_deg": round(ra_deg, 6),
                    "dec_deg": round(dec_deg, 6),
                    "alt_deg": round(alt_deg, 4),
                    "az_deg": round(az_deg, 4),
                    "rate_az_deg_per_s": round(rate["az_deg_per_s"], 6),
                    "rate_alt_deg_per_s": round(rate["alt_deg_per_s"], 6),
                    "message": f"{display_name}: Alt={alt_deg:.1f}°, Az={az_deg:.1f}°",
                }

            # ── 月球 ────────────────────────────────────────────────────
            elif target_type == "moon":
                return self._resolve_solar_system_body("moon", lat, lon, time_utc)

            # ── 行星 ────────────────────────────────────────────────────
            elif target_type == "planet":
                planet_id = target_id.lower()
                return self._resolve_solar_system_body(planet_id, lat, lon, time_utc)

            # ── 自定义 ──────────────────────────────────────────────────
            elif target_type == "custom":
                custom_ra = target_spec.get("custom_ra", 0.0)
                custom_dec = target_spec.get("custom_dec", 0.0)
                custom_dra = target_spec.get("custom_dra", 0.0)    # "/s
                custom_ddec = target_spec.get("custom_ddec", 0.0)  # "/s

                # 应用自行修正到当前时间
                # 自定义坐标基于 J2000，自行单位为 "/s
                # 将 "/s 转换为 度
                dra_deg_per_s = custom_dra / 3600.0
                ddec_deg_per_s = custom_ddec / 3600.0

                # 简化处理：不进行严格的 epoch 转换，只应用线性自行
                ra_deg = custom_ra + dra_deg_per_s
                dec_deg = custom_dec + ddec_deg_per_s

                alt_deg, az_deg = self.converter.radec_to_altaz(
                    ra_deg, dec_deg, lat, lon, time_utc
                )

                rate = self._compute_rate(ra_deg, dec_deg, lat, lon, time_utc)

                return {
                    "success": True,
                    "type": "custom",
                    "id": "custom",
                    "display_name": "自定义目标",
                    "ra_deg": round(ra_deg, 6),
                    "dec_deg": round(dec_deg, 6),
                    "alt_deg": round(alt_deg, 4),
                    "az_deg": round(az_deg, 4),
                    "rate_az_deg_per_s": round(rate["az_deg_per_s"], 6),
                    "rate_alt_deg_per_s": round(rate["alt_deg_per_s"], 6),
                    "message": f"自定义: Alt={alt_deg:.1f}°, Az={az_deg:.1f}°",
                }

            else:
                return {"success": False, "message": f"不支持的目标类型: {target_type}"}

        except Exception as e:
            return {"success": False, "message": f"位置解析失败: {e}"}

    # ── 太阳系天体 ──────────────────────────────────────────────────────

    def _resolve_solar_system_body(self, body_id: str, lat: float, lon: float,
                                    time_utc: datetime) -> dict:
        """
        使用 astropy 内置星历解析太阳系天体位置

        支持的 body_id: "moon", "mercury", "venus", "mars", "jupiter",
                        "saturn", "uranus", "neptune"
        """
        try:
            # 设置使用内置星历（无需下载）
            with solar_system_ephemeris.set('builtin'):
                obstime = Time(time_utc)
                location = EarthLocation(lat=lat * u.deg, lon=lon * u.deg)

                body = get_body(body_id, obstime)
                ra_deg = body.ra.deg
                dec_deg = body.dec.deg

                # 转换到 Alt/Az
                altaz_frame = AltAz(obstime=obstime, location=location)
                altaz = body.transform_to(altaz_frame)
                alt_deg = altaz.alt.deg
                az_deg = altaz.az.deg

                # 计算跟踪速率
                rate = self._compute_rate(ra_deg, dec_deg, lat, lon, time_utc)

                # 名称映射
                name_map = {"moon": "月球", "mercury": "水星", "venus": "金星",
                            "mars": "火星", "jupiter": "木星", "saturn": "土星",
                            "uranus": "天王星", "neptune": "海王星"}
                display_name = name_map.get(body_id, body_id)

                return {
                    "success": True,
                    "type": "moon" if body_id == "moon" else "planet",
                    "id": body_id,
                    "display_name": display_name,
                    "ra_deg": round(ra_deg, 6),
                    "dec_deg": round(dec_deg, 6),
                    "alt_deg": round(alt_deg, 4),
                    "az_deg": round(az_deg, 4),
                    "rate_az_deg_per_s": round(rate["az_deg_per_s"], 6),
                    "rate_alt_deg_per_s": round(rate["alt_deg_per_s"], 6),
                    "message": f"{display_name}: Alt={alt_deg:.1f}°, Az={az_deg:.1f}°",
                }
        except Exception as e:
            return {"success": False, "message": f"太阳系天体解析失败: {e}"}

    # ── 跟踪速率计算 ────────────────────────────────────────────────────

    @staticmethod
    def _compute_rate(ra_deg: float, dec_deg: float, lat: float, lon: float,
                      time_utc: datetime) -> dict:
        """
        通过前后1秒的两个位置计算 Alt/Az 变化率

        Returns:
            {"az_deg_per_s": float, "alt_deg_per_s": float}
        """
        converter = CoordinateConverter()
        t1 = time_utc
        t2 = time_utc + timedelta(seconds=1)

        alt1, az1 = converter.radec_to_altaz(ra_deg, dec_deg, lat, lon, t1)
        alt2, az2 = converter.radec_to_altaz(ra_deg, dec_deg, lat, lon, t2)

        daz = az2 - az1
        dalt = alt2 - alt1

        # 处理 Az 过零（0° ↔ 360°）
        if daz > 180:
            daz -= 360
        elif daz < -180:
            daz += 360

        return {
            "az_deg_per_s": daz,
            "alt_deg_per_s": dalt,
        }


# ═══════════════════════════════════════════════════════════════════════════════
# 测试块
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 60)
    print("AstroHub v8.100 - rd2az 模块自检")
    print("=" * 60)

    # 1. 加载星表
    catalog = StarCatalog()
    catalog.load()
    all_stars = catalog.get_all()
    print(f"\n[1] 星表加载完成: {len(all_stars)} 颗星")

    polaris = catalog.get_polaris()
    if polaris:
        print(f"    北极星: HIP={polaris['hip']}, RA={polaris['ra_deg']}°, Dec={polaris['dec_deg']}°")

    # 2. 坐标转换
    converter = CoordinateConverter()
    now = datetime.now(timezone.utc)
    lat, lon = 29.45, 100.33
    alt, az = converter.radec_to_altaz(polaris["ra_deg"], polaris["dec_deg"], lat, lon, now)
    print(f"\n[2] 坐标转换: 北极星 Alt={alt:.2f}°, Az={az:.2f}°")

    # 3. CelestialResolver - 识别测试
    resolver = CelestialResolver()
    print(f"\n[3] 天体识别:")
    for name in ["polaris", "mars", "moon", "HIP32349", "北极星", "天狼星", "unknown_xyz"]:
        result = resolver.identify_target(name)
        status = "✓" if result["found"] else "✗"
        print(f"    {status} {name:>15s} → {result['message']}")

    # 4. CelestialResolver - 位置解析
    print(f"\n[4] 位置解析:")
    specs = [
        {"type": "star", "id": "HIP11767"},
        {"type": "moon", "id": "moon"},
        {"type": "planet", "id": "mars"},
        {"type": "custom", "id": "custom", "custom_ra": 80.0, "custom_dec": 20.0,
         "custom_dra": 0.0, "custom_ddec": 0.0},
    ]
    for spec in specs:
        result = resolver.resolve_target(spec, lat, lon, now)
        if result["success"]:
            print(f"    {spec['type']:>7s}: RA={result['ra_deg']:.4f}°, "
                  f"Dec={result['dec_deg']:.4f}°, "
                  f"Alt={result['alt_deg']:.2f}°, Az={result['az_deg']:.2f}°")
            print(f"            速率: Az={result['rate_az_deg_per_s']:.6f}°/s, "
                  f"Alt={result['rate_alt_deg_per_s']:.6f}°/s")
        else:
            print(f"    {spec['type']:>7s}: ✗ {result['message']}")

    print(f"\n{'=' * 60}")
    print("自检完成")
    print(f"{'=' * 60}")