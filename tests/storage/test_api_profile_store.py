from profit_accounting_26.application.api_profile_store import (
    ApiProfile,
    ApiProfileStore,
    LOCAL_REESTIMATE,
    VISUAL_AI,
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
