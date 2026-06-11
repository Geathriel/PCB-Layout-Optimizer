from __future__ import annotations

from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass
import os
import random
import time
from typing import Callable

from app.core.geometry import (
    has_required_spacing_between_polygons,
    normalized_footprint_polygon,
    placement_dimensions_from_footprint,
    polygon_fits_in_panel,
    transformed_placement_polygon,
)
from app.models.footprint import Footprint
from app.models.placement import Placement
from app.models.project import Project


MAX_UNLIMITED_ITEMS_PER_FOOTPRINT = 300
RANDOM_ORDER_ATTEMPTS = 16
RANDOM_SEED = 42
COORD_PRECISION = 6
EPSILON = 1e-9
MAX_CANDIDATE_POINTS = 1000
MAX_LOCAL_POLYGON_POINTS_PER_PLACEMENT = 250
DEFAULT_TIME_LIMIT_SECONDS = 60.0


ProgressCallback = Callable[[int, int, int], None]
CancelCallback = Callable[[], bool]


@dataclass(frozen=True, slots=True)
class _Item:
    footprint: Footprint
    instance_index: int


@dataclass(frozen=True, slots=True)
class _PreparedShape:
    footprint: Footprint
    rotated: bool
    rotation_angle: int
    width: float
    height: float
    real_area: float


def _norm(value: float) -> float:
    value = round(value, COORD_PRECISION)
    if abs(value) < 10 ** -COORD_PRECISION:
        return 0.0
    return value


def _rotation_angles(footprint: Footprint) -> list[int]:
    if footprint.allow_rotation:
        return [0, 90, 180, 270]
    return [0]


def _prepared_shapes(footprint: Footprint) -> list[_PreparedShape]:
    shapes: list[_PreparedShape] = []

    for angle in _rotation_angles(footprint):
        width, height = placement_dimensions_from_footprint(
            footprint,
            rotation_angle=angle,
        )
        rotated = angle % 180 != 0

        probe = Placement(
            footprint_id=footprint.id,
            x=0.0,
            y=0.0,
            width=width,
            height=height,
            rotated=rotated,
            rotation_angle=angle,
        )

        real_area = transformed_placement_polygon(footprint, probe).area

        shapes.append(
            _PreparedShape(
                footprint=footprint,
                rotated=rotated,
                rotation_angle=angle,
                width=width,
                height=height,
                real_area=real_area,
            )
        )

    unique: list[_PreparedShape] = []
    seen: set[tuple[float, float, tuple[tuple[float, float], ...]]] = set()

    for shape in shapes:
        poly = normalized_footprint_polygon(
            shape.footprint,
            rotation_angle=shape.rotation_angle,
        )

        coords = tuple(
            (_norm(x), _norm(y))
            for x, y in poly.exterior.coords[:-1]
        )

        key = (_norm(shape.width), _norm(shape.height), coords)

        if key not in seen:
            unique.append(shape)
            seen.add(key)

    return unique


def _build_prepared_shapes_cache(project: Project) -> dict[str, list[_PreparedShape]]:
    return {
        footprint.id: _prepared_shapes(footprint)
        for footprint in project.footprints
    }


def _effective_item_area(footprint: Footprint, spacing: float) -> float:
    width, height = placement_dimensions_from_footprint(
        footprint,
        rotation_angle=0,
    )
    return max((width + spacing) * (height + spacing), EPSILON)


def _estimate_unlimited_quantity(project: Project, footprint: Footprint) -> int:
    estimated = int(project.panel.area / _effective_item_area(footprint, project.spacing)) + 4
    return max(1, min(MAX_UNLIMITED_ITEMS_PER_FOOTPRINT, estimated))


def _expand_items(project: Project) -> list[_Item]:
    items: list[_Item] = []

    for footprint in project.footprints:
        quantity = footprint.quantity
        if quantity is None:
            quantity = _estimate_unlimited_quantity(project, footprint)

        for instance_index in range(quantity):
            items.append(_Item(footprint=footprint, instance_index=instance_index))

    return items


