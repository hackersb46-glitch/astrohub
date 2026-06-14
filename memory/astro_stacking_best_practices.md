# 天文图像叠加对齐最佳实践

> 生成时间：2026-06-04 | 子代理调研

---

## 1. 星点检测算法对比

| 方法 | 精度 | 性能 | 适用场景 | 优点 | 缺点 |
|------|------|------|----------|------|------|
| **DAOPHOT** (Stetson) | ⭐⭐⭐⭐⭐ 极高 | 慢 (Fortran C) | 密集星场、测光 | 亚像素级星心定位，PSF拟合，经典标准 | 速度慢，配置复杂，需手动调参 |
| **SExtractor** (Bertin) | ⭐⭐⭐⭐⭐ 极高 | 快 (C 优化) | 大规模巡天、批量处理 | 自动检测+测光+分类，速度快，支持多阈值 | 对弥散天体敏感，密集星场需调参 |
| **photutils (DAOStarFinder)** | ⭐⭐⭐⭐ 高 | 中等 (Python) | Python 流程集成 | 纯Python，与Astropy生态集成好 | 比SExtractor慢，密集星场不如DAOPHOT |
| **photutils (IRAFStarFinder)** | ⭐⭐⭐⭐ 高 | 中等 | 替代DAOPHOT的Python实现 | DAOPHOT的Python复现 | 精度略低于原版DAOPHOT |
| **OpenCV (BLOB/DoG)** | ⭐⭐⭐ 中 | 快 (C++后端) | 快速原型、实时 | 速度快，易集成，GPU加速 | 非天文专用，无PSF建模，精度受限 |
| **OpenCV (Harris/FAST)** | ⭐⭐ 低 | 极快 | 粗略对齐预筛选 | 极快 | 不适合星点检测，设计用于角点 |

**推荐**：
- **最高精度**：DAOPHOT 或 SExtractor
- **Python 集成最佳**：`photutils.detection.DAOStarFinder` / `IRAFStarFinder`
- **快速预筛选**：OpenCV BLOB + photutils 精化

### 关键参数
```python
# photutils DAOStarFinder 关键参数
DAOStarFinder(
    fwhm=3.0,          # 星点半高全宽（像素），影响检测尺度
    threshold=10.0,    # 检测阈值（σ倍数），越高越严格
    sigma_radius=1.5,  # 用于计算局部背景的σ半径
    sharplo=0.2,       # 锐度下限，过滤宇宙射线/热像素
    sharphi=1.0,       # 锐度上限
    roundlo=-1.0,      # 圆度下限
    roundhi=1.0        # 圆度上限
)
```

---

## 2. 图像对齐方法对比

| 方法 | 精度 | 鲁棒性 | 速度 | 适用场景 | 关键特点 |
|------|------|--------|------|----------|----------|
| **星点匹配-三角形法** (astroalign) | ⭐⭐⭐⭐⭐ | 极高 | 中等 | 无WCS图像对齐 | 基于3点星群(asterism)匹配，对FoV/PSF差异鲁棒 |
| **星点匹配-模式匹配** (astrometry.net) | ⭐⭐⭐⭐⭐ | 极高 | 慢 | 绝对天球坐标解算 | 全局索引匹配，可给出精确WCS |
| **相位相关法** (FFT cross-correlation) | ⭐⭐⭐⭐ | 高 | 快 | 小位移/平移对齐 | 亚像素精度，但对旋转/缩放敏感 |
| **ECC** (Enhanced Correlation Coefficient) | ⭐⭐⭐⭐ | 高 | 中等 | 仿射/单应性变换 | OpenCV实现，支持仿射/透视变换 |
| **光流法** (Lucas-Kanade) | ⭐⭐⭐ | 中 | 快 | 连续帧跟踪 | 需要好的初始估计，对大位移失效 |
| **astroalign register()** | ⭐⭐⭐⭐⭐ | 极高 | 中等 | Python流水线首选 | 三角形匹配+scikit-image SimilarityTransform |

### 推荐方案

```
场景                    推荐方法
─────────────────────────────────────────────
无WCS，不同FoV/条件      astroalign (三角形法)
需要绝对天球坐标          astrometry.net
小位移平移对齐            相位相关法 (FFT)
已知近似变换的精细对齐     ECC (OpenCV)
连续帧跟踪(行星/月球)     光流法
批量快速预对齐            相位相关 → astroalign精化
```

