"""Supplementary face-mesh metrics from the model bundled in DriverDDS.zip.

This module observes landmarks for display only. It never sends serial commands
or changes the existing Haar-based eye alarm path.
"""

from __future__ import annotations

import math
import time
from collections import deque
from pathlib import Path
from typing import Any

import cv2

RIGHT_EYE_EAR = (33, 160, 158, 133, 153, 144)
LEFT_EYE_EAR = (362, 385, 387, 263, 373, 380)
MOUTH_MAR = (61, 37, 267, 291, 314, 84)
EYE_DOTS = RIGHT_EYE_EAR + LEFT_EYE_EAR
MOUTH_DOTS = MOUTH_MAR

FACE_MODEL = Path(__file__).resolve().parent / "models" / "face_landmarker.task"
YAWN_MAR_THRESHOLD = 0.60
YAWN_MIN_SECONDS = 0.40
YAWN_RATE_WINDOW_SECONDS = 60.0
NOD_PITCH_MARGIN_DEGREES = 12.0
NOD_MIN_SAMPLES = 15
NOD_NEUTRAL_ALPHA = 0.02
NOD_COUNT_AFTER_SECONDS = 0.60
DISTRACTION_YAW_DEGREES = 30.0
DISTRACTION_ALERT_SECONDS = 2.0


def _distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _aspect_ratio(points: list[tuple[float, float]], indices: tuple[int, ...]) -> float:
    p1, p2, p3, p4, p5, p6 = (points[index] for index in indices)
    horizontal = _distance(p1, p4)
    if horizontal < 1e-6:
        return 0.0
    vertical = _distance(p2, p6) + _distance(p3, p5)
    return vertical / (2.0 * horizontal)


def _euler_angles(matrix: Any) -> tuple[float, float, float]:
    """Return pitch, yaw, roll in degrees using the ZIP's Rz·Ry·Rx convention."""
    r = matrix
    sy = math.sqrt(float(r[0][0]) ** 2 + float(r[1][0]) ** 2)
    if sy > 1e-6:
        pitch = math.atan2(float(r[2][1]), float(r[2][2]))
        yaw = math.atan2(-float(r[2][0]), sy)
        roll = math.atan2(float(r[1][0]), float(r[0][0]))
    else:
        pitch = math.atan2(-float(r[1][2]), float(r[1][1]))
        yaw = math.atan2(-float(r[2][0]), sy)
        roll = 0.0
    return tuple(math.degrees(angle) for angle in (pitch, yaw, roll))


