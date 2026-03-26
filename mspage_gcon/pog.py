from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from datetime import datetime, timezone
import html
import json
import os
from pathlib import Path
import re
import shutil
from typing import Mapping


SLOT_PATTERN = re.compile(r"_(.+?)(?:_v[\d.]+)?$", re.IGNORECASE)
SHORT_LABEL_PATTERN = re.compile(r"([A-Z][0-9]+)", re.IGNORECASE)
POG_DIAGNOSTICS_FILENAME = "diagnostics.json"
POG_STALE_THRESHOLD_MINUTES = 180


@dataclass(frozen=True)
class POGPodConfig:
    id: str
    label: str
    enabled: bool = True


@dataclass(frozen=True)
class POGBoardConfig:
    title: str
    subtitle: str
    pods: list[POGPodConfig]


@dataclass(frozen=True)
class ManagedPogSource:
    id: str
    label: str
    pod_id: str
    source_type: str = "fixture"
    fixture_path: Path | None = None
    folder_id: str | None = None
    folder_scope: str = "SD"
    alias_overrides: dict[str, dict[str, object]] | None = None


@dataclass(frozen=True)
class PlanogramAsset:
    source_id: str
    slot_key: str
    planogram_id: str
    display_name: str
    image_name: str
    report_text: str
    modified_at: datetime
    end_at: datetime | None
    status: str
    groups: list[str]
    image_bytes: bytes | None = None
    image_provenance: str = "fixture"
    list_provenance: str = "fixture"
    list_rows: list[dict[str, str]] | None = None
    alias_crop_boxes: dict[str, tuple[float, float, float, float]] | None = None


@dataclass(frozen=True)
class POGPublishDiagnostics:
    status: str
    last_success_at: datetime | None
    source_mode: str
    details: dict[str, object] | None = None


def extract_slot_key(display_name: str) -> str:
    match = SLOT_PATTERN.search(display_name)
    if not match:
        raise ValueError(f"Unable to extract slot key from {display_name!r}")
    return match.group(1).strip()


def build_slot_short_label(slot_key: str) -> str:
    match = SHORT_LABEL_PATTERN.search(slot_key)
    return match.group(1).upper() if match else slot_key.strip().upper()


def build_slot_aliases(source: ManagedPogSource, slot_key: str) -> list[dict[str, object]]:
    normalized_slot_key = slot_key.strip()
    override = (source.alias_overrides or {}).get(normalized_slot_key, {})
    alias_ids = [str(value).strip().upper() for value in override.get("aliases") or infer_alias_ids(normalized_slot_key)]
    if not alias_ids:
        alias_ids = [build_slot_short_label(normalized_slot_key)]
    select_key = str(override.get("select_id") or infer_select_key(normalized_slot_key, alias_ids)).strip().upper()
    letter_id = str(override.get("letter_id") or select_key[0]).strip().upper()
    shared_group = len(alias_ids) > 1
    shared_group_label = normalized_slot_key.upper() if shared_group else None
    grouped_id = str(
        override.get("group_id")
        or (
            alias_ids[0]
            if override.get("aliases") and len(alias_ids) == 1
            else (alias_ids[0] if len(alias_ids) == 1 and normalized_slot_key.upper() == alias_ids[0] else normalized_slot_key)
        )
    ).strip().upper()
    grouped_label = str(override.get("label") or grouped_id).strip().upper()
    return [
        {
            "id": grouped_id,
            "aliasKey": grouped_id,
            "label": grouped_label,
            "podId": source.pod_id,
            "selectId": select_key,
            "letterId": letter_id,
            "sourceId": source.id,
            "sourceLabel": source.label,
            "sourceSlotKey": normalized_slot_key.upper(),
            "sharedGroup": shared_group,
            "sharedGroupLabel": shared_group_label,
            "aliasIndex": 0,
            "aliasCount": 1,
            "cropBox": None,
            "memberIds": alias_ids,
        }
    ]


