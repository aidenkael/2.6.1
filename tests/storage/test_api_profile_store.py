import json

from profit_accounting_26.application.api_profile_store import (
    ApiProfile,
    ApiProfileStore,
    LOCAL_REESTIMATE,
    VISUAL_AI,
)


def _make_profile(display_name: str) -> ApiProfile:
    return ApiProfile.create(
        display_name=display_name,
        provider="OpenAI",
        api_url="https://api.example.test/v1/chat/completions",
        model_name="vision-model",
    )


def test_profiles_and_keys_are_separate_and_bound_in_data_directory(tmp_path):
    store = ApiProfileStore(tmp_path)
    profile = ApiProfile.create(
        display_name="视觉模型",
        provider="OpenAI",
        api_url="https://api.example.test/v1/chat/completions",
        model_name="vision-model",
    )
    store.save_profile(profile, "secret-key")
    store.bind(VISUAL_AI, profile.profile_id)
    store.bind(LOCAL_REESTIMATE, profile.profile_id)

    public = store.public_path.read_text(encoding="utf-8")
    assert "secret-key" not in public
    assert store.key_path.is_file()
    assert store.bound_profile(VISUAL_AI) == (profile, "secret-key")
    assert store.bound_profile(LOCAL_REESTIMATE) == (profile, "secret-key")


def test_delete_profile_removes_profile_key_and_bindings(tmp_path):
    """第四轮 B8-12：删除后当前列表/文件/key/绑定全部不存在，其他配置不受影响。"""
    store = ApiProfileStore(tmp_path)
    profile = _make_profile("待删除")
    store.save_profile(profile, "secret-key")
    store.bind(VISUAL_AI, profile.profile_id)
    store.bind(LOCAL_REESTIMATE, profile.profile_id)
    other = _make_profile("保留配置")
    store.save_profile(other, "other-key")

    assert store.delete_profile(profile.profile_id) is True

    # 当前列表不再包含该配置
    public = store.load_public()
    assert all(item.get("profile_id") != profile.profile_id for item in public["profiles"])
    # api_profiles.json 磁盘文件中不存在
    raw_public = json.loads(store.public_path.read_text(encoding="utf-8"))
    assert all(item.get("profile_id") != profile.profile_id for item in raw_public["profiles"])
    # api_keys.local.json 中对应 key 已删除
    assert profile.profile_id not in store.load_keys()
    raw_keys = json.loads(store.key_path.read_text(encoding="utf-8"))
    assert profile.profile_id not in raw_keys
    # VISUAL_AI / LOCAL_REESTIMATE 绑定已清空
    assert store.bound_profile(VISUAL_AI) is None
    assert store.bound_profile(LOCAL_REESTIMATE) is None
    # 其他配置与其 key 不受影响
    assert any(item.get("profile_id") == other.profile_id for item in raw_public["profiles"])
    assert store.load_keys().get(other.profile_id) == "other-key"


def test_delete_profile_safe_when_missing(tmp_path):
    """第四轮 B 补充：profile 不存在/空 id 时安全返回，不崩溃。"""
    store = ApiProfileStore(tmp_path)
    keep = _make_profile("保留配置")
    store.save_profile(keep, "keep-key")
    assert store.delete_profile("missing-id") is False
    assert store.delete_profile("") is False
    assert store.load_keys().get(keep.profile_id) == "keep-key"


def test_delete_profile_persists_across_store_restart(tmp_path):
    """第四轮 B13：丢弃实例后新建 ApiProfileStore 重新读取，删除仍然生效。"""
    store = ApiProfileStore(tmp_path)
    profile = _make_profile("重启验证")
    store.save_profile(profile, "secret-key")
    store.bind(VISUAL_AI, profile.profile_id)
    store.bind(LOCAL_REESTIMATE, profile.profile_id)
    assert store.delete_profile(profile.profile_id) is True

    fresh = ApiProfileStore(tmp_path)
    assert all(item.get("profile_id") != profile.profile_id for item in fresh.load_public()["profiles"])
    assert profile.profile_id not in fresh.load_keys()
    assert fresh.bound_profile(VISUAL_AI) is None
    assert fresh.bound_profile(LOCAL_REESTIMATE) is None
