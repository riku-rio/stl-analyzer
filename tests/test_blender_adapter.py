from stl_analyzer.blender.adapter import SubprocessBlenderAdapter


def test_blender_adapter_success(tmp_path):
    script = tmp_path / "script.py"
    script.write_text("print('success')", encoding="utf-8")

    manifest = tmp_path / "manifest.json"
    manifest.write_text("{}", encoding="utf-8")

    fake_blender = tmp_path / "fake_blender.bat"
    fake_blender.write_text("@echo off\necho success\n", encoding="utf-8")

    adapter = SubprocessBlenderAdapter()
    result = adapter.run(
        executable=fake_blender, script=script, manifest_path=manifest, timeout_seconds=5.0
    )

    assert result.exit_code == 0
    assert not result.timed_out
    assert "success" in result.stdout


def test_blender_adapter_timeout(tmp_path):
    script = tmp_path / "script.py"
    script.write_text("import time\ntime.sleep(2)\n", encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    manifest.write_text("{}", encoding="utf-8")

    fake_blender = tmp_path / "fake_blender.bat"
    fake_blender.write_text("@echo off\nping 127.0.0.1 -n 3 >nul\n", encoding="utf-8")

    adapter = SubprocessBlenderAdapter()
    result = adapter.run(
        executable=fake_blender, script=script, manifest_path=manifest, timeout_seconds=0.5
    )

    assert result.exit_code == -1
    assert result.timed_out
