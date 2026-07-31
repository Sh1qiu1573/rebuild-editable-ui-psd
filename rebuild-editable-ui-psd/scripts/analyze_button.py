#!/usr/bin/env python3
"""Estimate button geometry and visible effect bands from a source image and body mask."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image

try:
    import cv2
except ImportError as exc:  # pragma: no cover - environment gate
    raise SystemExit("OpenCV is required: python -m pip install opencv-python-headless") from exc


def load_mask(path: Path, size: tuple[int, int]) -> np.ndarray:
    image = Image.open(path)
    alpha = image.getchannel("A") if "A" in image.getbands() else None
    channel = alpha if alpha is not None and alpha.getextrema()[0] < 255 else image.convert("L")
    if channel.size != size:
        raise SystemExit(f"Mask size {channel.size} does not match image size {size}")
    return np.asarray(channel, dtype=np.uint8) >= 128


def rgb_hex(color: np.ndarray) -> str:
    values = [int(round(value)) for value in color]
    return "#" + "".join(f"{value:02X}" for value in values)


def median_rgb(image: np.ndarray, mask: np.ndarray) -> np.ndarray:
    pixels = image[mask]
    if not len(pixels):
        return np.array([0.0, 0.0, 0.0])
    return np.median(pixels, axis=0)


def luminance(rgb: np.ndarray) -> float:
    return float(0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2])


def ordered_box(points: np.ndarray) -> np.ndarray:
    # Sum/difference ordering selects duplicate points for exact diamonds because
    # the top and left corners can have the same x+y. Polar ordering remains
    # stable for squares, 45-degree diamonds, and width/height-swapped boxes.
    center = points.mean(axis=0)
    angles = np.arctan2(points[:, 1] - center[1], points[:, 0] - center[0])
    return points[np.argsort(angles)].astype(np.float32)


def deskew(mask: np.ndarray, rect, image: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray | None]:
    points = ordered_box(cv2.boxPoints(rect))
    tl, tr, br, bl = points
    width = max(2, int(round(max(np.linalg.norm(br - bl), np.linalg.norm(tr - tl)))))
    height = max(2, int(round(max(np.linalg.norm(tr - br), np.linalg.norm(tl - bl)))))
    destination = np.array([[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]], dtype=np.float32)
    matrix = cv2.getPerspectiveTransform(points, destination)
    warped = cv2.warpPerspective((mask.astype(np.uint8) * 255), matrix, (width, height), flags=cv2.INTER_NEAREST)
    warped_image = cv2.warpPerspective(image, matrix, (width, height), flags=cv2.INTER_LINEAR) if image is not None else None
    if warped.shape[0] > warped.shape[1]:
        warped = np.rot90(warped)
        if warped_image is not None:
            warped_image = np.rot90(warped_image)
    ys, xs = np.nonzero(warped >= 128)
    crop = (slice(ys.min(), ys.max() + 1), slice(xs.min(), xs.max() + 1))
    return warped[crop] >= 128, warped_image[crop] if warped_image is not None else None


def directional_edge_luminance(mask: np.ndarray, image: np.ndarray) -> dict:
    gray = cv2.cvtColor(image.astype(np.uint8), cv2.COLOR_RGB2GRAY).astype(np.float32)
    distance = cv2.distanceTransform(mask.astype(np.uint8), cv2.DIST_L2, 5)
    core = mask & (distance >= max(3.0, min(mask.shape) * 0.15))
    core_value = float(np.median(gray[core])) if np.any(core) else float(np.median(gray[mask]))
    band = mask & (distance > 0) & (distance <= max(2.0, min(mask.shape) * 0.06))
    height, width = mask.shape
    zones = {
        "top": band & (np.indices(mask.shape)[0] < height * 0.35),
        "right": band & (np.indices(mask.shape)[1] > width * 0.65),
        "bottom": band & (np.indices(mask.shape)[0] > height * 0.65),
        "left": band & (np.indices(mask.shape)[1] < width * 0.35),
    }
    values = {name: float(np.median(gray[zone])) if np.any(zone) else core_value for name, zone in zones.items()}
    deltas = {name: value - core_value for name, value in values.items()}
    brightest = max(deltas, key=deltas.get)
    darkest = min(deltas, key=deltas.get)
    angle_by_side = {"right": 0.0, "bottom": 90.0, "left": 180.0, "top": 270.0}
    bevel = deltas[brightest] >= 4.0 and deltas[darkest] <= -4.0
    inner_shadow = deltas[darkest] <= -4.0
    return {
        "core_luminance": round(core_value, 4),
        "side_luminance": {name: round(value, 4) for name, value in values.items()},
        "side_minus_core": {name: round(value, 4) for name, value in deltas.items()},
        "brightest_side": brightest,
        "darkest_side": darkest,
        "light_direction_degrees_clockwise_from_right": angle_by_side[brightest],
        "inner_shadow_present": inner_shadow,
        "bevel_emboss_present": bevel,
        "contrast_span": round(deltas[brightest] - deltas[darkest], 4),
    }


def corner_radii(mask: np.ndarray) -> dict[str, float]:
    height, width = mask.shape
    sample = max(2, min(6, min(width, height) // 10))

    def starts_from_top(left: bool) -> list[int]:
        values = []
        for y in range(min(sample, height)):
            xs = np.flatnonzero(mask[y])
            if len(xs):
                values.append(int(xs.min() if left else width - 1 - xs.max()))
        return values

    def starts_from_side(top: bool, left: bool) -> list[int]:
        values = []
        columns = range(min(sample, width)) if left else range(width - 1, max(-1, width - 1 - sample), -1)
        for x in columns:
            ys = np.flatnonzero(mask[:, x])
            if len(ys):
                values.append(int(ys.min() if top else height - 1 - ys.max()))
        return values

    estimates = {
        "top_left": starts_from_top(True) + starts_from_side(True, True),
        "top_right": starts_from_top(False) + starts_from_side(True, False),
        "bottom_right": [],
        "bottom_left": [],
    }
    for y in range(height - 1, max(-1, height - 1 - sample), -1):
        xs = np.flatnonzero(mask[y])
        if len(xs):
            estimates["bottom_left"].append(int(xs.min()))
            estimates["bottom_right"].append(int(width - 1 - xs.max()))
    estimates["bottom_left"] += starts_from_side(False, True)
    estimates["bottom_right"] += starts_from_side(False, False)
    return {key: round(float(np.median(values)), 2) if values else 0.0 for key, values in estimates.items()}


def rounded_rect_mask(height: int, width: int, radius: int) -> np.ndarray:
    result = np.zeros((height, width), dtype=np.uint8)
    radius = max(0, min(radius, min(height, width) // 2))
    if radius == 0:
        result[:, :] = 1
        return result.astype(bool)
    cv2.rectangle(result, (radius, 0), (width - radius - 1, height - 1), 1, -1)
    cv2.rectangle(result, (0, radius), (width - 1, height - radius - 1), 1, -1)
    for x, y in (
        (radius, radius),
        (width - radius - 1, radius),
        (width - radius - 1, height - radius - 1),
        (radius, height - radius - 1),
    ):
        cv2.circle(result, (x, y), radius, 1, -1)
    return result.astype(bool)


def shape_model(mask: np.ndarray) -> dict:
    """Fit a true rounded rectangle and fail closed on decorative/custom contours."""
    height, width = mask.shape
    max_radius = max(0, min(height, width) // 2)
    best_radius = 0
    best_iou = -1.0
    best_candidate = rounded_rect_mask(height, width, 0)
    for radius in range(max_radius + 1):
        candidate = rounded_rect_mask(height, width, radius)
        union = np.count_nonzero(mask | candidate)
        iou = float(np.count_nonzero(mask & candidate) / max(union, 1))
        if iou > best_iou:
            best_radius, best_iou, best_candidate = radius, iou, candidate

    def contour_edge(value: np.ndarray) -> np.ndarray:
        contours, _ = cv2.findContours(value.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        edge = np.zeros(value.shape, dtype=np.uint8)
        cv2.drawContours(edge, contours, -1, 1, 1)
        return edge.astype(bool)

    actual_edge = contour_edge(mask)
    candidate_edge = contour_edge(best_candidate)
    distance_to_candidate = cv2.distanceTransform((~candidate_edge).astype(np.uint8), cv2.DIST_L2, 5)
    residuals = distance_to_candidate[actual_edge]
    boundary_p95 = float(np.percentile(residuals, 95)) if residuals.size else 0.0
    xor_ratio = float(np.count_nonzero(mask ^ best_candidate) / max(np.count_nonzero(mask), 1))
    regular = best_iou >= 0.985 and boundary_p95 <= 1.5 and xor_ratio <= 0.02
    if regular:
        recommendation = "native-rounded-rectangle"
    elif best_iou >= 0.90 and boundary_p95 <= 6.0:
        recommendation = "custom-vector-path"
    else:
        recommendation = "source-raster-smart-object"
    return {
        "classification": "regular-rounded-rectangle" if regular else "custom-or-irregular-frame",
        "recommended_reconstruction": recommendation,
        "fit_iou": round(best_iou, 6),
        "xor_area_ratio": round(xor_ratio, 6),
        "boundary_residual_p95_px": round(boundary_p95, 4),
        "best_uniform_radius_px": best_radius,
        "native_shape_allowed": regular,
        "thresholds": {"min_iou": 0.985, "max_xor_area_ratio": 0.02, "max_boundary_p95_px": 1.5},
    }


def normalize_rotation(rect) -> float:
    (_, _), (width, height), angle = rect
    if width < height:
        angle += 90.0
    while angle > 90:
        angle -= 180
    while angle <= -90:
        angle += 180
    return round(float(angle), 3)


def texture_metrics(gray: np.ndarray, core: np.ndarray) -> tuple[float, bool, float | None, float]:
    blurred = cv2.GaussianBlur(gray, (0, 0), 2.0)
    residual = gray.astype(np.float32) - blurred.astype(np.float32)
    score = float(np.std(residual[core])) if np.any(core) else 0.0
    gx = cv2.Sobel(residual, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(residual, cv2.CV_32F, 0, 1, ksize=3)
    magnitude = np.hypot(gx, gy)
    valid = core & (magnitude > np.percentile(magnitude[core], 70) if np.any(core) else False)
    if not np.any(valid):
        return round(score, 4), score >= 3.0, None, 0.0
    angles = (np.degrees(np.arctan2(gy[valid], gx[valid])) + 90.0) % 180.0
    weights = magnitude[valid]
    histogram, edges = np.histogram(angles, bins=36, range=(0, 180), weights=weights)
    peak = int(np.argmax(histogram))
    direction = float((edges[peak] + edges[peak + 1]) / 2)
    confidence = float(histogram[peak] / max(histogram.sum(), 1e-6))
    return round(score, 4), score >= 3.0, round(direction, 2), round(confidence, 4)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("image", type=Path)
    parser.add_argument("body_mask", type=Path, help="Mask of the button body, excluding shadow")
    parser.add_argument("--visible-body-mask", type=Path, help="Optional source-visible subset when the complete body is partly occluded")
    parser.add_argument("--content-exclusion-mask", type=Path, help="Optional text/icon mask to exclude from texture sampling")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--max-effect-distance", type=int, default=32)
    args = parser.parse_args()

    source_image = Image.open(args.image).convert("RGB")
    image = np.asarray(source_image, dtype=np.uint8)
    body = load_mask(args.body_mask, source_image.size)
    visible_body = load_mask(args.visible_body_mask, source_image.size) if args.visible_body_mask else body.copy()
    exclusion = load_mask(args.content_exclusion_mask, source_image.size) if args.content_exclusion_mask else np.zeros_like(body)
    if not np.any(body):
        raise SystemExit("Button body mask is empty")
    if np.any(visible_body & ~body):
        raise SystemExit("Visible body mask must be a subset of the complete/amodal body mask")

    contours, _ = cv2.findContours(body.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    contours = sorted(contours, key=cv2.contourArea, reverse=True)
    contour = contours[0]
    rect = cv2.minAreaRect(contour)
    center, dimensions, _ = rect
    deskewed, deskewed_image = deskew(body, rect, image)
    fitted_shape = shape_model(deskewed)
    directional = directional_edge_luminance(deskewed, deskewed_image)

    body_u8 = body.astype(np.uint8)
    distance_in = cv2.distanceTransform(body_u8, cv2.DIST_L2, 5)
    distance_out = cv2.distanceTransform((1 - body_u8), cv2.DIST_L2, 5)
    core_distance = max(3.0, min(dimensions) * 0.08)
    core = body & (distance_in >= core_distance) & ~exclusion
    if not np.any(core):
        core = body & ~exclusion
    inner_band = body & (distance_in > 0) & (distance_in <= max(3.0, core_distance / 2)) & ~exclusion
    far_ring = (~body) & (distance_out >= max(12, args.max_effect_distance // 2)) & (distance_out <= args.max_effect_distance)
    near_ring = (~body) & (distance_out > 0) & (distance_out <= min(4, args.max_effect_distance))

    fill_rgb = median_rgb(image, core)
    inner_rgb = median_rgb(image, inner_band)
    background_rgb = median_rgb(image, far_ring)
    outer_rgb = median_rgb(image, near_ring)
    inner_delta = luminance(inner_rgb) - luminance(fill_rgb)
    outer_color_delta = float(np.linalg.norm(outer_rgb - background_rgb))
    outer_stroke_present = outer_color_delta >= 10.0
    edge_colors_match = float(np.linalg.norm(inner_rgb - outer_rgb)) < 12.0
    inner_glow_present = abs(inner_delta) >= 4.0 and not (outer_stroke_present and edge_colors_match)

    stroke_width = 0.0
    if outer_stroke_present:
        for distance_px in range(1, min(13, args.max_effect_distance + 1)):
            ring = (~body) & (distance_out > distance_px - 1) & (distance_out <= distance_px)
            if not np.any(ring):
                continue
            ring_rgb = median_rgb(image, ring)
            resembles_edge = np.linalg.norm(ring_rgb - outer_rgb) < 25.0
            differs_from_background = np.linalg.norm(ring_rgb - background_rgb) >= 10.0
            if resembles_edge and differs_from_background:
                stroke_width = float(distance_px)
            elif distance_px > 1:
                break

    inner_glow_size = 0.0
    if inner_glow_present:
        for distance_px in range(1, min(17, int(distance_in.max()) + 1)):
            ring = body & (distance_in > distance_px - 1) & (distance_in <= distance_px) & ~exclusion
            if not np.any(ring):
                continue
            if abs(luminance(median_rgb(image, ring)) - luminance(fill_rgb)) >= 4.0:
                inner_glow_size = float(distance_px)

    gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
    texture_score, texture_present, texture_angle, texture_confidence = texture_metrics(gray, core)

    background_luminance = luminance(background_rgb)
    outside = (~body) & (distance_out > max(2.0, stroke_width + 0.5)) & (distance_out <= args.max_effect_distance)
    darkness = np.maximum(background_luminance - gray.astype(np.float32), 0.0) * outside
    shadow_weight = float(darkness.sum())
    if shadow_weight > 0:
        ys, xs = np.indices(body.shape)
        shadow_x = float((xs * darkness).sum() / shadow_weight)
        shadow_y = float((ys * darkness).sum() / shadow_weight)
        dx, dy = shadow_x - center[0], shadow_y - center[1]
        shadow_distance = float(math.hypot(dx, dy))
        shadow_angle = float((math.degrees(math.atan2(dy, dx)) + 360.0) % 360.0)
        shadow_opacity = float(np.clip(darkness[outside].max(initial=0) / max(background_luminance, 1.0), 0, 1))
        shadow_pixels = outside & (darkness >= max(2.0, float(darkness[outside].max(initial=0)) * 0.08))
        shadow_color = rgb_hex(median_rgb(image, shadow_pixels)) if np.any(shadow_pixels) else None
        shadow_extent = float(np.percentile(distance_out[shadow_pixels], 95)) if np.any(shadow_pixels) else 0.0
        dense_shadow = outside & (darkness >= float(darkness[outside].max(initial=0)) * 0.65)
        shadow_spread = float(np.percentile(distance_out[dense_shadow], 95)) if np.any(dense_shadow) else 0.0
        shadow_blur = max(0.0, shadow_extent - shadow_spread)
    else:
        shadow_distance, shadow_angle, shadow_opacity = 0.0, 0.0, 0.0
        shadow_color, shadow_extent, shadow_spread, shadow_blur = None, 0.0, 0.0, 0.0

    significant_components = [cv2.contourArea(item) for item in contours if cv2.contourArea(item) >= cv2.contourArea(contour) * 0.02]
    x, y, width, height = cv2.boundingRect(contour)
    report = {
        "source": str(args.image.resolve()),
        "body_mask": str(args.body_mask.resolve()),
        "bounds": [x, y, x + width, y + height],
        "center": [round(float(center[0]), 3), round(float(center[1]), 3)],
        "oriented_size": [round(float(max(dimensions)), 3), round(float(min(dimensions)), 3)],
        "rotation_angle_degrees": normalize_rotation(rect),
        "orientation_equivalents_degrees": [
            normalize_rotation(rect),
            round(normalize_rotation(rect) + 90.0, 3),
            round(normalize_rotation(rect) - 90.0, 3),
        ],
        "shape_model": fitted_shape,
        "amodal_body": {
            "complete_mask_supplied": bool(args.visible_body_mask),
            "visible_fraction": round(float(np.count_nonzero(visible_body) / max(np.count_nonzero(body), 1)), 6),
            "occluded_fraction": round(float(np.count_nonzero(body & ~visible_body) / max(np.count_nonzero(body), 1)), 6),
        },
        "corner_radius_px": corner_radii(deskewed),
        "fill": {"median_color": rgb_hex(fill_rgb)},
        "outer_shadow": {
            "present": shadow_opacity >= 0.03 and shadow_distance >= 1.0,
            "direction_angle_degrees_clockwise_from_right": round(shadow_angle, 3),
            "distance_px": round(shadow_distance, 3),
            "spread_estimate_px": round(shadow_spread, 3),
            "blur_size_estimate_px": round(shadow_blur, 3),
            "effect_extent_px": round(shadow_extent, 3),
            "color_estimate": shadow_color,
            "opacity_estimate": round(shadow_opacity, 4),
            "size_search_limit_px": args.max_effect_distance,
            "confidence": "low",
        },
        "inner_glow": {
            "present": inner_glow_present,
            "edge_minus_core_luminance": round(inner_delta, 4),
            "edge_color": rgb_hex(inner_rgb),
            "size_estimate_px": round(inner_glow_size, 3),
            "opacity_estimate": round(min(1.0, abs(inner_delta) / 255.0), 4),
            "confidence": "low",
        },
        "inner_shadow": {
            "present": directional["inner_shadow_present"],
            "darkest_side": directional["darkest_side"],
            "direction_angle_estimate_degrees_clockwise_from_right": directional["light_direction_degrees_clockwise_from_right"],
            "edge_contrast_evidence": directional["side_minus_core"],
            "confidence": "low",
        },
        "bevel_emboss": {
            "present": directional["bevel_emboss_present"],
            "light_direction_estimate_degrees_clockwise_from_right": directional["light_direction_degrees_clockwise_from_right"],
            "brightest_side": directional["brightest_side"],
            "darkest_side": directional["darkest_side"],
            "contrast_span": directional["contrast_span"],
            "size_depth_soften": "requires isolated render calibration",
            "confidence": "low",
        },
        "outer_stroke": {
            "present": outer_stroke_present,
            "edge_color": rgb_hex(outer_rgb),
            "color_distance_from_background": round(outer_color_delta, 4),
            "width_estimate_px": round(stroke_width, 3),
            "placement": "unknown",
            "confidence": "low",
        },
        "texture": {
            "present": texture_present,
            "high_frequency_score": texture_score,
            "dominant_angle_degrees": texture_angle,
            "angle_confidence": texture_confidence,
            "content_excluded": bool(args.content_exclusion_mask),
        },
        "warnings": (["Body mask contains multiple significant components"] if len(significant_components) > 1 else [])
        + (["Shape fails strict rounded-rectangle fit; do not replace it with a generic rectangle or chamfered polygon"] if not fitted_shape["native_shape_allowed"] else [])
        + (["No separate visible-body mask supplied; verify that the body mask is complete rather than an occlusion fragment"] if not args.visible_body_mask else [])
        + (["No content exclusion mask supplied; texture evidence may include text/icons/highlights"] if not args.content_exclusion_mask else [])
        + ["Effect estimates require source-background and visual confirmation"],
    }

    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    print(rendered)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
