"""
情绪视觉映射服务

将 5D 情绪状态（energy, pleasure, activation, longing, security）映射为
前端可渲染的头像边框视觉参数，包括色相、饱和度、亮度、发光强度、
微光类型和情绪标签。

设计理念：
- pleasure 控制色相：负向情绪偏冷蓝，正向情绪偏暖橙
- |pleasure| 控制饱和度：情绪越强烈，颜色越鲜艳
- energy 控制亮度：精力越高越明亮
- activation 控制发光强度：激活度越高，光晕越强
- longing + pleasure 组合决定微光类型
"""


def lerp(start: float, end: float, t: float) -> float:
    """线性插值，t 被限制在 [0, 1] 范围内。"""
    return start + (end - start) * max(0.0, min(1.0, t))


def normalize(value: float, min_val: float, max_val: float) -> float:
    """将 value 从 [min_val, max_val] 归一化到 [0, 1]。"""
    if max_val == min_val:
        return 0.5
    return (value - min_val) / (max_val - min_val)


def classify_mood_label(pleasure: float, energy: float, longing: float) -> str:
    """
    根据 pleasure、energy、longing 组合生成中文情绪标签。

    标签体系：
    - pleasure > 0.5 且 energy > 60 → "心情很好"
    - pleasure > 0.2 → "心情不错"
    - pleasure 在 [-0.2, 0.2] → 根据 longing 细分
    - pleasure < -0.2 → "有点低落"
    - pleasure < -0.5 → "心情不好"
    """
    if pleasure > 0.5 and energy > 60:
        return "心情很好"
    elif pleasure > 0.2:
        return "心情不错"
    elif pleasure > -0.2:
        # 平静区间，根据 longing 细分
        if longing > 0.6:
            return "有点想你"
        elif energy < 30:
            return "有点累"
        return "平静"
    elif pleasure > -0.5:
        return "有点低落"
    else:
        return "心情不好"


def compute_emotion_visual(
    energy: float,
    pleasure: float,
    activation: float,
    longing: float,
    security: float,
) -> dict:
    """
    将 5D 情绪值映射为前端可渲染的视觉参数。

    Args:
        energy: 能量值（0-100）
        pleasure: 愉悦度（-1.0 到 1.0）
        activation: 激活度（-1.0 到 1.0）
        longing: 依恋度（0.0 到 1.0）
        security: 安全感（-1.0 到 1.0）

    Returns:
        dict: 包含以下字段的视觉参数：
            - border_hue (int): 边框色相（0-360）
            - border_saturation (int): 边框饱和度（0-100）
            - border_brightness (int): 边框亮度（0-100）
            - glow_intensity (int): 发光强度（0-100）
            - shimmer_type (str): 微光类型（"purple" | "warm" | "cold" | "none"）
            - mood_label (str): 中文情绪标签
    """
    # 色相: pleasure 从 -1(冷蓝 220°) 到 +1(暖橙 35°)
    hue = lerp(220, 35, normalize(pleasure, -1, 1))

    # 饱和度: |pleasure| 越大越鲜艳，基础 30%，最高 100%
    saturation = lerp(30, 100, abs(pleasure))

    # 亮度: energy 越高越亮，范围 25%-95%
    brightness = lerp(25, 95, energy / 100)

    # 发光强度: activation 从 -1 到 +1 映射为 0-100
    glow = normalize(activation, -1, 1) * 100

    # 微光类型: 由 longing 和 pleasure 共同决定
    if longing > 0.6:
        shimmer = "purple"
    elif pleasure > 0.3:
        shimmer = "warm"
    elif pleasure < -0.3:
        shimmer = "cold"
    else:
        shimmer = "none"

    # 情绪标签（中文）
    mood = classify_mood_label(pleasure, energy, longing)

    return {
        "border_hue": round(hue),
        "border_saturation": round(saturation),
        "border_brightness": round(brightness),
        "glow_intensity": round(glow),
        "shimmer_type": shimmer,
        "mood_label": mood,
    }
