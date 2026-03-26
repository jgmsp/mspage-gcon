from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import math
import re
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .pog import ManagedPogSource, PlanogramAsset, build_slot_aliases, extract_slot_key, parse_datetime


DEFAULT_NEXGEN_BASE_URL = "https://app.nexgenpog.com"


@dataclass(frozen=True)
class NexgenCredentials:
    username: str
    password: str
    base_url: str = DEFAULT_NEXGEN_BASE_URL
    headless: bool = True
    timeout_ms: int = 30_000


class NexgenPogLiveFetcher:
    def __init__(self, credentials: NexgenCredentials) -> None:
        self.credentials = credentials

    @classmethod
    def from_environment(cls, environment=None) -> "NexgenPogLiveFetcher":
        env = environment or {}
        username = env.get("NEXGENPOG_USERNAME")
        password = env.get("NEXGENPOG_PASSWORD")
        if not username or not password:
            raise RuntimeError("Missing required Nexgen credentials.")
        base_url = env.get("NEXGENPOG_BASE_URL") or DEFAULT_NEXGEN_BASE_URL
        headless = str(env.get("NEXGENPOG_HEADLESS", "true")).strip().lower() != "false"
        timeout_ms = int(env.get("NEXGENPOG_TIMEOUT_MS", "30000"))
        return cls(
            NexgenCredentials(
                username=username,
                password=password,
                base_url=base_url.rstrip("/"),
                headless=headless,
                timeout_ms=timeout_ms,
            )
        )

    def fetch_source_assets(self, source: ManagedPogSource) -> list[PlanogramAsset]:
        try:
            from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
            from playwright.sync_api import sync_playwright
        except ImportError as error:
            raise RuntimeError(
                "Live Nexgen ingest requires the Python Playwright package. "
                "Install it before running live MSP-POG publishing."
            ) from error

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=self.credentials.headless)
            context = browser.new_context(accept_downloads=True)
            page = context.new_page()
            page.set_default_timeout(self.credentials.timeout_ms)
            try:
                self._login_and_open_source(page, source, playwright_timeout_error=PlaywrightTimeoutError)
                rows = self._enumerate_rows(page)
                assets = [self._build_asset_from_row(page, row, source, PlaywrightTimeoutError) for row in rows]
                return [asset for asset in assets if asset is not None]
            finally:
                context.close()
                browser.close()

    def _login_and_open_source(self, page, source: ManagedPogSource, *, playwright_timeout_error) -> None:
        page.goto(self._source_url(source), wait_until="domcontentloaded")
        if "/idm/Login" not in page.url and "/vc/Login/" not in page.url:
            return

        username_box = page.locator('input[type="text"], input[type="email"]').first
        username_box.fill(self.credentials.username)
        next_button = page.get_by_role("link", name="Next")
        if next_button.count():
            next_button.click()
        else:
            page.get_by_role("button", name="Next").click()

        password_box = page.locator('input[type="password"]').first
        password_box.fill(self.credentials.password)
        submit_button = page.get_by_role("link", name="Submit")
        if submit_button.count():
            submit_button.click()
        else:
            page.get_by_role("button", name="Submit").click()

        try:
            page.wait_for_url("**/vc/PlanogramList**", timeout=self.credentials.timeout_ms)
        except playwright_timeout_error:
            page.goto(self._source_url(source), wait_until="domcontentloaded")
            page.wait_for_url("**/vc/PlanogramList**", timeout=self.credentials.timeout_ms)

    def _source_url(self, source: ManagedPogSource) -> str:
        if not source.folder_id:
            raise ValueError(f"Nexgen source {source.id} is missing folder_id.")
        return f"{self.credentials.base_url}/vc/PlanogramList?p={source.folder_id}&p1={source.folder_scope}"

    def _enumerate_rows(self, page) -> list[dict[str, str]]:
        page.wait_for_selector(
            "tr.k-master-row td a.ItemName",
            state="visible",
            timeout=self.credentials.timeout_ms,
        )
        data = page.evaluate(
            """
            () => Array.from(document.querySelectorAll('tr.k-master-row')).map((row) => {
              const anchor = row.querySelector('a.ItemName');
              if (!anchor) {
                return null;
              }
              const cells = Array.from(row.querySelectorAll('td')).map((td) => td.innerText.trim().replace(/\\s+/g, ' '));
              return {
                display_name: anchor.textContent.trim(),
                gateway_url: anchor.href,
                internal_id: cells[2] || '',
                gateway_key: cells[3] || '',
                modified_by: cells[7] || '',
                modified_at: cells[8] || '',
                shared_by: cells[10] || '',
                status: cells[11] || '',
                start_at: cells[12] || '',
                end_at: cells[13] || '',
                groups: cells[14] || ''
              };
            }).filter(Boolean)
            """
        )
        return [row for row in data if row.get("display_name")]

    def _build_asset_from_row(self, page, row: dict[str, str], source: ManagedPogSource, playwright_timeout_error):
        display_name = row["display_name"].strip()
        gateway_url = row.get("gateway_url") or ""
        if "/vc/AuthGateway/Gateway" not in gateway_url:
            return None
        try:
            slot_key = extract_slot_key(display_name)
        except ValueError:
            return None
        if row.get("status") and row["status"].strip().lower() not in {"active", ""}:
            return None

        page.goto(gateway_url, wait_until="domcontentloaded")
        page.wait_for_load_state("networkidle", timeout=self.credentials.timeout_ms)
        image_bytes, image_name, image_provenance = self._export_image(
            page,
            row=row,
            playwright_timeout_error=playwright_timeout_error,
        )

        planogram_id = row.get("internal_id") or row.get("gateway_key") or self._extract_gateway_id(gateway_url)
        return PlanogramAsset(
            source_id=source.id,
            slot_key=slot_key,
            planogram_id=planogram_id,
            display_name=display_name,
            image_name=image_name,
            report_text="",
            modified_at=self._parse_nexgen_date(row.get("modified_at")) or datetime.now(timezone.utc),
            end_at=self._parse_nexgen_date(row.get("end_at"), allow_none=True),
            status=row.get("status") or "Active",
            groups=[group.strip() for group in (row.get("groups") or "").split(",") if group.strip()],
            image_bytes=image_bytes,
            image_provenance=image_provenance,
            list_provenance="unused",
            list_rows=None,
        )

    def _open_planogram_and_capture_product_rows(self, page, *, row: dict[str, str], playwright_timeout_error):
        with page.expect_response(
            lambda response: "/webapi/api/ProductBin/" in response.url,
            timeout=self.credentials.timeout_ms,
        ) as response_info:
            page.goto(row["gateway_url"], wait_until="domcontentloaded")
        page.wait_for_load_state("networkidle", timeout=self.credentials.timeout_ms)
        try:
            payload = response_info.value.json()
        except Exception as error:
            raise ValueError(f"Unable to read ProductBin response for {row['display_name']}: {error}") from error
        return self._normalize_productbin_rows(payload), "nexgen-productbin"

    def _extract_gateway_id(self, url: str) -> str:
        parsed = urlparse(url)
        query = parse_qs(parsed.query)
        return query.get("p", ["unknown-planogram"])[0]

    def _export_image(self, page, *, row: dict[str, str], playwright_timeout_error):
        planogram_id = row.get("internal_id") or row.get("gateway_key") or "planogram"
        try:
            with page.expect_download(timeout=5_000) as download_info:
                page.get_by_text("Image", exact=True).click()
            download = download_info.value
            download_path = download.path()
            if download_path:
                data = Path(download_path).read_bytes()
                suffix = Path(download.suggested_filename or "").suffix or ".png"
                return data, f"{planogram_id}{suffix}", "nexgen-native-image"
        except playwright_timeout_error:
            pass
        except Exception:
            pass

        self._dismiss_active_dialogs(page)
        clip = self._planogram_image_clip(page)
        screenshot_bytes = page.screenshot(type="png", clip=clip) if clip else page.screenshot(full_page=True, type="png")
        return screenshot_bytes, f"{planogram_id}.png", "nexgen-screenshot-fallback"

    def _planogram_image_clip(self, page) -> dict[str, float] | None:
        try:
            clip = page.evaluate(
                """
                () => {
                  const elements = Array.from(document.querySelectorAll('.planogramShelf, .product-image'));
                  const boxes = elements
                    .map((element) => element.getBoundingClientRect())
                    .filter((rect) => rect.width > 0 && rect.height > 0);
                  if (!boxes.length) {
                    return null;
                  }
                  const minX = Math.min(...boxes.map((rect) => rect.x));
                  const minY = Math.min(...boxes.map((rect) => rect.y));
                  const maxX = Math.max(...boxes.map((rect) => rect.x + rect.width));
                  const maxY = Math.max(...boxes.map((rect) => rect.y + rect.height));
                  return { x: minX, y: minY, width: maxX - minX, height: maxY - minY };
                }
                """
            )
        except Exception:
            return None
        if not isinstance(clip, dict):
            return None
        try:
            x = max(float(clip["x"]) - 8.0, 0.0)
            y = max(float(clip["y"]) - 8.0, 0.0)
            width = max(float(clip["width"]) + 16.0, 1.0)
            height = max(float(clip["height"]) + 16.0, 1.0)
        except (KeyError, TypeError, ValueError):
            return None
        return {
            "x": math.floor(x),
            "y": math.floor(y),
            "width": math.ceil(width),
            "height": math.ceil(height),
        }

    def _planogram_alias_crop_boxes(self, page, alias_ids: list[str]) -> dict[str, tuple[float, float, float, float]]:
        if len(alias_ids) <= 1:
            return {}
        base_clip = self._planogram_image_clip(page)
        if not base_clip:
            return {}
        layout = self._planogram_layout(page)
        shelves = layout.get("shelves") or []
        products = layout.get("products") or []
        if not products:
            return {}

        crop_boxes: dict[str, tuple[float, float, float, float]] = {}
        band_width = float(base_clip["width"]) / len(alias_ids)
        for index, alias_id in enumerate(alias_ids):
            band_left = float(base_clip["x"]) + band_width * index
            band_right = float(base_clip["x"]) + band_width * (index + 1)
            band_products = [
                rect for rect in products
                if band_left <= rect["x"] + rect["width"] / 2.0 < band_right
            ]
            if not band_products:
                continue
            product_bounds = self._union_rects(band_products)
            expanded_product_bounds = self._pad_rect(product_bounds, x_pad=18.0, y_pad=18.0)
            band_shelves = [
                rect
                for rect in shelves
                if band_left <= rect["x"] + rect["width"] / 2.0 < band_right
                and self._rects_overlap_vertically(rect, expanded_product_bounds, margin=24.0)
            ]
            vertical_bounds = self._union_rects(band_products + band_shelves) if band_shelves else product_bounds
            crop_bounds = {
                "x": product_bounds["x"] - 12.0,
                "y": vertical_bounds["y"] - 8.0,
                "width": product_bounds["width"] + 24.0,
                "height": vertical_bounds["height"] + 16.0,
            }
            crop_boxes[alias_id] = self._relative_crop_box(base_clip, crop_bounds)
        return crop_boxes

    def _planogram_layout(self, page) -> dict[str, list[dict[str, float]]]:
        try:
            layout = page.evaluate(
                """
                () => ({
                  shelves: Array.from(document.querySelectorAll('.planogramShelf')).map((element) => {
                    const rect = element.getBoundingClientRect();
                    return { x: rect.x, y: rect.y, width: rect.width, height: rect.height };
                  }).filter((rect) => rect.width > 0 && rect.height > 0),
                  products: Array.from(document.querySelectorAll('.product-image')).map((element) => {
                    const rect = element.getBoundingClientRect();
                    return { x: rect.x, y: rect.y, width: rect.width, height: rect.height };
                  }).filter((rect) => rect.width > 0 && rect.height > 0),
                })
                """
            )
        except Exception:
            return {"shelves": [], "products": []}
        if not isinstance(layout, dict):
            return {"shelves": [], "products": []}
        return {
            "shelves": self._normalize_rects(layout.get("shelves")),
            "products": self._normalize_rects(layout.get("products")),
        }

    def _normalize_rects(self, values) -> list[dict[str, float]]:
        rects: list[dict[str, float]] = []
        if not isinstance(values, list):
            return rects
        for value in values:
            if not isinstance(value, dict):
                continue
            try:
                rect = {
                    "x": float(value["x"]),
                    "y": float(value["y"]),
                    "width": float(value["width"]),
                    "height": float(value["height"]),
                }
            except (KeyError, TypeError, ValueError):
                continue
            if rect["width"] <= 0 or rect["height"] <= 0:
                continue
            rects.append(rect)
        return rects

    def _union_rects(self, rects: list[dict[str, float]]) -> dict[str, float]:
        min_x = min(rect["x"] for rect in rects)
        min_y = min(rect["y"] for rect in rects)
        max_x = max(rect["x"] + rect["width"] for rect in rects)
        max_y = max(rect["y"] + rect["height"] for rect in rects)
        return {
            "x": min_x,
            "y": min_y,
            "width": max_x - min_x,
            "height": max_y - min_y,
        }

    def _pad_rect(self, rect: dict[str, float], *, x_pad: float, y_pad: float) -> dict[str, float]:
        return {
            "x": rect["x"] - x_pad,
            "y": rect["y"] - y_pad,
            "width": rect["width"] + x_pad * 2.0,
            "height": rect["height"] + y_pad * 2.0,
        }

    def _rects_overlap_vertically(self, rect: dict[str, float], other: dict[str, float], *, margin: float) -> bool:
        rect_top = rect["y"] - margin
        rect_bottom = rect["y"] + rect["height"] + margin
        other_top = other["y"]
        other_bottom = other["y"] + other["height"]
        return rect_bottom >= other_top and other_bottom >= rect_top

    def _relative_crop_box(
        self,
        base_clip: dict[str, float],
        crop_bounds: dict[str, float],
    ) -> tuple[float, float, float, float]:
        base_left = float(base_clip["x"])
        base_top = float(base_clip["y"])
        base_right = base_left + float(base_clip["width"])
        base_bottom = base_top + float(base_clip["height"])
        left = min(max(crop_bounds["x"], base_left), base_right)
        top = min(max(crop_bounds["y"], base_top), base_bottom)
        right = min(max(crop_bounds["x"] + crop_bounds["width"], base_left), base_right)
        bottom = min(max(crop_bounds["y"] + crop_bounds["height"], base_top), base_bottom)
        if right <= left:
            right = min(base_right, left + 1.0)
        if bottom <= top:
            bottom = min(base_bottom, top + 1.0)
        width = max(base_right - base_left, 1.0)
        height = max(base_bottom - base_top, 1.0)
        return (
            round((left - base_left) / width, 6),
            round((top - base_top) / height, 6),
            round((right - base_left) / width, 6),
            round((bottom - base_top) / height, 6),
        )

    def _normalize_productbin_rows(self, payload: object) -> list[dict[str, str]]:
        if not isinstance(payload, list):
            raise ValueError("Expected ProductBin payload to be a list.")
        normalized_rows: list[dict[str, str]] = []
        seen_product_ids: set[str] = set()
        for item in payload:
            if not isinstance(item, dict):
                continue
            product_id = str(item.get("productID") or item.get("productUID") or item.get("uid") or "").strip()
            name = str(item.get("name") or "").strip()
            if not product_id or not name or product_id in seen_product_ids:
                continue
            seen_product_ids.add(product_id)
            size_unit_each = self._extract_size_unit_each(item, product_name=name)
            case_pack_size = str(item.get("caseComment") or "").strip()
            normalized_rows.append(
                {
                    "product": self._clean_product_name(name, size_unit_each=size_unit_each),
                    "sizeUnitEach": size_unit_each,
                    "casePackSize": case_pack_size,
                }
            )
        if not normalized_rows:
            raise ValueError("ProductBin payload did not contain usable ProductBin rows.")
        return normalized_rows

    def _extract_size_unit_each(self, item: dict[str, object], *, product_name: str) -> str:
        size_description = str(item.get("sizeDescription") or "").strip()
        if size_description:
            return size_description
        size_value = item.get("size")
        uom = str(item.get("uom") or "").strip().lower()
        if isinstance(size_value, (int, float)) and size_value > 0 and uom:
            return f"{size_value:g} {uom}"
        parsed_from_name = self._extract_size_from_name(product_name)
        return parsed_from_name or ""

    def _extract_size_from_name(self, product_name: str) -> str | None:
        match = re.search(r"((?:\d+(?:\.\d+)?)|(?:\.\d+))\s*(oz|fl oz|lb|g|kg|ml|l|ct)\b", product_name, re.IGNORECASE)
        if not match:
            return None
        value = match.group(1)
        if value.startswith("."):
            value = f"0{value}"
        unit = match.group(2).lower()
        return f"{value} {unit}"

    def _clean_product_name(self, product_name: str, *, size_unit_each: str) -> str:
        if not size_unit_each:
            return product_name.strip()
        cleaned = re.sub(
            r"\s*((?:\d+(?:\.\d+)?)|(?:\.\d+))\s*(oz|fl oz|lb|g|kg|ml|l|ct)\b\s*$",
            "",
            product_name,
            flags=re.IGNORECASE,
        )
        return cleaned.rstrip(" .-").strip() or product_name.strip()

    def _dismiss_active_dialogs(self, page) -> None:
        dialog_locator = page.locator('[role="dialog"]')
        for _ in range(3):
            try:
                if dialog_locator.count() == 0:
                    return
            except Exception:
                return
            try:
                page.keyboard.press("Escape")
            except Exception:
                return

    def _read_report_download(self, path: Path) -> str:
        suffix = path.suffix.lower()
        if suffix in {".txt", ".csv", ".tsv"}:
            return path.read_text(encoding="utf-8", errors="replace")
        if suffix == ".pdf":
            try:
                from pypdf import PdfReader
            except ImportError:
                return ""
            with path.open("rb") as handle:
                reader = PdfReader(handle)
                return "\n".join((page.extract_text() or "").strip() for page in reader.pages if page.extract_text())
        return path.read_text(encoding="utf-8", errors="replace")

    def _parse_nexgen_date(self, value: str | None, *, allow_none: bool = False) -> datetime | None:
        if not value:
            if allow_none:
                return None
            raise ValueError("Missing Nexgen date value.")
        value = value.strip()
        for pattern in ("%b %d, %Y", "%m/%d/%y", "%m/%d/%Y"):
            try:
                return datetime.strptime(value, pattern).replace(tzinfo=timezone.utc)
            except ValueError:
                continue
        return parse_datetime(value, allow_none=allow_none)
