# 天文经纬仪（Alt-Az Mount）校准技术方案

> 基于 T-Point/MaxPoint 模型，涵盖安装参数校准、坐标转换建模、校准流程全流程。

---

## 目录

1. [坐标系定义](#1-坐标系定义)
2. [安装参数（误差项）定义](#2-安装参数误差项定义)
3. [经典 T-Point 指向模型](#3-经典-t-point-指向模型)
4. [Alt-Az 坐标转换数学模型](#4-alt-az-坐标转换数学模型)
5. [球面谐波误差模型](#5-球面谐波误差模型)
6. [机械回差（Backlash）建模](#6-机械回差backlash建模)
7. [轴倾斜与镜筒弯曲（Tube Flexure）](#7-轴倾斜与镜筒弯曲tube-flexure)
8. [校准算法流程](#8-校准算法流程)
9. [多星拟合与最小二乘求解](#9-多星拟合与最小二乘求解)
10. [实现注意事项](#10-实现注意事项)

---

## 1. 坐标系定义

### 1.1 天球坐标系

| 坐标系 | 参数1 | 参数2 | 说明 |
|--------|-------|-------|------|
| 赤道坐标系 (ICRS/J2000) | RA (α) | DEC (δ) | J2000.0 历元 |
| 地平坐标系 (Alt-Az) | 方位角 A | 高度角 h | 方位从北点起算，东增 |
| 时角坐标系 | 时角 H | DEC (δ) | H = LST - α |

### 1.2 机械坐标系

| 轴 | 编码器读数 | 理想指向 |
|----|-----------|---------|
| Pan（方位轴） | A_enc | 理论方位角 A |
| Tilt（俯仰轴） | h_enc | 理论高度角 h |

### 1.3 坐标转换（理想 Alt-Az ↔ 赤道）

```
sin(h) = sin(φ)sin(δ) + cos(φ)cos(δ)cos(H)
cos(h)sin(A) = -cos(δ)sin(H)
cos(h)cos(A) = sin(δ)cos(φ) - cos(δ)sin(φ)cos(H)
```

其中 φ 为观测站纬度，H = LST - α 为时角。

---

## 2. 安装参数（误差项）定义

### 2.1 一级误差项（6项基础安装误差）

| 编号 | 参数名 | 符号 | 物理含义 | 量级 |
|------|--------|------|---------|------|
| 1 | 水平偏差-南北 | Δh_NS | Pan轴不水平，南北方向倾斜 | arcsec |
| 2 | 水平偏差-东西 | Δh_EW | Pan轴不水平，东西方向倾斜 | arcsec |
| 3 | 方位零点偏差 | IA | Azimuth Index Error，方位编码器零点偏移 | arcsec |
| 4 | 俯仰零点偏差 | IH | Altitude Index Error，俯仰编码器零点偏移 | arcsec |
| 5 | 轴不正交性 | NP | Pan轴与Tilt轴不垂直（Collimation Error） | arcsec |
| 6 | 轴倾斜 | AW | Tilt轴相对Pan轴的倾斜（Tube tilt） | arcsec |

### 2.2 二级误差项（结构与传动）

| 编号 | 参数名 | 符号 | 物理含义 |
|------|--------|------|---------|
| 7 | 方位轴倾斜-极轴分量 | ΔPA | 等效极轴偏差（Alt-Az下表现为方位轴倾斜） |
| 8 | 镜筒弯曲-重力 | ΔEL_flex | 俯仰方向重力引起的镜筒弯曲 |
| 9 | 方位轴弯曲 | ΔAZ_flex | 方位方向重力引起的弯曲 |
| 10 | 齿轮偏心率 | E_az, E_el | 编码器/齿轮偏心引起的周期性误差 |
| 11 | 齿轮周期误差 | P_az, P_el | 齿轮啮合周期误差 |
| 12 | 机械回差 | B_az, B_el | 方向切换时的空程 |

### 2.3 误差项分类

```
安装参数 (固定，不随时间变):
├── IA, IH (零点偏差)
├── NP (轴不正交)
├── Δh_NS, Δh_EW (水平偏差)
└── ΔPA (极轴偏差)

结构参数 (随姿态缓慢变化):
├── ΔEL_flex(ALT) (镜筒弯曲，高度角函数)
├── ΔAZ_flex(ALT) (方位弯曲)
└── AW (轴倾斜)

传动参数 (周期性):
├── E_az * sin(A_enc + φ_az) (方位偏心)
├── E_el * sin(h_enc + φ_el) (俯仰偏心)
└── B_az, B_el (回差，方向相关)
```

---

## 3. 经典 T-Point 指向模型

T-Point 由 Patrick Wallace 开发，其模型在 Alt-Az 下的误差方程：

### 3.1 方位角误差方程

```
ΔA = IA + NP·tan(h) + (Δh_NS·cos(A) + Δh_EW·sin(A))·tan(h)
     + AW·sec(h) + ΔPA·sec(h)·sin(A)
     + E_az·sin(A_enc + φ_az) + E_az2·sin(2A_enc + φ_az2)
     + 球面谐波残差项
```

### 3.2 俯仰角误差方程

```
Δh = IH + AW·cos(h) + ΔEL_flex·cos(h)
     + (Δh_NS·sin(A) - Δh_EW·cos(A))
     + E_el·sin(h_enc + φ_el)
     + 球面谐波残差项
```

### 3.3 参数物理意义

| 参数 | 对应 T-Point 项 | 依赖关系 |
|------|----------------|---------|
| IA | `pa` (polar axis offset) | 常数 |
| IH | `ie` (index error) | 常数 |
| NP | `np` (non-perpendicularity) | ∝ tan(h) |
| Δh_NS | `ma` (mount axis tilt) | ∝ tan(h)·cos(A) |
| Δh_EW | `me` (mount axis tilt E-W) | ∝ tan(h)·sin(A) |
| AW | `aw` (axis tilt) | ∝ sec(h) |
| ΔPA | `pol` (polar misalignment) | ∝ sec(h)·sin(A) |

---

## 4. Alt-Az 坐标转换数学模型

### 4.1 完整转换流程

```
目标: (α, δ) → 修正后的 (A_corr, h_corr)

步骤:
1. (α, δ) → (H, δ)  时角转换
   H = LST - α

2. (H, δ) → (A_ideal, h_ideal)  理想球面转换
   sin(h_ideal) = sin(φ)sin(δ) + cos(φ)cos(δ)cos(H)
   tan(A_ideal) = -sin(H) / (cos(H)sin(φ) - tan(δ)cos(φ))

3. (A_ideal, h_ideal) → (A_corr, h_corr)  误差修正
   A_corr = A_ideal + ΔA(A_ideal, h_ideal, params)
   h_corr = h_ideal + Δh(A_ideal, h_ideal, params)

4. (A_corr, h_corr) → 电机指令 (步进/伺服)
```

### 4.2 逆变换（编码器 → 天球坐标）

```
编码器读数 (A_enc, h_enc)
  → 去除回差 B_az, B_el
  → (A_mech, h_mech)
  → 去除安装误差
  → (A_true, h_true)
  → 球面逆变换
  → (H, δ) → (α, δ)
```

### 4.3 Alt-Az 下的极轴偏差表达

Alt-Az 架台不存在传统"极轴对准"概念，但方位轴倾斜会产生等效效应：

```
方位轴倾斜向量: v_tilt = (δ_NS, δ_EW, 1)

等效极轴偏差角:
  θ_pa = arctan(√(δ_NS² + δ_EW²))

在指向误差中的表达:
  ΔA_pa = θ_pa · sec(h) · sin(A - A_tilt)
  Δh_pa = θ_pa · cos(A - A_tilt)
```

其中 A_tilt = arctan2(δ_EW, δ_NS) 为倾斜方向。

---

## 5. 球面谐波误差模型

### 5.1 基本原理

残差误差（无法用物理参数解释的部分）用球面谐波展开：

```
ΔA_res(A, h) = Σ_{l=0}^{L} Σ_{m=-l}^{l} a_{lm} · Y_{lm}(A, h)
Δh_res(A, h) = Σ_{l=0}^{L} Σ_{m=-l}^{l} b_{lm} · Y_{lm}(A, h)
```

其中 Y_{lm} 为球面谐波函数。

### 5.2 实用简化（T-Point 采用的 Fourier 级数）

实际应用中 T-Point 使用方位角的 Fourier 级数 + 高度角的多项式：

```
ΔA(A, h) = Σ_i [CA_i·cos(i·A) + SA_i·sin(i·A)] · f_i(h)
Δh(A, h) = Σ_i [CE_i·cos(i·A) + SE_i·sin(i·A)] · g_i(h)
```

其中 f_i(h), g_i(h) 为高度角依赖函数（通常为 sec(h), tan(h), 常数等）。

### 5.3 T-Point 模型项展开

| T-Point 项 | 方位修正 | 俯仰修正 | 说明 |
|-----------|---------|---------|------|
| PA | 0 | PA·cos(h) | 极轴偏差（赤道架台） |
| IE | 0 | IE | 俯仰零点 |
| NP | NP·tan(h) | 0 | 轴不正交 |
| AW | AW·sec(h) | 0 | 轴倾斜 |
| AN | AN·cos(A)·tan(h) | AN·sin(A) | 方位轴倾斜-北分量 |
| AE | AE·sin(A)·tan(h) | -AE·cos(A) | 方位轴倾斜-东分量 |
| N | 0 | N·cos(h) | 镜筒弯曲 |
| CA/SA | CA·cos(A)+SA·sin(A) | -CA·sin(A)+SA·cos(A) | 方位谐波 1 阶 |
| CB/SB | CB·cos(2A)+SB·sin(2A) | -2·CB·sin(2A)+2·SB·cos(2A) | 方位谐波 2 阶 |
| ... | ... | ... | 高阶谐波 |

### 5.4 推荐项数选择

| 精度目标 | 建议项数 | 需要星数 |
|---------|---------|---------|
| ~30 arcsec | 6项（基础） | ≥10 |
| ~10 arcsec | 10项（含谐波1阶） | ≥20 |
| ~3 arcsec | 15项（含谐波2阶+弯曲） | ≥30 |
| ~1 arcsec | 20+项（高阶+球面谐波） | ≥50 |

---

## 6. 机械回差（Backlash）建模

### 6.1 物理机制

```
齿轮传动 → 齿隙间隙 → 方向切换时空程
编码器在齿隙内不反映真实运动
```

### 6.2 数学模型

```
B(A_enc) = sign(dA/dt) · B_az_max / 2
B(h_enc) = sign(dh/dt) · B_el_max / 2

修正:
  A_true = A_enc - B(A_enc)
  h_true = h_enc - B(h_enc)
```

### 6.3 实测标定方法

```
步骤:
1. 固定目标（天体或地面标志）
2. 从正向趋近 → 记录编码器读数 A_fwd
3. 从反向趋近 → 记录编码器读数 A_rev
4. Backlash = |A_fwd - A_rev|
5. 多位置重复 → 取平均或拟合函数

注意:
- 回差可能随位置变化（齿轮偏心）
- 回差可能随时间变化（磨损）
- 建议定期重新标定
```

---

## 7. 轴倾斜与镜筒弯曲（Tube Flexure）

### 7.1 镜筒弯曲模型

```
ΔEL_flex(h) = C_el · cos(h) + D_el · sin(h)

物理含义:
- C_el · cos(h): 重力引起的镜筒下垂（高度角越大影响越小）
- D_el · sin(h): 侧向弯曲分量
```

### 7.2 方位轴弯曲

```
ΔAZ_flex(A, h) = C_az · cos(A) · cos(h) + D_az · sin(A) · cos(h)
```

### 7.3 组合模型

```
ΔA_total = ΔA_install + ΔA_harmonic + ΔAZ_flex
Δh_total = Δh_install + Δh_harmonic + ΔEL_flex
```

---

## 8. 校准算法流程

### 8.1 完整校准流程

```
┌─────────────────────────────────────────────────────────┐
│  Step 0: 准备工作                                         │
│  - 安装水平仪，粗调水平                                     │
│  - 确认编码器零点（机械标记对齐）                             │
│  - 记录观测站经纬度、海拔                                    │
│  - 加载最新星表（J2000）                                    │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│  Step 1: 单星校准（基础零点）                                │
│  - 指向已知亮星（如天狼星、北极星）                            │
│  - 用 CCD/相机精确定位星中心                                │
│  - 记录: (A_enc, h_enc) 和 (α, δ)                        │
│  - 计算初始 IA, IH                                        │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│  Step 2: 多星数据采集                                      │
│  - 选择全天分布的校准星（≥20颗）                             │
│  - 覆盖高度角范围: 15° ~ 85°                               │
│  - 覆盖方位角范围: 0° ~ 360°                              │
│  - 避免天顶盲区 (zenith blind spot)                        │
│  - 每颗星:                                                │
│    1. 粗指向 → CCD 视场捕获                                │
│    2. 星图匹配 → 精确定位                                   │
│    3. 记录 (A_enc, h_enc, α, δ, timestamp)              │
│    4. 正反向趋近各一次（测回差）                              │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│  Step 3: 数据预处理                                       │
│  - 大气折射修正:                                          │
│    Δh_ref = R · cot(h_apparent + 7.31/(h_apparent+4.4))  │
│    R ≈ 1 arcmin (标准条件)                                │
│  - 计算观测时刻的 (H, δ)                                  │
│  - 理想转换 (A_ideal, h_ideal)                            │
│  - 残差: ΔA = A_enc - A_ideal, Δh = h_enc - h_ideal      │
│  - 剔除粗差 (>3σ)                                         │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│  Step 4: 参数拟合                                        │
│  - 构建观测矩阵 M:                                       │
│    M · x = y                                             │
│    x = [IA, IH, NP, AW, AN, AE, ...]                    │
│    y = [ΔA_1, Δh_1, ΔA_2, Δh_2, ...]                    │
│  - 最小二乘求解:                                         │
│    x = (M^T M)^(-1) M^T y                               │
│  - 或使用加权最小二乘 (WLS)                               │
│  - 或鲁棒估计 (Huber, RANSAC)                             │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│  Step 5: 残差分析与模型选择                                │
│  - 计算 RMS 残差: RMS_A, RMS_h                            │
│  - 残差分布检查 (正态性检验)                               │
│  - 残差 vs 高度角 / 方位角图                               │
│  - 如果残差有系统性模式 → 增加模型项                         │
│  - 交叉验证 (留一法 / K-fold)                              │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│  Step 6: 模型验证                                        │
│  - 用保留的验证星测试                                      │
│  - 检查天顶附近精度                                        │
│  - 检查不同高度角范围精度                                   │
│  - 验证正反向趋近一致性                                     │
│  - 目标: RMS < 规格要求                                    │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│  Step 7: 部署与在线修正                                    │
│  - 存储模型参数                                            │
│  - 实时指向计算:                                           │
│    目标(α,δ) → 理想(A,h) → +ΔA,Δh → 电机指令              │
│  - 可选: 在线参数更新（递推最小二乘）                          │
└─────────────────────────────────────────────────────────┘
```

### 8.2 关键参数说明

#### 天顶盲区 (Zenith Blind Spot)

```
问题: 在 Alt-Az 架台的天顶附近 (h ≈ 90°):
  - tan(h) → ∞
  - sec(h) → ∞
  - 方位角变化率 dA/dt → ∞（需要无限快的方位电机）

解决方案:
  1. 校准星选择时排除 h > 85° 的区域
  2. 模型中 tan(h), sec(h) 项在天顶附近截断
  3. 天顶区域使用插值而非外推
  4. 如需天顶观测 → 使用 field derotator + 特殊策略
```

#### 大气折射修正

```
标准折射公式 (Saemundsson):
  R = (1.02 / tan(h + 10.3/(h+5.11))) arcmin  (h 单位: 度)

修正后的观测高度角:
  h_true = h_observed - R

参数依赖:
  - 气压 P: R ∝ P
  - 温度 T: R ∝ 1/T
  - 湿度: 次要修正

实时折射计算需要:
  - 本地气压计读数
  - 温度传感器
  - 可选湿度传感器
```

---

## 9. 多星拟合与最小二乘求解

### 9.1 线性最小二乘

对于线性模型 y = M·x + ε：

```python
# 伪代码
import numpy as np

def solve_pointing_model(star_data, model_terms):
    """
    star_data: list of dicts with keys:
      - A_enc, h_enc: encoder readings
      - alpha, delta: catalog RA/DEC (rad)
      - timestamp: observation time
    
    model_terms: list of callable functions
      Each returns (dA/dparam, dh/dparam) for a given (A, h)
    """
    n_stars = len(star_data)
    n_params = len(model_terms)
    
    # Build observation matrix
    M = np.zeros((2*n_stars, n_params))
    y = np.zeros(2*n_stars)
    
    for i, star in enumerate(star_data):
        # Ideal position
        A_ideal, h_ideal = equatorial_to_altaz(
            star['alpha'], star['delta'], 
            star['timestamp'], obs_lat, obs_lon
        )
        # Apply refraction correction
        h_ideal = apply_refraction(h_ideal, pressure, temperature)
        
        # Residuals
        dA = star['A_enc'] - A_ideal
        dh = star['h_enc'] - h_ideal
        
        y[2*i]   = dA
        y[2*i+1] = dh
        
        # Jacobian
        for j, term in enumerate(model_terms):
            da_dj, dh_dj = term(A_ideal, h_ideal)
            M[2*i,   j] = da_dj
            M[2*i+1, j] = dh_dj
    
    # Solve
    x_hat = np.linalg.lstsq(M, y, rcond=None)[0]
    
    # Residuals
    residuals = y - M @ x_hat
    rms = np.sqrt(np.mean(residuals**2))
    
    return x_hat, rms, residuals
```

### 9.2 加权最小二乘

```python
def weighted_solve(star_data, model_terms, weights=None):
    """
    weights: per-observation weights (e.g., based on SNR, airmass)
    """
    if weights is None:
        weights = np.ones(2*len(star_data))
    
    W = np.diag(weights)
    M_weighted = W @ M
    y_weighted = W @ y
    
    x_hat = np.linalg.lstsq(M_weighted, y_weighted, rcond=None)[0]
    return x_hat
```

### 9.3 鲁棒估计（RANSAC）

```python
from sklearn.linear_model import RANSACRegressor

def robust_solve(star_data, model_terms):
    """Use RANSAC to reject outliers"""
    M, y = build_observation_matrix(star_data, model_terms)
    
    # Solve for A and h separately
    ransac_A = RANSACRegressor()
    ransac_A.fit(M[::2], y[::2])
    
    ransac_h = RANSACRegressor()
    ransac_h.fit(M[1::2], y[1::2])
    
    return ransac_A.estimator_.coef_, ransac_h.estimator_.coef_
```

### 9.4 递推最小二乘（在线更新）

```python
class RecursiveLeastSquares:
    """For online parameter updates during operation"""
    
    def __init__(self, n_params, forgetting_factor=0.99):
        self.n = n_params
        self.P = np.eye(n_params) * 1e6  # Initial covariance
        self.theta = np.zeros(n_params)   # Parameters
        self.forget = forgetting_factor
    
    def update(self, m, y_obs):
        """
        m: regression vector (n_params,)
        y_obs: new observation (scalar)
        """
        # Prediction error
        pred = m @ self.theta
        e = y_obs - pred
        
        # Gain
        S = m @ self.P @ m.T + 1
        K = self.P @ m / S
        
        # Update
        self.theta = self.theta + K * e
        self.P = (self.P - K @ m @ self.P) / self.forget
        
        return e, np.sqrt(K @ m)  # residual, uncertainty
```

### 9.5 星表选择策略

```
校准星选择原则:
1. 亮度: V < 6.0 (肉眼可见，易于CCD捕获)
2. 全天均匀分布:
   - 按赤纬分区: δ < -30°, -30°~0°, 0°~30°, 30°~60°, >60°
   - 每区 ≥4 颗星
3. 高度角覆盖:
   - h < 30°: 3-5 颗 (低高度角，折射影响大)
   - 30° < h < 60°: 8-10 颗
   - h > 60°: 5-8 颗 (避免天顶)
4. 方位角覆盖:
   - 每 45° 扇区 ≥2 颗星
5. 时角覆盖:
   - 覆盖 H = -6h ~ +6h 范围

星表来源:
- Hipparcos (高精度, ~118,000 颗星)
- Tycho-2 (2,500,000 颗星)
- Gaia DR3 (最高精度, 但需要岁差/自行修正)
```

---

## 10. 实现注意事项

### 10.1 数值稳定性

```
问题: tan(h) 和 sec(h) 在高高度角时发散

解决方案:
  1. 截断: tan(h) → tan(min(h, 85°))
  2. 天顶区域使用独立插值模型
  3. 正则化: 添加小阻尼项到 (M^T M)^(-1)
```

### 10.2 单位一致性

```
推荐:
  - 所有角度: 弧度 (rad)
  - 编码器: 弧度 (从 counts 转换)
  - 模型参数: 弧度 (输出时转 arcsec)
  - 时间: UTC + JD/ MJD
```

### 10.3 岁差与章动

```
对于高精度 (<1 arcsec):
  - 应用 IAU 2006/2000A 岁差-章动模型
  - 将 J2000 星表位置转换到观测时刻
  - 使用 SOFA (IAU) 或 NOVAS (NASA) 库
```

### 10.4 温度补偿

```
机械参数随温度漂移:
  IA(T) = IA_0 + k_IA · (T - T_0)
  NP(T) = NP_0 + k_NP · (T - T_0)
  
实现:
  - 安装温度传感器
  - 在不同温度下标定
  - 拟合温度系数
  - 运行时实时补偿
```

### 10.5 推荐技术栈

```
核心计算:
  - Python + NumPy / SciPy (开发验证)
  - C/C++ (实时控制)
  
星表与天文计算:
  - astropy (Python)
  - SOFA / ERFA (C/Fortran)
  - NOVAS (NASA)
  
数据库:
  - SQLite (模型参数存储)
  - CSV/JSON (校准数据导出)
  
可视化:
  - matplotlib (残差分析)
  - plotly (交互式)
```

---

## 附录 A: 完整参数列表

| 编号 | 参数 | T-Point 名 | 量级 | 是否温度相关 |
|------|------|-----------|------|------------|
| 1 | IA | `ie` | arcsec | 否 |
| 2 | IH | `pa` | arcsec | 否 |
| 3 | NP | `np` | arcsec | 是 |
| 4 | Δh_NS | `an` | arcsec | 否 |
| 5 | Δh_EW | `ae` | arcsec | 否 |
| 6 | AW | `aw` | arcsec | 是 |
| 7 | CA | `ca` | arcsec | 否 |
| 8 | SA | `sa` | arcsec | 否 |
| 9 | CB | `cb` | arcsec | 否 |
| 10 | SB | `sb` | arcsec | 否 |
| 11 | CC | `cc` | arcsec | 否 |
| 12 | SC | `sc` | arcsec | 否 |
| 13 | N | `n` | arcsec | 是 |
| 14 | E_az | - | arcsec | 否 |
| 15 | E_el | - | arcsec | 否 |
| 16 | B_az | - | arcsec | 否 |
| 17 | B_el | - | arcsec | 否 |

## 附录 B: 参考文献

1. Wallace, P. (1994). "TPOINT - Telescope Pointing Analysis System". Starlink SUN/100.
2. Wallace, P. et al. (2006). "Evaluation of the ALMA Prototype Antennas". PASP, 118, 1234. arXiv:astro-ph/0609329
3. "Modeling and calibration of pointing errors with alt-az telescope". New Astronomy, 2016. DOI: 10.1016/j.newast.2016.02.007
4. "Using Allan Variance Based Semi-Parameter Model to Calibrate Pointing Errors of Alt-az Telescopes". Applied Sciences, 2018. DOI: 10.3390/app8040614
5. "A new calibration model for pointing a radio telescope that considers nonlinear errors in the azimuth axis". Research in Astronomy and Astrophysics, 2014. DOI: 10.1088/1674-4527/14/6/011
6. Software Bisque, TPoint Add-on Documentation. https://www.bisque.com
7. Clear Sky Institute, TPoint. https://www.clearskyinstitute.com/pointing/