def _shape_sort_key(item: _Item) -> tuple[float, float, float, int, str, int]:
    footprint = item.footprint

    width, height = placement_dimensions_from_footprint(
        footprint,
        rotation_angle=0,
    )

    aspect = max(width, height) / max(min(width, height), EPSILON)
    custom_shape_priority = 1 if footprint.has_custom_shape else 0

    return (
        width * height,
        max(width, height),
        aspect,
        custom_shape_priority,
        footprint.id,
        item.instance_index,
    )


def _order_signature(order: list[_Item]) -> tuple[tuple[str, int], ...]:
    return tuple((item.footprint.id, item.instance_index) for item in order)


def _generate_orders(items: list[_Item]) -> list[list[_Item]]:
    orders: list[list[_Item]] = []
    seen: set[tuple[tuple[str, int], ...]] = set()

    def add_order(order: list[_Item]) -> None:
        signature = _order_signature(order)
        if signature not in seen:
            seen.add(signature)
            orders.append(order)

    add_order(sorted(items, key=_shape_sort_key, reverse=True))
    add_order(sorted(items, key=_shape_sort_key))
    add_order(sorted(items, key=lambda i: max(i.footprint.width, i.footprint.height), reverse=True))
    add_order(sorted(items, key=lambda i: min(i.footprint.width, i.footprint.height), reverse=True))
    add_order(sorted(items, key=lambda i: (i.footprint.has_custom_shape, i.footprint.area), reverse=True))
    add_order(sorted(items, key=lambda i: (i.footprint.quantity is None, i.footprint.area), reverse=True))
    add_order(sorted(items, key=lambda i: (i.footprint.quantity is None, i.footprint.area)))

    rng = random.Random(RANDOM_SEED)
    base = list(items)

    for _ in range(RANDOM_ORDER_ATTEMPTS):
        shuffled = list(base)
        rng.shuffle(shuffled)

        shuffled.sort(
            key=lambda i: _shape_sort_key(i)[0] * rng.uniform(0.75, 1.25),
            reverse=True,
        )

        add_order(shuffled)

    return orders


def _axis_anchors(values: list[float], limit: int = 12) -> list[float]:
    unique = sorted({_norm(v) for v in values})

    if len(unique) <= limit:
        return unique

    sampled = {unique[0], unique[-1]}
    step = (len(unique) - 1) / max(limit - 1, 1)

    for i in range(limit):
        sampled.add(unique[round(i * step)])

    return sorted(sampled)


def _filter_candidate_points(
    raw_points: list[tuple[float, float]],
    shape: _PreparedShape,
    project: Project,
) -> list[tuple[float, float]]:
    margin = project.spacing
    max_x = project.panel.width - margin - shape.width
    max_y = project.panel.height - margin - shape.height

    points: list[tuple[float, float]] = []

    for x, y in raw_points:
        x = _norm(x)
        y = _norm(y)

        if x < margin - EPSILON or y < margin - EPSILON:
            continue

        if x > max_x + EPSILON or y > max_y + EPSILON:
            continue

        points.append((x, y))

    points = sorted(set(points), key=lambda p: (p[1], p[0]))
    return points[:MAX_CANDIDATE_POINTS]