class FaceSignals:
    """Track yawn, nod and look-away signals from one FaceLandmarker face."""

    def __init__(self, model_path: Path = FACE_MODEL) -> None:
        import mediapipe as mp
        from mediapipe.tasks import python as mp_python
        from mediapipe.tasks.python import vision

        model_path = Path(model_path)
        if not model_path.is_file():
            raise FileNotFoundError(f"FaceLandmarker model missing: {model_path}")

        options = vision.FaceLandmarkerOptions(
            base_options=mp_python.BaseOptions(model_asset_path=str(model_path)),
            running_mode=vision.RunningMode.VIDEO,
            num_faces=1,
            min_face_detection_confidence=0.5,
            min_face_presence_confidence=0.5,
            min_tracking_confidence=0.5,
            output_face_blendshapes=True,
            output_facial_transformation_matrixes=True,
        )
        self._mp = mp
        self._landmarker = vision.FaceLandmarker.create_from_options(options)
        self._started = time.monotonic()
        self._last_timestamp_ms = -1
        self._neutral_pitch: float | None = None
        self._neutral_yaw: float | None = None
        self._pose_samples = 0
        self._head_down_since: float | None = None
        self._head_nod_counted = False
        self._distraction_since: float | None = None
        self._distraction_counted = False
        self._yawn_since: float | None = None
        self._yawn_counted = False
        self._yawn_events: deque[float] = deque()
        self._yawn_count = 0
        self._head_nod_count = 0
        self._distraction_count = 0
        self._last_points: list[tuple[int, int]] = []
        self._last_snapshot: dict[str, Any] = self._empty_snapshot()

    @staticmethod
    def _empty_snapshot() -> dict[str, Any]:
        return {
            "available": True,
            "face_detected": False,
            "calibrating": True,
            "mouth_aspect_ratio": None,
            "yawning": False,
            "yawn_count": 0,
            "yawns_per_minute": 0,
            "head_nod": False,
            "head_nod_count": 0,
            "head_down_seconds": 0.0,
            "pitch_drop_degrees": None,
            "yaw_deviation_degrees": None,
            "distracted": False,
            "distraction_alert": False,
            "distraction_seconds": 0.0,
            "distraction_count": 0,
            "blink_probability": None,
        }

    def process(self, frame_bgr: Any, now: float | None = None) -> dict[str, Any]:
        now = time.monotonic() if now is None else now
        rgb = self._mp.Image(
            image_format=self._mp.ImageFormat.SRGB,
            data=cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB),
        )
        timestamp_ms = int((now - self._started) * 1000)
        timestamp_ms = max(timestamp_ms, self._last_timestamp_ms + 1)
        self._last_timestamp_ms = timestamp_ms
        result = self._landmarker.detect_for_video(rgb, timestamp_ms)
        self._last_points = []

        if not result.face_landmarks:
            self._reset_in_progress_events()
            self._last_snapshot = self._snapshot_without_face(now)
            return dict(self._last_snapshot)

        landmarks = result.face_landmarks[0]
        height, width = frame_bgr.shape[:2]
        points = [(float(point.x) * width, float(point.y) * height) for point in landmarks]
        self._last_points = [(int(x), int(y)) for x, y in points]

        mar = _aspect_ratio(points, MOUTH_MAR)
        self._update_yawns(mar, now)
        pitch = yaw = roll = None
        matrices = getattr(result, "facial_transformation_matrixes", None)
        if matrices:
            pitch, yaw, roll = _euler_angles(matrices[0])
        pose = self._update_pose(pitch, yaw, now)

        blink_probability = None
        blendshapes = getattr(result, "face_blendshapes", None)
        if blendshapes:
            scores = {category.category_name: category.score for category in blendshapes[0]}
            left = scores.get("eyeBlinkLeft")
            right = scores.get("eyeBlinkRight")
            if left is not None and right is not None:
                blink_probability = (float(left) + float(right)) / 2.0

        self._last_snapshot = {
            "available": True,
            "face_detected": True,
            "calibrating": self._pose_samples < NOD_MIN_SAMPLES,
            "mouth_aspect_ratio": round(mar, 3),
            "yawning": self._yawn_since is not None and now - self._yawn_since >= YAWN_MIN_SECONDS,
            "yawn_count": self._yawn_count,
            "yawns_per_minute": self._yawn_rate(now),
            **pose,
            "blink_probability": round(blink_probability, 3) if blink_probability is not None else None,
        }
        return dict(self._last_snapshot)

    def _update_yawns(self, mar: float, now: float) -> None:
        if mar > YAWN_MAR_THRESHOLD:
            if self._yawn_since is None:
                self._yawn_since = now
                self._yawn_counted = False
            elif not self._yawn_counted and now - self._yawn_since >= YAWN_MIN_SECONDS:
                self._yawn_count += 1
                self._yawn_events.append(now)
                self._yawn_counted = True
        else:
            self._yawn_since = None
            self._yawn_counted = False

    def _yawn_rate(self, now: float) -> int:
        while self._yawn_events and now - self._yawn_events[0] > YAWN_RATE_WINDOW_SECONDS:
            self._yawn_events.popleft()
        return len(self._yawn_events)

    def _update_pose(self, pitch: float | None, yaw: float | None, now: float) -> dict[str, Any]:
        if pitch is None or yaw is None:
            self._head_down_since = None
            self._head_nod_counted = False
            self._distraction_since = None
            self._distraction_counted = False
            return {
                "head_nod": False,
                "head_nod_count": self._head_nod_count,
                "head_down_seconds": 0.0,
                "pitch_drop_degrees": None,
                "yaw_deviation_degrees": None,
                "distracted": False,
                "distraction_alert": False,
                "distraction_seconds": 0.0,
                "distraction_count": self._distraction_count,
            }

        if self._neutral_pitch is None:
            self._neutral_pitch, self._neutral_yaw = pitch, yaw
        self._pose_samples += 1
        pitch_drop = self._neutral_pitch - pitch
        yaw_deviation = yaw - (self._neutral_yaw if self._neutral_yaw is not None else yaw)
        trusted = self._pose_samples >= NOD_MIN_SAMPLES
        head_down = trusted and pitch_drop > NOD_PITCH_MARGIN_DEGREES

        if not head_down:
            self._neutral_pitch = NOD_NEUTRAL_ALPHA * pitch + (1.0 - NOD_NEUTRAL_ALPHA) * self._neutral_pitch
        self._neutral_yaw = NOD_NEUTRAL_ALPHA * yaw + (1.0 - NOD_NEUTRAL_ALPHA) * (self._neutral_yaw or yaw)

        if head_down:
            if self._head_down_since is None:
                self._head_down_since = now
            head_down_seconds = now - self._head_down_since
            if head_down_seconds >= NOD_COUNT_AFTER_SECONDS and not self._head_nod_counted:
                self._head_nod_count += 1
                self._head_nod_counted = True
        else:
            self._head_down_since = None
            self._head_nod_counted = False
            head_down_seconds = 0.0

        distracted = trusted and abs(yaw_deviation) > DISTRACTION_YAW_DEGREES
        if distracted:
            if self._distraction_since is None:
                self._distraction_since = now
            distraction_seconds = now - self._distraction_since
            distraction_alert = distraction_seconds >= DISTRACTION_ALERT_SECONDS
            if distraction_alert and not self._distraction_counted:
                self._distraction_count += 1
                self._distraction_counted = True
        else:
            self._distraction_since = None
            self._distraction_counted = False
            distraction_seconds = 0.0
            distraction_alert = False

        return {
            "head_nod": bool(head_down),
            "head_nod_count": self._head_nod_count,
            "head_down_seconds": round(head_down_seconds, 2),
            "pitch_drop_degrees": round(pitch_drop, 1),
            "yaw_deviation_degrees": round(yaw_deviation, 1),
            "distracted": bool(distracted),
            "distraction_alert": bool(distraction_alert),
            "distraction_seconds": round(distraction_seconds, 2),
            "distraction_count": self._distraction_count,
        }

    def _reset_in_progress_events(self) -> None:
        self._yawn_since = None
        self._yawn_counted = False
        self._head_down_since = None
        self._head_nod_counted = False
        self._distraction_since = None
        self._distraction_counted = False

    def _snapshot_without_face(self, now: float) -> dict[str, Any]:
        snapshot = dict(self._last_snapshot)
        snapshot["yawns_per_minute"] = self._yawn_rate(now)
        snapshot.update({
            "face_detected": False,
            "mouth_aspect_ratio": None,
            "yawning": False,
            "head_nod": False,
            "head_down_seconds": 0.0,
            "pitch_drop_degrees": None,
            "yaw_deviation_degrees": None,
            "distracted": False,
            "distraction_alert": False,
            "distraction_seconds": 0.0,
            "blink_probability": None,
            "calibrating": self._pose_samples < NOD_MIN_SAMPLES,
        })
        return snapshot

    def landmark_pixels(self) -> list[tuple[int, int]]:
        return list(self._last_points)

    def close(self) -> None:
        self._landmarker.close()
