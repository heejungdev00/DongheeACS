import sqlite3
import json
from datetime import datetime


class LogDB:
    def __init__(self, path="logs.db"):
        self.path = path
        self._init()

    def _init(self):
        with sqlite3.connect(self.path) as conn:
            # 기본 로그 테이블
            conn.execute("""
                CREATE TABLE IF NOT EXISTS logs (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    created    TEXT,
                    coil_addr  INTEGER,
                    fromnode  TEXT,
                    tonode    TEXT,
                    payload    TEXT,
                    mission_id TEXT,
                    success    INTEGER
                )
            """)
            # 미션 추적 테이블
            conn.execute("""
                CREATE TABLE IF NOT EXISTS mission_tracking (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    mission_id  TEXT UNIQUE,
                    signal      TEXT,        -- JSON 직렬화된 신호 정보
                    status      TEXT,        -- PENDING / RUNNING / DONE / FAILED
                    retry_count INTEGER DEFAULT 0,
                    created_at  TEXT,
                    updated_at  TEXT
                )
            """)

    # ── 로그 ──────────────────────────────────────────
    def insert(self, signal: dict, result: dict):
        accepted   = result.get("payload", {}).get("acceptedmissions", [])
        mission_id = accepted[0] if accepted else None
        success    = 1 if mission_id else 0
        with sqlite3.connect(self.path) as conn:
            conn.execute("""
                INSERT INTO logs
                (created, coil_addr, fromnode, tonode, payload, mission_id, success)
                VALUES (?,?,?,?,?,?,?)
            """, (
                datetime.now().isoformat(),
                signal.get("coil_address"),
                signal.get("fromnode"),
                signal.get("tonode") or signal.get("tostation"),
                signal.get("payload"),
                mission_id,
                success,
            ))

    def get_all(self, limit=100):
        with sqlite3.connect(self.path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM logs ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
            return [dict(r) for r in rows]

    # ── 미션 추적 ──────────────────────────────────────
    def track_mission(self, mission_id: str, signal: dict):
        """미션 생성 시 추적 시작"""
        now = datetime.now().isoformat()
        with sqlite3.connect(self.path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO mission_tracking
                (mission_id, signal, status, retry_count, created_at, updated_at)
                VALUES (?,?,?,?,?,?)
            """, (
                mission_id,
                json.dumps(signal, ensure_ascii=False),
                "RUNNING",
                0,
                now,
                now,
            ))

    def update_mission_status(self, mission_id: str, status: str):
        """미션 상태 업데이트 (RUNNING / DONE / FAILED)"""
        with sqlite3.connect(self.path) as conn:
            conn.execute("""
                UPDATE mission_tracking
                SET status = ?, updated_at = ?
                WHERE mission_id = ?
            """, (status, datetime.now().isoformat(), mission_id))

    def increment_retry(self, mission_id: str):
        with sqlite3.connect(self.path) as conn:
            conn.execute("""
                UPDATE mission_tracking
                SET retry_count = retry_count + 1, updated_at = ?
                WHERE mission_id = ?
            """, (datetime.now().isoformat(), mission_id))

    def get_running_missions(self):
        """현재 RUNNING 상태인 미션 목록"""
        with sqlite3.connect(self.path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT * FROM mission_tracking
                WHERE status = 'RUNNING'
            """).fetchall()
            result = []
            for r in rows:
                d = dict(r)
                d["signal"] = json.loads(d["signal"])
                result.append(d)
            return result

    def get_tracking_all(self, limit=100):
        with sqlite3.connect(self.path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT * FROM mission_tracking
                ORDER BY id DESC LIMIT ?
            """, (limit,)).fetchall()
            result = []
            for r in rows:
                d = dict(r)
                d["signal"] = json.loads(d["signal"])
                result.append(d)
            return result
        
    def delete_tracking(self, mission_id: str) -> bool:
        """
        추적 테이블에서 미션 레코드를 완전히 삭제합니다.
        (재생성 로직 중지 + 추적 목록에서 제거)
        ANT 서버의 실제 미션에는 영향 없음.
        """
        with sqlite3.connect(self.path) as conn:
            cursor = conn.execute(
                "DELETE FROM mission_tracking WHERE mission_id = ?",
                (mission_id,)
            )
            return cursor.rowcount > 0
        
    def get_tracking_by_id(self, mission_id: str) -> dict | None:
        """현재 DB에 저장되어 있는 특정 미션의 추적 데이터를 그대로 가져옵니다."""
        with sqlite3.connect(self.path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM mission_tracking WHERE mission_id = ?", 
                (mission_id,)
            ).fetchone()
            
            if row:
                d = dict(row)
                d["signal"] = json.loads(d["signal"])  # 이미 DB에 있는 signal 문자열을 딕셔너리로 변환
                return d
            return None