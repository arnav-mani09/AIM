import math

ZONE_LABELS = [
    "restricted_area",
    "paint",
    "mid_range_left",
    "mid_range_right",
    "corner_three_left",
    "corner_three_right",
    "wing_three_left",
    "wing_three_right",
    "top_of_key_three",
]

BASKET = (0.5, 0.11)
R_RESTRICTED = 0.085
LANE_HALF_WIDTH = 0.16
FREE_THROW_Y = 0.404
R_THREE_ARC = 0.50
CORNER_Y_CUTOFF = 0.298
TOP_OF_KEY_HALF_ANGLE_DEG = 20


def classify_zone(x: float, y: float) -> str:
    dx, dy = x - BASKET[0], y - BASKET[1]
    dist = math.hypot(dx, dy)

    if dist <= R_RESTRICTED:
        return "restricted_area"

    in_lane = abs(dx) <= LANE_HALF_WIDTH and y <= FREE_THROW_Y
    if in_lane and dist <= R_THREE_ARC:
        return "paint"

    if dist < R_THREE_ARC:
        return "mid_range_left" if dx < 0 else "mid_range_right"

    if y <= CORNER_Y_CUTOFF and abs(dx) >= (0.5 - 0.06):
        return "corner_three_left" if dx < 0 else "corner_three_right"

    angle = math.degrees(math.atan2(abs(dx), dy)) if dy > 0 else 90
    if angle <= TOP_OF_KEY_HALF_ANGLE_DEG:
        return "top_of_key_three"
    return "wing_three_left" if dx < 0 else "wing_three_right"
