# PTZ 天文校准方案：将 PTZ 设备作为经纬仪实现 RA/DEC 定位

## 1. 核心问题

PTZ 摄像头是 Alt-Az（地平坐标）机械结构，而天文目标用 RA/DEC（赤道坐标）描述。
核心链路：**RA/DEC → Alt/Az → PTZ Pan-Tilt → 图像验证 → 误差补偿**

```
RA/DEC (J2000/当前历元)
    │
    ▼
  坐标转换 (考虑观测者经纬度、UTC、岁差、章动、大气折射)
    │
    ▼
  Alt/Az (地平坐标)
    │
    ▼
  PTZ Pan-Tilt 指令 (需校准机械误差)
    │
    ▼
  图像捕获 → Plate Solving → 实际指向 → 误差补偿模型
    │
    ▼
  修正后的 Pan-Tilt 指令 → 目标精度
```

---

## 2. 坐标转换数学模型

### 2.1 RA/DEC → Alt/Az (标准公式)

**输入**: RA (α), DEC (δ), 观测者纬度 (φ), 当地恒星时 (LST)

```
时角: H = LST - α

高度角: sin(alt) = sin(φ)·sin(δ) + cos(φ)·cos(δ)·cos(H)
方位角: cos(A) = (sin(δ) - sin(φ)·sin(alt)) / (cos(φ)·cos(alt))
        sin(A) = -cos(δ)·sin(H) / cos(alt)
        Az = atan2(sin(A), cos(A))  [注意象限]
```

**关键计算环节**:
1. UTC → 格林尼治恒星时 (GMST): 使用 IAU 2006 公式
2. GMST → 当地恒星时 (LST): LST = GMST + 观测者经度
3. 岁差修正: J2000 → 当前历元 (IAU 2006 P03 模型)
4. 章动修正: IAU 2000A 模型 (精度 < 1 mas)
5. 大气折射: Saastamoinen 或 Bennett 公式 (低仰角时可达 0.5°)

### 2.2 Alt/Az → PTZ Pan-Tilt 映射

理想情况:
```
Pan = Az - Az_offset
Tilt = alt - tilt_offset
```

但 PTZ 存在系统误差，需要校准模型。

---

## 3. PTZ 误差来源与校准模型

### 3.1 主要误差源

| 误差类型 | 描述 | 典型量级 |
|----------|------|----------|
| 水平零点偏移 | Pan 轴零点与真北偏差 | 0.1°-2° |
| 垂直零点偏移 | Tilt 轴零点与水平面偏差 | 0.1°-1° |
| 轴非正交 | Pan/Tilt 轴不完全垂直 | 0.01°-0.1° |
| 编码器非线性 | Pan/Tilt 编码器误差 | 0.01°-0.05° |
| 机械弯曲 | 重量导致的结构变形 | 0.01°-0.05° |
| 光学轴偏差 | 光轴与机械轴不对齐 | 0.05°-0.5° |

### 3.2 校准模型 (类 T-Point 简化版)

采用 **球面谐波模型** (Spherical Harmonic Pointing Model):

```
ΔPan(pan, tilt) = c0 + c1·tan(tilt) + c2·sec(tilt)·sin(pan) 
                  + c3·sec(tilt)·cos(pan) + c4·tan²(tilt) + ...

ΔTilt(pan, tilt) = d0 + d1·tilt + d2·sin(pan) + d3·cos(pan) 
                   + d4·sin(2·pan) + d5·cos(2·pan) + ...
```

**经典 T-Point 模型** (Wallace, Patrick 1998, TPOINT 软件):
```
IA (方位零偏) + CA (编码器周期误差项) + NP (极轴对准误差) +
AX (轴非正交) + MA (镜筒弯曲) + TF (温度弯曲) + ...
```

### 3.3 推荐校准参数 (最少有效模型)

```
Pan_error = IA + CA·sin(pan) + NP·tan(tilt) + AX·sec(tilt)·cos(pan)
Tilt_error = IE + MA·cos(tilt) + CE·sin(tilt)
```

最少需 **7 个参数**，建议用 **10-15 颗星** 进行最小二乘拟合。

---

## 4. 校准流程

### Phase 1: 初始对准 (粗校准)

```
1. 水平校准 PTZ 基座 (气泡水平仪或数字水平仪)
2. 确定 Pan 零点: 对准已知方位目标 (地标、北极星)
3. 确定 Tilt 零点: 水平位置 (水平仪确认)
4. 记录时间、GPS 坐标 (用于 LST 计算)
```

### Phase 2: 星场采集 (数据采集)

