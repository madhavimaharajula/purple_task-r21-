"""Ingest POS transactions CSV into the event store and compute join KPIs."""
from __future__ import annotations
import uuid, pandas as pd
from datetime import datetime
from pathlib import Path
from app.storage import EventStore
from app.schemas.events import BillingEvent


def ingest_pos_csv(es: EventStore, csv_path: str, default_camera="POS") -> int:
    df = pd.read_csv(csv_path)
    df["ts"] = pd.to_datetime(df["order_date"] + " " + df["order_time"],
                              format="%d-%m-%Y %H:%M:%S", errors="coerce")
    n = 0
    for _, r in df.iterrows():
        ev = BillingEvent(
            event_id=str(uuid.uuid4()),
            store_id=str(r["store_id"]),
            camera_id=default_camera,
            event_timestamp=r["ts"].to_pydatetime() if pd.notna(r["ts"]) else datetime.utcnow(),
            order_id=str(r["order_id"]),
            product_id=str(r["product_id"]),
            brand_name=str(r["brand_name"]),
            total_amount=float(r["total_amount"]),
        )
        es.append(ev); n += 1
    return n


def pos_vs_visitors(es: EventStore, store_id: str) -> pd.DataFrame:
    return es.query("""
      WITH hourly AS (
        SELECT date_trunc('hour', event_timestamp) AS hour,
               event_type, COUNT(*) AS n
        FROM events WHERE store_id = ?
        GROUP BY 1,2
      )
      PIVOT hourly ON event_type USING SUM(n)
    """, [store_id])