def infer_alias_ids(slot_key: str) -> list[str]:
    token_matches = [match.upper() for match in re.findall(r"[A-Z]+\d+", slot_key.strip(), re.IGNORECASE)]
    if len(token_matches) > 1:
        return token_matches

    range_match = re.fullmatch(r"([A-Z]+)(\d+)\s*-\s*(?:([A-Z]+))?(\d+)", slot_key.strip(), re.IGNORECASE)
    if range_match:
        prefix = range_match.group(1).upper()
        end_prefix = (range_match.group(3) or prefix).upper()
        start = int(range_match.group(2))
        end = int(range_match.group(4))
        if prefix == end_prefix and start <= end:
            return [f"{prefix}{number}" for number in range(start, end + 1)]

    short_label = build_slot_short_label(slot_key)
    return [short_label]


def infer_select_key(slot_key: str, alias_ids: list[str]) -> str:
    prefix_match = re.match(r"^([A-Z]+)", slot_key.strip(), re.IGNORECASE)
    if prefix_match:
        return prefix_match.group(1).upper()
    if alias_ids:
        fallback_match = re.match(r"^([A-Z]+)", alias_ids[0], re.IGNORECASE)
        if fallback_match:
            return fallback_match.group(1).upper()
    return build_slot_short_label(slot_key)[:1]


def normalize_crop_box(value: object) -> tuple[float, float, float, float] | None:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return None
    left, top, right, bottom = (float(part) for part in value)
    return (left, top, right, bottom)


def parse_product_report_text(report_text: str) -> list[dict[str, str]]:
    lines = [line.strip() for line in report_text.splitlines() if line.strip()]
    if not lines:
        return []
    headers = [normalize_report_header(part) for part in split_report_line(lines[0])]
    rows: list[dict[str, str]] = []
    for raw_line in lines[1:]:
        values = split_report_line(raw_line)
        if not values:
            continue
        row = {
            header: value
            for header, value in zip(headers, values)
            if header and value
        }
        if row:
            rows.append(row)
    return rows


def build_static_product_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    static_rows: list[dict[str, str]] = []
    for row in rows:
        product = str(
            row.get("product")
            or row.get("productName")
            or row.get("name")
            or ""
        ).strip()
        size_unit_each = str(
            row.get("sizeUnitEach")
            or row.get("size")
            or row.get("sizeDescription")
            or ""
        ).strip()
        case_pack_size = str(
            row.get("casePackSize")
            or row.get("casePack")
            or row.get("caseComment")
            or ""
        ).strip()
        if not any((product, size_unit_each, case_pack_size)):
            continue
        static_rows.append(
            {
                "product": product,
                "sizeUnitEach": size_unit_each,
                "casePackSize": case_pack_size,
            }
        )
    return static_rows


def choose_current_and_pending_assets(
    assets: list[PlanogramAsset],
    *,
    now: datetime,
) -> tuple[PlanogramAsset, PlanogramAsset | None]:
    if not assets:
        raise ValueError("At least one asset is required.")

    sorted_assets = sorted(assets, key=asset_priority_key)
    first_non_expired = next(
        (index for index, asset in enumerate(sorted_assets) if not is_expired(asset, now=now)),
        None,
    )
    current_index = first_non_expired if first_non_expired is not None else len(sorted_assets) - 1
    current = sorted_assets[current_index]
    pending = sorted_assets[current_index + 1] if current_index + 1 < len(sorted_assets) else None
    return current, pending


