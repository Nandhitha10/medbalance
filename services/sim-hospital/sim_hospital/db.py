"""SQLite database layer for simulated hospital nodes."""

from datetime import date
import logging
import sqlite3
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class HospitalDB:
    """Manages the hospital's private SQLite stock inventory and dispense audit log."""

    def __init__(self, db_path: str = ":memory:"):
        self.db_path = db_path
        self._shared_conn = None
        if db_path == ":memory:":
            self._shared_conn = sqlite3.connect(":memory:", check_same_thread=False)
            self._shared_conn.row_factory = sqlite3.Row
        self._init_tables()

    def get_connection(self) -> sqlite3.Connection:
        if self._shared_conn is not None:
            return self._shared_conn
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_tables(self) -> None:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS hospital_stock (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    drug_code TEXT NOT NULL,
                    batch_no TEXT NOT NULL,
                    expiry TEXT NOT NULL,
                    quantity INTEGER NOT NULL CHECK (quantity >= 0),
                    UNIQUE(drug_code, batch_no)
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS dispense_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    day_index INTEGER NOT NULL,
                    date TEXT NOT NULL,
                    drug_code TEXT NOT NULL,
                    demand INTEGER NOT NULL,
                    dispensed INTEGER NOT NULL,
                    stockout INTEGER NOT NULL
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS transfer_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_id TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    drug_code TEXT NOT NULL,
                    batch_no TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    timestamp TEXT NOT NULL
                )
            """)
            conn.commit()

    def load_initial_stock(self, lots: List[Dict[str, Any]]) -> None:
        """Replace current stock with initial seed inventory."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM hospital_stock")
            for lot in lots:
                cursor.execute("""
                    INSERT OR REPLACE INTO hospital_stock (drug_code, batch_no, expiry, quantity)
                    VALUES (?, ?, ?, ?)
                """, (lot["drug_code"], lot["batch_no"], str(lot["expiry"]), int(lot["quantity"])))
            conn.commit()

    def get_inventory(self) -> List[Dict[str, Any]]:
        """Fetch all lots with positive stock on hand, ordered by earliest expiry first."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT drug_code, batch_no, expiry, quantity
                FROM hospital_stock
                WHERE quantity > 0
                ORDER BY expiry ASC, batch_no ASC
            """)
            return [dict(row) for row in cursor.fetchall()]

    def dispense_fefo(
        self,
        drug_code: str,
        demand: int,
        day_index: int,
        current_date_str: str,
    ) -> Tuple[int, int]:
        """Dispense stock using First-Expiry-First-Out (FEFO) and log any stockouts."""
        remaining_demand = demand
        dispensed_total = 0

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, batch_no, expiry, quantity
                FROM hospital_stock
                WHERE drug_code = ? AND quantity > 0
                ORDER BY expiry ASC, batch_no ASC
            """, (drug_code,))
            rows = cursor.fetchall()

            for row in rows:
                if remaining_demand <= 0:
                    break

                available = row["quantity"]
                qty_to_take = min(available, remaining_demand)

                cursor.execute("""
                    UPDATE hospital_stock
                    SET quantity = quantity - ?
                    WHERE id = ?
                """, (qty_to_take, row["id"]))

                dispensed_total += qty_to_take
                remaining_demand -= qty_to_take

            stockout = max(0, remaining_demand)
            cursor.execute("""
                INSERT INTO dispense_history (day_index, date, drug_code, demand, dispensed, stockout)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (day_index, current_date_str, drug_code, demand, dispensed_total, stockout))
            conn.commit()

        return (dispensed_total, stockout)

    def expire_lots(self, current_date_str: str) -> int:
        """Zero out any lots whose expiry date is less than or equal to current sim date."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) as cnt
                FROM hospital_stock
                WHERE expiry <= ? AND quantity > 0
            """, (current_date_str,))
            count = cursor.fetchone()["cnt"]

            cursor.execute("""
                UPDATE hospital_stock
                SET quantity = 0
                WHERE expiry <= ? AND quantity > 0
            """, (current_date_str,))
            conn.commit()
            return count

    def record_outbound_transfer(
        self,
        order_id: str,
        drug_code: str,
        batch_no: str,
        quantity: int,
        timestamp_str: str,
    ) -> int:
        """Deduct stock for an outbound transfer order."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, quantity
                FROM hospital_stock
                WHERE drug_code = ? AND batch_no = ?
            """, (drug_code, batch_no))
            row = cursor.fetchone()

            if not row or row["quantity"] < quantity:
                raise ValueError(
                    f"Insufficient stock for outbound transfer: have {row['quantity'] if row else 0}, need {quantity}"
                )

            remaining = row["quantity"] - quantity
            cursor.execute("""
                UPDATE hospital_stock
                SET quantity = ?
                WHERE id = ?
            """, (remaining, row["id"]))

            cursor.execute("""
                INSERT INTO transfer_events (order_id, direction, drug_code, batch_no, quantity, timestamp)
                VALUES (?, 'OUTBOUND', ?, ?, ?, ?)
            """, (order_id, drug_code, batch_no, quantity, timestamp_str))
            conn.commit()
            return remaining

    def record_inbound_transfer(
        self,
        order_id: str,
        drug_code: str,
        batch_no: str,
        expiry_str: str,
        quantity: int,
        timestamp_str: str,
    ) -> None:
        """Add arrived stock to local inventory."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO hospital_stock (drug_code, batch_no, expiry, quantity)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(drug_code, batch_no) DO UPDATE SET
                    quantity = quantity + excluded.quantity,
                    expiry = excluded.expiry
            """, (drug_code, batch_no, expiry_str, quantity))

            cursor.execute("""
                INSERT INTO transfer_events (order_id, direction, drug_code, batch_no, quantity, timestamp)
                VALUES (?, 'INBOUND', ?, ?, ?, ?)
            """, (order_id, drug_code, batch_no, quantity, timestamp_str))
            conn.commit()