```
1. PTZ 移动到 N 个已知星体位置 (N ≥ 10, 均匀分布在天球)
2. 每个位置:
   a. 发送理论 Pan/Tilt 指令
   b. 捕获图像
   c. Plate Solving 确定实际指向 (RA_actual, DEC_actual)
   d. 转换为 Alt_actual, Az_actual
   e. 计算偏差: ΔPan = Pan_actual - Pan_theory
                    ΔTilt = Tilt_actual - Tilt_theory
3. 覆盖范围:
   - Tilt: 10° ~ 85° (避开天顶奇点)
   - Pan: 全范围 0° ~ 360°
   - 每 30° azimuth 至少一个点，多仰角层
```

### Phase 3: 模型拟合

```
1. 用最小二乘法拟合校准参数
2. 验证: 留出 2-3 颗星做交叉验证
3. RMS 目标: < 0.1° (约 6 arcmin)
4. 如不达标 → 增加校准点或增加模型参数
```

### Phase 4: 在线精修 (可选)

```
1. 每次定位后, plate solve 确认
2. 更新校准模型 (递推最小二乘)
3. 长期漂移补偿 (温度、机械老化)
```

---

## 5. 所需硬件/软件

### 5.1 硬件

| 组件 | 要求 | 示例 |
|------|------|------|
| PTZ 摄像头 | 支持 ONVIF/Pan-Tilt 精确控制 | Sony EVI-D100, Panasonic AW-UE150, PTZOptics |
| 分辨率 | ≥ 1080p (plate solving 需要足够星点) | 1080p 最低, 4K 更好 |
| 镜头 | 广角 (FOV ≥ 30°) 利于 plate solving | 焦距 4-8mm |
| 三脚架 | 稳固、可水平调节 | Manfrotto 等 |
| GPS 模块 | 精度 ≤ 10m (影响 LST) | USB GPS 或手机 GPS |
| (可选) IMU | 初始水平检测 | BNO055 |

### 5.2 软件

| 组件 | 用途 | 推荐 |
|------|------|------|
| 坐标转换 | RA/DEC ↔ Alt/Az | **Astropy** (Python) / **libastro** (XEphem) |
| Plate Solving | 图像 → 精确指向 | **ASTAP** (推荐，快) / **Astrometry.net** (准但慢) |
| 星表 | plate solving 参考 | Gaia DR3 / UCAC4 / Tycho-2 |
| 校准拟合 | 误差模型求解 | NumPy/SciPy (最小二乘) |
| PTZ 控制 | ONVIF/Visca/Pelco | onvif-zeep (Python) / Visca over IP |
| (可选) TPOINT | 经典指向分析 |商业软件，非必须 |

### 5.3 Python 核心依赖

```python
# 坐标转换
from astropy.coordinates import SkyCoord, AltAz, EarthLocation
from astropy.time import Time
import astropy.units as u

# 示例代码
location = EarthLocation(lat=lat*u.deg, lon=lon*u.deg, height=alt*u.m)
time = Time('2025-01-01 12:00:00', scale='utc')
target = SkyCoord(ra=ra*u.deg, dec=dec*u.deg, frame='icrs')
altaz = target.transform_to(AltAz(obstime=time, location=location))
alt = altaz.alt.deg
az = altaz.az.deg
```

---

## 6. 精度预期

| 级别 | RMS 误差 | 条件 |
|------|----------|------|
| 理论计算 (无校准) | 0.5° - 2° | 仅坐标转换，含典型 PTZ 误差 |
| 粗校准后 | 0.2° - 0.5° | 零点对准 + 水平 |
| 完整校准 (7参数) | 0.05° - 0.15° | 10-20 颗星拟合 |
| 完整校准 (15参数) | 0.02° - 0.08° | 20+ 颗星，含温度 |
| 在线修正 | 0.01° - 0.03° | 每次 plate solve 修正 |

**影响因素**:
- PTZ 编码器分辨率 (典型 0.01°-0.1°)
- 光学畸变 (桶形/枕形畸变影响 plate solving 中心)
- 大气折射 (低仰角 < 15° 时 > 0.1°)
- 温度漂移 (金属膨胀 ~0.01°/10°C)

---

## 7. Plate Solving 详解

### 7.1 ASTAP (推荐)

- **优点**: 本地运行、速度极快 (< 2s)、精度 ~ 1-2 arcsec
- **星表**: 自含 H17-H23 星表 (Gaia)
- **安装**: astap.org
- **调用**: CLI 模式 `astap -solve image.jpg`
- **输出**: RA, DEC, 旋转角, 像素比例

### 7.2 Astrometry.net

