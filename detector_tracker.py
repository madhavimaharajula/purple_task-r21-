"""YOLOv8 person detection + ByteTrack tracking via Ultralytics.

Falls back gracefully when GPU is unavailable.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import List
import numpy as np

try:
    from ultralytics import YOLO
except ImportError as e:
    YOLO = None  # type: ignore


@dataclass
class Detection:
    track_id: int
    x1: float; y1: float; x2: float; y2: float
    conf: float
    cls:  int

    @property
    def cx(self): return (self.x1+self.x2)/2
    @property
    def cy(self): return (self.y1+self.y2)/2


class DetectorTracker:
    def __init__(self, model: str = "yolov8n.pt", device: str = "cpu",
                 conf: float = 0.35, iou: float = 0.5, classes=(0,),
                 tracker: str = "bytetrack.yaml"):
        if YOLO is None:
            raise RuntimeError("ultralytics not installed. `pip install ultralytics`")
        self.model = YOLO(model)
        self.device, self.conf, self.iou = device, conf, iou
        self.classes = list(classes)
        self.tracker = tracker

    def __call__(self, frame: np.ndarray) -> List[Detection]:
        res = self.model.track(frame, persist=True, tracker=self.tracker,
                               conf=self.conf, iou=self.iou,
                               classes=self.classes, device=self.device,
                               verbose=False)
        out: List[Detection] = []
        if not res:
            return out
        r = res[0]
        if r.boxes is None or r.boxes.id is None:
            return out
        ids   = r.boxes.id.int().cpu().numpy()
        xyxy  = r.boxes.xyxy.cpu().numpy()
        confs = r.boxes.conf.cpu().numpy()
        clss  = r.boxes.cls.int().cpu().numpy()
        for i, tid in enumerate(ids):
            x1,y1,x2,y2 = xyxy[i]
            out.append(Detection(int(tid), float(x1),float(y1),float(x2),float(y2),
                                 float(confs[i]), int(clss[i])))
        return out
