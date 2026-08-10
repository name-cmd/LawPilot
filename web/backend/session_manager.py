"""服务端会话管理器（改进指南阶段三 3.1）。

- Token：secrets 安全随机串（32 字节以上），记录所属用户与过期时间；
- 有效期 24 小时（Config.SESSION_TTL_SEC），每次校验通过自动续期（滑动过期）；
- 多端共存：同一用户可多设备同时登录，新登录不吊销旧 Token
  （测试人员公网共用账号场景不会被互踢，见设计文档 §1.3）；
- Token 表持久化 data/users/tokens.json：服务重启后 Token 仍然有效，
  启动时自动清理已过期 Token；
- 内存缓存 + 原子写（tmp + rename），JSON 损坏回退空表，不阻塞服务启动。
"""
import json
import os
import secrets
import threading
import time
from pathlib import Path
from typing import Optional

from src.config import Config


class SessionManager:
    def __init__(self, ttl_sec: Optional[int] = None, path: Optional[Path] = None):
        self.ttl_sec = ttl_sec or Config.SESSION_TTL_SEC
        self.path = Path(path or Config.USER_DATA_DIR) / "tokens.json"
        self._lock = threading.RLock()
        # token -> {"username": str, "expires_at": float}
        self._tokens: dict[str, dict] = {}
        self._load()

    # ── 落盘与恢复 ──────────────────────────────────────────────
    def _load(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8"))
                self._tokens = raw.get("tokens", {})
            except (json.JSONDecodeError, ValueError):
                self._tokens = {}
        # 启动清理过期 Token
        self._cleanup(save=False)

    def _save(self) -> None:
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps({"tokens": self._tokens}, ensure_ascii=False),
            encoding="utf-8",
        )
        os.replace(tmp, self.path)  # 原子替换，防止写一半损坏

    def _cleanup(self, save: bool = True) -> None:
        """删除全部过期 Token（save=False 用于启动时首次清理，避免重复落盘）。"""
        now = time.time()
        expired = [t for t, rec in self._tokens.items() if rec.get("expires_at", 0) <= now]
        if expired:
            for t in expired:
                self._tokens.pop(t, None)
            if save:
                self._save()

    # ── 操作 ────────────────────────────────────────────────────
    def create(self, username: str) -> str:
        """登录成功：签发新 Token。"""
        with self._lock:
            token = secrets.token_urlsafe(32)
            self._tokens[token] = {"username": username, "expires_at": time.time() + self.ttl_sec}
            self._save()
            return token

    def verify(self, token: str) -> Optional[str]:
        """校验 Token：有效返回用户名并自动续期；无效/过期返回 None。"""
        with self._lock:
            rec = self._tokens.get(token)
            if not rec:
                return None
            if rec.get("expires_at", 0) <= time.time():
                self._tokens.pop(token, None)
                self._save()
                return None
            # 滑动续期：有效访问重置过期时间
            rec["expires_at"] = time.time() + self.ttl_sec
            self._save()
            return rec.get("username")

    def revoke(self, token: str) -> None:
        """登出：吊销 Token。"""
        with self._lock:
            if self._tokens.pop(token, None) is not None:
                self._save()

    def active_count(self) -> int:
        with self._lock:
            return len(self._tokens)
