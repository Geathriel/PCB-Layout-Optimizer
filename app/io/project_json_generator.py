import json
from pathlib import Path
from typing import Any

from PIL import Image
from shapely import affinity
from shapely.geometry import MultiPolygon, Polygon, box
from shapely.ops import unary_union


SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp"}


def ask_non_empty_string(prompt: str) -> str:
    while True:
        value = input(prompt).strip()
        if value:
            return value
        print("Value cannot be empty.")


def ask_float(prompt: str, min_value: float | None = None) -> float:
    while True:
        raw = input(prompt).strip().replace(",", ".")
        try:
            value = float(raw)
        except ValueError:
            print("Enter a valid number.")
            continue

        if min_value is not None and value < min_value:
            print(f"Value must be >= {min_value}.")
            continue

        return value


def ask_optional_int(prompt: str) -> int | None:
    while True:
        raw = input(prompt).strip().lower()

        if raw in {"", "none", "null", "n"}:
            return None

        try:
            value = int(raw)
        except ValueError:
            print("Enter an integer, or leave empty for unlimited.")
            continue

        if value <= 0:
            print("Quantity must be greater than 0.")
            continue

        return value


def ask_yes_no(prompt: str, default: bool = True) -> bool:
    suffix = "[Y/n]" if default else "[y/N]"
    while True:
        raw = input(f"{prompt} {suffix} ").strip().lower()

        if raw == "":
            return default
        if raw in {"y", "yes", "t", "true", "1"}:
            return True
        if raw in {"n", "no", "f", "false", "0"}:
            return False

        print("Enter yes or no.")


