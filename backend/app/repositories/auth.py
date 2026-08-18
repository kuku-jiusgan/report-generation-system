from typing import Any

from ..database_common import now_iso


class AuthRepositoryMixin:
    """Users, roles, permissions and authentication sessions."""

    def seed_roles(self, roles: list[dict[str, Any]], permissions: dict[str, set[str]]) -> None:
        timestamp = now_iso()
        with self.connect() as connection:
            for role in roles:
                connection.execute(
                    """INSERT INTO auth_roles(code,name,description,immutable,updated_at) VALUES(?,?,?,?,?)
                       ON CONFLICT(code) DO UPDATE SET name=excluded.name,description=excluded.description,
                       immutable=excluded.immutable""",
                    (role["code"], role["name"], role.get("description", ""),
                     int(role.get("immutable", False)), timestamp),
                )
                exists = connection.execute(
                    "SELECT 1 FROM auth_role_permissions WHERE role_code=? LIMIT 1", (role["code"],),
                ).fetchone()
                if not exists:
                    connection.executemany(
                        "INSERT INTO auth_role_permissions(role_code,permission_code,updated_at) VALUES(?,?,?)",
                        [(role["code"], code, timestamp) for code in sorted(permissions.get(role["code"], set()))],
                    )

    def count_users(self) -> int:
        with self.connect() as connection:
            return int(connection.execute("SELECT COUNT(*) FROM auth_users").fetchone()[0])

    def create_user(self, item: dict[str, Any]) -> dict[str, Any]:
        timestamp = now_iso()
        with self.connect() as connection:
            connection.execute(
                """INSERT INTO auth_users(id,username,display_name,password_hash,role_code,enabled,
                   must_change_password,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)""",
                (item["id"], item["username"], item["display_name"], item["password_hash"], item["role_code"],
                 int(item.get("enabled", True)), int(item.get("must_change_password", True)), timestamp, timestamp),
            )
        return self.get_user(item["id"])

    def get_user(self, user_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM auth_users WHERE id=?", (user_id,)).fetchone()
        return dict(row) if row else None

    def get_user_by_username(self, username: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM auth_users WHERE username=? COLLATE NOCASE", (username,),
            ).fetchone()
        return dict(row) if row else None

    def list_users(self, query: str = "") -> list[dict[str, Any]]:
        with self.connect() as connection:
            if query:
                pattern = f"%{query}%"
                rows = connection.execute(
                    """SELECT * FROM auth_users WHERE username LIKE ? OR display_name LIKE ?
                       ORDER BY created_at DESC""", (pattern, pattern),
                ).fetchall()
            else:
                rows = connection.execute("SELECT * FROM auth_users ORDER BY created_at DESC").fetchall()
        return [dict(row) for row in rows]

    def update_user(self, user_id: str, **changes: Any) -> dict[str, Any] | None:
        allowed = {"display_name", "password_hash", "role_code", "enabled", "must_change_password", "last_login_at"}
        values = {key: value for key, value in changes.items() if key in allowed}
        if not values:
            return self.get_user(user_id)
        values["updated_at"] = now_iso()
        with self.connect() as connection:
            connection.execute(
                f"UPDATE auth_users SET {','.join(f'{key}=?' for key in values)} WHERE id=?",
                (*values.values(), user_id),
            )
        return self.get_user(user_id)

    def delete_user_sessions(self, user_id: str) -> None:
        with self.connect() as connection:
            connection.execute("DELETE FROM auth_sessions WHERE user_id=?", (user_id,))

    def delete_user_sessions_for_role(self, role_code: str) -> None:
        with self.connect() as connection:
            connection.execute(
                "DELETE FROM auth_sessions WHERE user_id IN (SELECT id FROM auth_users WHERE role_code=?)",
                (role_code,),
            )

    def create_session(self, token_hash: str, user_id: str, expires_at: str) -> None:
        timestamp = now_iso()
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO auth_sessions(token_hash,user_id,expires_at,created_at,last_seen_at) VALUES(?,?,?,?,?)",
                (token_hash, user_id, expires_at, timestamp, timestamp),
            )

    def get_session_user(self, token_hash: str) -> dict[str, Any] | None:
        timestamp = now_iso()
        with self.connect() as connection:
            row = connection.execute(
                """SELECT u.* FROM auth_sessions s JOIN auth_users u ON u.id=s.user_id
                   WHERE s.token_hash=? AND s.expires_at>? AND u.enabled=1""", (token_hash, timestamp),
            ).fetchone()
            if row:
                connection.execute("UPDATE auth_sessions SET last_seen_at=? WHERE token_hash=?", (timestamp, token_hash))
            else:
                connection.execute("DELETE FROM auth_sessions WHERE token_hash=?", (token_hash,))
        return dict(row) if row else None

    def delete_session(self, token_hash: str) -> None:
        with self.connect() as connection:
            connection.execute("DELETE FROM auth_sessions WHERE token_hash=?", (token_hash,))

    def role_permissions(self, role_code: str) -> set[str]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT permission_code FROM auth_role_permissions WHERE role_code=?", (role_code,),
            ).fetchall()
        return {str(row["permission_code"]) for row in rows}

    def list_roles(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            roles = [dict(row) for row in connection.execute("SELECT * FROM auth_roles ORDER BY code").fetchall()]
        for role in roles:
            role["permissions"] = sorted(self.role_permissions(role["code"]))
        return roles

    def replace_role_permissions(self, role_code: str, permissions: set[str]) -> None:
        timestamp = now_iso()
        with self.connect() as connection:
            connection.execute("DELETE FROM auth_role_permissions WHERE role_code=?", (role_code,))
            connection.executemany(
                "INSERT INTO auth_role_permissions(role_code,permission_code,updated_at) VALUES(?,?,?)",
                [(role_code, code, timestamp) for code in sorted(permissions)],
            )
            connection.execute("UPDATE auth_roles SET updated_at=? WHERE code=?", (timestamp, role_code))

    def backfill_report_ownership(self, user_id: str) -> None:
        with self.connect() as connection:
            connection.execute("UPDATE reports SET created_by=? WHERE created_by IS NULL", (user_id,))
            connection.execute("UPDATE reports SET updated_by=? WHERE updated_by IS NULL", (user_id,))
