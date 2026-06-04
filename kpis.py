"""Real-time KPIs computed directly from the DuckDB event store."""
from __future__ import annotations
import pandas as pd
from app.storage import EventStore


def compute_kpis(es: EventStore, store_id: str) -> dict:
    df = es.query("""
        SELECT event_type, COUNT(*) AS n
        FROM events WHERE store_id = ?
        GROUP BY event_type
    """, [store_id])
    by = dict(zip(df["event_type"], df["n"])) if not df.empty else {}
    entries = int(by.get("entry", 0))
    exits   = int(by.get("exit", 0))
    zone_in = int(by.get("zone_entered", 0))
    billing = int(by.get("billing", 0))
    return {
        "total_entries":  entries,
        "total_exits":    exits,
        "current_inside": max(entries - exits, 0),
        "zone_visits":    zone_in,
        "billing_events": billing,
        "conversion_rate": (billing / entries) if entries else 0.0,
    }


def funnel(es: EventStore, store_id: str) -> pd.DataFrame:
    return es.query("""
      WITH e AS (
        SELECT event_type FROM events WHERE store_id = ?
      )
      SELECT 'entries'  AS stage, SUM(CASE WHEN event_type='entry'        THEN 1 ELSE 0 END) AS n FROM e
      UNION ALL SELECT 'zone_visits', SUM(CASE WHEN event_type='zone_entered' THEN 1 ELSE 0 END) FROM e
      UNION ALL SELECT 'billing',     SUM(CASE WHEN event_type='billing'      THEN 1 ELSE 0 END) FROM e
    """, [store_id])


def heatmap_zones(es: EventStore, store_id: str) -> pd.DataFrame:
    return es.query("""
      SELECT json_extract_string(payload,'$.zone_id')   AS zone_id,
             json_extract_string(payload,'$.zone_name') AS zone_name,
             COUNT(*) AS visits
      FROM events
      WHERE store_id = ? AND event_type = 'zone_entered'
      GROUP BY 1,2 ORDER BY visits DESC
    """, [store_id])
