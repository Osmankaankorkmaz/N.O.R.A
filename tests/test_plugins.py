import json

import pytest

from nora.nora_personality import CommandError
from nora.nora_plugins import PluginRegistry, validate_manifest
from nora.nora_store import NoraStore


def manifest(plugin_id="study"):
    return {
        "schema": 1,
        "id": plugin_id,
        "name": "Çalışma",
        "version": "1.0.0",
        "description": "Güvenli komut paketi",
        "commands": [
            {
                "name": "başla",
                "phrase": "stüdyo zamanı",
                "reply": "Stüdyo hazır.",
                "steps": [{"command": "pet_action", "action": "sit"}],
            }
        ],
    }


def test_plugin_manifest_rejects_code_unsafe_steps_and_builtin_shadowing(tmp_path):
    validate_manifest(manifest())
    for change in (
        lambda d: d.update({"python": "print(1)"}),
        lambda d: d["commands"][0].update(
            {"steps": [{"command": "run_code", "code": "print(1)"}]}
        ),
        lambda d: d["commands"][0].update({"phrase": "uyu"}),
        lambda d: d.update({"schema": True}),
        lambda d: d.update({"id": "../evil"}),
    ):
        data = manifest()
        change(data)
        with pytest.raises(CommandError):
            validate_manifest(data)


def test_plugin_install_enable_match_and_persist(tmp_path):
    store = NoraStore(tmp_path / "state.json")
    registry = PluginRegistry(tmp_path / "plugins", store)
    source = tmp_path / "source.json"
    source.write_text(json.dumps(manifest()), encoding="utf-8")
    installed = registry.install(source)
    assert installed.id == "study"
    assert registry.match("stüdyo zamanı") is None
    store.set_plugin_enabled("study", True)
    matched = registry.match("Hey Nora, stüdyo zamanı!")
    assert matched is not None and matched[1].name == "başla"
    assert NoraStore(tmp_path / "state.json").enabled_plugins == ["study"]
    with pytest.raises(CommandError):
        registry.install(source)
    registry.install(source, overwrite=True)
    registry.delete("study")
    assert store.enabled_plugins == []
    assert registry.match("stüdyo zamanı") is None


def test_plugin_limits_and_symlink_are_rejected(tmp_path):
    store = NoraStore(tmp_path / "state.json")
    registry = PluginRegistry(tmp_path / "plugins", store)
    registry.directory.mkdir()
    link = registry.directory / "evil.json"
    target = tmp_path / "target.json"
    target.write_text(json.dumps(manifest("evil")), encoding="utf-8")
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("symlink unsupported")
    manifests, errors = registry.load_all()
    assert manifests == [] and errors
    data = manifest()
    data["commands"] = [
        {**data["commands"][0], "name": f"komut {i}", "phrase": f"özel ifade {i}"}
        for i in range(13)
    ]
    with pytest.raises(CommandError):
        validate_manifest(data)


def test_shipped_example_plugin_is_valid():
    from pathlib import Path

    data = json.loads(Path("docs/plugins/study-pack.json").read_text(encoding="utf-8"))
    assert validate_manifest(data).id == "study-pack"


def test_plugin_phrase_conflicts_are_rejected_on_install_and_match(tmp_path):
    store = NoraStore(tmp_path / "state.json")
    registry = PluginRegistry(tmp_path / "plugins", store)
    first = tmp_path / "first.json"
    first.write_text(json.dumps(manifest("study")), encoding="utf-8")
    registry.install(first)
    second = tmp_path / "second.json"
    second.write_text(json.dumps(manifest("other")), encoding="utf-8")
    with pytest.raises(CommandError, match="çakışıyor"):
        registry.install(second)
    # Simulate a manually placed conflicting pack: it must never silently run.
    registry.directory.mkdir(exist_ok=True)
    (registry.directory / "other.json").write_text(
        json.dumps(manifest("other")), encoding="utf-8"
    )
    store.set_plugin_enabled("study", True)
    store.set_plugin_enabled("other", True)
    with pytest.raises(CommandError, match="çakış"):
        registry.match("stüdyo zamanı")
    with pytest.raises(CommandError, match="çakış"):
        registry.command_steps("study", "başla")
    assert "Çakışan ifadeler" in registry.listing()


def test_plugin_filename_mismatch_and_limit_are_safe(tmp_path):
    store = NoraStore(tmp_path / "state.json")
    registry = PluginRegistry(tmp_path / "plugins", store)
    registry.directory.mkdir()
    (registry.directory / "wrong.json").write_text(
        json.dumps(manifest("study")), encoding="utf-8"
    )
    manifests, errors = registry.load_all()
    assert manifests == [] and any("dosya adıyla" in error for error in errors)
    for i in range(21):
        (registry.directory / f"p{i}.json").write_text(
            json.dumps(manifest(f"p{i}")), encoding="utf-8"
        )
    manifests, errors = registry.load_all()
    assert manifests == [] and any("sınırı" in error for error in errors)