- **优点**: 无需初始猜测、精度极高
- **缺点**: 需要上传或本地安装 (heavy, ~100GB 索引)
- **本地版**: `astrometry.net` + index files
- **API**: `nova.astrometry.net` (免费但排队)

### 7.3 Plate Solving 在 PTZ 中的角色

```
PTZ 指向目标 → 拍图 → Plate Solve → 得实际(RA,DEC)
    │
    ▼
实际(RA,DEC) → Alt/Az → 实际(Pan,Tilt)
    │
    ▼
对比理论(Pan,Tilt) → 计算误差 → 更新校准模型
```

---

## 8. 参考项目与资源

### 8.1 开源项目

| 项目 | 描述 | URL |
|------|------|-----|
| **INDI / Ekos** | 天文设备控制框架，含 pointing model | inductive-kickback.com/projects/indi |
| **KStars** | 天文软件，含 T-Point 兼容校准 | edu.kde.org/kstars |
| **Astropy** | Python 天文坐标库 | astropy.org |
| **ASTAP** | 快速 plate solver | astap.org |
| **Astrometry.net** | 盲 plate solving | astrometry.net |
| **PyEphem / Skyfield** | 天体计算 | github.com/brandon-rhodes/pyephem |
| **pynpoint** | Python 指向模型 | (社区项目) |
| **Telescope Pointing Library** | C 库 | github.com/rickadair/telescope_pointing |

### 8.2 关键论文/文档

| 文献 | 核心内容 |
|------|----------|
| **Wallace, P. (1998)** "TPOINT Telescope Pointing Analysis" | 经典 T-Point 模型，7-15 参数系统 |
| **Wallace, P. (2008)** "SOFA Astrometry Tools" | IAU 标准坐标转换库 |
| **Lang et al. (2010)** "Astrometry.net: Blind Astrometric Calibration" | 盲 plate solving 算法 (ApJ) |
| **Hogg et al.** "Astrometry.net" 系列论文 | 树索引 + 几何哈希匹配 |
| **Kiss et al.** "ASTAP" 技术文档 | 快速 plate solving 方法 |
| **Kaplan (2005)** "The IAU Resolutions on Astronomical Reference Systems" | 坐标系统标准 |

### 8.3 实用资源

- **USNO MICA**: 美国海军天文台天文计算
- **XEphem**: 交互式天文程序 (含 pointing model)
- **Stellarium**: 天文可视化 (可导出星位)
- **Gaia Archive**: 最新星表 (gea.esac.esa.int/archive)

---

## 9. 实施方案建议 (PTZ 专用)

### 最小可行方案 (MVP)

```
步骤 1: 安装 PTZ + Python + Astropy + ASTAP
步骤 2: 实现 RA/DEC → Alt/Az → Pan/Tilt 基础链路
步骤 3: 手动对准 5 颗亮星，记录偏差
步骤 4: 拟合 3 参数模型 (IA, IE, NP)
步骤 5: 验证 3 颗独立星
步骤 6: 迭代优化
预期精度: ~0.3° (约月球直径的 60%)
```

### 完整方案

```
步骤 1-5: 同 MVP
步骤 6: 自动扫描 15-20 颗星 (覆盖全天空)
步骤 7: 拟合 7-10 参数模型
步骤 8: 加入温度传感器补偿
步骤 9: 实现在线 plate solve 修正
步骤 10: 长期漂移监测
预期精度: ~0.05° (约月球直径的 10%)
```

---

## 10. 关键风险与缓解

| 风险 | 影响 | 缓解 |
|------|------|------|
| PTZ 回程误差 | 重复性差 | 单方向逼近 + 软件补偿 |
| 天顶奇点 | Tilt≈90° 时 Pan 无定义 | 避开天顶 ±5° |
| 大气折射 | 低仰角偏差大 | Bennett 公式修正 |
| 光学畸变 | Plate solve 中心偏移 | 标定镜头畸变 |
| 温度漂移 | 长期精度下降 | 定期重校准 + 温度补偿 |
| 星表匹配失败 | Plate solve 失败 | 增大 FOV / 提高曝光 |

---

## 11. 总结

```
PTZ 天文校准 = 坐标转换 + 系统误差建模 + plate solve 验证

核心公式:
  Alt/Az = f(RA, DEC, lat, lon, UTC)    [标准天文学]
  Pan_cmd = Az + model(pan, tilt)        [7-15 参数误差模型]
  Tilt_cmd = alt + model(pan, tilt)      [最小二乘拟合]

验证工具:
  Plate Solve → 确认实际指向 → 迭代优化

预期精度 (完整校准): 0.02° - 0.1°
```
