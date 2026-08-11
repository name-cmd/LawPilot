"""用户注册表：账号信息 + 密码哈希存储 + 每用户 API Key。

存储位置：data/users/users.json（不入库，见 .gitignore）。
- 密码用 hashlib.pbkdf2_hmac（sha256, 10 万次迭代）+ 随机盐哈希，不存明文；
- 首次启动自动种子测试账号（root/user1/user2，密码均 123456，全部哈希存储）；
- 内存缓存 + 原子写（tmp + rename），JSON 损坏回退空表，不阻塞服务启动。
"""
import hashlib
import json
import os
import re
import secrets
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from src.config import Config

# 用户名规则：3-20 位字母/数字/下划线（首字符必须是字母或下划线）
_USERNAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{2,19}$")
_PBKDF2_ITERATIONS = 100_000


@dataclass
class User:
    username: str
    password_hash: str
    salt: str
    display_name: str
    api_key: Optional[str] = None  # 用户自配百炼 Key；None = 回退服务端 .env
    created_at: int = 0

    def to_dict(self) -> dict:
        return {
            "username": self.username,
            "password_hash": self.password_hash,
            "salt": self.salt,
            "display_name": self.display_name,
            "api_key": self.api_key,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "User":
        return cls(
            username=d["username"],
            password_hash=d["password_hash"],
            salt=d["salt"],
            display_name=d.get("display_name", d["username"]),
            api_key=d.get("api_key"),
            created_at=d.get("created_at", 0),
        )


def hash_password(password: str, salt: Optional[str] = None) -> tuple[str, str]:
    """pbkdf2 哈希密码，返回 (password_hash, salt)。盐缺省时随机生成。"""
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), _PBKDF2_ITERATIONS)
    return digest.hex(), salt


def validate_username(username: str) -> Optional[str]:
    """校验用户名，非法时返回中文原因，合法返回 None。"""
    if not _USERNAME_RE.match(username):
        return "用户名需为 3-20 位字母/数字/下划线（以字母或下划线开头）"
    return None


def validate_password(password: str) -> Optional[str]:
    if len(password) < 6:
        return "密码至少 6 位"
    return None


class UsernameTakenError(ValueError):
    """用户名已被注册（HTTP 409）。"""


class UserStore:
    """用户注册表：内存缓存 + JSON 落盘（单文件 data/users/users.json）。"""

    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path or Config.USER_DATA_DIR) / "users.json"
        self._lock = threading.RLock()
        self._users: dict[str, User] = {}
        self._load()

    # ── 落盘与恢复 ──────────────────────────────────────────────
    def _load(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8"))
                self._users = {u["username"]: User.from_dict(u) for u in raw.get("users", [])}
            except (json.JSONDecodeError, KeyError, ValueError):
                # JSON 损坏：回退空表，不阻塞服务启动
                self._users = {}
        # 种子账号：缺失才补（已存在账号不动，保留其资料与 Key）
        changed = False
        for seed in ("root", "user1", "user2"):
            if seed not in self._users:
                h, s = hash_password("123456")
                self._users[seed] = User(
                    username=seed,
                    password_hash=h,
                    salt=s,
                    display_name=seed,
                    created_at=int(time.time()),
                )
                changed = True
        if changed:
            self._save()

    def _save(self) -> None:
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps({"users": [u.to_dict() for u in self._users.values()]}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(tmp, self.path)  # 原子替换，防止写一半损坏

    # ── 查询与操作 ──────────────────────────────────────────────
    def get_user(self, username: str) -> Optional[User]:
        with self._lock:
            return self._users.get(username)

    def authenticate(self, username: str, password: str) -> Optional[User]:
        with self._lock:
            user = self._users.get(username)
            if not user:
                return None
            digest, _ = hash_password(password, user.salt)
            if secrets.compare_digest(digest, user.password_hash):
                return user
            return None

    def register(self, username: str, password: str) -> User:
        """注册新用户；用户名非法/重名/密码过短抛 ValueError（中文原因）。"""
        reason = validate_username(username)
        if reason:
            raise ValueError(reason)
        reason = validate_password(password)
        if reason:
            raise ValueError(reason)
        with self._lock:
            if username in self._users:
                raise UsernameTakenError("用户名已被注册")
            h, s = hash_password(password)
            user = User(
                username=username,
                password_hash=h,
                salt=s,
                display_name=username,
                created_at=int(time.time()),
            )
            self._users[username] = user
            self._save()
            return user

    def update_api_key(self, username: str, api_key: Optional[str]) -> None:
        """更新用户自配 API Key（空字符串视为清除，回退服务端 Key）。"""
        with self._lock:
            user = self._users.get(username)
            if not user:
                return
            user.api_key = (api_key or "").strip() or None
            self._save()

    def change_password(self, username: str, new_password: str) -> None:
        """修改密码：重新生成盐 + 哈希并落盘。"""
        with self._lock:
            user = self._users.get(username)
            if not user:
                return
            h, s = hash_password(new_password)
            user.password_hash = h
            user.salt = s
            self._save()

    def display_name(self, username: str) -> str:
        user = self._users.get(username)
        return user.display_name if user else username
