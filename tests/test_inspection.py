"""Tests for geometry inspection service (MVP-0506)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from stl_analyzer.blender.adapter import BlenderResult
from stl_analyzer.errors import DomainError
from stl_analyzer.models.geometry import (
    INSPECTION_SCHEMA_VERSION,
    INSPECTION_SCRIPT_VERSION,
    BoundingBox,
    InspectionResult,
)
from stl_analyzer.services.inspection_service import InspectionService

# ─────────────────────────── helpers ────────────────────────────────────────


def _make_workspace(tmp_path: Path, case_id: str = "case-001") -> Path:
    """Create a minimal workspace with a fake STL file."""
    config_toml = (
        '[project]\nstl_root = "stl"\nassets_directory = "assets"\n\n'
        '[blender]\nexecutable = "blender"\ntimeout_seconds = 30\n\n'
        '[scan]\nallowed_extensions = [".stl"]\nmaximum_files_per_case = 1\n'
        'assumed_unit = "millimeters"\n\n'
        '[render]\nwidth = 512\nheight = 512\nengine = "BLENDER_EEVEE_NEXT"\n'
        'default_preset = "dental_arch"\n\n'
        "[workflow]\nmaximum_iterations = 6\n"
        'required_views = ["occlusal", "anterior", "posterior", "left", "right", "isometric"]\n\n'
        "[output]\nretain_all_iterations = true\nwrite_event_log = true\n"
    )
    (tmp_path / "stl-analyzer.toml").write_text(config_toml, encoding="utf-8")
    case_dir = tmp_path / "stl" / case_id
    case_dir.mkdir(parents=True)
    (case_dir / "model.stl").write_bytes(b"solid fake\nendsolid fake\n")
    return tmp_path


def _make_result_json(case_id: str, source_sha256: str) -> dict:  # type: ignore[type-arg]
    return {
        "schema_version": INSPECTION_SCHEMA_VERSION,
        "script_version": INSPECTION_SCRIPT_VERSION,
        "tool_version": "0.1.0",
        "case_id": case_id,
        "source_path": f"/fake/stl/{case_id}/model.stl",
        "source_sha256": source_sha256,
        "source_size_bytes": 22,
        "blender_version": "4.1.0",
        "vertex_count": 8,
        "polygon_count": 12,
        "object_count": 1,
        "component_count": 1,
        "bounding_box": {
            "min": [-10.0, -10.0, -5.0],
            "max": [10.0, 10.0, 5.0],
        },
        "dimensions": [20.0, 20.0, 10.0],
        "center": [0.0, 0.0, 0.0],
        "assumed_unit": "millimeters",
        "warnings": [],
        "inspection_timestamp": "2026-01-01T00:00:00Z",
    }


class FakeAdapter:
    """Fake BlenderAdapter that writes a canned inspection result."""

    def __init__(
        self,
        *,
        exit_code: int = 0,
        timed_out: bool = False,
        result_payload: dict | None = None,  # type: ignore[type-arg]
        write_result: bool = True,
    ) -> None:
        self._exit_code = exit_code
        self._timed_out = timed_out
        self._result_payload = result_payload
        self._write_result = write_result

    def run(self, *, executable, script, manifest_path, timeout_seconds):  # type: ignore[override]
        # Read manifest to know where to write the result.
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        output_path = Path(manifest["output_path"])
        source_path = Path(manifest["source_path"])

        if self._timed_out:
            return BlenderResult(
                stdout="", stderr="", exit_code=-1, duration_seconds=0.5, timed_out=True
            )

        if self._exit_code != 0:
            return BlenderResult(
                stdout="",
                stderr="Error: something failed",
                exit_code=self._exit_code,
                duration_seconds=0.1,
                timed_out=False,
            )

        if self._write_result:
            # Compute real hash for the source path if it exists
            import hashlib

            sha = hashlib.sha256()
            if source_path.exists():
                sha.update(source_path.read_bytes())
            actual_hash = sha.hexdigest()

            payload = self._result_payload or _make_result_json(manifest["case_id"], actual_hash)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )

        return BlenderResult(
            stdout="OK", stderr="", exit_code=0, duration_seconds=0.1, timed_out=False
        )


# ──────────────────────────── tests ─────────────────────────────────────────


class TestInspectionServiceSuccess:
    def test_successful_inspection(self, tmp_path: Path) -> None:
        workspace = _make_workspace(tmp_path)
        from stl_analyzer.services.workspace import WorkspaceService

        config = WorkspaceService().load_config(workspace)
        adapter = FakeAdapter()
        service = InspectionService(adapter)

        result, cache_hit = service.inspect(
            workspace_root=workspace, config=config, case_id="case-001"
        )

        assert not cache_hit
        assert result.vertex_count == 8
        assert result.polygon_count == 12
        assert result.assumed_unit == "millimeters"
        assert result.case_id == "case-001"
        assert len(result.bounding_box.min) == 3

        # geometry.json should be written
        geometry_json = workspace / "stl" / "case-001" / "assets" / "geometry.json"
        assert geometry_json.exists()

    def test_cache_hit(self, tmp_path: Path) -> None:
        workspace = _make_workspace(tmp_path)
        from stl_analyzer.services.workspace import WorkspaceService

        config = WorkspaceService().load_config(workspace)
        adapter = FakeAdapter()
        service = InspectionService(adapter)

        # First inspection writes geometry.json
        result1, _ = service.inspect(workspace_root=workspace, config=config, case_id="case-001")

        # Second inspection should be a cache hit (no Blender call needed)
        run_count = [0]
        original_run = adapter.run

        def counting_run(**kwargs):  # type: ignore[no-untyped-def]
            run_count[0] += 1
            return original_run(**kwargs)

        adapter.run = counting_run  # type: ignore[method-assign]

        result2, cache_hit = service.inspect(
            workspace_root=workspace, config=config, case_id="case-001"
        )

        assert cache_hit
        assert run_count[0] == 0
        assert result2.vertex_count == result1.vertex_count

    def test_force_reinspection(self, tmp_path: Path) -> None:
        workspace = _make_workspace(tmp_path)
        from stl_analyzer.services.workspace import WorkspaceService

        config = WorkspaceService().load_config(workspace)
        adapter = FakeAdapter()
        service = InspectionService(adapter)

        # Populate cache
        service.inspect(workspace_root=workspace, config=config, case_id="case-001")

        run_count = [0]
        orig = adapter.run

        def counting_run(**kwargs):  # type: ignore[no-untyped-def]
            run_count[0] += 1
            return orig(**kwargs)

        adapter.run = counting_run  # type: ignore[method-assign]

        _, cache_hit = service.inspect(
            workspace_root=workspace, config=config, case_id="case-001", force=True
        )

        assert not cache_hit
        assert run_count[0] == 1

    def test_cache_invalidated_on_hash_change(self, tmp_path: Path) -> None:
        workspace = _make_workspace(tmp_path)
        from stl_analyzer.services.workspace import WorkspaceService

        config = WorkspaceService().load_config(workspace)
        adapter = FakeAdapter()
        service = InspectionService(adapter)

        # First inspection
        service.inspect(workspace_root=workspace, config=config, case_id="case-001")

        # Mutate source file → hash changes → cache should be invalidated
        stl_path = workspace / "stl" / "case-001" / "model.stl"
        stl_path.write_bytes(b"solid changed\nendsolid changed\n")

        run_count = [0]
        orig = adapter.run

        def counting_run(**kwargs):  # type: ignore[no-untyped-def]
            run_count[0] += 1
            return orig(**kwargs)

        adapter.run = counting_run  # type: ignore[method-assign]

        _, cache_hit = service.inspect(workspace_root=workspace, config=config, case_id="case-001")

        assert not cache_hit
        assert run_count[0] == 1


class TestInspectionServiceFailures:
    def test_blender_timeout(self, tmp_path: Path) -> None:
        workspace = _make_workspace(tmp_path)
        from stl_analyzer.services.workspace import WorkspaceService

        config = WorkspaceService().load_config(workspace)
        adapter = FakeAdapter(timed_out=True)
        service = InspectionService(adapter)

        with pytest.raises(DomainError) as exc_info:
            service.inspect(workspace_root=workspace, config=config, case_id="case-001")

        assert exc_info.value.code == "BLENDER_TIMEOUT"

    def test_blender_nonzero_exit(self, tmp_path: Path) -> None:
        workspace = _make_workspace(tmp_path)
        from stl_analyzer.services.workspace import WorkspaceService

        config = WorkspaceService().load_config(workspace)
        adapter = FakeAdapter(exit_code=1)
        service = InspectionService(adapter)

        with pytest.raises(DomainError) as exc_info:
            service.inspect(workspace_root=workspace, config=config, case_id="case-001")

        assert exc_info.value.code == "BLENDER_NONZERO_EXIT"

    def test_missing_result_file(self, tmp_path: Path) -> None:
        workspace = _make_workspace(tmp_path)
        from stl_analyzer.services.workspace import WorkspaceService

        config = WorkspaceService().load_config(workspace)
        adapter = FakeAdapter(write_result=False)
        service = InspectionService(adapter)

        with pytest.raises(DomainError) as exc_info:
            service.inspect(workspace_root=workspace, config=config, case_id="case-001")

        assert exc_info.value.code == "INSPECTION_RESULT_MISSING"

    def test_invalid_json_result(self, tmp_path: Path) -> None:
        workspace = _make_workspace(tmp_path)
        from stl_analyzer.services.workspace import WorkspaceService

        config = WorkspaceService().load_config(workspace)

        class BrokenJsonAdapter:
            def run(self, *, executable, script, manifest_path, timeout_seconds):  # type: ignore[no-untyped-def]
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                output_path = Path(manifest["output_path"])
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text("not json {{{{", encoding="utf-8")
                return BlenderResult("", "", 0, 0.1, False)

        service = InspectionService(BrokenJsonAdapter())  # type: ignore[arg-type]

        with pytest.raises(DomainError) as exc_info:
            service.inspect(workspace_root=workspace, config=config, case_id="case-001")

        assert exc_info.value.code == "INSPECTION_INVALID_JSON"

    def test_source_hash_mismatch_in_result(self, tmp_path: Path) -> None:
        workspace = _make_workspace(tmp_path)
        from stl_analyzer.services.workspace import WorkspaceService

        config = WorkspaceService().load_config(workspace)

        bad_payload = _make_result_json("case-001", "0" * 64)  # wrong hash

        adapter = FakeAdapter(result_payload=bad_payload)
        service = InspectionService(adapter)

        with pytest.raises(DomainError) as exc_info:
            service.inspect(workspace_root=workspace, config=config, case_id="case-001")

        assert exc_info.value.code == "INSPECTION_HASH_MISMATCH"

    def test_schema_validation_failure(self, tmp_path: Path) -> None:
        workspace = _make_workspace(tmp_path)
        from stl_analyzer.services.workspace import WorkspaceService

        config = WorkspaceService().load_config(workspace)

        class SchemaBreakingAdapter:
            def run(self, *, executable, script, manifest_path, timeout_seconds):  # type: ignore[no-untyped-def]
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                output_path = Path(manifest["output_path"])
                output_path.parent.mkdir(parents=True, exist_ok=True)
                # Missing required fields
                output_path.write_text(
                    json.dumps({"schema_version": "1", "case_id": "case-001"}),
                    encoding="utf-8",
                )
                return BlenderResult("", "", 0, 0.1, False)

        service = InspectionService(SchemaBreakingAdapter())  # type: ignore[arg-type]

        with pytest.raises(DomainError) as exc_info:
            service.inspect(workspace_root=workspace, config=config, case_id="case-001")

        assert exc_info.value.code == "INSPECTION_SCHEMA_INVALID"

    def test_missing_case(self, tmp_path: Path) -> None:
        workspace = _make_workspace(tmp_path)
        from stl_analyzer.services.workspace import WorkspaceService

        config = WorkspaceService().load_config(workspace)
        adapter = FakeAdapter()
        service = InspectionService(adapter)

        with pytest.raises(DomainError) as exc_info:
            service.inspect(workspace_root=workspace, config=config, case_id="nonexistent")

        assert exc_info.value.exit_code.value == 4  # INVALID_CASE


class TestInspectionManifest:
    def test_validate_inspection_result_hash_ok(self) -> None:
        from stl_analyzer.models.geometry import validate_inspection_result_hash

        result = InspectionResult(
            tool_version="0.1.0",
            case_id="c",
            source_path="/p",
            source_sha256="abc123",
            source_size_bytes=1,
            blender_version="4.1",
            vertex_count=1,
            polygon_count=1,
            object_count=1,
            bounding_box=BoundingBox(min=[0.0, 0.0, 0.0], max=[1.0, 1.0, 1.0]),
            dimensions=[1.0, 1.0, 1.0],
            center=[0.5, 0.5, 0.5],
            assumed_unit="millimeters",
            inspection_timestamp="2026-01-01T00:00:00Z",
        )
        issues = validate_inspection_result_hash(result, "abc123")
        assert issues == []

    def test_validate_inspection_result_hash_mismatch(self) -> None:
        from stl_analyzer.models.geometry import validate_inspection_result_hash

        result = InspectionResult(
            tool_version="0.1.0",
            case_id="c",
            source_path="/p",
            source_sha256="actual_hash",
            source_size_bytes=1,
            blender_version="4.1",
            vertex_count=1,
            polygon_count=1,
            object_count=1,
            bounding_box=BoundingBox(min=[0.0, 0.0, 0.0], max=[1.0, 1.0, 1.0]),
            dimensions=[1.0, 1.0, 1.0],
            center=[0.5, 0.5, 0.5],
            assumed_unit="millimeters",
            inspection_timestamp="2026-01-01T00:00:00Z",
        )
        issues = validate_inspection_result_hash(result, "expected_hash")
        assert len(issues) == 1
        assert "mismatch" in issues[0]
