"""
SkyAtlas v8.102 — 天体目标选择后端
支持太阳系天体实时计算、梅西耶天体本地列表、文本模糊搜索、Stellarium 远程读取
"""

import json
import re
import urllib.request
from pathlib import Path

from astropy.coordinates import get_body, SkyCoord
from astropy.time import Time
import astropy.units as u


# 梅西耶天体完整列表 M1-M110
# 格式: (编号, 中文名, RA_deg, Dec_deg, 类型, 星等, 星座)
_MESSIER_DATA = [
    (1, "蟹状星云", 83.6331, 22.0145, "超新星遗迹", 8.4, "金牛座"),
    (2, None, 323.3626, -0.8064, "球状星团", 6.5, "宝瓶座"),
    (3, None, 205.5484, 28.3773, "球状星团", 6.2, "猎犬座"),
    (4, None, 245.8968, -26.5255, "球状星团", 5.6, "天蝎座"),
    (5, None, 229.6384, 2.0827, "球状星团", 5.6, "巨蛇座"),
    (6, "蝴蝶星团", 265.0836, -32.2533, "疏散星团", 4.2, "天蝎座"),
    (7, "托勒密星团", 268.3817, -34.7847, "疏散星团", 3.3, "天蝎座"),
    (8, "礁湖星云", 270.9271, -24.3867, "发射星云", 6.0, "人马座"),
    (9, None, 259.7991, -18.5161, "球状星团", 7.7, "蛇夫座"),
    (10, None, 254.2872, -4.0994, "球状星团", 6.4, "蛇夫座"),
    (11, "野鸭星团", 282.7706, -6.2700, "疏散星团", 5.8, "盾牌座"),
    (12, None, 251.8103, -1.9478, "球状星团", 6.7, "蛇夫座"),
    (13, "武仙座球状星团", 250.4235, 36.4613, "球状星团", 5.8, "武仙座"),
    (14, None, 264.4017, -3.2459, "球状星团", 7.6, "蛇夫座"),
    (15, None, 322.4931, 12.1667, "球状星团", 6.2, "飞马座"),
    (16, "鹰星云", 274.7000, -13.8167, "发射星云", 6.0, "巨蛇座"),
    (17, "欧米茄星云", 275.1083, -16.1767, "发射星云", 6.0, "人马座"),
    (18, None, 274.9938, -17.1000, "疏散星团", 7.5, "人马座"),
    (19, None, 255.5266, -26.2679, "球状星团", 6.8, "蛇夫座"),
    (20, "三裂星云", 270.5958, -23.0300, "发射星云", 6.3, "人马座"),
    (21, None, 271.0563, -22.4900, "疏散星团", 5.9, "人马座"),
    (22, None, 279.0997, -23.9046, "球状星团", 5.1, "人马座"),
    (23, None, 269.2446, -19.0100, "疏散星团", 5.5, "人马座"),
    (24, "人马座星云", 274.1250, -18.8333, "星云星团", 4.6, "人马座"),
    (25, None, 277.8981, -19.1300, "疏散星团", 4.6, "人马座"),
    (26, None, 281.3033, -9.3900, "疏散星团", 8.0, "盾牌座"),
    (27, "哑铃星云", 299.9014, 22.7211, "行星状星云", 7.4, "狐狸座"),
    (28, None, 276.1370, -24.8698, "球状星团", 6.8, "人马座"),
    (29, None, 305.9863, 38.4800, "疏散星团", 6.6, "天鹅座"),
    (30, None, 325.0922, -23.1790, "球状星团", 7.2, "摩羯座"),
    (31, "仙女座星系", 10.6847, 41.2693, "旋涡星系", 3.4, "仙女座"),
    (32, None, 10.6741, 40.8602, "椭圆星系", 8.1, "仙女座"),
    (33, "三角座星系", 23.4584, 30.6602, "旋涡星系", 5.7, "三角座"),
    (34, None, 40.5111, 42.7600, "疏散星团", 5.2, "英仙座"),
    (35, None, 92.2238, 24.3333, "疏散星团", 5.1, "双子座"),
    (36, None, 84.0500, 34.1300, "疏散星团", 6.0, "御夫座"),
    (37, None, 88.0792, 32.5533, "疏散星团", 5.6, "御夫座"),
    (38, None, 82.1792, 35.8500, "疏散星团", 6.4, "御夫座"),
    (39, None, 322.9500, 48.2500, "疏散星团", 4.6, "天鹅座"),
    (40, None, 185.5999, 58.0831, "双星", 8.4, "大熊座"),
    (41, None, 101.5030, -20.7333, "疏散星团", 4.5, "大犬座"),
    (42, "猎户座大星云", 83.8221, -5.3911, "发射星云", 4.0, "猎户座"),
    (43, None, 83.8788, -5.2700, "发射星云", 7.0, "猎户座"),
    (44, "鬼宿星团", 130.0950, 19.6667, "疏散星团", 3.1, "巨蟹座"),
    (45, "昴星团", 56.8708, 24.1000, "疏散星团", 1.6, "金牛座"),
    (46, None, 115.4446, -14.8100, "疏散星团", 6.0, "船尾座"),
    (47, None, 114.1458, -14.4667, "疏散星团", 4.4, "船尾座"),
    (48, None, 123.4321, -5.7500, "疏散星团", 5.5, "长蛇座"),
    (49, None, 187.4436, 8.0005, "椭圆星系", 8.4, "室女座"),
    (50, None, 105.7583, -8.3333, "疏散星团", 5.9, "麒麟座"),
    (51, "涡状星系", 202.4696, 47.1950, "旋涡星系", 8.4, "猎犬座"),
    (52, None, 351.2000, 61.5600, "疏散星团", 6.9, "仙后座"),
    (53, None, 198.2296, 18.1683, "球状星团", 7.6, "后发座"),
    (54, None, 283.7567, -30.4783, "球状星团", 7.6, "人马座"),
    (55, None, 294.9988, -30.9617, "球状星团", 7.0, "人马座"),
    (56, None, 289.1480, 30.1833, "球状星团", 8.3, "天琴座"),
    (57, "环状星云", 283.3962, 33.0291, "行星状星云", 8.8, "天琴座"),
    (58, None, 189.4317, 11.8181, "旋涡星系", 9.7, "室女座"),
    (59, None, 190.5121, 11.6483, "椭圆星系", 9.6, "室女座"),
    (60, None, 190.9146, 11.5525, "椭圆星系", 8.8, "室女座"),
    (61, None, 190.9121, 4.4736, "旋涡星系", 9.7, "室女座"),
    (62, None, 254.7746, -30.1136, "球状星团", 7.6, "蛇夫座"),
    (63, "向日葵星系", 198.9554, 42.0292, "旋涡星系", 8.6, "猎犬座"),
    (64, "黑眼星系", 194.1821, 21.6825, "旋涡星系", 8.5, "后发座"),
    (65, None, 169.7330, 13.0922, "旋涡星系", 9.3, "狮子座"),
    (66, None, 170.0625, 12.9889, "旋涡星系", 8.9, "狮子座"),
    (67, None, 132.5979, 11.8167, "疏散星团", 6.1, "巨蟹座"),
    (68, None, 189.8681, -26.7428, "球状星团", 7.8, "长蛇座"),
    (69, None, 277.8463, -32.3481, "球状星团", 7.6, "人马座"),
    (70, None, 280.8033, -32.2917, "球状星团", 7.8, "人马座"),
    (71, None, 298.3604, 18.7783, "球状星团", 6.1, "天箭座"),
    (72, None, 313.3654, -12.5372, "球状星团", 9.2, "宝瓶座"),
    (73, None, 314.7242, -12.6333, "疏散星团", 9.0, "宝瓶座"),
    (74, None, 24.1713, 15.7833, "旋涡星系", 9.4, "双鱼座"),
    (75, None, 301.5200, -21.7667, "球状星团", 8.5, "摩羯座"),
    (76, "小哑铃星云", 25.5821, 51.5753, "行星状星云", 10.1, "英仙座"),
    (77, None, 40.6696, -0.0136, "旋涡星系", 8.9, "鲸鱼座"),
    (78, None, 86.6946, 0.0500, "反射星云", 8.3, "猎户座"),
    (79, None, 81.1192, -24.5217, "球状星团", 7.7, "天兔座"),
    (80, None, 244.2604, -22.9717, "球状星团", 7.3, "天蝎座"),
    (81, None, 148.8883, 69.0650, "旋涡星系", 6.9, "大熊座"),
    (82, "雪茄星系", 148.9675, 69.6800, "不规则星系", 8.4, "大熊座"),
    (83, None, 204.2538, -29.8650, "旋涡星系", 7.5, "长蛇座"),
    (84, None, 186.2654, 12.8867, "透镜状星系", 9.1, "室女座"),
    (85, None, 186.3513, 18.1883, "透镜状星系", 9.1, "后发座"),
    (86, None, 186.5483, 12.9367, "透镜状星系", 9.2, "室女座"),
    (87, "室女A星系", 187.7059, 12.3911, "椭圆星系", 8.6, "室女座"),
    (88, None, 187.9972, 14.4200, "旋涡星系", 9.6, "后发座"),
    (89, None, 188.9142, 12.5550, "椭圆星系", 9.8, "室女座"),
    (90, None, 189.2074, 13.1633, "旋涡星系", 9.5, "室女座"),
    (91, None, 188.8142, 14.4950, "旋涡星系", 10.2, "后发座"),
    (92, None, 259.2804, 43.1350, "球状星团", 6.4, "武仙座"),
    (93, None, 116.1263, -23.8600, "疏散星团", 6.0, "船尾座"),
    (94, None, 192.2213, 41.1200, "旋涡星系", 8.2, "猎犬座"),
    (95, None, 161.7417, 11.7000, "棒旋星系", 9.7, "狮子座"),
    (96, None, 161.6904, 11.8200, "旋涡星系", 9.2, "狮子座"),
    (97, "猫头鹰星云", 168.6988, 55.0189, "行星状星云", 9.9, "大熊座"),
    (98, None, 183.4492, 14.9017, "旋涡星系", 10.1, "后发座"),
    (99, None, 184.7067, 14.4117, "旋涡星系", 9.9, "后发座"),
    (100, None, 185.7288, 15.8217, "棒旋星系", 9.4, "后发座"),
    (101, "风车星系", 210.8025, 54.3483, "旋涡星系", 7.9, "大熊座"),
    (102, None, 226.6233, 55.7633, "透镜状星系", 10.5, "牧夫座"),
    (103, None, 23.3417, 60.6500, "疏散星团", 7.4, "仙后座"),
    (104, "草帽星系", 189.9979, -11.6231, "旋涡星系", 8.0, "室女座"),
    (105, None, 161.9563, 12.5850, "椭圆星系", 9.3, "狮子座"),
    (106, None, 184.7396, 47.3033, "旋涡星系", 8.4, "猎犬座"),
    (107, None, 248.1325, -13.0533, "球状星团", 7.9, "蛇夫座"),
    (108, None, 167.8792, 55.6750, "旋涡星系", 10.0, "大熊座"),
    (109, None, 179.3996, 53.3750, "棒旋星系", 9.8, "大熊座"),
    (110, None, 10.0929, 41.2683, "椭圆星系", 8.5, "仙女座"),
]