def _candidate_points(
    placements: list[Placement],
    shape: _PreparedShape,
    project: Project,
    footprints_by_id: dict[str, Footprint],
    fast_mode: bool = False,
) -> list[tuple[float, float]]:
    spacing = project.spacing
    margin = project.spacing

    x_values: set[float] = {
        _norm(margin),
        _norm(project.panel.width - margin - shape.width),
    }

    y_values: set[float] = {
        _norm(margin),
        _norm(project.panel.height - margin - shape.height),
    }

    raw_points: list[tuple[float, float]] = []

    for placement in placements:
        x_values.update(
            {
                _norm(placement.x),
                _norm(placement.x2 + spacing),
                _norm(placement.x - shape.width - spacing),
                _norm(placement.x2 - shape.width),
            }
        )

        y_values.update(
            {
                _norm(placement.y),
                _norm(placement.y2 + spacing),
                _norm(placement.y - shape.height - spacing),
                _norm(placement.y2 - shape.height),
            }
        )

    # Szybkie punkty bottom-left / skyline.
    for y in sorted(y_values):
        for x in sorted(x_values):
            raw_points.append((x, y))

    # Fast mode: kończymy tutaj.
    # To jest bardzo ważne, bo ta wersja ma szybko przejść po wszystkich elementach
    # i dać pełny bazowy layout, nawet jeśli nie jest idealny.
    if fast_mode:
        return _filter_candidate_points(raw_points, shape, project)

    has_any_custom_shape = shape.footprint.has_custom_shape or any(
        footprints_by_id[p.footprint_id].has_custom_shape
        for p in placements
    )

    if not has_any_custom_shape:
        return _filter_candidate_points(raw_points, shape, project)

    candidate_poly = normalized_footprint_polygon(
        shape.footprint,
        rotation_angle=shape.rotation_angle,
    )

    c_min_x, c_min_y, c_max_x, c_max_y = candidate_poly.bounds

    candidate_x_anchors = _axis_anchors(
        [c_min_x, c_max_x] + [x for x, _ in candidate_poly.exterior.coords[:-1]],
        limit=6,
    )

    candidate_y_anchors = _axis_anchors(
        [c_min_y, c_max_y] + [y for _, y in candidate_poly.exterior.coords[:-1]],
        limit=6,
    )

    deltas = (-spacing, 0.0, spacing)

    for placement in placements:
        existing_footprint = footprints_by_id[placement.footprint_id]
        existing_poly = transformed_placement_polygon(existing_footprint, placement)

        e_min_x, e_min_y, e_max_x, e_max_y = existing_poly.bounds

        existing_x_anchors = _axis_anchors(
            [e_min_x, e_max_x] + [x for x, _ in existing_poly.exterior.coords[:-1]],
            limit=6,
        )

        existing_y_anchors = _axis_anchors(
            [e_min_y, e_max_y] + [y for _, y in existing_poly.exterior.coords[:-1]],
            limit=6,
        )

        added_for_this_placement = 0

        for ey in existing_y_anchors:
            for cy in candidate_y_anchors:
                for dy in deltas:
                    y = ey - cy + dy

                    for ex in existing_x_anchors:
                        for cx in candidate_x_anchors:
                            for dx in deltas:
                                x = ex - cx + dx
                                raw_points.append((x, y))

                                added_for_this_placement += 1

                                if added_for_this_placement >= MAX_LOCAL_POLYGON_POINTS_PER_PLACEMENT:
                                    break
                            if added_for_this_placement >= MAX_LOCAL_POLYGON_POINTS_PER_PLACEMENT:
                                break
                        if added_for_this_placement >= MAX_LOCAL_POLYGON_POINTS_PER_PLACEMENT:
                            break
                    if added_for_this_placement >= MAX_LOCAL_POLYGON_POINTS_PER_PLACEMENT:
                        break
                if added_for_this_placement >= MAX_LOCAL_POLYGON_POINTS_PER_PLACEMENT:
                    break
            if added_for_this_placement >= MAX_LOCAL_POLYGON_POINTS_PER_PLACEMENT:
                break

    return _filter_candidate_points(raw_points, shape, project)

def _make_placement(shape: _PreparedShape, x: float, y: float) -> Placement:
    return Placement(
        footprint_id=shape.footprint.id,
        x=_norm(x),
        y=_norm(y),
        width=_norm(shape.width),
        height=_norm(shape.height),
        rotated=shape.rotated,
        rotation_angle=shape.rotation_angle,
    )


def _can_place(
    candidate: Placement,
    footprint: Footprint,
    project: Project,
    placements: list[Placement],
    footprints_by_id: dict[str, Footprint],
) -> bool:
    candidate_poly = transformed_placement_polygon(footprint, candidate)

    if not polygon_fits_in_panel(project.panel, candidate_poly, project.spacing):
        return False

    expanded_candidate_bounds = (
        candidate.x - project.spacing,
        candidate.y - project.spacing,
        candidate.x2 + project.spacing,
        candidate.y2 + project.spacing,
    )

    for existing in placements:
        if (
            expanded_candidate_bounds[2] < existing.x - EPSILON
            or expanded_candidate_bounds[0] > existing.x2 + EPSILON
            or expanded_candidate_bounds[3] < existing.y - EPSILON
            or expanded_candidate_bounds[1] > existing.y2 + EPSILON
        ):
            continue

        existing_footprint = footprints_by_id[existing.footprint_id]
        existing_poly = transformed_placement_polygon(existing_footprint, existing)

        if not has_required_spacing_between_polygons(
            candidate_poly,
            existing_poly,
            project.spacing,
        ):
            return False

    return True