def build_pog_manifest(
    *,
    board: POGBoardConfig,
    sources: list[ManagedPogSource],
    assets: list[PlanogramAsset],
    generated_at: datetime,
    output_dir: Path,
) -> dict[str, object]:
    source_index = {source.id: source for source in sources}
    grouped_assets: dict[tuple[str, str], list[PlanogramAsset]] = {}
    for asset in assets:
        grouped_assets.setdefault((asset.source_id, asset.slot_key), []).append(asset)

    slot_entries: list[dict[str, object]] = []
    source_ids_by_pod: dict[str, list[str]] = {pod.id: [] for pod in board.pods}
    select_ids_by_source: dict[str, list[str]] = {}
    slot_ids_by_select: dict[str, list[str]] = {}

    for (source_id, slot_key), grouped in sorted(grouped_assets.items(), key=lambda item: slot_sort_key(item[0][1])):
        source = source_index[source_id]
        if source.id not in source_ids_by_pod.setdefault(source.pod_id, []):
            source_ids_by_pod[source.pod_id].append(source.id)
        current, pending = choose_current_and_pending_assets(grouped, now=generated_at)
        for alias in build_slot_aliases(source, slot_key):
            select_key = str(alias["selectId"])
            select_id = build_select_id(source.id, select_key)
            slot_id = build_grouped_slot_id(source.id, str(alias["id"]))
            if select_id not in select_ids_by_source.setdefault(source.id, []):
                select_ids_by_source[source.id].append(select_id)
            slot_ids_by_select.setdefault(select_id, []).append(slot_id)
            slot_entries.append(
                {
                    "id": slot_id,
                    "aliasKey": alias["aliasKey"],
                    "label": alias["label"],
                    "slotKey": slot_key,
                    "sourceSlotKey": alias["sourceSlotKey"],
                    "podId": source.pod_id,
                    "letterId": alias["letterId"],
                    "selectId": select_id,
                    "selectKey": select_key,
                    "sourceId": source.id,
                    "sourceLabel": source.label,
                    "sharedGroup": alias["sharedGroup"],
                    "sharedGroupLabel": alias["sharedGroupLabel"],
                    "title": slot_key,
                    "memberIds": alias["memberIds"],
                    "aliasIndex": alias["aliasIndex"],
                    "aliasCount": alias["aliasCount"],
                    "current": build_asset_payload(current),
                    "pending": build_asset_payload(pending) if pending else None,
                }
            )

    pod_entries: list[dict[str, object]] = []
    for pod in board.pods:
        pod_entries.append(
            {
                "id": pod.id,
                "label": pod.label,
                "enabled": pod.enabled,
                "sourceIds": source_ids_by_pod.get(pod.id) or [],
            }
        )

    source_entries: list[dict[str, object]] = []
    for source in sources:
        source_entries.append(
            {
                "id": source.id,
                "label": source.label,
                "podId": source.pod_id,
                "selectIds": select_ids_by_source.get(source.id) or [],
            }
        )

    select_entries: list[dict[str, object]] = []
    for source in sources:
        for select_id in select_ids_by_source.get(source.id) or []:
            slot_ids = slot_ids_by_select.get(select_id, [])
            select_entries.append(
                {
                    "id": select_id,
                    "label": parse_select_key(select_id),
                    "podId": source.pod_id,
                    "sourceId": source.id,
                    "slotIds": slot_ids,
                }
            )

    default_pod_id = None
    default_source_id = None
    default_select_id = None
    default_slot_id = None
    for pod in pod_entries:
        if pod["enabled"] and pod["sourceIds"]:
            default_pod_id = pod["id"]
            default_source_id = pod["sourceIds"][0]
            matching_source = next((source for source in source_entries if source["id"] == default_source_id), None)
            default_select_id = matching_source["selectIds"][0] if matching_source and matching_source["selectIds"] else None
            matching_select = next((select for select in select_entries if select["id"] == default_select_id), None)
            default_slot_id = matching_select["slotIds"][0] if matching_select and matching_select["slotIds"] else None
            break

    return {
        "board": {
            "title": board.title,
            "subtitle": board.subtitle,
            "generatedAt": isoformat_utc(generated_at),
            "outputDir": output_dir.as_posix(),
            "defaultPodId": default_pod_id,
            "defaultSourceId": default_source_id,
            "defaultSelectId": default_select_id,
            "defaultSlotId": default_slot_id,
        },
        "pods": pod_entries,
        "sources": source_entries,
        "selects": select_entries,
        "slots": slot_entries,
    }


