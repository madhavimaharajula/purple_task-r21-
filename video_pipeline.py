"""End-to-end per-camera video pipeline:
   frames -> detector+tracker -> {zone logic | line crossings} -> events -> EventStore
"""
from __future__ import annotations
import uuid, time
from datetime import datetime, timezone
from pathlib import Path
import cv2
import yaml
from loguru import logger

from app.schemas.events import (
    EntryEvent, ExitEvent, ZoneEnteredEvent, ZoneExitedEvent
)
from app.storage import EventStore
from .detector_tracker import DetectorTracker
from .zone_logic import ZoneTracker, LineCrosser
from .demographics import DemographicsEstimator, age_bucket


def _now_iso():
    return datetime.now(timezone.utc)


def _ts_from_frame(start: datetime, fps: float, frame_idx: int) -> datetime:
    return datetime.fromtimestamp(start.timestamp() + frame_idx / max(fps, 1.0), tz=timezone.utc)


def run_pipeline(store_cfg_path: str, app_cfg_path: str,
                 cameras: list[str] | None = None, max_seconds: float | None = None):
    store_cfg = yaml.safe_load(Path(store_cfg_path).read_text())
    app_cfg   = yaml.safe_load(Path(app_cfg_path).read_text())

    store_id = store_cfg["store_id"]
    es = EventStore(app_cfg["storage"]["duckdb_path"], app_cfg["storage"]["events_jsonl"])
    det = DetectorTracker(**{
        "model":   app_cfg["detection"]["model"],
        "device":  app_cfg["detection"]["device"],
        "conf":    app_cfg["detection"]["conf"],
        "iou":     app_cfg["detection"]["iou"],
        "classes": app_cfg["detection"]["classes"],
        "tracker": app_cfg["tracking"]["tracker"],
    })
    demo = DemographicsEstimator(
        app_cfg["demographics"]["face_model"],
        app_cfg["demographics"]["min_face_pixels"],
    ) if app_cfg["demographics"]["enabled"] else None

    for cam in store_cfg["cameras"]:
        if cameras and cam["camera_id"] not in cameras:
            continue
        video_path = cam["video"]
        if not Path(video_path).exists():
            logger.warning(f"Video missing: {video_path}  (skipping)")
            continue
        _process_camera(cam, store_id, video_path, det, demo, es, max_seconds)
    logger.info("Pipeline finished")


def _process_camera(cam, store_id, video_path, det, demo, es, max_seconds):
    role = cam["role"]
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    ok, frame = cap.read()
    if not ok:
        logger.error(f"Cannot read {video_path}"); return
    h, w = frame.shape[:2]
    start_time = _now_iso()
    zt = ZoneTracker(cam["zones"], w, h) if role == "zone" else None
    lc = LineCrosser(cam["entry_line"], w, h) if role == "entry" else None
    # Billing zone: treat as a SHELF-like zone for counting visits to register
    if role == "billing":
        zt = ZoneTracker([{
            "zone_id":  f'{store_id}_BILLING',
            "zone_name":"Billing Counter",
            "zone_type":"BILLING",
            "is_revenue_zone": True,
            "polygon":  cam["billing_polygon"],
        }], w, h)

    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
    f_idx, max_frames = 0, int((max_seconds or 1e9) * fps)
    track_demo: dict[int, dict] = {}

    while True:
        ok, frame = cap.read()
        if not ok or f_idx >= max_frames:
            break
        dets = det(frame)
        ts = _ts_from_frame(start_time, fps, f_idx)
        for d in dets:
            if d.track_id not in track_demo and demo is not None:
                crop = frame[max(int(d.y1),0):int(d.y2), max(int(d.x1),0):int(d.x2)]
                g, a, ab, hidden = demo.estimate(crop)
                track_demo[d.track_id] = {
                    "gender": g, "age": a, "age_bucket": ab, "face_hidden": hidden
                }
            td = track_demo.get(d.track_id, {})

            if zt is not None:
                entered, exited = zt.update(d.track_id, d.cx, d.cy)
                for z in entered:
                    es.append(ZoneEnteredEvent(
                        event_id=str(uuid.uuid4()), store_id=store_id,
                        camera_id=cam["camera_id"], event_timestamp=ts,
                        track_id=d.track_id, zone_id=z["zone_id"],
                        zone_name=z["zone_name"], zone_type=z["zone_type"],
                        is_revenue_zone=bool(z["is_revenue_zone"]),
                        zone_hotspot_x=float(d.cx), zone_hotspot_y=float(d.cy),
                        gender=td.get("gender"), age=td.get("age"),
                        age_bucket=td.get("age_bucket"),
                    ))
                for z in exited:
                    es.append(ZoneExitedEvent(
                        event_id=str(uuid.uuid4()), store_id=store_id,
                        camera_id=cam["camera_id"], event_timestamp=ts,
                        track_id=d.track_id, zone_id=z["zone_id"],
                        zone_name=z["zone_name"], zone_type=z["zone_type"],
                        is_revenue_zone=bool(z["is_revenue_zone"]),
                        zone_hotspot_x=float(d.cx), zone_hotspot_y=float(d.cy),
                        gender=td.get("gender"), age=td.get("age"),
                        age_bucket=td.get("age_bucket"),
                    ))
            if lc is not None:
                ev = lc.update(d.track_id, d.cx, d.cy)
                if ev == "entry":
                    es.append(EntryEvent(
                        event_id=str(uuid.uuid4()), store_id=store_id,
                        camera_id=cam["camera_id"], event_timestamp=ts,
                        id_token=f"ID_{store_id}_{d.track_id}",
                        gender_pred=td.get("gender"), age_pred=td.get("age"),
                        age_bucket=td.get("age_bucket"),
                        is_face_hidden=bool(td.get("face_hidden", True)),
                    ))
                elif ev == "exit":
                    es.append(ExitEvent(
                        event_id=str(uuid.uuid4()), store_id=store_id,
                        camera_id=cam["camera_id"], event_timestamp=ts,
                        id_token=f"ID_{store_id}_{d.track_id}",
                    ))
        f_idx += 1
    cap.release()
    logger.info(f"Camera {cam['camera_id']} processed {f_idx} frames")