### astroalign 关键用法
```python
import astroalign as aa

# 完整对齐（source对齐到target）
aligned_image, footprint = aa.register(source_image, target_image)

# 仅获取变换和控制点对应
transf, (src_stars, tgt_stars) = aa.find_transform(source, target)
# transf: scikit-image SimilarityTransform (含scale, rotation, translation)
```

### 相位相关法关键参数
```python
from skimage.registration import phase_cross_correlation
shift, error, diffphase = phase_cross_correlation(
    ref_image, moving_image,
    upsample_factor=100,    # 亚像素精度：越大越精确
    reference_mask=None     # 可选掩码
)
```

### ECC 关键参数
```python
import cv2
criteria = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 50, 1e-10)
warp_mode = cv2.MOTION_AFFINE  # 或 cv2.MOTION_HOMOGRAPHY
warp_matrix = np.eye(2, 3, dtype=np.float32)
cc, warp_matrix = cv2.findTransformECC(
    templateImage, inputImage, warp_matrix,
    warp_mode, criteria, inputMask=None, gaussFiltSize=5
)
```

---

## 3. 叠加算法对比

| 方法 | 噪声抑制 | 异常值抵抗 | 速度 | 帧数要求 | 适用场景 |
|------|----------|------------|------|----------|----------|
| **Mean (平均)** | √N 改善 | 差 | 最快 | 任意 | 无异常值的干净数据 |
| **Median (中值)** | ~1.25×√N | 极好 | 中等 | ≥3 | 有卫星轨迹/飞机/热像素 |
| **Sigma Clipping** | 接近Mean | 好 | 中等 | ≥5 | 专业天文叠加首选 |
| **Winsorized Mean** | 接近Mean | 好 | 快 | ≥3 | 平衡速度和鲁棒性 |
| **MinMax (clip N low/high)** | 中等 | 好 | 快 | ≥3 | IRAF传统方法 |

### Sigma Clipping vs Median vs Mean 效果对比

```
噪声抑制效果（理论，N帧叠加）：
Mean:          σ/√N              (最优，但无异常值抵抗)
Median:        ~1.25×σ/√N        (稍差，但异常值抵抗极强)
Sigma Clip:    接近 σ/√N          (接近最优+异常值抵抗)
Winsorized:    接近 σ/√N          (速度比Sigma Clip快)

推荐帧数下的最佳选择：
3-5 帧  →  Median（Sigma Clip样本太少不稳定）
5-15 帧 →  Sigma Clipping（σ=3.0, max_iter=5）
15+ 帧  →  Sigma Clipping（σ=2.5-3.0, max_iter=5）或 Winsorized Mean
```

### ccdproc Combiner 实现

```python
from ccdproc import Combiner
from astropy.nddata import CCDData
import numpy as np

# 创建Combiner
c = Combiner([CCDData(img, unit=u.adu) for img in image_list])

# Sigma Clipping + 平均叠加（推荐）
c.sigma_clipping(low_thresh=3.0, high_thresh=3.0, func='mean')
result = c.average_combine()

# 中值叠加（异常值多时）
result = c.median_combine()

# MinMax clipping (IRAF风格)
c.clip_extrema(nlow=1, nhigh=1)
result = c.average_combine()

# 关键参数：
# sigma_clipping:
#   low_thresh=3.0    # 下限σ阈值（越大越宽松）
#   high_thresh=3.0   # 上限σ阈值
#   func='mean'       # 中心统计量 ('mean'/'median')
#   dev_func='std'    # 偏差度量
#
# median_combine:
#   uncertainty = 1.4826 × MAD (中值绝对偏差)
```

---

## 4. 成熟软件参考

| 软件 | 对齐方式 | 叠加方式 | 特点 | 局限 |
|------|----------|----------|------|------|
| **DeepSkyStacker** | 星点检测+星匹配 | Mean/Median/Sigma/Winsorized/Kappa-Sigma | 免费开源，Windows首选，自动校准帧处理 | 仅Windows，不支持Linux/Mac |
| **PixInsight** | StarAlignment (星点匹配) | ImageIntegration (各种clipping) | 专业级，最全面，支持WCS | 付费($$)，学习曲线陡 |
| **Siril** | 多种：星点/注册/行星 | 多种叠加+Sigma clipping | 免费开源，跨平台，脚本化 | 文档不如PixInsight |
| **ASTAP** | 星点匹配+WCS | 平均叠加 | 免费，堆叠+plate solving一体 | 叠加功能较简单 |

### DeepSkyStacker 叠加方法
- Kappa-Sigma Clipping (最佳噪声抑制)
- Auto Adaptive Weighted Average
- Median / Mean
- Biweight Median / Winsorized

