"""AstroHub v8.10 - 星点检测与匹配
SEP 星点提取 + 三角匹配对齐
"""
import numpy as np

try:
    import sep
    HAS_SEP = True
except ImportError:
    HAS_SEP = False


def extract_stars(gray: np.ndarray, thresh: float = 5.0, min_area: int = 5) -> list[dict]:
    """从灰度图提取星点。

    Args:
        gray: 灰度图 (numpy array, float64 推荐)
        thresh: 检测阈值 (sigma 倍数)
        min_area: 最小像素面积

    Returns:
        [{"x": float, "y": float, "flux": float, "fwhm": float}, ...]
    """
    if not HAS_SEP:
        return _fallback_extract(gray, thresh, min_area)

    data = gray.astype(np.float64)
    bkg = sep.Background(data)
    data_sub = data - bkg.back()

    objects = sep.extract(data_sub, thresh, err=bkg.globalrms, minarea=min_area)

    stars = []
    for obj in objects:
        if obj["flux"] <= 0:
            continue
        stars.append({
            "x": float(obj["x"]),
            "y": float(obj["y"]),
            "flux": float(obj["flux"]),
            "fwhm": float(obj["fwhm"]) if "fwhm" in obj.dtype.names else 0.0,
        })
    return stars


def _fallback_extract(gray: np.ndarray, thresh: float, min_area: int) -> list[dict]:
    """无 SEP 时的 OpenCV 降级方案。"""
    import cv2
    data = gray.astype(np.float64)
    mean_val = data.mean()
    std_val = data.std()
    binary = (data > mean_val + thresh * std_val).astype(np.uint8) * 255
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    stars = []
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < min_area:
            continue
        M = cv2.moments(cnt)
        if M["m00"] == 0:
            continue
        cx = M["m10"] / M["m00"]
        cy = M["m01"] / M["m00"]
        flux = data[int(cy), int(cx)] if 0 <= int(cy) < data.shape[0] and 0 <= int(cx) < data.shape[1] else 0
        stars.append({"x": cx, "y": cy, "flux": float(flux), "fwhm": 0.0})

    return sorted(stars, key=lambda s: -s["flux"])


def _build_triangles(points: list[dict]) -> list[tuple]:
    """从星点列表构建三角形特征 (边长比排序)。"""
    triangles = []
    n = len(points)
    for i in range(n):
        for j in range(i + 1, n):
            for k in range(j + 1, n):
                a = np.hypot(points[i]["x"] - points[j]["x"], points[i]["y"] - points[j]["y"])
                b = np.hypot(points[j]["x"] - points[k]["x"], points[j]["y"] - points[k]["y"])
                c = np.hypot(points[k]["x"] - points[i]["x"], points[k]["y"] - points[i]["y"])
                sides = sorted([a, b, c])
                if sides[0] < 1:
                    continue
                ratio = (sides[0] / sides[2], sides[1] / sides[2])
                triangles.append((ratio, i, j, k))
    return triangles


def match_stars(
    ref_stars: list[dict],
    src_stars: list[dict],
    max_stars: int = 30,
) -> tuple | None:
    """三角匹配两帧星点，计算仿射变换矩阵。

    Args:
        ref_stars: 参考帧星点
        src_stars: 待对齐帧星点
        max_stars: 使用的最亮星数量

    Returns:
        (M, dx, dy, angle_deg) 或 None
    """
    import cv2

    ref = sorted(ref_stars, key=lambda s: -s["flux"])[:max_stars]
    src = sorted(src_stars, key=lambda s: -s["flux"])[:max_stars]

    if len(ref) < 3 or len(src) < 3:
        return None

    # 构建三角形并匹配
    ref_tris = _build_triangles(ref)
    src_tris = _build_triangles(src)

    matches = []
    for (rr, ri, rj, rk) in ref_tris:
        for (sr, si, sj, sk) in src_tris:
            if abs(rr[0] - sr[0]) < 0.05 and abs(rr[1] - sr[1]) < 0.05:
                matches.append((ri, si, rj, sj, rk, sk))
                if len(matches) >= 5:
                    break
        if len(matches) >= 5:
            break

    if len(matches) < 1:
        return None

    # 收集匹配点对 (去重)
    point_pairs = {}
    for ri, si, rj, sj, rk, sk in matches:
        point_pairs[ri] = si
        point_pairs[rj] = sj
        point_pairs[rk] = sk

    src_pts = np.float32([[src[si]["x"], src[si]["y"]] for si in point_pairs.values()])
    dst_pts = np.float32([[ref[ri]["x"], ref[ri]["y"]] for ri in point_pairs.keys()])

    if len(src_pts) < 3:
        return None

    # 估算仿射变换 (2x3 矩阵)
    M, _ = cv2.estimateAffinePartial2D(src_pts, dst_pts)
    if M is None:
        # 降级: 仅平移
        dx = dst_pts[:, 0].mean() - src_pts[:, 0].mean()
        dy = dst_pts[:, 1].mean() - src_pts[:, 1].mean()
        return (np.array([[1, 0, dx], [0, 1, dy]], dtype=np.float32), dx, dy, 0.0)

    dx, dy = M[0, 2], M[1, 2]
    angle = np.degrees(np.arctan2(M[1, 0], M[0, 0]))
    return (M, dx, dy, angle)
