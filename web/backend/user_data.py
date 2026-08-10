"""每用户数据存储：会话 / 收藏 / 个人资料（改进指南阶段三 3.2）。

存储位置：data/users/{username}.json（不入库，见 .gitignore）。
- 用户名在注册时已校验（3-20 位字母/数字/下划线），天然可安全用作文件名；
- 内存按用户名缓存 + 原子写（tmp + rename），JSON 损坏回退空数据；
- 资料与会话分开读写：会话整包频繁保存不会覆盖资料（反之亦然）。
"""
import json
import os
import threading
from pathlib import Path
from typing import Any, Dict, Optional

from src.config import Config


class UserDataStore:
    def __init__(self, path: Optional[Path] = None):
        self.dir = Path(path or Config.USER_DATA_DIR)
        self._lock = threading.RLock()
        self._cache: Dict[str, Dict[str, Any]] = {}
        self.dir.mkdir(parents=True, exist_ok=True)

    def _file(self, username: str) -> Path:
        return self.dir / f"{username}.json"

    def _load_raw(self, username: str) -> Dict[str, Any]:
        """读取该用户数据（损坏回退空数据）；不存在返回空 dict + exists=False。"""
        path = self._file(username)
        if not path.exists():
            return {}
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            return raw if isinstance(raw, dict) else {}
        except (json.JSONDecodeError, ValueError):
            return {}

    def exists(self, username: str) -> bool:
        with self._lock:
            if username in self._cache:
                return True
            return self._file(username).exists()

    def load(self, username: str) -> Dict[str, Any]:
        """返回 {sessions, favorites, profile, exists}（调用方不持有的键自行补默认）。"""
        with self._lock:
            if username not in self._cache:
                self._cache[username] = self._load_raw(username)
            data = self._cache[username]
            return {
                "sessions": data.get("sessions", []),
                "favorites": data.get("favorites", []),
                "profile": data.get("profile", {}),
                "exists": bool(data),
            }

    def save_data(self, username: str, sessions: list, favorites: list) -> None:
        """整包保存会话 + 收藏（不覆盖资料；无资料时保留空 profile 键）。"""
        with self._lock:
            data = self._cache.get(username, self._load_raw(username))
            data["sessions"] = sessions
            data["favorites"] = favorites
            data.setdefault("profile", {})
            self._cache[username] = data
            self._save(username, data)

    def get_profile(self, username: str) -> Dict[str, Any]:
        with self._lock:
            data = self._cache.get(username, self._load_raw(username))
            return data.get("profile", {})

    def save_profile(self, username: str, patch: Dict[str, Any]) -> Dict[str, Any]:
        """合并保存资料字段（None 字段忽略，不清除已有值）。返回保存后的完整资料。"""
        with self._lock:
            data = self._cache.get(username, self._load_raw(username))
            profile = dict(data.get("profile", {}))
            for k, v in patch.items():
                if v is not None:
                    profile[k] = v
            data["profile"] = profile
            data.setdefault("sessions", [])
            data.setdefault("favorites", [])
            self._cache[username] = data
            self._save(username, data)
            return profile

    def _save(self, username: str, data: Dict[str, Any]) -> None:
        path = self._file(username)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(tmp, path)  # 原子替换，防止写一半损坏
