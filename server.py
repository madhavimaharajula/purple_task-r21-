"""FastAPI realtime API.

Endpoints
---------
GET  /health
GET  /stores/{store_id}/kpis         -> live KPIs
GET  /stores/{store_id}/funnel
GET  /stores/{store_id}/heatmap
GET  /stores/{store_id}/events       -> recent events
GET  /stores/{store_id}/anomalies    -> detect & return anomalies
GET  /stores/{store_id}/stream       -> Server-Sent Events of new events
POST /ingest/pos                     -> upload POS CSV
"""
from __future__ import annotations
import asyncio, yaml, json
from pathlib import Path
from typing import AsyncGenerator
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse

from app.storage import EventStore
from app.analytics import compute_kpis, funnel, heatmap_zones, detect_anomalies, ingest_pos_csv

CFG = yaml.safe_load(Path("configs/app.yaml").read_text())
ES  = EventStore(CFG["storage"]["duckdb_path"], CFG["storage"]["events_jsonl"])

app = FastAPI(title="Store Intelligence API", version="1.0.0")


@app.get("/health")
def health(): return {"ok": True}


@app.get("/stores/{store_id}/kpis")
def kpis(store_id: str): return compute_kpis(ES, store_id)


@app.get("/stores/{store_id}/funnel")
def funnel_ep(store_id: str):
    return JSONResponse(funnel(ES, store_id).to_dict(orient="records"))


@app.get("/stores/{store_id}/heatmap")
def heatmap_ep(store_id: str):
    return JSONResponse(heatmap_zones(ES, store_id).to_dict(orient="records"))


@app.get("/stores/{store_id}/events")
def recent_events(store_id: str, limit: int = 100):
    df = ES.recent(store_id, limit)
    return JSONResponse(json.loads(df.to_json(orient="records")))


@app.get("/stores/{store_id}/anomalies")
def anomalies(store_id: str):
    return [a.model_dump(mode="json") for a in detect_anomalies(ES, store_id, CFG["anomaly"])]


@app.get("/stores/{store_id}/stream")
async def stream(store_id: str):
    """SSE stream of newly-appended events (tails the JSONL file)."""
    path = Path(CFG["storage"]["events_jsonl"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch(exist_ok=True)

    async def gen() -> AsyncGenerator[dict, None]:
        with open(path, "r", encoding="utf-8") as f:
            f.seek(0, 2)  # tail
            while True:
                line = f.readline()
                if not line:
                    await asyncio.sleep(0.5); continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                if rec.get("store_id") == store_id:
                    yield {"event": rec.get("event_type","event"),
                           "data": json.dumps(rec)}
    return EventSourceResponse(gen())


@app.post("/ingest/pos")
async def ingest_pos(file: UploadFile = File(...)):
    if not file.filename.endswith(".csv"):
        raise HTTPException(400, "expected csv")
    dest = Path("data/processed") / file.filename
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(await file.read())
    n = ingest_pos_csv(ES, str(dest))
    return {"ingested": n}
