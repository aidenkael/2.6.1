from pathlib import Path

from profit_accounting_26.application import SettingsService


def test_forwarder_stable_id_archive_and_restore():
    forwarder = SettingsService.new_forwarder("测试货代", 88, 7, 8000)
    archived = SettingsService.archive(forwarder)
    restored = SettingsService.restore(archived)
    assert archived.id == forwarder.id == restored.id
    assert archived.archived and not archived.enabled
    assert not restored.archived and not restored.enabled


def test_settings_can_be_copied_to_new_data_directory(tmp_path: Path):
    source = SettingsService(tmp_path / "old" / "settings.json")
    values = {"vision_api_endpoint": "https://example.test/v1", "vision_api_model": "vision-model"}
    source.save(values)

    SettingsService.save_copy(source.load(), tmp_path / "new" / "settings.json")

    migrated = SettingsService(tmp_path / "new" / "settings.json").load()
    assert migrated["vision_api_endpoint"] == "https://example.test/v1"
    assert migrated["vision_api_model"] == "vision-model"