def write_pog_outputs(
    *,
    output_dir: Path,
    manifest: dict[str, object],
    assets: list[PlanogramAsset],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    assets_dir = output_dir / "assets"
    data_dir = output_dir / "data"
    assets_dir.mkdir(parents=True, exist_ok=True)
    if data_dir.exists():
        shutil.rmtree(data_dir)

    assets_by_planogram_id = {asset.planogram_id: asset for asset in assets}
    written_outputs: set[str] = set()
    for slot in manifest.get("slots", []):
        for phase in ("current", "pending"):
            asset_payload = slot.get(phase)
            if not asset_payload:
                continue
            output_key = str(asset_payload["imagePath"])
            if output_key in written_outputs:
                continue
            written_outputs.add(output_key)
            asset = assets_by_planogram_id[str(asset_payload["pogId"])]
            image_path = output_dir / str(asset_payload["imagePath"])
            image_path.parent.mkdir(parents=True, exist_ok=True)
            write_alias_image_file(
                image_path=image_path,
                asset=asset,
                alias_label=str(slot["label"]),
                alias_index=int(slot["aliasIndex"]),
                alias_count=int(slot["aliasCount"]),
                crop_box=asset_payload.get("cropBox"),
            )

    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def load_pog_publish_config(
    path: Path,
    *,
    mode: str = "fixture",
    environment: Mapping[str, str] | None = None,
    load_assets: bool = True,
) -> tuple[POGBoardConfig, list[ManagedPogSource], list[PlanogramAsset]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    board_payload = payload.get("board") or {}
    pod_entries = [
        POGPodConfig(
            id=str(pod["id"]).strip(),
            label=str(pod["label"]).strip(),
            enabled=bool(pod.get("enabled", True)),
        )
        for pod in payload.get("board", {}).get("pods", [])
    ]
    board = POGBoardConfig(
        title=str(board_payload.get("title", "MSP-POG")).strip(),
        subtitle=str(board_payload.get("subtitle", "")).strip(),
        pods=pod_entries,
    )
    base_dir = path.parent
    sources: list[ManagedPogSource] = []
    assets: list[PlanogramAsset] = []

    for source_payload in payload.get("sources", []):
        source = ManagedPogSource(
            id=str(source_payload["id"]).strip(),
            label=str(source_payload["label"]).strip(),
            pod_id=str(source_payload["pod_id"]).strip(),
            source_type=str(source_payload.get("type", "fixture")).strip(),
            fixture_path=(base_dir / str(source_payload["fixture"]).strip()) if source_payload.get("fixture") else None,
            folder_id=str(source_payload.get("folder_id") or "").strip() or None,
            folder_scope=str(source_payload.get("folder_scope") or "SD").strip() or "SD",
            alias_overrides={
                str(key).strip(): value
                for key, value in (source_payload.get("alias_overrides") or {}).items()
            }
            or None,
        )
        sources.append(source)

    assets: list[PlanogramAsset] = []
    if load_assets:
        assets = collect_pog_assets(
            sources=sources,
            mode=mode,
            environment=environment,
        )

    return board, sources, assets


def load_pog_fixture_assets(path: Path, *, default_source_id: str | None = None) -> list[PlanogramAsset]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    items = payload.get("planograms")
    if not isinstance(items, list):
        raise ValueError("POG fixture must contain a 'planograms' list.")
    return [build_planogram_asset(item, default_source_id=default_source_id) for item in items]


def build_asset_payload(
    asset: PlanogramAsset,
) -> dict[str, object]:
    return {
        "pogId": asset.planogram_id,
        "displayName": asset.display_name,
        "imagePath": f"assets/{Path(asset.image_name).name}",
        "endAt": isoformat_utc(asset.end_at) if asset.end_at else None,
        "modifiedAt": isoformat_utc(asset.modified_at),
        "status": asset.status,
        "groups": asset.groups,
        "imageProvenance": asset.image_provenance,
    }


def build_select_id(source_id: str, select_key: str) -> str:
    return f"{source_id}--{slugify(select_key)}"


def build_grouped_slot_id(source_id: str, slot_id: str) -> str:
    return f"{source_id}--{slugify(slot_id)}"


def parse_select_key(select_id: str) -> str:
    return select_id.rsplit("--", 1)[-1].upper()


def slugify(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.strip().lower())
    return normalized.strip("-") or "slot"


def build_asset_svg(asset: PlanogramAsset, *, slot_label: str | None = None) -> str:
    title = html.escape(asset.display_name)
    slot_label = html.escape(slot_label or build_slot_short_label(asset.slot_key))
    groups = html.escape(", ".join(asset.groups) if asset.groups else "No groups")
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="900" viewBox="0 0 1200 900">'
        '<defs><linearGradient id="bg" x1="0%" y1="0%" x2="100%" y2="100%">'
        '<stop offset="0%" stop-color="#0f172a"/><stop offset="100%" stop-color="#1d4ed8"/>'
        "</linearGradient></defs>"
        '<rect width="1200" height="900" fill="url(#bg)"/>'
        '<rect x="52" y="52" width="1096" height="796" rx="36" fill="rgba(255,255,255,0.10)" stroke="rgba(255,255,255,0.22)"/>'
        f'<text x="84" y="122" fill="#bfdbfe" font-family="Avenir Next, Segoe UI, sans-serif" font-size="32">MSP-POG Placeholder</text>'
        f'<text x="84" y="230" fill="#ffffff" font-family="Avenir Next, Segoe UI, sans-serif" font-size="86" font-weight="700">{slot_label}</text>'
        f'<text x="84" y="310" fill="#dbeafe" font-family="Avenir Next, Segoe UI, sans-serif" font-size="30">{title}</text>'
        f'<text x="84" y="384" fill="#bfdbfe" font-family="Avenir Next, Segoe UI, sans-serif" font-size="28">Groups: {groups}</text>'
        f'<text x="84" y="458" fill="#bfdbfe" font-family="Avenir Next, Segoe UI, sans-serif" font-size="28">Status: {html.escape(asset.status)}</text>'
        "</svg>\n"
    )


def build_asset_placeholder_png(asset: PlanogramAsset, *, slot_label: str) -> bytes:
    try:
        from PIL import Image, ImageDraw
    except ImportError as error:
        raise RuntimeError("Pillow is required to build MSP-POG placeholder PNGs.") from error

    image = Image.new("RGB", (1200, 900), "#0f172a")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((52, 52, 1148, 848), radius=36, fill="#1e3a5f", outline="#5fa6d5", width=3)
    draw.text((84, 122), "MSP-POG Placeholder", fill="#bfdbfe")
    draw.text((84, 230), slot_label, fill="#ffffff")
    draw.text((84, 310), asset.display_name, fill="#dbeafe")
    draw.text((84, 384), f"Groups: {', '.join(asset.groups) if asset.groups else 'No groups'}", fill="#bfdbfe")
    draw.text((84, 458), f"Status: {asset.status}", fill="#bfdbfe")
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def write_alias_image_file(
    *,
    image_path: Path,
    asset: PlanogramAsset,
    alias_label: str,
    alias_index: int,
    alias_count: int,
    crop_box: object,
) -> None:
    suffix = image_path.suffix.lower()
    if asset.image_bytes is not None and suffix != ".svg":
        image_path.write_bytes(asset.image_bytes)
        return
    if suffix == ".svg":
        image_path.write_text(build_asset_svg(asset, slot_label=alias_label), encoding="utf-8")
        return
    image_path.write_bytes(build_asset_placeholder_png(asset, slot_label=alias_label))


def render_alias_image_bytes(
    *,
    image_bytes: bytes,
    alias_index: int,
    alias_count: int,
    crop_box: tuple[float, float, float, float] | None,
) -> bytes:
    try:
        from PIL import Image
    except ImportError as error:
        raise RuntimeError("Pillow is required to render MSP-POG alias images.") from error

    with Image.open(BytesIO(image_bytes)) as image:
        rendered = image.convert("RGBA")
        base_left, base_top, base_right, base_bottom = detect_planogram_bounds(rendered)
        if crop_box is not None:
            left = int(base_left + (base_right - base_left) * crop_box[0])
            top = int(base_top + (base_bottom - base_top) * crop_box[1])
            right = int(base_left + (base_right - base_left) * crop_box[2])
            bottom = int(base_top + (base_bottom - base_top) * crop_box[3])
        else:
            left, top, right, bottom = base_left, base_top, base_right, base_bottom
            if alias_count > 1:
                alias_width = max((right - left) / alias_count, 1)
                left = int(round(base_left + alias_width * alias_index))
                right = int(round(base_left + alias_width * (alias_index + 1)))
        cropped = rendered.crop((left, top, max(right, left + 1), max(bottom, top + 1)))
        buffer = BytesIO()
        cropped.save(buffer, format="PNG")
        return buffer.getvalue()


def detect_planogram_bounds(image) -> tuple[int, int, int, int]:
    rgb_image = image.convert("RGB")
    width, height = rgb_image.size
    sample_x = min(max(width // 10, 0), width - 1)
    sample_y = min(max(height // 10, 0), height - 1)
    background = rgb_image.getpixel((sample_x, sample_y))
    top_margin = min(80, max(height // 10, 1))
    bottom_margin = min(60, max(height // 10, 1))
    left_margin = min(90, max(width // 10, 1))

    xs: list[int] = []
    ys: list[int] = []
    for y in range(top_margin, max(height - bottom_margin, top_margin + 1)):
        for x in range(left_margin, width):
            pixel = rgb_image.getpixel((x, y))
            if color_distance(pixel, background) > 18:
                xs.append(x)
                ys.append(y)
    if not xs or not ys:
        return (0, 0, width, height)
    return (min(xs), min(ys), max(xs) + 1, max(ys) + 1)


def color_distance(left: tuple[int, int, int], right: tuple[int, int, int]) -> int:
    return sum(abs(int(a) - int(b)) for a, b in zip(left, right))


def split_report_line(line: str) -> list[str]:
    delimiter = "|" if "|" in line else "\t"
    return [part.strip() for part in line.split(delimiter)]


def normalize_report_header(header: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", " ", header.strip().lower()).strip()
    mapping = {
        "product name": "productName",
        "upc": "upc",
        "size": "size",
        "sku": "sku",
        "brand": "brand",
    }
    return mapping.get(normalized, "".join(word.capitalize() if index else word for index, word in enumerate(normalized.split())))


def asset_priority_key(asset: PlanogramAsset) -> tuple[datetime, datetime]:
    end_at = asset.end_at or datetime.max.replace(tzinfo=timezone.utc)
    return (end_at, asset.modified_at)


def is_expired(asset: PlanogramAsset, *, now: datetime) -> bool:
    return bool(asset.end_at and asset.end_at <= now)


def slot_sort_key(slot_key: str) -> tuple[str, int, str]:
    match = SHORT_LABEL_PATTERN.search(slot_key)
    if not match:
        return (slot_key.upper(), 0, slot_key.upper())
    letter = match.group(1)[0].upper()
    number = int(match.group(1)[1:])
    return (letter, number, slot_key.upper())


def isoformat_utc(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def build_planogram_asset(payload: dict[str, object], *, default_source_id: str | None = None) -> PlanogramAsset:
    display_name = str(payload.get("display_name") or payload.get("name") or "").strip()
    if not display_name:
        raise ValueError("Planogram fixture item requires display_name.")
    planogram_id = str(payload.get("planogram_id") or payload.get("pog_id") or "").strip()
    if not planogram_id:
        raise ValueError(f"Planogram fixture item {display_name!r} requires planogram_id.")
    source_id = str(payload.get("source_id") or default_source_id or "fixture").strip()
    if not source_id:
        raise ValueError(f"Planogram fixture item {display_name!r} requires source_id.")

    groups = payload.get("groups") or []
    return PlanogramAsset(
        source_id=source_id,
        slot_key=str(payload.get("slot_key") or extract_slot_key(display_name)).strip(),
        planogram_id=planogram_id,
        display_name=display_name,
        image_name=str(payload.get("image_name") or f"{planogram_id}.png").strip(),
        report_text=str(payload.get("report_text") or "").strip(),
        modified_at=parse_datetime(payload.get("modified_at")),
        end_at=parse_datetime(payload.get("end_at"), allow_none=True),
        status=str(payload.get("status") or "Active").strip(),
        groups=[str(group).strip() for group in groups if str(group).strip()],
        list_rows=build_static_product_rows(
            [
                {
                    key: str(value).strip()
                    for key, value in row.items()
                    if str(value).strip()
                }
                for row in payload.get("list_rows") or []
            ]
        )
        if payload.get("list_rows")
        else None,
    )


def parse_datetime(value: object, *, allow_none: bool = False) -> datetime | None:
    if value in (None, ""):
        if allow_none:
            return None
        raise ValueError("Datetime value is required.")
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    return datetime.fromisoformat(text)


def resolve_pog_publish_mode(
    *,
    requested_mode: str,
    sources: list[ManagedPogSource],
    environment: Mapping[str, str] | None = None,
) -> str:
    normalized = requested_mode.strip().lower()
    if normalized not in {"auto", "fixture", "live"}:
        raise ValueError(f"Unsupported POG publish mode: {requested_mode}")
    if normalized != "auto":
        return normalized
    if any(source.source_type == "nexgen" for source in sources) and has_live_pog_credentials(environment):
        return "live"
    return "fixture"


def has_live_pog_credentials(environment: Mapping[str, str] | None = None) -> bool:
    env = environment or os.environ
    return bool(env.get("NEXGENPOG_USERNAME") and env.get("NEXGENPOG_PASSWORD"))


def collect_pog_assets(
    *,
    sources: list[ManagedPogSource],
    mode: str,
    environment: Mapping[str, str] | None = None,
    live_fetcher=None,
) -> list[PlanogramAsset]:
    normalized_mode = mode.strip().lower()
    if normalized_mode == "fixture":
        return collect_fixture_pog_assets(sources)
    if normalized_mode != "live":
        raise ValueError(f"Unsupported POG asset collection mode: {mode}")

    live_sources = [source for source in sources if source.source_type == "nexgen"]
    if not live_sources:
        raise ValueError("Live POG mode requires at least one Nexgen source.")
    fetcher = live_fetcher or build_default_live_pog_fetcher(environment)
    assets: list[PlanogramAsset] = []
    for source in live_sources:
        assets.extend(fetcher(source))
    return assets


def collect_fixture_pog_assets(sources: list[ManagedPogSource]) -> list[PlanogramAsset]:
    assets: list[PlanogramAsset] = []
    for source in sources:
        if source.fixture_path is None:
            if source.source_type == "fixture":
                raise ValueError(f"Fixture source {source.id} is missing fixture_path.")
            continue
        assets.extend(load_pog_fixture_assets(source.fixture_path, default_source_id=source.id))
    return assets


def build_default_live_pog_fetcher(environment: Mapping[str, str] | None = None):
    from .pog_live import NexgenPogLiveFetcher

    return NexgenPogLiveFetcher.from_environment(environment).fetch_source_assets


def build_pog_publish_diagnostics(
    *,
    status: str,
    last_success_at: datetime | None,
    source_mode: str,
    details: dict[str, object] | None = None,
) -> POGPublishDiagnostics:
    return POGPublishDiagnostics(
        status=status,
        last_success_at=last_success_at,
        source_mode=source_mode,
        details=details,
    )


def build_pog_diagnostics_payload(diagnostics: POGPublishDiagnostics) -> dict[str, object | None]:
    payload: dict[str, object | None] = {
        "status": diagnostics.status,
        "lastSuccessAt": isoformat_utc(diagnostics.last_success_at) if diagnostics.last_success_at else None,
        "sourceMode": diagnostics.source_mode,
        "staleAfterMinutes": POG_STALE_THRESHOLD_MINUTES,
    }
    if diagnostics.details:
        payload.update(diagnostics.details)
    return payload


def write_pog_diagnostics(output_dir: Path, diagnostics: POGPublishDiagnostics) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = build_pog_diagnostics_payload(diagnostics)
    (output_dir / POG_DIAGNOSTICS_FILENAME).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def read_pog_last_success_at(output_dir: Path) -> datetime | None:
    diagnostics = _read_pog_diagnostics(output_dir / POG_DIAGNOSTICS_FILENAME)
    if diagnostics and diagnostics.last_success_at:
        return diagnostics.last_success_at
    manifest_path = output_dir / "manifest.json"
    if not manifest_path.exists():
        return None
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    generated_at = payload.get("board", {}).get("generatedAt")
    return parse_datetime(generated_at, allow_none=True)


def has_last_good_pog_publish(output_dir: Path) -> bool:
    return (output_dir / "manifest.json").exists()


def write_pog_failure_diagnostics(
    output_dir: Path,
    *,
    attempted_at: datetime,
    source_mode: str,
    details: dict[str, object] | None = None,
) -> POGPublishDiagnostics:
    last_success_at = read_pog_last_success_at(output_dir)
    diagnostics = build_pog_publish_diagnostics(
        status=_pog_failure_status(attempted_at=attempted_at, last_success_at=last_success_at),
        last_success_at=last_success_at,
        source_mode=source_mode,
        details=details,
    )
    write_pog_diagnostics(output_dir, diagnostics)
    return diagnostics


def _pog_failure_status(*, attempted_at: datetime, last_success_at: datetime | None) -> str:
    if last_success_at is None:
        return "stale"
    delta_seconds = attempted_at.astimezone(timezone.utc).timestamp() - last_success_at.astimezone(timezone.utc).timestamp()
    if delta_seconds > POG_STALE_THRESHOLD_MINUTES * 60:
        return "stale"
    return "degraded"


def _read_pog_diagnostics(path: Path) -> POGPublishDiagnostics | None:
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return POGPublishDiagnostics(
        status=str(payload.get("status") or "unknown"),
        last_success_at=parse_datetime(payload.get("lastSuccessAt"), allow_none=True),
        source_mode=str(payload.get("sourceMode") or "unknown"),
        details=payload,
    )
