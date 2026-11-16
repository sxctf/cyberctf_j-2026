import math
from app.config import TOLERANCE, MIN_SIDE


def distance(p1, p2):
    return math.sqrt((p1[0]-p2[0])**2 + (p1[1]-p2[1])**2)


def check_triangle(points):
    if len(points) != 3:
        return False

    d1 = distance(points[0], points[1])
    d2 = distance(points[1], points[2])
    d3 = distance(points[2], points[0])

    sides = [d1, d2, d3]

    spread = max(sides) - min(sides)
    avg = sum(sides) / 3

    # Если надо ослабить, то увеличить до 0.03/0.04
    tolerance = max(TOLERANCE, avg * 0.015)

    return (
        spread < tolerance
        and avg > MIN_SIDE
    )