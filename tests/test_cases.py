import pytest

from stl_analyzer.errors import DomainError
from stl_analyzer.models.cases import CaseState
from stl_analyzer.models.config import ScanConfig
from stl_analyzer.services.case_service import CaseDiscovery, CaseValidation


@pytest.fixture
def workspace_with_stl(tmp_path):
    stl_root = tmp_path / "stl"
    stl_root.mkdir()
    return tmp_path, stl_root


@pytest.fixture
def scan_config():
    return ScanConfig()


def test_empty_stl_root(workspace_with_stl, scan_config):
    workspace, _stl_root = workspace_with_stl
    discovery = CaseDiscovery()
    cases = discovery.list_cases(workspace, "stl", scan_config)
    assert len(cases) == 0


def test_one_valid_case(workspace_with_stl, scan_config):
    workspace, stl_root = workspace_with_stl
    case_dir = stl_root / "case1"
    case_dir.mkdir()
    (case_dir / "model.stl").touch()

    discovery = CaseDiscovery()
    cases = discovery.list_cases(workspace, "stl", scan_config)

    assert len(cases) == 1
    assert cases[0].case_id == "case1"
    assert cases[0].state == CaseState.READY
    assert cases[0].source_file == "stl/case1/model.stl"


def test_missing_stl(workspace_with_stl, scan_config):
    workspace, stl_root = workspace_with_stl
    case_dir = stl_root / "case2"
    case_dir.mkdir()
    (case_dir / "not_an_stl.txt").touch()

    discovery = CaseDiscovery()
    cases = discovery.list_cases(workspace, "stl", scan_config)

    assert len(cases) == 1
    assert cases[0].state == CaseState.MISSING_STL


def test_multiple_stl_files(workspace_with_stl, scan_config):
    workspace, stl_root = workspace_with_stl
    case_dir = stl_root / "case3"
    case_dir.mkdir()
    (case_dir / "model1.stl").touch()
    (case_dir / "model2.stl").touch()

    discovery = CaseDiscovery()
    cases = discovery.list_cases(workspace, "stl", scan_config)

    assert len(cases) == 1
    assert cases[0].state == CaseState.MULTIPLE_STL_FILES


def test_nested_stl_only(workspace_with_stl, scan_config):
    workspace, stl_root = workspace_with_stl
    case_dir = stl_root / "case4"
    case_dir.mkdir()
    nested = case_dir / "nested"
    nested.mkdir()
    (nested / "model.stl").touch()

    discovery = CaseDiscovery()
    cases = discovery.list_cases(workspace, "stl", scan_config)

    assert len(cases) == 1
    assert cases[0].state == CaseState.MISSING_STL


def test_uppercase_extension(workspace_with_stl, scan_config):
    workspace, stl_root = workspace_with_stl
    case_dir = stl_root / "case5"
    case_dir.mkdir()
    (case_dir / "model.STL").touch()

    discovery = CaseDiscovery()
    cases = discovery.list_cases(workspace, "stl", scan_config)

    assert len(cases) == 1
    assert cases[0].state == CaseState.READY
    assert cases[0].source_file == "stl/case5/model.STL"


def test_mixed_cases(workspace_with_stl, scan_config):
    workspace, stl_root = workspace_with_stl

    # Valid
    (stl_root / "caseA").mkdir()
    (stl_root / "caseA" / "1.stl").touch()

    # Missing
    (stl_root / "caseB").mkdir()

    # Non-directory entry at stl_root (should be ignored)
    (stl_root / "file.txt").touch()

    discovery = CaseDiscovery()
    cases = discovery.list_cases(workspace, "stl", scan_config)

    assert len(cases) == 2
    assert cases[0].case_id == "caseA"
    assert cases[1].case_id == "caseB"


def test_validation_traversal_attempts(workspace_with_stl, scan_config):
    workspace, _stl_root = workspace_with_stl
    validator = CaseValidation()

    with pytest.raises(DomainError) as exc:
        validator.validate_case(workspace, "stl", "assets", scan_config, "../other")
    assert exc.value.code == "INVALID_CASE_ID"


def test_validation_unsafe_assets_path(workspace_with_stl, scan_config):
    workspace, stl_root = workspace_with_stl
    case_dir = stl_root / "case1"
    case_dir.mkdir()
    (case_dir / "model.stl").touch()

    validator = CaseValidation()
    with pytest.raises(DomainError) as exc:
        validator.validate_case(workspace, "stl", "../outside_assets", scan_config, "case1")
    assert exc.value.code == "INVALID_ASSETS_PATH"


def test_validation_success(workspace_with_stl, scan_config):
    workspace, stl_root = workspace_with_stl
    case_dir = stl_root / "case1"
    case_dir.mkdir()
    # Need at least 1 byte so we can read it in validate_case to check read access
    (case_dir / "model.stl").write_bytes(b"0")

    validator = CaseValidation()
    case = validator.validate_case(workspace, "stl", "assets", scan_config, "case1")

    assert case.state == CaseState.READY
