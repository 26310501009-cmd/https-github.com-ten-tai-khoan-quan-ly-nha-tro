import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from auth import hash_password


DEFAULT_DB_PATH = Path(os.environ.get("BOARDING_HOUSE_DB", "data/boarding_house.db"))


@contextmanager
def connect(db_path=DEFAULT_DB_PATH):
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize(db_path=DEFAULT_DB_PATH):
    with connect(db_path) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                username TEXT NOT NULL UNIQUE,
                full_name TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK (role IN ('chu_tro', 'quan_ly'))
            );
            CREATE TABLE IF NOT EXISTS rooms (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                room_type TEXT NOT NULL DEFAULT 'Phòng đơn',
                price INTEGER NOT NULL CHECK (price >= 0),
                area REAL NOT NULL DEFAULT 0 CHECK (area >= 0),
                status TEXT NOT NULL DEFAULT 'Trống'
                    CHECK (status IN ('Trống', 'Đang thuê', 'Bảo trì'))
            );
            CREATE TABLE IF NOT EXISTS tenants (
                id INTEGER PRIMARY KEY,
                full_name TEXT NOT NULL,
                national_id TEXT NOT NULL DEFAULT '',
                phone TEXT NOT NULL,
                hometown TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS contracts (
                id INTEGER PRIMARY KEY,
                room_id INTEGER NOT NULL REFERENCES rooms(id),
                tenant_id INTEGER NOT NULL REFERENCES tenants(id),
                start_date TEXT NOT NULL,
                expires_on TEXT,
                end_date TEXT,
                rent INTEGER NOT NULL CHECK (rent >= 0),
                deposit INTEGER NOT NULL CHECK (deposit >= 0),
                deposit_returned INTEGER NOT NULL DEFAULT 0 CHECK (deposit_returned >= 0),
                status TEXT NOT NULL DEFAULT 'Đang hiệu lực'
                    CHECK (status IN ('Đang hiệu lực', 'Đã kết thúc')),
                CHECK (deposit_returned <= deposit)
            );
            CREATE UNIQUE INDEX IF NOT EXISTS one_active_contract_per_room
                ON contracts(room_id) WHERE status = 'Đang hiệu lực';
            CREATE TABLE IF NOT EXISTS meter_readings (
                id INTEGER PRIMARY KEY,
                room_id INTEGER NOT NULL REFERENCES rooms(id),
                month TEXT NOT NULL,
                electricity_old REAL NOT NULL CHECK (electricity_old >= 0),
                electricity_new REAL NOT NULL CHECK (electricity_new >= electricity_old),
                water_old REAL NOT NULL CHECK (water_old >= 0),
                water_new REAL NOT NULL CHECK (water_new >= water_old),
                UNIQUE(room_id, month)
            );
            CREATE TABLE IF NOT EXISTS bills (
                id INTEGER PRIMARY KEY,
                room_id INTEGER NOT NULL REFERENCES rooms(id),
                contract_id INTEGER NOT NULL REFERENCES contracts(id),
                month TEXT NOT NULL,
                rent_amount INTEGER NOT NULL CHECK (rent_amount >= 0),
                electricity_amount INTEGER NOT NULL CHECK (electricity_amount >= 0),
                water_amount INTEGER NOT NULL CHECK (water_amount >= 0),
                service_amount INTEGER NOT NULL DEFAULT 0 CHECK (service_amount >= 0),
                total INTEGER NOT NULL CHECK (total >= 0),
                status TEXT NOT NULL DEFAULT 'Chưa thanh toán'
                    CHECK (status IN ('Chưa thanh toán', 'Đã thanh toán')),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                paid_at TEXT,
                UNIQUE(room_id, month)
            );
            """
        )
        users = [
            ("chu_hung", "Chủ trọ Hùng", "HungPhat@2026", "chu_tro"),
            ("chi_lan", "Quản lý Lan", "Lan@2026", "quan_ly"),
        ]
        for username, name, password, role in users:
            exists = connection.execute(
                "SELECT 1 FROM users WHERE username = ?", (username,)
            ).fetchone()
            if not exists:
                connection.execute(
                    """INSERT INTO users (username, full_name, password_hash, role)
                       VALUES (?, ?, ?, ?)""",
                    (username, name, hash_password(password), role),
                )
        connection.executemany(
            """
            INSERT OR IGNORE INTO rooms (name, room_type, price, area)
            VALUES (?, ?, ?, ?)
            """,
            [
                (f"P.{number}", "Phòng đôi" if number % 5 == 0 else "Phòng đơn",
                 2500000 if number % 5 == 0 else 1800000, 25 if number % 5 == 0 else 18)
                for number in range(101, 121)
            ],
        )