class SkyAtlas:
    """天体目标选择后端 — 太阳系实时坐标 + 梅西耶目录 + 模糊搜索 + Stellarium"""

    SOLAR_BODIES = ["sun", "moon", "mercury", "venus", "mars", "jupiter", "saturn"]
    SOLAR_NAMES_CN = {
        "sun": "太阳", "moon": "月球", "mercury": "水星",
        "venus": "金星", "mars": "火星", "jupiter": "木星", "saturn": "土星",
    }
    # 别名映射（用户常用名 → 标准英文名）
    SOLAR_ALIASES = {
        "月亮": "moon", "月球": "moon",
        "太阳": "sun", "日": "sun",
        "水星": "mercury", "金星": "venus", "火星": "mars",
        "木星": "jupiter", "土星": "saturn",
    }

    def __init__(self):
        self.local_ip = self._read_local_ip()
        self.stellarium_url = f"http://{self.local_ip}:8090/api/main/object_info"
        self.messier_catalog = self._load_messier_catalog()

    def _read_local_ip(self) -> str:
        """从 data/reports/localhost.json 读取本机IP，失败回退 127.0.0.1"""
        try:
            path = Path(__file__).resolve().parents[2] / "data" / "reports" / "localhost.json"
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            return data.get("local_ip", "127.0.0.1")
        except Exception:
            return "127.0.0.1"

    def _load_messier_catalog(self) -> list[dict]:
        """构建梅西耶天体列表"""
        catalog = []
        for num, name_cn, ra_deg, dec_deg, obj_type, mag, const in _MESSIER_DATA:
            display_name = f"M{num}" + (f" {name_cn}" if name_cn else "")
            catalog.append({
                "name": display_name,
                "ra": round(ra_deg, 4),
                "dec": round(dec_deg, 4),
                "type": "messier",
                "magnitude": mag,
                "constellation": const,
                "object_type": obj_type,
                "number": num,
            })
        return catalog

    def get_solar_system_bodies(self) -> list[dict]:
        """返回太阳系天体实时坐标（RA/Dec 度数）"""
        now = Time.now()
        results = []
        for body_name in self.SOLAR_BODIES:
            try:
                coord = get_body(body_name, now)
                results.append({
                    "name": self.SOLAR_NAMES_CN[body_name],
                    "ra": round(coord.ra.deg, 4),
                    "dec": round(coord.dec.deg, 4),
                    "type": "solar",
                })
            except Exception:
                continue
        return results

    def get_messier_targets(self) -> list[dict]:
        """返回梅西耶天体列表"""
        return self.messier_catalog

    def search_target(self, query: str) -> list[dict]:
        """模糊搜索天体 — 支持 m42 / M42 / m 42 / 猎户 等格式"""
        q = query.strip()
        if not q:
            return []

        results = []

        # 1. 梅西耶编号精确匹配: m42 / M42 / m 42
        m_match = re.match(r"^[mM]\s*(\d{1,3})$", q)
        if m_match:
            num = int(m_match.group(1))
            for item in self.messier_catalog:
                if item["number"] == num:
                    results.append(item)
                    return results

        # 2. 模糊匹配梅西耶: 名称包含查询
        q_lower = q.lower()
        for item in self.messier_catalog:
            name_lower = item["name"].lower()
            if q_lower in name_lower:
                results.append(item)

        # 3. 太阳系天体名称匹配
        matched_solar = False
        # 3.1 别名匹配（月亮→月球）
        if q in self.SOLAR_ALIASES:
            body_name = self.SOLAR_ALIASES[q]
            cn_name = self.SOLAR_NAMES_CN[body_name]
            coord = get_body(body_name, Time.now())
            results.append({
                "name": cn_name,
                "ra": round(coord.ra.deg, 4),
                "dec": round(coord.dec.deg, 4),
                "type": "solar",
            })
            matched_solar = True
        # 3.2 原名匹配（仅当别名未命中时）
        if not matched_solar:
            for body_name, cn_name in self.SOLAR_NAMES_CN.items():
                if q_lower in cn_name or q_lower in body_name:
                    coord = get_body(body_name, Time.now())
                    results.append({
                        "name": cn_name,
                        "ra": round(coord.ra.deg, 4),
                        "dec": round(coord.dec.deg, 4),
                        "type": "solar",
                    })
                # 实时计算坐标
                try:
                    coord = get_body(body_name, Time.now())
                    ra = round(coord.ra.deg, 4)
                    dec = round(coord.dec.deg, 4)
                except Exception:
                    ra, dec = 0, 0
                results.append({
                    "name": cn_name,
                    "ra": ra,
                    "dec": dec,
                    "type": "solar",
                })

        # 4. 星座名匹配梅西耶
        for item in self.messier_catalog:
            if q_lower in item.get("constellation", "").lower():
                if item not in results:
                    results.append(item)

        return results

    def get_stellarium_target(self) -> dict | None:
        """从 Stellarium 获取当前选中目标，失败返回 None"""
        try:
            req = urllib.request.Request(self.stellarium_url, method="GET")
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            if not data:
                return None
            return {
                "name": data.get("name", "未知"),
                "ra": data.get("ra", 0),
                "dec": data.get("dec", 0),
                "type": "stellarium",
                "magnitude": data.get("magnitude"),
                "constellation": data.get("constellation"),
            }
        except Exception:
            return None


# 单例
_instance = None


def get_skyatlas() -> SkyAtlas:
    """获取 SkyAtlas 单例"""
    global _instance
    if _instance is None:
        _instance = SkyAtlas()
    return _instance
