"""Optional gender/age estimation using InsightFace.

If insightface isn't available or no face is found, returns Nones so
the pipeline stays functional.
"""
from __future__ import annotations
from typing import Optional, Tuple
import numpy as np

try:
    from insightface.app import FaceAnalysis
except Exception:
    FaceAnalysis = None


def age_bucket(age: int) -> str:
    if age < 18:  return "0-17"
    if age < 25:  return "18-24"
    if age < 35:  return "25-34"
    if age < 45:  return "35-44"
    if age < 55:  return "45-54"
    return "55+"


class DemographicsEstimator:
    def __init__(self, model_name: str = "buffalo_l", min_face_pixels: int = 24):
        self.enabled = FaceAnalysis is not None
        self.min_face_pixels = min_face_pixels
        if not self.enabled:
            self.app = None
            return
        try:
            self.app = FaceAnalysis(name=model_name)
            self.app.prepare(ctx_id=-1, det_size=(320, 320))
        except Exception:
            self.enabled = False
            self.app = None

    def estimate(self, crop: np.ndarray) -> Tuple[Optional[str], Optional[int], Optional[str], bool]:
        """Return (gender, age, age_bucket, is_face_hidden)."""
        if not self.enabled or crop is None or crop.size == 0:
            return None, None, None, True
        h, w = crop.shape[:2]
        if min(h, w) < self.min_face_pixels:
            return None, None, None, True
        try:
            faces = self.app.get(crop)
            if not faces:
                return None, None, None, True
            f = max(faces, key=lambda x: (x.bbox[2]-x.bbox[0])*(x.bbox[3]-x.bbox[1]))
            g = "M" if int(f.sex if hasattr(f,"sex") else f.gender) == 1 else "F"
            a = int(f.age)
            return g, a, age_bucket(a), False
        except Exception:
            return None, None, None, True