def _candidate_score(
    candidate: Placement,
    placements: list[Placement],
) -> tuple[float, float, float, float, float, float]:
    if not placements:
        return (
            candidate.y2,
            candidate.x2,
            candidate.y,
            candidate.x,
            candidate.width * candidate.height,
            0.0,
        )

    min_x = min([p.x for p in placements] + [candidate.x])
    min_y = min([p.y for p in placements] + [candidate.y])
    max_x = max([p.x2 for p in placements] + [candidate.x2])
    max_y = max([p.y2 for p in placements] + [candidate.y2])

    bbox_width = max_x - min_x
    bbox_height = max_y - min_y
    bbox_area = bbox_width * bbox_height

    return (
        max_y,
        bbox_area,
        bbox_height,
        bbox_width,
        candidate.y2,
        candidate.x2,
    )


def _best_candidate_for_item(
    item: _Item,
    project: Project,
    placements: list[Placement],
    footprints_by_id: dict[str, Footprint],
    prepared_shapes_cache: dict[str, list[_PreparedShape]],
    should_cancel: CancelCallback | None = None,
    fast_mode: bool = False,
) -> Placement | None:
    candidates: list[Placement] = []

    shapes = list(prepared_shapes_cache[item.footprint.id])
    shapes.sort(key=lambda s: s.rotation_angle)
    for shape in shapes:
        if should_cancel is not None and should_cancel():
            return None

        points = _candidate_points(
            placements=placements,
            shape=shape,
            project=project,
            footprints_by_id=footprints_by_id,
            fast_mode=fast_mode,
        )

        for x, y in points:
            if should_cancel is not None and should_cancel():
                return None

            candidate = _make_placement(shape, x, y)

            if _can_place(
                candidate=candidate,
                footprint=item.footprint,
                project=project,
                placements=placements,
                footprints_by_id=footprints_by_id,
            ):
                candidates.append(candidate)

                # W fast mode nie zbieramy setek kandydatów.
                # Bierzemy pierwsze kilka sensownych i wybieramy najlepszy.
                if fast_mode and len(candidates) >= 16:
                    break

        if fast_mode and candidates:
            break

    if not candidates:
        return None

    candidates.sort(key=lambda c: _candidate_score(c, placements))
    return candidates[0]

def _pack_order(
    project: Project,
    ordered_items: list[_Item],
    prepared_shapes_cache: dict[str, list[_PreparedShape]],
    deadline: float | None = None,
    should_cancel: CancelCallback | None = None,
    fast_mode: bool = False,
) -> list[Placement]:
    placements: list[Placement] = []
    footprints_by_id = {footprint.id: footprint for footprint in project.footprints}

    def stop_requested() -> bool:
        if should_cancel is not None and should_cancel():
            return True

        if deadline is not None and time.monotonic() >= deadline:
            return True

        return False

    for item in ordered_items:
        # W normal/refinement mode respektujemy timeout.
        # W fast baseline NIE ucinamy pierwszego pełnego przejścia timeoutem,
        # bo chcemy mieć kompletny bazowy layout.
        if not fast_mode and stop_requested():
            break

        candidate = _best_candidate_for_item(
            item=item,
            project=project,
            placements=placements,
            footprints_by_id=footprints_by_id,
            prepared_shapes_cache=prepared_shapes_cache,
            should_cancel=should_cancel,
            fast_mode=fast_mode,
        )

        if candidate is not None:
            placements.append(candidate)

    return placements

def _layout_score(
    project: Project,
    placements: list[Placement],
) -> tuple[int, float, float, float, float]:
    if not placements:
        return (0, 0.0, 0.0, 0.0, 0.0)

    footprints_by_id = {footprint.id: footprint for footprint in project.footprints}

    real_area = 0.0

    for placement in placements:
        real_area += transformed_placement_polygon(
            footprints_by_id[placement.footprint_id],
            placement,
        ).area

    min_x = min(p.x for p in placements)
    min_y = min(p.y for p in placements)
    max_x = max(p.x2 for p in placements)
    max_y = max(p.y2 for p in placements)

    bbox_width = max_x - min_x
    bbox_height = max_y - min_y
    bbox_area = bbox_width * bbox_height

    return (
        len(placements),
        real_area,
        -bbox_area,
        -bbox_height,
        -bbox_width,
    )