def is_supported_image(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS


def find_content_bbox(image: Image.Image, threshold: int = 245) -> tuple[int, int, int, int] | None:
    rgba = image.convert("RGBA")
    width, height = rgba.size
    pixels = rgba.load()

    min_x = width
    min_y = height
    max_x = -1
    max_y = -1

    for y in range(height):
        for x in range(width):
            r, g, b, a = pixels[x, y]

            if a == 0:
                continue

            brightness = (r + g + b) / 3
            if brightness >= threshold:
                continue

            if x < min_x:
                min_x = x
            if y < min_y:
                min_y = y
            if x > max_x:
                max_x = x
            if y > max_y:
                max_y = y

    if max_x == -1 or max_y == -1:
        return None

    return min_x, min_y, max_x + 1, max_y + 1


def expand_bbox(
    bbox: tuple[int, int, int, int],
    image_size: tuple[int, int],
    margin: int,
) -> tuple[int, int, int, int]:
    min_x, min_y, max_x, max_y = bbox
    width, height = image_size

    min_x = max(0, min_x - margin)
    min_y = max(0, min_y - margin)
    max_x = min(width, max_x + margin)
    max_y = min(height, max_y + margin)

    return min_x, min_y, max_x, max_y


def crop_image_to_content(
    image_path: Path,
    output_dir: Path,
    threshold: int = 245,
    margin: int = 0,
) -> dict[str, Any]:
    with Image.open(image_path) as img:
        img = img.convert("RGBA")
        bbox = find_content_bbox(img, threshold=threshold)

        if bbox is None:
            raise ValueError(f"No non-white content detected in image: {image_path.name}")

        bbox = expand_bbox(bbox, img.size, margin=margin)
        cropped = img.crop(bbox)

        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{image_path.stem}_cropped.png"
        cropped.save(output_path)

        cropped_width, cropped_height = cropped.size

        return {
            "original_path": str(image_path),
            "cropped_path": str(output_path),
            "bbox": {
                "left": bbox[0],
                "top": bbox[1],
                "right": bbox[2],
                "bottom": bbox[3],
            },
            "cropped_pixel_size": {
                "width": cropped_width,
                "height": cropped_height,
            },
        }


def _is_foreground_pixel(r: int, g: int, b: int, a: int, threshold: int) -> bool:
    if a == 0:
        return False
    brightness = (r + g + b) / 3
    return brightness < threshold


def polygon_from_cropped_image(
    cropped_image_path: str | Path,
    threshold: int = 245,
    simplify_tolerance_px: float = 1.0,
) -> list[tuple[float, float]]:
    image_path = Path(cropped_image_path)

    with Image.open(image_path) as img:
        rgba = img.convert("RGBA")
        width, height = rgba.size
        pixels = rgba.load()

        pixel_boxes = []

        for y in range(height):
            for x in range(width):
                r, g, b, a = pixels[x, y]
                if _is_foreground_pixel(r, g, b, a, threshold):
                    # Odwracamy Y, żeby układ był "matematyczny" od lewego dolnego rogu
                    pixel_boxes.append(box(x, height - (y + 1), x + 1, height - y))

        if not pixel_boxes:
            raise ValueError(f"No foreground pixels detected in cropped image: {image_path}")

        merged = unary_union(pixel_boxes)

        if isinstance(merged, MultiPolygon):
            merged = max(merged.geoms, key=lambda g: g.area)

        if not isinstance(merged, Polygon):
            raise ValueError("Could not build a valid polygon from image.")

        if simplify_tolerance_px > 0:
            merged = merged.simplify(simplify_tolerance_px, preserve_topology=True)

        if not merged.is_valid:
            merged = merged.buffer(0)

        if merged.is_empty:
            raise ValueError("Generated polygon is empty.")

        coords = list(merged.exterior.coords[:-1])
        return [(float(x), float(y)) for x, y in coords]


def scale_polygon_points(
    polygon_points_px: list[tuple[float, float]],
    pixel_width: int,
    pixel_height: int,
    real_width: float,
    real_height: float,
) -> list[tuple[float, float]]:
    if pixel_width <= 0 or pixel_height <= 0:
        raise ValueError("Pixel width and height must be > 0.")

    scale_x = real_width / pixel_width
    scale_y = real_height / pixel_height

    poly = Polygon(polygon_points_px)
    if not poly.is_valid:
        poly = poly.buffer(0)

    scaled = affinity.scale(poly, xfact=scale_x, yfact=scale_y, origin=(0, 0))
    min_x, min_y, _, _ = scaled.bounds
    scaled = affinity.translate(scaled, xoff=-min_x, yoff=-min_y)

    coords = list(scaled.exterior.coords[:-1])
    return [(round(float(x), 6), round(float(y), 6)) for x, y in coords]


def collect_project_metadata() -> dict[str, Any]:
    print("\n=== Project settings ===")
    panel_width = ask_float("Panel width: ", min_value=0.000001)
    panel_height = ask_float("Panel height: ", min_value=0.000001)
    spacing = ask_float("Spacing: ", min_value=0.0)

    return {
        "panel": {
            "width": panel_width,
            "height": panel_height,
        },
        "spacing": spacing,
    }


def collect_footprint_metadata(
    source_name: str,
    cropped_pixel_width: int,
    cropped_pixel_height: int,
) -> dict[str, Any]:
    print(f"\n=== Footprint metadata for: {source_name} ===")
    print(f"Cropped image size: {cropped_pixel_width} x {cropped_pixel_height} px")

    footprint_id = ask_non_empty_string("Footprint id: ")
    width = ask_float("Real width: ", min_value=0.000001)
    height = ask_float("Real height: ", min_value=0.000001)
    quantity = ask_optional_int("Quantity (empty/none = unlimited): ")
    allow_rotation = ask_yes_no("Allow rotation?", default=True)

    return {
        "id": footprint_id,
        "width": width,
        "height": height,
        "allow_rotation": allow_rotation,
        "quantity": quantity,
    }


def build_project_data(
    project_meta: dict[str, Any],
    footprint_entries: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "panel": project_meta["panel"],
        "spacing": project_meta["spacing"],
        "footprints": footprint_entries,
    }


def generate_project_json_from_images(
    input_paths: list[str | Path],
    output_json_path: str | Path,
    cropped_output_dir: str | Path = "assets/footprints",
    threshold: int = 245,
    margin: int = 0,
    simplify_tolerance_px: float = 1.0,
    generate_polygon_points: bool = True,
) -> Path:
    image_paths = [Path(p) for p in input_paths]

    if not image_paths:
        raise ValueError("No input images provided.")

    invalid_paths = [p for p in image_paths if not is_supported_image(p)]
    if invalid_paths:
        names = ", ".join(str(p) for p in invalid_paths)
        raise ValueError(f"Unsupported or missing image files: {names}")

    project_meta = collect_project_metadata()
    cropped_dir = Path(cropped_output_dir)

    footprints: list[dict[str, Any]] = []
    used_ids: set[str] = set()

    for image_path in image_paths:
        crop_info = crop_image_to_content(
            image_path=image_path,
            output_dir=cropped_dir,
            threshold=threshold,
            margin=margin,
        )

        footprint = collect_footprint_metadata(
            source_name=image_path.name,
            cropped_pixel_width=crop_info["cropped_pixel_size"]["width"],
            cropped_pixel_height=crop_info["cropped_pixel_size"]["height"],
        )

        if footprint["id"] in used_ids:
            raise ValueError(f"Duplicate footprint id: {footprint['id']}")
        used_ids.add(footprint["id"])

        if generate_polygon_points:
            polygon_px = polygon_from_cropped_image(
                crop_info["cropped_path"],
                threshold=threshold,
                simplify_tolerance_px=simplify_tolerance_px,
            )
            polygon_real = scale_polygon_points(
                polygon_points_px=polygon_px,
                pixel_width=crop_info["cropped_pixel_size"]["width"],
                pixel_height=crop_info["cropped_pixel_size"]["height"],
                real_width=footprint["width"],
                real_height=footprint["height"],
            )
            footprint["polygon_points"] = polygon_real

        footprint["source_image"] = crop_info["original_path"]
        footprint["cropped_image"] = crop_info["cropped_path"]
        footprint["cropped_pixel_width"] = crop_info["cropped_pixel_size"]["width"]
        footprint["cropped_pixel_height"] = crop_info["cropped_pixel_size"]["height"]
        footprint["crop_bbox"] = crop_info["bbox"]

        footprints.append(footprint)

    project_data = build_project_data(project_meta, footprints)

    output_path = Path(output_json_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(project_data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    return output_path


def collect_images_from_directory(directory: str | Path) -> list[Path]:
    directory_path = Path(directory)
    if not directory_path.exists() or not directory_path.is_dir():
        raise ValueError(f"Directory does not exist: {directory_path}")

    images = [
        path for path in sorted(directory_path.iterdir())
        if is_supported_image(path)
    ]

    if not images:
        raise ValueError(f"No supported images found in: {directory_path}")

    return images


def main() -> None:
    print("=== PCB project JSON generator ===")
    mode = ask_non_empty_string(
        "Choose mode: 'dir' for directory, 'files' for manual list: "
    ).lower()

    if mode == "dir":
        directory = ask_non_empty_string("Images directory path: ")
        image_paths = collect_images_from_directory(directory)
    elif mode == "files":
        raw = ask_non_empty_string(
            "Enter image paths separated by commas: "
        )
        image_paths = [Path(part.strip()) for part in raw.split(",") if part.strip()]
    else:
        raise ValueError("Mode must be 'dir' or 'files'.")

    output_json_path = ask_non_empty_string("Output JSON path: ")

    threshold = int(ask_float("Threshold (0-255, default ~245 recommended): ", min_value=0.0))
    margin = int(ask_float("Crop margin in pixels: ", min_value=0.0))
    simplify_tolerance_px = ask_float("Polygon simplify tolerance in px (e.g. 1.0): ", min_value=0.0)
    generate_polygon_points = ask_yes_no("Generate polygon_points from images?", default=True)

    output_path = generate_project_json_from_images(
        input_paths=image_paths,
        output_json_path=output_json_path,
        cropped_output_dir="assets/footprints",
        threshold=threshold,
        margin=margin,
        simplify_tolerance_px=simplify_tolerance_px,
        generate_polygon_points=generate_polygon_points,
    )

    print(f"\nJSON saved to: {output_path}")


if __name__ == "__main__":
    main()