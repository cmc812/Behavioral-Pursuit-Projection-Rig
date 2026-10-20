# utils.py
import numpy as np

# def interpolate_points(points, speed_cm_s=5, sampling_rate_hz=30):
#     interpolated = []
#     dist_per_sample = speed_cm_s / sampling_rate_hz
#     for i in range(len(points)-1):
#         x1, y1 = points[i]
#         x2, y2 = points[i+1]
#         dx, dy = x2 - x1, y2 - y1
#         distance = (dx**2 + dy**2)**0.5
#         steps = max(int(distance / dist_per_sample), 1)
#         for step in range(steps):
#             fraction = step / steps
#             new_x = x1 + fraction * dx
#             new_y = y1 + fraction * dy
#             interpolated.append((new_x, new_y))
#     interpolated.append(points[-1])
#     return interpolated

def rdp(points, epsilon):
    """
    Simplifies a list of points using the Ramer-Douglas-Peucker algorithm.
    """
    if len(points) < 3:
        return points

    # Find the point with the max distance
    start, end = points[0], points[-1]
    max_dist = 0
    index = 0
    for i in range(1, len(points) - 1):
        dist = perpendicular_distance(points[i], start, end)
        if dist > max_dist:
            index = i
            max_dist = dist

    # If max distance is greater than epsilon, recursively simplify
    if max_dist > epsilon:
        first_half = rdp(points[:index + 1], epsilon)
        second_half = rdp(points[index:], epsilon)
        return first_half[:-1] + second_half
    else:
        return [start, end]

def perpendicular_distance(point, start, end):
    x, y = point
    x1, y1 = start
    x2, y2 = end

    if x1 == x2 and y1 == y2:
        return ((x - x1)**2 + (y - y1)**2)**0.5

    num = abs((y2 - y1)*x - (x2 - x1)*y + x2*y1 - y2*x1)
    den = ((y2 - y1)**2 + (x2 - x1)**2)**0.5
    return num / den