### PixInsight StarAlignment 关键点
- 使用 StarDetector 找星
- 三角形模式匹配
- 支持 Thin-Plate Spline / Affine / Projective 变换
- 默认结构相似性阈值：0.35-0.45

---

## 5. Python 库方案推荐

### 推荐流水线

```
原始FITS → 校准(暗场/平场) → 星点检测 → 图像对齐 → Sigma Clip叠加 → 输出
    │              │                │            │           │
  astropy      ccdproc       photutils     astroalign    ccdproc
  fits        ImageCalibration  DAOStarFinder  register()  Combiner
```

### 各库职责

| 库 | 职责 | 关键API |
|----|------|---------|
| **astropy** | FITS I/O, WCS, 坐标系统 | `fits.open()`, `wcs.WCS`, `coordinates` |
| **ccdproc** | CCD校准, 叠加, WCS投影 | `Combiner`, `sigma_clipping`, `wcs_project` |
| **photutils** | 星点检测, 孔径测光, 背景估计 | `DAOStarFinder`, `background`, `aperture_photometry` |
| **astroalign** | 无WCS图像对齐 | `register()`, `find_transform()` |
| **reproject** | 基于WCS的重投影 | `reproject_interp()`, `reproject_exact()` |
| **scikit-image** | 变换估计, 插值 | `SimilarityTransform`, `warp()` |

### 关键参数建议汇总

```python
# ==================== 星点检测 ====================
# photutils DAOStarFinder
fwhm = 3.0          # 根据实际 seeing 调整（像素）
threshold = 5.0     # SNR 阈值，拥挤场降低到 3-5
sharplo = 0.2       # 过滤非星形物体
sharphi = 1.0
roundlo = -0.5      # 过滤椭圆/线性特征
roundhi = 0.5

# ==================== 对齐 ====================
# astroalign
# 内置参数通常无需调整，关键控制点数量：
# 默认最多匹配 20 个控制点
# 如果星点少，可以降低 min_area 参数

# 相位相关
upsample_factor = 100   # 亚像素精度

# ==================== Sigma Clipping ====================
low_thresh = 3.0        # σ 下限
high_thresh = 3.0       # σ 上限
func = 'mean'           # 中心值计算方式
max_iter = 5            # 最大迭代次数

# 帧数较少时(3-5帧):
low_thresh = 3.0, high_thresh = 3.0  # 保守
# 帧数较多时(15+帧):
low_thresh = 2.5, high_thresh = 2.5  # 更激进

# ==================== 插值 ====================
# 对齐时的插值方式
order = 'bilinear'      # 速度和精度平衡（ccdproc wcs_project）
# 或
order = 'bicubic'       # 更高精度，但更慢
```

---

## 6. 完整推荐方案

### 方案 A：全自动 Python 流水线（推荐）

```python
from astropy.nddata import CCDData
from astropy import units as u
from ccdproc import Combiner
from photutils.detection import DAOStarFinder
import astroalign as aa
import numpy as np

# Step 1: 校准（暗场、平场）
# 使用 ccdproc subtract_dark, flat_correct

# Step 2: 叠加
c = Combiner([CCDData(img, unit=u.adu) for img in calibrated_images])

# Step 3: Sigma Clipping
c.sigma_clipping(low_thresh=3.0, high_thresh=3.0, func='mean')

# Step 4: 叠加
result = c.average_combine()

# Step 5: 如果图像无WCS，使用astroalign预对齐
# 以第一张为参考，对齐其余
aligned_images = [calibrated_images[0]]
for img in calibrated_images[1:]:
    aligned, _ = aa.register(img, calibrated_images[0])
    aligned_images.append(aligned)
```

### 方案 B：高精度专业流水线

```
1. SExtractor 星点检测（最高精度）
2. astrometry.net 解算WCS
3. reproject 精确重投影
4. ccdproc Sigma Clipping + Average Combine
```

---

## 参考资源

- **astroalign**: https://github.com/quatrope/astroalign (160 stars)
  - 论文: Beroiz et al. 2020, Astronomy & Computing, 100384
- **ccdproc**: https://ccdproc.readthedocs.io/en/stable/ (v2.5.1)
- **photutils**: https://photutils.readthedocs.io/
- **astropy**: https://docs.astropy.org/en/stable/
- **DeepSkyStacker**: http://deepskystacker.free.fr/
- **PixInsight**: https://pixinsight.com/
- **Siril**: https://free-astro.org/siril/
