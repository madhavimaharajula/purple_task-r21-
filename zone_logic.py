"""Zone occupancy + line-crossing logic."""
from __future__ import annotations
from typing import Dict, List, Tuple
import numpy as np
import cv2


def polygon_from_normalized(poly_norm, w: int, h: int) -> np.ndarray:
    return np.array([[int(x*w), int(y*h)] for x,y in poly_norm], dtype=np.int32)


def point_in_polygon(pt, poly: np.ndarray) -> bool:
    return cv2.pointPolygonTest(poly, (float(pt[0]), float(pt[1])), False) >= 0


class ZoneTracker:
    """Tracks which tracks are currently inside which zones; emits enter/exit."""
    def __init__(self, zones: List[dict], frame_w: int, frame_h: int):
        self.zones = []
        for z in zones:
            self.zones.append({
                **z,
                "polygon_px": polygon_from_normalized(z["polygon"], frame_w, frame_h)
            })
        # current state: {track_id: set(zone_id)}
        self.current: Dict[int, set] = {}

    def update(self, track_id: int, cx: float, cy: float) -> Tuple[List[dict], List[dict]]:
        """Return (entered_zones, exited_zones) for this track at this frame."""
        inside = set()
        for z in self.zones:
            if point_in_polygon((cx, cy), z["polygon_px"]):
                inside.add(z["zone_id"])
        prev = self.current.get(track_id, set())
        entered_ids = inside - prev
        exited_ids  = prev - inside
        self.current[track_id] = inside
        zmap = {z["zone_id"]: z for z in self.zones}
        return ([zmap[z] for z in entered_ids], [zmap[z] for z in exited_ids])


class LineCrosser:
    """Counts directional line crossings (for entry/exit cameras)."""
    def __init__(self, line_norm, frame_w: int, frame_h: int):
        (x1,y1),(x2,y2) = line_norm
        self.p1 = np.array([x1*frame_w, y1*frame_h])
        self.p2 = np.array([x2*frame_w, y2*frame_h])
        self.last_side: Dict[int, int] = {}

    def _side(self, pt) -> int:
        v = self.p2 - self.p1
        w = np.array(pt) - self.p1
        cross = v[0]*w[1] - v[1]*w[0]
        return 1 if cross > 0 else (-1 if cross < 0 else 0)

    def update(self, track_id: int, cx: float, cy: float) -> str:
        s = self._side((cx, cy))
        prev = self.last_side.get(track_id, 0)
        self.last_side[track_id] = s
        if prev == 0 or s == 0 or prev == s:
            return "none"
        return "entry" if s > 0 else "exit"
