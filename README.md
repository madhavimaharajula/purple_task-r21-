# Store Intelligence System — Purplle Tech Challenge 2026 (Round 2)

End-to-end pipeline that turns raw in-store CCTV footage + POS data into
real-time intelligence (entries/exits, zone dwell, demographics,
conversion, anomalies) exposed via FastAPI and a Streamlit dashboard.

```
CCTV mp4 ─► YOLOv8 + ByteTrack ─► zone / line logic ─► Event Bus (JSONL + DuckDB)
                                                       │
POS CSV  ─► ingest_pos ──────────────────────────────► │ ─► FastAPI  (REST + SSE)
                                                       │ ─► Streamlit Dashboard
                                                       └─► Anomaly Detector
```

## 1. Folder layout
```
store-intel/
├── app/
│   ├── api/server.py            FastAPI app (REST + SSE)
│   ├── pipeline/                detection, tracking, zones, demographics
│   ├── schemas/events.py        Pydantic event schemas (versioned)
│   ├── storage/event_store.py   JSONL + DuckDB append-only store
│   ├── analytics/               KPIs, anomalies, POS join
│   └── dashboard/streamlit_app.py
├── configs/                     store_1.yaml, store_2.yaml, app.yaml
├── data/
│   ├── raw/{store_1,store_2}/   ← put the CCTV mp4 files here
│   ├── sample/                  sample POS + sample event stream + layouts
│   └── processed/               DuckDB + events.jsonl (auto-created)
├── scripts/                     CLI entrypoints
├── tests/                       pytest smoke tests
├── Dockerfile / docker-compose.yml
└── requirements.txt
```

## 2. Setup in VS Code (step by step)

1. **Unzip** the project anywhere, e.g. `D:\purplle\store-intel\`.
2. **Open the folder** in VS Code → *File ▸ Open Folder*.
3. Install the **Python extension** (Microsoft) if you don't have it.
4. Open a terminal (`Ctrl+\``) and create a virtual environment:
   ```bash
   python -m venv .venv
   # Windows
   .venv\Scripts\activate
   # macOS/Linux
   source .venv/bin/activate
   ```
5. Upgrade pip and install everything:
   ```bash
   python -m pip install --upgrade pip
   pip install -r requirements.txt
   ```
   First run will also download `yolov8n.pt` (~6 MB) and InsightFace
   `buffalo_l` (~300 MB) automatically. If you don't want demographics,
   set `demographics.enabled: false` in `configs/app.yaml`.
6. (Optional) **GPU**: set `detection.device: cuda` in `configs/app.yaml`
   and install the CUDA build of PyTorch from https://pytorch.org.

## 3. Put the videos in place

Copy the unzipped CCTV files exactly like this:
```
data/raw/store_1/CAM 1 - zone.mp4
data/raw/store_1/CAM 2 - zone.mp4
data/raw/store_1/CAM 3 - entry.mp4
data/raw/store_1/CAM 5 - billing.mp4

data/raw/store_2/entry 1.mp4
data/raw/store_2/entry 2.mp4
data/raw/store_2/zone.mp4
data/raw/store_2/billing_area.mp4
```
The store layouts and sample data are already inside `data/sample/`.

## 4. Run

### 4.1 Seed the system with the provided samples
```bash
python scripts/ingest_pos.py             --csv  data/sample/pos_sample.csv
python scripts/replay_sample_events.py   --jsonl data/sample/sample_events.jsonl
```

### 4.2 Process video footage
```bash
# Full store 1
python scripts/run_pipeline.py --store configs/store_1.yaml
# Or just one camera for a quick test
python scripts/run_pipeline.py --store configs/store_1.yaml --cameras CAM3 --max-seconds 30
# Store 2
python scripts/run_pipeline.py --store configs/store_2.yaml
```

### 4.3 Start the API
```bash
uvicorn app.api.server:app --reload --port 8000
```
Open http://localhost:8000/docs for Swagger.

### 4.4 Start the dashboard
```bash
streamlit run app/dashboard/streamlit_app.py
```
Open http://localhost:8501 — set Store ID `ST1008` or `ST1076`.

### 4.5 Live SSE stream
```bash
curl -N http://localhost:8000/stores/ST1008/stream
```

### 4.6 One-command Docker
```bash
docker compose up --build
```

## 5. API endpoints
| Method | Path                                | Description |
|------:|--------------------------------------|-------------|
| GET   | /health                              | health check |
| GET   | /stores/{id}/kpis                    | live KPIs |
| GET   | /stores/{id}/funnel                  | entries → zone → billing |
| GET   | /stores/{id}/heatmap                 | per-zone visit counts |
| GET   | /stores/{id}/events?limit=100        | recent events |
| GET   | /stores/{id}/anomalies               | run anomaly detection now |
| GET   | /stores/{id}/stream                  | SSE live event stream |
| POST  | /ingest/pos (multipart `file`)       | ingest POS csv |

## 6. Event schema (canonical)

All events share:
`schema_version, event_id, event_type, store_id, camera_id, event_timestamp`.

Per-type fields are defined in `app/schemas/events.py`:
* **entry / exit** — `id_token`, demographics, group info
* **zone_entered / zone_exited** — `track_id`, `zone_id`, `zone_name`,
  `zone_type`, `is_revenue_zone`, hotspot coords, demographics
* **billing** — `order_id`, `product_id`, `brand_name`, `total_amount`
* **anomaly** — `anomaly_type`, `severity`, `details`

Storage:
* **JSONL** at `data/processed/events.jsonl` — replayable bus
* **DuckDB** at `data/processed/store_intel.duckdb` — SQL analytics

## 7. Anomaly detection
* **long_dwell** — track stayed in a zone > `dwell_minutes_threshold`
* **pos_visitor_mismatch** — billing events without any entry in last N minutes
* **staff_loitering** — placeholder hook in `configs/app.yaml`

## 8. Production-readiness notes
* Append-only event bus + Pydantic v2 schemas with `schema_version`
* Thread-safe DuckDB writes, SSE tailing of JSONL for live UIs
* Stateless API → horizontally scalable behind a load balancer
* Easy swap: JSONL → Kafka (`aiokafka` already in requirements);
  DuckDB → Postgres/Snowflake by changing the `EventStore` driver
* Docker / docker-compose included
* Pytest smoke tests in `tests/`

## 9. Test
```bash
pytest -q
```

## 10. Troubleshooting
* `torch` install failing on Windows → install CPU build first:
  `pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu`
* `cv2` import error on Linux → `apt-get install libgl1`
* InsightFace model download blocked → set `demographics.enabled: false`
* No GPU → the system runs end-to-end on CPU (slower but functional)
