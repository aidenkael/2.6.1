import json

from profit_accounting_26.application.api_profile_store import (
    ApiProfile,
    ApiProfileStore,
    IMAGE_RISK,
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
    store.bind(IMAGE_RISK, profile.profile_id)

    public = store.public_path.read_text(encoding="utf-8")
    assert "secret-key" not in public
    assert store.key_path.is_file()
    assert store.bound_profile(VISUAL_AI) == (profile, "secret-key")
    assert store.bound_profile(LOCAL_REESTIMATE) == (profile, "secret-key")
    assert store.bound_profile(IMAGE_RISK) == (profile, "secret-key")


def test_delete_profile_removes_profile_key_and_bindings(tmp_path):
    """第四轮 B8-12：删除后当前列表/文件/key/绑定全部不存在，其他配置不受影响。"""
    store = ApiProfileStore(tmp_path)
    profile = _make_profile("待删除")
    store.save_profile(profile, "secret-key")
    store.bind(VISUAL_AI, profile.profile_id)
    store.bind(LOCAL_REESTIMATE, profile.profile_id)
    store.bind(IMAGE_RISK, profile.profile_id)
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
    # 三个 binding 绑定已清空
    assert store.bound_profile(VISUAL_AI) is None
    assert store.bound_profile(LOCAL_REESTIMATE) is None
    assert store.bound_profile(IMAGE_RISK) is None
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
    store.bind(IMAGE_RISK, profile.profile_id)
    assert store.delete_profile(profile.profile_id) is True

    fresh = ApiProfileStore(tmp_path)
    assert all(item.get("profile_id") != profile.profile_id for item in fresh.load_public()["profiles"])
    assert profile.profile_id not in fresh.load_keys()
    assert fresh.bound_profile(VISUAL_AI) is None
    assert fresh.bound_profile(LOCAL_REESTIMATE) is None
    assert fresh.bound_profile(IMAGE_RISK) is None


def test_new_config_default_image_risk_is_none(tmp_path):
    """新配置默认 IMAGE_RISK=None。"""
    store = ApiProfileStore(tmp_path)
    public = store.load_public()
    assert public["button_bindings"].get(IMAGE_RISK) is None


def test_old_config_missing_image_risk_still_reads(tmp_path):
    """旧配置缺少 IMAGE_RISK 仍正常读取。"""
    store = ApiProfileStore(tmp_path)
    # 手动写入旧配置（不含 IMAGE_RISK）
    old_data = {
        "profiles": [],
        "button_bindings": {VISUAL_AI: None, LOCAL_REESTIMATE: None},
    }
    store.public_path.write_text(json.dumps(old_data), encoding="utf-8")
    public = store.load_public()
    assert public["button_bindings"].get(VISUAL_AI) is None
    assert public["button_bindings"].get(LOCAL_REESTIMATE) is None
    assert public["button_bindings"].get(IMAGE_RISK) is None


def test_three_bindings_save_and_restore(tmp_path):
    """三个 binding 都可保存/恢复。"""
    store = ApiProfileStore(tmp_path)
    p = _make_profile("全绑定")
    store.save_profile(p, "key")
    store.bind(VISUAL_AI, p.profile_id)
    store.bind(LOCAL_REESTIMATE, p.profile_id)
    store.bind(IMAGE_RISK, p.profile_id)
    assert store.bound_profile(VISUAL_AI) == (p, "key")
    assert store.bound_profile(LOCAL_REESTIMATE) == (p, "key")
    assert store.bound_profile(IMAGE_RISK) == (p, "key")


def test_same_profile_bound_to_all_three(tmp_path):
    """同一 Profile 可同时绑定三个功能。"""
    store = ApiProfileStore(tmp_path)
    p = _make_profile("三合一")
    store.save_profile(p, "key")
    store.bind(VISUAL_AI, p.profile_id)
    store.bind(LOCAL_REESTIMATE, p.profile_id)
    store.bind(IMAGE_RISK, p.profile_id)
    public = store.load_public()
    bindings = public["button_bindings"]
    assert bindings[VISUAL_AI] == p.profile_id
    assert bindings[LOCAL_REESTIMATE] == p.profile_id
    assert bindings[IMAGE_RISK] == p.profile_id


def test_image_risk_unbound_no_fallback_visual_ai(tmp_path):
    """图片检测未绑定时明确返回 None，不 fallback VISUAL_AI。"""
    store = ApiProfileStore(tmp_path)
    p = _make_profile("仅视觉")
    store.save_profile(p, "key")
    store.bind(VISUAL_AI, p.profile_id)
    # IMAGE_RISK 未绑定
    assert store.bound_profile(IMAGE_RISK) is None
    assert store.bound_profile(VISUAL_AI) == (p, "key")
