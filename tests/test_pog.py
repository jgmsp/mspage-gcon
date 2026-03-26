from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from mspage_gcon.pog import (
    ManagedPogSource,
    PlanogramAsset,
    POGBoardConfig,
    POGPodConfig,
    build_pog_manifest,
    build_slot_aliases,
    build_slot_short_label,
    choose_current_and_pending_assets,
    extract_slot_key,
    has_last_good_pog_publish,
    load_pog_fixture_assets,
    load_pog_publish_config,
    parse_product_report_text,
    read_pog_last_success_at,
    resolve_pog_publish_mode,
    write_pog_outputs,
)
from mspage_gcon.pog_live import NexgenCredentials, NexgenPogLiveFetcher
from mspage_gcon.pog_main import main as pog_main


ROOT = Path(__file__).resolve().parents[1]


class PogPipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 3, 23, 12, 0, tzinfo=timezone.utc)
        self.pods = [
            POGPodConfig(id="pod-1", label="Pod 1", enabled=True),
            POGPodConfig(id="pod-2", label="Pod 2", enabled=False),
            POGPodConfig(id="pod-3", label="Pod 3", enabled=False),
            POGPodConfig(id="pod-4", label="Pod 4", enabled=True),
            POGPodConfig(id="pod-5", label="Pod 5", enabled=True),
        ]
        self.board = POGBoardConfig(
            title="MSP-POG",
            subtitle="quick-pog viewer for G.",
            pods=self.pods,
        )
        self.source = ManagedPogSource(
            id="msp-cegm-pod-5",
            label="MSP - CEGM POD 5",
            pod_id="pod-5",
        )

    def test_extract_slot_key_and_short_label_from_planogram_names(self) -> None:
        self.assertEqual(extract_slot_key("MSP - CEGM POD 5_A1-A3_v1.0"), "A1-A3")
        self.assertEqual(extract_slot_key("MSP - CEGM POD 5_M4_v1.0"), "M4")
        self.assertEqual(extract_slot_key("MSP - CEGM POD 5_CASHWRAP BACK"), "CASHWRAP BACK")
        self.assertEqual(build_slot_short_label("A1-A3"), "A1")
        self.assertEqual(build_slot_short_label("M4"), "M4")

    def test_build_slot_aliases_collapses_ranges_commas_and_cashwrap_to_grouped_slots(self) -> None:
        grouped_aliases = build_slot_aliases(self.source, "M1-M3")
        self.assertEqual(len(grouped_aliases), 1)
        self.assertEqual(grouped_aliases[0]["id"], "M1-M3")
        self.assertEqual(grouped_aliases[0]["label"], "M1-M3")
        self.assertEqual(grouped_aliases[0]["sourceSlotKey"], "M1-M3")
        self.assertEqual(grouped_aliases[0]["selectId"], "M")
        self.assertTrue(grouped_aliases[0]["sharedGroup"])

        comma_aliases = build_slot_aliases(self.source, "C1, C3")
        self.assertEqual(len(comma_aliases), 1)
        self.assertEqual(comma_aliases[0]["id"], "C1, C3")
        self.assertTrue(comma_aliases[0]["sharedGroup"])

        cashwrap_group = build_slot_aliases(self.source, "CW1-CW2")
        self.assertEqual(cashwrap_group[0]["id"], "CW1-CW2")
        self.assertEqual(cashwrap_group[0]["selectId"], "CW")
        self.assertTrue(cashwrap_group[0]["sharedGroup"])

        cashwrap_source = ManagedPogSource(
            id="msp-cegm-pod-5",
            label="MSP - CEGM POD 5",
            pod_id="pod-5",
            alias_overrides={
                "CASHWRAP BACK": {
                    "aliases": ["BACK"],
                    "select_id": "CASHWRAP",
                    "letter_id": "C",
                }
            },
        )
        cashwrap_aliases = build_slot_aliases(cashwrap_source, "CASHWRAP BACK")
        self.assertEqual([alias["id"] for alias in cashwrap_aliases], ["BACK"])
        self.assertEqual(cashwrap_aliases[0]["selectId"], "CASHWRAP")
        self.assertEqual(cashwrap_aliases[0]["letterId"], "C")
        self.assertFalse(cashwrap_aliases[0]["sharedGroup"])

    def test_choose_current_and_pending_assets_auto_promotes_expired_entries(self) -> None:
        assets = [
            PlanogramAsset(
                source_id=self.source.id,
                slot_key="M6",
                planogram_id="old",
                display_name="MSP - CEGM POD 5_M6_v1.0",
                image_name="old.svg",
                report_text="Product Name | UPC\nOld Bar | 111\n",
                modified_at=datetime(2026, 3, 20, 12, 0, tzinfo=timezone.utc),
                end_at=datetime(2026, 3, 22, 12, 0, tzinfo=timezone.utc),
                status="Active",
                groups=["Energy Bars"],
            ),
            PlanogramAsset(
                source_id=self.source.id,
                slot_key="M6",
                planogram_id="current",
                display_name="MSP - CEGM POD 5_M6_v2.0",
                image_name="current.svg",
                report_text="Product Name | UPC\nCurrent Bar | 222\n",
                modified_at=datetime(2026, 3, 23, 11, 0, tzinfo=timezone.utc),
                end_at=datetime(2026, 4, 9, 12, 0, tzinfo=timezone.utc),
                status="Active",
                groups=["Energy Bars"],
            ),
            PlanogramAsset(
                source_id=self.source.id,
                slot_key="M6",
                planogram_id="pending",
                display_name="MSP - CEGM POD 5_M6_v3.0",
                image_name="pending.svg",
                report_text="Product Name | UPC\nFuture Bar | 333\n",
                modified_at=datetime(2026, 3, 23, 13, 0, tzinfo=timezone.utc),
                end_at=datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc),
                status="Active",
                groups=["Energy Bars"],
            ),
        ]

        current, pending = choose_current_and_pending_assets(assets, now=self.now)

        self.assertEqual(current.planogram_id, "current")
        self.assertEqual(pending.planogram_id, "pending")

    def test_parse_product_report_text_extracts_structured_rows(self) -> None:
        rows = parse_product_report_text(
            "Product Name | UPC | Size\n"
            "KIND Dark Chocolate Nuts | 602652171660 | 1.4 oz\n"
            "RXBAR Blueberry | 859162007413 | 1.83 oz\n"
        )

        self.assertEqual(
            rows,
            [
                {
                    "productName": "KIND Dark Chocolate Nuts",
                    "upc": "602652171660",
                    "size": "1.4 oz",
                },
                {
                    "productName": "RXBAR Blueberry",
                    "upc": "859162007413",
                    "size": "1.83 oz",
                },
            ],
        )

    def test_normalize_productbin_rows_prefers_structured_size_and_deduplicates(self) -> None:
        fetcher = NexgenPogLiveFetcher(
            NexgenCredentials(
                username="user@example.com",
                password="secret",
            )
        )

        rows = fetcher._normalize_productbin_rows(
            [
                {
                    "productID": 1,
                    "name": "KIND DARK CHOCOLATE NUTS 1.4OZ",
                    "size": 1.4,
                    "uom": "oz",
                    "sizeDescription": "",
                    "caseComment": "12 ct",
                },
                {
                    "productID": 1,
                    "name": "KIND DARK CHOCOLATE NUTS 1.4OZ",
                    "size": 1.4,
                    "uom": "oz",
                    "sizeDescription": "",
                    "caseComment": "12 ct",
                },
            ]
        )

        self.assertEqual(
            rows,
            [
                {
                    "product": "KIND DARK CHOCOLATE NUTS",
                    "sizeUnitEach": "1.4 oz",
                    "casePackSize": "12 ct",
                }
            ],
        )

    def test_normalize_productbin_rows_parses_size_from_name_when_structured_fields_blank(self) -> None:
        fetcher = NexgenPogLiveFetcher(
            NexgenCredentials(
                username="user@example.com",
                password="secret",
            )
        )

        rows = fetcher._normalize_productbin_rows(
            [
                {
                    "productID": 2,
                    "name": "ARTISAN TROPIC CASSAVA STRIPS SEA SALT 2OZ",
                    "size": 0,
                    "uom": "",
                    "sizeDescription": "",
                    "caseComment": None,
                }
            ]
        )

        self.assertEqual(
            rows,
            [
                {
                    "product": "ARTISAN TROPIC CASSAVA STRIPS SEA SALT",
                    "sizeUnitEach": "2 oz",
                    "casePackSize": "",
                }
            ],
        )

    def test_normalize_productbin_rows_handles_leading_decimal_sizes(self) -> None:
        fetcher = NexgenPogLiveFetcher(
            NexgenCredentials(
                username="user@example.com",
                password="secret",
            )
        )

        rows = fetcher._normalize_productbin_rows(
            [
                {
                    "productID": 4,
                    "name": "MOOSH NOT CANDY COTTON CANDY .35OZ",
                    "size": 0,
                    "uom": "",
                    "sizeDescription": "",
                    "caseComment": None,
                }
            ]
        )

        self.assertEqual(
            rows,
            [
                {
                    "product": "MOOSH NOT CANDY COTTON CANDY",
                    "sizeUnitEach": "0.35 oz",
                    "casePackSize": "",
                }
            ],
        )

    def test_normalize_productbin_rows_rejects_unusable_payload(self) -> None:
        fetcher = NexgenPogLiveFetcher(
            NexgenCredentials(
                username="user@example.com",
                password="secret",
            )
        )

        with self.assertRaisesRegex(ValueError, "usable ProductBin"):
            fetcher._normalize_productbin_rows(
                [
                    {
                        "productID": 3,
                        "name": "",
                        "size": 0,
                        "uom": "",
                        "sizeDescription": "",
                        "caseComment": None,
                    }
                ]
            )

    def test_build_pog_manifest_groups_enabled_pods_sources_selects_slots_and_pending(self) -> None:
        assets = [
            PlanogramAsset(
                source_id="pod-1-food-hall",
                slot_key="A1-A3",
                planogram_id="pod1-a-current",
                display_name="MSP - CEGM FOOD HALL POD 1_A1-A3_v1.0",
                image_name="pod1-a-current.png",
                report_text="",
                modified_at=datetime(2026, 2, 9, 12, 0, tzinfo=timezone.utc),
                end_at=datetime(2026, 4, 9, 12, 0, tzinfo=timezone.utc),
                status="Active",
                groups=["Feature Table - Medium"],
            ),
            PlanogramAsset(
                source_id=self.source.id,
                slot_key="A1-A3",
                planogram_id="a-current",
                display_name="MSP - CEGM POD 5_A1-A3_v1.0",
                image_name="a-current.svg",
                report_text="Product Name | UPC\nTrail Mix | 123\n",
                modified_at=datetime(2026, 2, 9, 12, 0, tzinfo=timezone.utc),
                end_at=datetime(2026, 4, 9, 12, 0, tzinfo=timezone.utc),
                status="Active",
                groups=["Feature Table - Medium"],
            ),
            PlanogramAsset(
                source_id=self.source.id,
                slot_key="CASHWRAP BACK",
                planogram_id="cw-back",
                display_name="MSP - CEGM POD 5_CASHWRAP BACK_v1.0",
                image_name="cw-back.png",
                report_text="Product Name | UPC\nSparkling Water | 555\n",
                modified_at=datetime(2026, 3, 21, 12, 0, tzinfo=timezone.utc),
                end_at=datetime(2026, 4, 9, 12, 0, tzinfo=timezone.utc),
                status="Active",
                groups=["Cashwrap Drinks"],
            ),
            PlanogramAsset(
                source_id=self.source.id,
                slot_key="M1-M3",
                planogram_id="m-current",
                display_name="MSP - CEGM POD 5_M1-M3_v1.0",
                image_name="m-current.png",
                report_text="Product Name | UPC\nKettle Chips | 456\n",
                modified_at=datetime(2026, 3, 22, 12, 0, tzinfo=timezone.utc),
                end_at=datetime(2026, 3, 24, 12, 0, tzinfo=timezone.utc),
                status="Active",
                groups=["Chips"],
            ),
            PlanogramAsset(
                source_id=self.source.id,
                slot_key="M1-M3",
                planogram_id="m-pending",
                display_name="MSP - CEGM POD 5_M1-M3_v2.0",
                image_name="m-pending.png",
                report_text="Product Name | UPC\nPopcorn | 789\n",
                modified_at=datetime(2026, 3, 23, 13, 0, tzinfo=timezone.utc),
                end_at=datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc),
                status="Active",
                groups=["Chips"],
            ),
            PlanogramAsset(
                source_id=self.source.id,
                slot_key="M4",
                planogram_id="m4-current",
                display_name="MSP - CEGM POD 5_M4_v1.0",
                image_name="m4-current.svg",
                report_text="Product Name | UPC\nAlmonds | 987\n",
                modified_at=datetime(2026, 3, 21, 12, 0, tzinfo=timezone.utc),
                end_at=datetime(2026, 4, 9, 12, 0, tzinfo=timezone.utc),
                status="Active",
                groups=["Nuts"],
            ),
        ]

        manifest = build_pog_manifest(
            board=self.board,
            sources=[
                ManagedPogSource(
                    id="pod-1-food-hall",
                    label="MSP - CEGM FOOD HALL POD 1",
                    pod_id="pod-1",
                ),
                ManagedPogSource(
                    id=self.source.id,
                    label=self.source.label,
                    pod_id=self.source.pod_id,
                    alias_overrides={
                        "CASHWRAP BACK": {
                            "aliases": ["BACK"],
                            "select_id": "CASHWRAP",
                            "letter_id": "C",
                        }
                    },
                )
            ],
            assets=assets,
            generated_at=self.now,
            output_dir=Path("docs/pog"),
        )

        self.assertEqual(manifest["board"]["title"], "MSP-POG")
        self.assertEqual(manifest["board"]["subtitle"], "quick-pog viewer for G.")
        self.assertEqual(manifest["board"]["defaultSourceId"], "pod-1-food-hall")
        self.assertEqual(manifest["board"]["defaultPodId"], "pod-1")
        self.assertEqual(manifest["board"]["defaultSelectId"], "pod-1-food-hall--a")
        self.assertEqual(manifest["board"]["defaultSlotId"], "pod-1-food-hall--a1-a3")
        self.assertFalse(manifest["pods"][1]["enabled"])
        self.assertFalse(manifest["pods"][2]["enabled"])
        pod1 = next(item for item in manifest["pods"] if item["id"] == "pod-1")
        pod5 = next(item for item in manifest["pods"] if item["id"] == "pod-5")
        self.assertEqual(pod1["sourceIds"], ["pod-1-food-hall"])
        self.assertEqual(pod5["sourceIds"], ["msp-cegm-pod-5"])
        source5 = next(item for item in manifest["sources"] if item["id"] == "msp-cegm-pod-5")
        self.assertEqual(source5["selectIds"], ["msp-cegm-pod-5--a", "msp-cegm-pod-5--cashwrap", "msp-cegm-pod-5--m"])
        select_m = next(item for item in manifest["selects"] if item["id"] == "msp-cegm-pod-5--m")
        self.assertEqual(select_m["slotIds"], ["msp-cegm-pod-5--m1-m3", "msp-cegm-pod-5--m4"])
        slot = next(item for item in manifest["slots"] if item["id"] == "msp-cegm-pod-5--m1-m3")
        self.assertEqual(slot["label"], "M1-M3")
        self.assertEqual(slot["sourceSlotKey"], "M1-M3")
        self.assertTrue(slot["sharedGroup"])
        self.assertEqual(slot["current"]["pogId"], "m-current")
        self.assertEqual(slot["pending"]["pogId"], "m-pending")
        self.assertEqual(slot["current"]["imagePath"], "assets/m-current.png")
        self.assertEqual(slot["title"], "M1-M3")
        cashwrap = next(item for item in manifest["slots"] if item["id"] == "msp-cegm-pod-5--back")
        self.assertEqual(cashwrap["selectId"], "msp-cegm-pod-5--cashwrap")
        self.assertEqual(cashwrap["selectKey"], "CASHWRAP")
        self.assertEqual(cashwrap["letterId"], "C")

    def test_build_pog_manifest_reuses_shared_image_path_for_grouped_slots(self) -> None:
        assets = [
            PlanogramAsset(
                source_id=self.source.id,
                slot_key="M1-M3",
                planogram_id="m-current",
                display_name="MSP - CEGM POD 5_M1-M3_v1.0",
                image_name="m-current.png",
                report_text="Product Name | UPC\nKettle Chips | 456\n",
                modified_at=datetime(2026, 3, 22, 12, 0, tzinfo=timezone.utc),
                end_at=datetime(2026, 4, 9, 12, 0, tzinfo=timezone.utc),
                status="Active",
                groups=["Chips"],
            ),
        ]

        manifest = build_pog_manifest(
            board=self.board,
            sources=[self.source],
            assets=assets,
            generated_at=self.now,
            output_dir=Path("docs/pog"),
        )

        slot_paths = {
            slot["id"]: slot["current"]["imagePath"]
            for slot in manifest["slots"]
        }
        self.assertEqual(slot_paths["msp-cegm-pod-5--m1-m3"], "assets/m-current.png")

    def test_write_pog_outputs_publishes_shared_images_for_grouped_slots(self) -> None:
        from io import BytesIO
        from PIL import Image

        image_buffer = BytesIO()
        Image.new("RGB", (60, 30), "#336699").save(image_buffer, format="PNG")
        assets = [
            PlanogramAsset(
                source_id=self.source.id,
                slot_key="M1-M3",
                planogram_id="m-current",
                display_name="MSP - CEGM POD 5_M1-M3_v1.0",
                image_name="m-current.png",
                report_text="Product Name | UPC\nProtein Bar | 654\n",
                modified_at=datetime(2026, 3, 23, 11, 0, tzinfo=timezone.utc),
                end_at=datetime(2026, 4, 9, 12, 0, tzinfo=timezone.utc),
                status="Active",
                groups=["Energy Bars"],
                image_bytes=image_buffer.getvalue(),
            ),
        ]

        with TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            manifest = build_pog_manifest(
                board=self.board,
                sources=[self.source],
                assets=assets,
                generated_at=self.now,
                output_dir=output_dir,
            )
            write_pog_outputs(output_dir=output_dir, manifest=manifest, assets=assets)

            manifest_path = output_dir / "manifest.json"
            self.assertTrue(manifest_path.exists())
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            slot_ids = [slot["id"] for slot in payload["slots"]]
            self.assertEqual(slot_ids, ["msp-cegm-pod-5--m1-m3"])
            self.assertEqual(
                {slot["current"]["imagePath"] for slot in payload["slots"]},
                {"assets/m-current.png"},
            )
            self.assertTrue((output_dir / "assets" / "m-current.png").exists())
            self.assertFalse((output_dir / "data").exists())

    def test_static_pog_shell_contains_expected_controls(self) -> None:
        html = (ROOT / "docs" / "pog" / "index.html").read_text(encoding="utf-8")

        self.assertIn("MSP-POG", html)
        self.assertIn("quick-pog viewer for G.", html)
        self.assertIn('id="theme-cycle"', html)
        self.assertIn("mspage-gcon-theme", html)
        self.assertIn('id="flow-select"', html)
        self.assertIn('id="source-filters"', html)
        self.assertIn("Which", html)
        self.assertIn('id="pending-toggle"', html)
        self.assertIn('id="pog-status-line"', html)
        self.assertIn('id="slot-shared-badge"', html)
        self.assertIn('id="slot-selection"', html)
        self.assertIn('id="flow-filter"', html)
        self.assertIn('id="flow-subselect"', html)
        self.assertIn('id="flow-which"', html)
        self.assertIn('id="flow-viewer"', html)

    def test_static_pog_app_uses_grouped_source_image_viewer(self) -> None:
        script = (ROOT / "docs" / "pog" / "app.js").read_text(encoding="utf-8")

        self.assertIn("activeSourceId", script)
        self.assertIn("activeTheme", script)
        self.assertIn("getSourcesForActivePod", script)
        self.assertIn("selects", script)
        self.assertIn("sharedGroup", script)
        self.assertIn("const THEMES =", script)
        self.assertIn("cycleTheme", script)
        self.assertIn("renderFlowVisibility", script)
        self.assertIn("slot.sourceSlotKey", script)
        self.assertIn("Selected", script)
        self.assertNotIn("LIST_COLUMNS", script)
        self.assertNotIn("renderList", script)

    def test_repo_pog_publish_config_loads_fixture_sources(self) -> None:
        board, sources, assets = load_pog_publish_config(ROOT / "config" / "pog_sources.json")

        self.assertEqual(board.title, "MSP-POG")
        self.assertEqual([source.id for source in sources], ["pod-1-food-hall", "pod-1-shoyu", "pod-4-twin-burger", "msp-cegm-pod-5"])
        self.assertEqual(sources[0].source_type, "nexgen")
        self.assertEqual(sources[0].folder_id, "b8c19453-87a8-489b-a3ca-fe8cf337bbea")
        self.assertTrue(str(sources[0].fixture_path).endswith("pog_fixture_pod1_food_hall.json"))
        self.assertIn("CASHWRAP BACK", sources[-1].alias_overrides)
        self.assertTrue(any(asset.slot_key == "M1-M3" for asset in assets))

    def test_fixture_asset_loader_derives_slot_keys_from_display_names(self) -> None:
        assets = load_pog_fixture_assets(ROOT / "config" / "pog_fixture.json")

        slot_keys = {asset.slot_key for asset in assets}
        self.assertIn("A1-A3", slot_keys)
        self.assertIn("CASHWRAP BACK", slot_keys)
        self.assertIn("M8", slot_keys)

    def test_pog_main_generates_publishable_output_from_repo_config(self) -> None:
        with TemporaryDirectory() as temp_dir:
            exit_code = pog_main(
                [
                    "--output-dir",
                    temp_dir,
                    "--config",
                    str(ROOT / "config" / "pog_sources.json"),
                ]
            )

            self.assertEqual(exit_code, 0)
            manifest_path = Path(temp_dir) / "manifest.json"
            self.assertTrue(manifest_path.exists())
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["board"]["title"], "MSP-POG")
            self.assertTrue(len(manifest["sources"]) >= 4)
            self.assertTrue(len(manifest["slots"]) >= 4)
            self.assertTrue((Path(temp_dir) / "index.html").exists())
            self.assertTrue((Path(temp_dir) / manifest["slots"][0]["current"]["imagePath"]).exists())
            self.assertTrue((Path(temp_dir) / "diagnostics.json").exists())
            self.assertEqual(read_pog_last_success_at(Path(temp_dir)), datetime.fromisoformat(manifest["board"]["generatedAt"].replace("Z", "+00:00")))

    def test_publish_workflow_runs_pog_generator(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "publish.yml").read_text(encoding="utf-8")

        self.assertIn("python3 -m mspage_gcon.pog_main", workflow)
        self.assertIn("--mode auto", workflow)
        self.assertIn("Install Playwright for live MSP-POG", workflow)

    def test_resolve_pog_publish_mode_prefers_live_when_creds_present(self) -> None:
        sources = [
            ManagedPogSource(
                id="msp-cegm-pod-5",
                label="MSP - CEGM POD 5",
                pod_id="pod-5",
                source_type="nexgen",
                folder_id="folder-1",
                fixture_path=ROOT / "config" / "pog_fixture.json",
            )
        ]

        mode = resolve_pog_publish_mode(
            requested_mode="auto",
            sources=sources,
            environment={
                "NEXGENPOG_USERNAME": "user@example.com",
                "NEXGENPOG_PASSWORD": "secret",
            },
        )

        self.assertEqual(mode, "live")

    def test_resolve_pog_publish_mode_falls_back_to_fixture_without_creds(self) -> None:
        sources = [
            ManagedPogSource(
                id="msp-cegm-pod-5",
                label="MSP - CEGM POD 5",
                pod_id="pod-5",
                source_type="nexgen",
                folder_id="folder-1",
                fixture_path=ROOT / "config" / "pog_fixture.json",
            )
        ]

        mode = resolve_pog_publish_mode(
            requested_mode="auto",
            sources=sources,
            environment={},
        )

        self.assertEqual(mode, "fixture")

    def test_nexgen_row_enumeration_waits_for_item_links_and_extracts_grid_rows(self) -> None:
        class FakePage:
            def __init__(self) -> None:
                self.wait_calls: list[tuple[str, str, int]] = []

            def wait_for_selector(self, selector: str, *, state: str, timeout: int) -> None:
                self.wait_calls.append((selector, state, timeout))

            def evaluate(self, script: str):
                if "tr.k-master-row" not in script or "a.ItemName" not in script:
                    return []
                return [
                    {
                        "display_name": "MSP - CEGM POD 5_M6_v1.0",
                        "gateway_url": "https://app.nexgenpog.com/vc/AuthGateway/Gateway?p=row-1",
                        "internal_id": "244001",
                        "gateway_key": "row-1",
                        "modified_by": "Julie Kim",
                        "modified_at": "Mar 23, 2026",
                        "shared_by": "whart@otgexp.com",
                        "status": "Active",
                        "start_at": "Mar 20, 2026",
                        "end_at": "Apr 09, 2026",
                        "groups": "Energy Bars",
                    }
                ]

        fetcher = NexgenPogLiveFetcher(
            NexgenCredentials(
                username="user@example.com",
                password="secret",
                timeout_ms=60_000,
            )
        )
        page = FakePage()

        rows = fetcher._enumerate_rows(page)

        self.assertEqual(
            page.wait_calls,
            [("tr.k-master-row td a.ItemName", "visible", 60_000)],
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["display_name"], "MSP - CEGM POD 5_M6_v1.0")

    def test_nexgen_image_fallback_dismisses_dialog_before_screenshot(self) -> None:
        class FakeTimeout(Exception):
            pass

        class FakeDownloadContext:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                raise FakeTimeout("no download")

        class FakeTextLocator:
            def __init__(self, page, label: str) -> None:
                self.page = page
                self.label = label

            def click(self) -> None:
                if self.label == "Image":
                    self.page.dialog_count = 1

        class FakeDialogLocator:
            def __init__(self, page) -> None:
                self.page = page

            def count(self) -> int:
                return self.page.dialog_count

        class FakeKeyboard:
            def __init__(self, page) -> None:
                self.page = page

            def press(self, key: str) -> None:
                self.page.keys_pressed.append(key)
                if key == "Escape":
                    self.page.dialog_count = 0

        class FakePage:
            def __init__(self) -> None:
                self.dialog_count = 0
                self.keys_pressed: list[str] = []
                self.keyboard = FakeKeyboard(self)
                self.screenshot_kwargs = None

            def expect_download(self, *, timeout: int):
                return FakeDownloadContext()

            def get_by_text(self, label: str, exact: bool = False):
                return FakeTextLocator(self, label)

            def locator(self, selector: str):
                if selector == '[role="dialog"]':
                    return FakeDialogLocator(self)
                raise AssertionError(f"Unexpected selector: {selector}")

            def evaluate(self, script: str):
                return {
                    "x": 100,
                    "y": 80,
                    "width": 600,
                    "height": 400,
                }

            def screenshot(self, *, type: str, clip=None, full_page=None) -> bytes:
                if self.dialog_count:
                    raise AssertionError("dialog should be dismissed before screenshot fallback")
                self.screenshot_kwargs = {"type": type, "clip": clip, "full_page": full_page}
                return b"png"

        fetcher = NexgenPogLiveFetcher(
            NexgenCredentials(
                username="user@example.com",
                password="secret",
            )
        )

        page = FakePage()
        image_bytes, image_name, provenance = fetcher._export_image(
            page,
            row={"internal_id": "244001"},
            playwright_timeout_error=FakeTimeout,
        )

        self.assertEqual(image_bytes, b"png")
        self.assertEqual(image_name, "244001.png")
        self.assertEqual(provenance, "nexgen-screenshot-fallback")
        self.assertEqual(
            page.screenshot_kwargs,
            {
                "type": "png",
                "clip": {"x": 92, "y": 72, "width": 616, "height": 416},
                "full_page": None,
            },
        )

    def test_nexgen_build_asset_skips_folder_rows(self) -> None:
        fetcher = NexgenPogLiveFetcher(
            NexgenCredentials(
                username="user@example.com",
                password="secret",
            )
        )

        asset = fetcher._build_asset_from_row(
            page=object(),
            row={
                "display_name": "z_Archived",
                "gateway_url": "https://app.nexgenpog.com/vc/PlanogramList?p=subfolder",
            },
            source=self.source,
            playwright_timeout_error=RuntimeError,
        )

        self.assertIsNone(asset)

    def test_nexgen_planogram_image_clip_uses_dom_union(self) -> None:
        class FakePage:
            def evaluate(self, script: str):
                return {
                    "x": 379,
                    "y": 102,
                    "width": 964,
                    "height": 960,
                }

        fetcher = NexgenPogLiveFetcher(
            NexgenCredentials(
                username="user@example.com",
                password="secret",
            )
        )

        clip = fetcher._planogram_image_clip(FakePage())

        self.assertEqual(
            clip,
            {
                "x": 371,
                "y": 94,
                "width": 980,
                "height": 976,
            },
        )

    def test_nexgen_open_planogram_captures_productbin_rows(self) -> None:
        class FakeResponse:
            def json(self):
                return [
                    {
                        "productID": 22,
                        "name": "KETTLE CHIPS SEA SALT 2OZ",
                        "size": 0,
                        "uom": "",
                        "sizeDescription": "",
                        "caseComment": "",
                    }
                ]

        class FakeResponseContext:
            def __init__(self) -> None:
                self.value = FakeResponse()

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return None

        class FakePage:
            def expect_response(self, predicate, *, timeout: int):
                self.timeout = timeout
                return FakeResponseContext()

            def goto(self, url: str, *, wait_until: str) -> None:
                self.url = url

            def wait_for_load_state(self, state: str, *, timeout: int) -> None:
                self.wait_state = (state, timeout)

        fetcher = NexgenPogLiveFetcher(
            NexgenCredentials(
                username="user@example.com",
                password="secret",
                timeout_ms=60_000,
            )
        )

        rows, provenance = fetcher._open_planogram_and_capture_product_rows(
            FakePage(),
            row={
                "display_name": "MSP - CEGM POD 5_B1-B4_v1.0",
                "gateway_url": "https://app.nexgenpog.com/vc/AuthGateway/Gateway?p=row-1",
            },
            playwright_timeout_error=RuntimeError,
        )

        self.assertEqual(provenance, "nexgen-productbin")
        self.assertEqual(
            rows,
            [
                {
                    "product": "KETTLE CHIPS SEA SALT",
                    "sizeUnitEach": "2 oz",
                    "casePackSize": "",
                }
            ],
        )

    def test_pog_main_reuses_last_good_publish_when_live_ingest_fails(self) -> None:
        with TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            first_exit = pog_main(
                [
                    "--output-dir",
                    temp_dir,
                    "--config",
                    str(ROOT / "config" / "pog_sources.json"),
                    "--mode",
                    "fixture",
                ]
            )
            self.assertEqual(first_exit, 0)
            original_manifest = (output_dir / "manifest.json").read_text(encoding="utf-8")
            self.assertTrue(has_last_good_pog_publish(output_dir))

            with patch("mspage_gcon.pog.collect_pog_assets", side_effect=RuntimeError("live boom")):
                second_exit = pog_main(
                    [
                        "--output-dir",
                        temp_dir,
                        "--config",
                        str(ROOT / "config" / "pog_sources.json"),
                        "--mode",
                        "live",
                    ]
                )

            self.assertEqual(second_exit, 0)
            self.assertEqual((output_dir / "manifest.json").read_text(encoding="utf-8"), original_manifest)
            diagnostics = json.loads((output_dir / "diagnostics.json").read_text(encoding="utf-8"))
            self.assertEqual(diagnostics["status"], "degraded")
            self.assertEqual(diagnostics["sourceMode"], "live")

    @unittest.skipUnless(
        os.environ.get("NEXGENPOG_USERNAME") and os.environ.get("NEXGENPOG_PASSWORD"),
        "Live Nexgen credentials not configured.",
    )
    def test_live_smoke_mode_can_generate_a_manifest(self) -> None:
        with TemporaryDirectory() as temp_dir:
            exit_code = pog_main(
                [
                    "--output-dir",
                    temp_dir,
                    "--config",
                    str(ROOT / "config" / "pog_sources.json"),
                    "--mode",
                    "live",
                ]
            )

            self.assertEqual(exit_code, 0)
            manifest = json.loads((Path(temp_dir) / "manifest.json").read_text(encoding="utf-8"))
            self.assertTrue(manifest["slots"])
            self.assertTrue(any(source["podId"] == "pod-1" for source in manifest["sources"]))
            self.assertTrue(any(source["podId"] == "pod-4" for source in manifest["sources"]))


if __name__ == "__main__":
    unittest.main()
