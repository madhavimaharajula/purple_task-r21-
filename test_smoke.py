"""Smoke tests that do NOT require video files or torch."""
from app.storage import EventStore
from app.schemas.events import EntryEvent, BillingEvent
from app.analytics import compute_kpis
from datetime import datetime, timezone
import tempfile, os, uuid


def test_event_roundtrip(tmp_path):
    db = tmp_path/"x.duckdb"; jl = tmp_path/"x.jsonl"
    es = EventStore(str(db), str(jl))
    es.append(EntryEvent(event_id=str(uuid.uuid4()), store_id="S1", camera_id="C1",
                         event_timestamp=datetime.now(timezone.utc), id_token="ID_1"))
    es.append(BillingEvent(event_id=str(uuid.uuid4()), store_id="S1", camera_id="POS",
                           event_timestamp=datetime.now(timezone.utc), order_id="O1",
                           product_id="P1", brand_name="B", total_amount=100.0))
    k = compute_kpis(es, "S1")
    assert k["total_entries"] == 1
    assert k["billing_events"] == 1
