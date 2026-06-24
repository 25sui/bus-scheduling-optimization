"""
JWT 认证模块

提供登录、Token 验证、权限控制功能。
用户数据存储在 users.json（轻量，无需数据库）。
"""

import json
import hashlib
import secrets
from pathlib import Path
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

# ── 配置 ──────────────────────────────────────────────

SECRET_KEY = "bus-scheduling-secret-key-change-in-production-2026"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24

# Bearer token 提取器
security = HTTPBearer()


# ── 用户数据管理（文件型，轻量）────────────────────

def _get_users_file() -> Path:
    """返回 users.json 路径"""
    from src.config import MODEL_DIR
    return MODEL_DIR.parent / "users.json"


def load_users() -> dict:
    """加载用户数据"""
    f = _get_users_file()
    if not f.exists():
        # 初始化默认用户
        default = {
            "admin": {
                "password_hash": _hash_password("admin123"),
                "role": "admin",
                "real_name": "系统管理员",
            },
            "dispatcher": {
                "password_hash": _hash_password("disp123"),
                "role": "dispatcher",
                "real_name": "调度员",
            },
            "viewer": {
                "password_hash": _hash_password("view123"),
                "role": "viewer",
                "real_name": "观察员",
            },
        }
        save_users(default)
        return default
    with open(f, "r", encoding="utf-8") as fp:
        return json.load(fp)


def save_users(users: dict):
    """保存用户数据"""
    f = _get_users_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    with open(f, "w", encoding="utf-8") as fp:
        json.dump(users, fp, ensure_ascii=False, indent=2)


def _hash_password(pwd: str) -> str:
    """SHA-256 密码哈希（简易版，生产环境应用 bcrypt）"""
    return hashlib.sha256(pwd.encode("utf-8")).hexdigest()


# ── Token 工具 ──────────────────────────────────────────────

def create_access_token(username: str, role: str) -> str:
    """生成 JWT access token"""
    expire = datetime.now(timezone.utc) + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    payload = {
        "sub": username,
        "role": role,
        "exp": expire,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    """解码并验证 JWT token"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token 已过期，请重新登录",
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的 Token",
        )


# ── FastAPI 依赖项 ──────────────────────────────────────

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    """验证 Bearer Token，返回当前用户信息"""
    token = credentials.credentials
    payload = decode_token(token)
    users = load_users()
    username = payload.get("sub")
    if username not in users:
        raise HTTPException(status_code=401, detail="用户不存在")
    return {"username": username, "role": payload.get("role")}


def require_role(required_role: str):
    """角色权限依赖工厂"""

    async def _check_role(user: dict = Depends(get_current_user)) -> dict:
        role_hierarchy = {"viewer": 0, "dispatcher": 1, "admin": 2}
        if role_hierarchy.get(user["role"], 0) < role_hierarchy.get(required_role, 99):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"权限不足：需要 {required_role} 及以上角色",
            )
        return user

    return _check_role


# ── 路由注册助手 ──────────────────────────────────────

def register_auth_routes(app):
    """向 FastAPI 应用注册认证路由"""

    @app.post("/api/auth/login")
    def login(username: str = Query(...), password: str = Query(...)):
        """用户登录，返回 JWT token"""
        users = load_users()
        if username not in users:
            raise HTTPException(status_code=401, detail="用户名或密码错误")
        stored_hash = users[username]["password_hash"]
        if stored_hash != _hash_password(password):
            raise HTTPException(status_code=401, detail="用户名或密码错误")
        role = users[username].get("role", "viewer")
        token = create_access_token(username, role)
        return {
            "access_token": token,
            "token_type": "bearer",
            "expires_in": ACCESS_TOKEN_EXPIRE_HOURS * 3600,
            "username": username,
            "role": role,
        }

    @app.get("/api/auth/me")
    def get_me(user: dict = Depends(get_current_user)):
        """获取当前登录用户信息"""
        users = load_users()
        u = users.get(user["username"], {})
        return {
            "username": user["username"],
            "role": user["role"],
            "real_name": u.get("real_name", ""),
        }

    @app.post("/api/auth/change-password")
    def change_password(
        old_password: str = Query(...),
        new_password: str = Query(...),
        user: dict = Depends(require_role("viewer")),
    ):
        """修改当前用户密码"""
        users = load_users()
        u = users.get(user["username"])
        if u["password_hash"] != _hash_password(old_password):
            raise HTTPException(status_code=400, detail="原密码错误")
        u["password_hash"] = _hash_password(new_password)
        save_users(users)
        return {"status": "success", "message": "密码已修改"}
