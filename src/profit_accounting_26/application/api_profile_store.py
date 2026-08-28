from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from uuid import uuid4

from profit_accounting_26.shared import ensure_data_dir_allowed


VISUAL_AI = "visual_ai"
LOCAL_REESTIMATE = "local_reestimate"
IMAGE_RISK = "image_risk"

PROVIDER_PRESETS = {
    "DeepSeek": "https://api.deepseek.com/chat/completions",
    "GLM": "https://open.bigmodel.cn/api/paas/v4/chat/completions",
    "阿里云百炼": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "OpenAI": "https://api.openai.com/v1/chat/completions",
    "自定义": "",
}


@dataclass(frozen=True, slots=True)
class ApiProfile:
    profile_id: str
    display_name: str
    provider: str
    api_url: str
    model_name: str

    @classmethod
    def create(
        cls,
        *,
        display_name: str,
        provider: str,
        api_url: str,
        model_name: str,
    ) -> "ApiProfile":
        return cls(
            profile_id=uuid4().hex,
            display_name=display_name.strip(),
            provider=provider if provider in PROVIDER_PRESETS else "自定义",
            api_url=api_url.strip(),
            model_name=model_name.strip(),
        )


class ApiProfileStore:
    """Public API profiles and private keys kept inside the chosen data directory."""

    def __init__(self, data_dir: str | Path) -> None:
        self.data_dir = Path(data_dir)
        self.public_path = self.data_dir / "api_profiles.json"
        self.key_path = self.data_dir / "api_keys.local.json"

    @staticmethod
    def _empty_public() -> dict:
        return {
            "profiles": [],
            "button_bindings": {VISUAL_AI: None, LOCAL_REESTIMATE: None, IMAGE_RISK: None},
        }

    def load_public(self) -> dict:
        if not self.public_path.is_file():
            return self._empty_public()
        try:
            data = json.loads(self.public_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return self._empty_public()
        if not isinstance(data, dict):
            return self._empty_public()
        data.setdefault("profiles", [])
        data.setdefault("button_bindings", {})
        data["button_bindings"].setdefault(VISUAL_AI, None)
        data["button_bindings"].setdefault(LOCAL_REESTIMATE, None)
        data["button_bindings"].setdefault(IMAGE_RISK, None)
        return data

    def load_keys(self) -> dict[str, str]:
        if not self.key_path.is_file():
            return {}
        try:
            data = json.loads(self.key_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return {str(key): str(value) for key, value in data.items()} if isinstance(data, dict) else {}

    @staticmethod
    def _atomic_write(path: Path, data: dict) -> None:
        # 生命周期守卫：写入目标位于数据目录内，废弃目录不得被陈旧会话复活
        ensure_data_dir_allowed(path.parent)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)

    def save_profile(self, profile: ApiProfile, api_key: str) -> None:
        public = self.load_public()
        profiles = public["profiles"]
        payload = asdict(profile)
        for index, existing in enumerate(profiles):
            if existing.get("profile_id") == profile.profile_id:
                profiles[index] = payload
                break
        else:
            profiles.append(payload)
        self._atomic_write(self.public_path, public)

        keys = self.load_keys()
        if api_key.strip():
            keys[profile.profile_id] = api_key.strip()
        else:
            keys.pop(profile.profile_id, None)
        self._atomic_write(self.key_path, keys)

    def delete_profile(self, profile_id: str) -> bool:
        """真实持久化删除一个 API 配置。

        一次操作完成：
        1. 从 api_profiles.json 的 profiles 中删除该 profile；
        2. 从 api_keys.local.json 删除该 profile 的 API Key；
        3. VISUAL_AI / LOCAL_REESTIMATE 若绑定该 profile 则清空绑定；
        4. 两个文件均原子写入；不影响其他配置；
        5. profile 不存在时安全返回 False，不崩溃。
        """
        if not profile_id:
            return False
        public = self.load_public()
        profiles = [item for item in public["profiles"] if isinstance(item, dict)]
        remaining = [item for item in profiles if item.get("profile_id") != profile_id]
        existed = len(remaining) != len(profiles)
        public["profiles"] = remaining
        bindings = public["button_bindings"]
        binding_cleared = False
        for action in (VISUAL_AI, LOCAL_REESTIMATE, IMAGE_RISK):
            if bindings.get(action) == profile_id:
                bindings[action] = None
                binding_cleared = True
        keys = self.load_keys()
        key_existed = profile_id in keys
        if key_existed:
            keys.pop(profile_id, None)
        if not (existed or binding_cleared or key_existed):
            return False
        self._atomic_write(self.public_path, public)
        self._atomic_write(self.key_path, keys)
        return existed

    def bind(self, action: str, profile_id: str | None) -> None:
        if action not in {VISUAL_AI, LOCAL_REESTIMATE, IMAGE_RISK}:
            raise ValueError("未知 API 绑定")
        public = self.load_public()
        valid_ids = {str(item.get("profile_id")) for item in public["profiles"]}
        if profile_id and profile_id not in valid_ids:
            raise ValueError("绑定的 API 配置不存在")
        public["button_bindings"][action] = profile_id
        self._atomic_write(self.public_path, public)

    def bound_profile(self, action: str) -> tuple[ApiProfile, str] | None:
        public = self.load_public()
        profile_id = public["button_bindings"].get(action)
        if not profile_id:
            return None
        raw = next((item for item in public["profiles"] if item.get("profile_id") == profile_id), None)
        if not isinstance(raw, dict):
            return None
        try:
            profile = ApiProfile(**raw)
        except TypeError:
            return None
        return profile, self.load_keys().get(profile.profile_id, "")