def _default_worker_count() -> int:
    cpu_count = os.cpu_count() or 1
    return max(1, min(cpu_count - 1, 24))


def pack_advanced(
    project: Project,
    *,
    workers: int | None = None,
    time_limit_seconds: float | None = DEFAULT_TIME_LIMIT_SECONDS,
    progress_callback: ProgressCallback | None = None,
    should_cancel: CancelCallback | None = None,
) -> list[Placement]:
    items = _expand_items(project)

    if not items:
        return []

    orders = _generate_orders(items)
    prepared_shapes_cache = _build_prepared_shapes_cache(project)

    if workers is None:
        workers = _default_worker_count()

    workers = max(1, workers)

    deadline = None
    if time_limit_seconds is not None and time_limit_seconds > 0:
        deadline = time.monotonic() + time_limit_seconds

    best_layout: list[Placement] = []
    best_score = _layout_score(project, best_layout)

    done = 0
    total = len(orders)

    def cancelled_or_timed_out() -> bool:
        if should_cancel is not None and should_cancel():
            return True

        if deadline is not None and time.monotonic() >= deadline:
            return True

        return False

    first_order = orders[0]

    first_layout = _pack_order(
        project=project,
        ordered_items=first_order,
        prepared_shapes_cache=prepared_shapes_cache,
        deadline=None,
        should_cancel=should_cancel,
        fast_mode=True,
    )

    first_score = _layout_score(project, first_layout)

    if first_score > best_score:
        best_layout = first_layout
        best_score = first_score

    done += 1

    if progress_callback is not None:
        progress_callback(done, total, len(best_layout))

    if cancelled_or_timed_out():
        return best_layout

    remaining_orders = orders[1:]

    if not remaining_orders:
        return best_layout

    if workers == 1:
        for order in remaining_orders:
            if cancelled_or_timed_out():
                break

            layout = _pack_order(
                project=project,
                ordered_items=order,
                prepared_shapes_cache=prepared_shapes_cache,
                deadline=deadline,
                should_cancel=should_cancel,
                fast_mode=False,
            )

            score = _layout_score(project, layout)

            if score > best_score:
                best_layout = layout
                best_score = score

            done += 1

            if progress_callback is not None:
                progress_callback(done, total, len(best_layout))

        return best_layout

    # Nie submitujemy wszystkiego naraz i nie używamy as_completed(),
    # bo as_completed() może blokować, jeśli żaden future nie wróci.
    executor = ThreadPoolExecutor(max_workers=workers)
    pending = set()
    order_index = 0

    try:
        while order_index < len(remaining_orders) and len(pending) < workers:
            order = remaining_orders[order_index]
            order_index += 1

            pending.add(
                executor.submit(
                    _pack_order,
                    project,
                    order,
                    prepared_shapes_cache,
                    deadline,
                    should_cancel,
                    False,
                )
            )

        while pending:
            if cancelled_or_timed_out():
                break

            finished, pending = wait(
                pending,
                timeout=0.25,
                return_when=FIRST_COMPLETED,
            )

            if not finished:
                continue

            for future in finished:
                try:
                    layout = future.result()
                except Exception:
                    done += 1
                    continue

                score = _layout_score(project, layout)

                if score > best_score:
                    best_layout = layout
                    best_score = score

                done += 1

                if progress_callback is not None:
                    progress_callback(done, total, len(best_layout))

            while (
                order_index < len(remaining_orders)
                and len(pending) < workers
                and not cancelled_or_timed_out()
            ):
                order = remaining_orders[order_index]
                order_index += 1

                pending.add(
                    executor.submit(
                        _pack_order,
                        project,
                        order,
                        prepared_shapes_cache,
                        deadline,
                        should_cancel,
                    )
                )

    finally:
        for future in pending:
            future.cancel()

        executor.shutdown(wait=False, cancel_futures=True)

    return best_layout

def pack_naive(project: Project) -> list[Placement]:
    return pack_advanced(project)