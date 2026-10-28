
import os
import cv2
import serial
import time
from dashboard_server import start_dashboard
from vision_signals import (
    DISTRACTION_ALERT_SECONDS,
    DISTRACTION_YAW_DEGREES,
    EYE_DOTS,
    MOUTH_DOTS,
    NOD_COUNT_AFTER_SECONDS,
    NOD_PITCH_MARGIN_DEGREES,
    FaceSignals,
    YAWN_MAR_THRESHOLD,
    YAWN_MIN_SECONDS,
)

# =========================================================
# ESP32 SERIAL CONNECTION
# =========================================================

SERIAL_PORT = os.getenv("SERIAL_PORT", "COM8")
BAUD_RATE = int(os.getenv("BAUD_RATE", "115200"))

esp32 = None

try:
    print(f"[INFO] Connecting to ESP32 on {SERIAL_PORT}...")

    esp32 = serial.Serial(
        port=SERIAL_PORT,
        baudrate=BAUD_RATE,
        timeout=1,
        write_timeout=1
    )

    time.sleep(2)
    esp32.reset_input_buffer()
    esp32.reset_output_buffer()

    print(f"[SUCCESS] ESP32 connected on {SERIAL_PORT}")

except serial.SerialException as e:
    print("[ERROR] ESP32 connection failed:", e)
    esp32 = None


# =========================================================
# LOAD OPENCV CLASSIFIERS
# =========================================================

face_cascade = cv2.CascadeClassifier(
    cv2.data.haarcascades +
    "haarcascade_frontalface_default.xml"
)

eye_cascade = cv2.CascadeClassifier(
    cv2.data.haarcascades +
    "haarcascade_eye.xml"
)

if face_cascade.empty() or eye_cascade.empty():
    print("[ERROR] Could not load OpenCV Haar cascades.")
    if esp32:
        esp32.close()
    raise SystemExit


# =========================================================
# USB CAMERA SETTINGS
# =========================================================

# Use ONLY the USB camera's configured index.
# Do not automatically switch to another camera index.
CAMERA_INDEX = int(os.getenv("CAMERA_INDEX", "0"))

print("[INFO] Opening USB camera only.")
print("[INFO] Camera index:", CAMERA_INDEX)


# =========================================================
# OPEN USB CAMERA
# =========================================================

cap = None

# Try Windows DirectShow first, then Media Foundation.
# Both attempts use the SAME camera index.
for backend in (cv2.CAP_DSHOW, cv2.CAP_MSMF):

    candidate = cv2.VideoCapture(CAMERA_INDEX, backend)

    if candidate.isOpened():
        ret, test_frame = candidate.read()

        if ret and test_frame is not None:
            cap = candidate
            print("[SUCCESS] USB camera opened.")
            break

    candidate.release()

if cap is None:
    print("[ERROR] USB camera could not be opened.")
    print("[INFO] Check USB connection, camera index and permissions.")
    print("[INFO] Close other applications using the USB camera.")

    if esp32:
        try:
            esp32.write(b'O')
        except Exception:
            pass
        esp32.close()

    raise SystemExit


# =========================================================
# CAMERA RESOLUTION
# =========================================================

cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)


# =========================================================
# DROWSINESS SETTINGS
# =========================================================

CLOSED_TIME_THRESHOLD = float(os.getenv("CLOSED_TIME_THRESHOLD", "2.0"))
BUZZER_DURATION = float(os.getenv("BUZZER_DURATION", "5.0"))

eyes_closed_start = None
buzzer_start_time = None
buzzer_active = False

last_command = None
ui_driver_status = "STARTING"
ui_eye_state = "UNKNOWN"
ui_closed_duration = 0.0
monitor_started_at = time.monotonic()
dashboard = None
face_signals = None
face_signal_error = None

try:
    face_signals = FaceSignals()
    print("[INFO] ZIP FaceLandmarker model loaded for supplementary metrics.")
except Exception as error:
    face_signal_error = str(error)
    print("[WARN] Supplementary face metrics unavailable:", error)


# =========================================================
# SEND COMMAND TO ESP32
# =========================================================

def send_to_esp32(command):
    global last_command

    if esp32 is None:
        return

    if command == last_command:
        return

    try:
        esp32.write(command.encode("ascii"))
        esp32.flush()
        print("[ESP32] Sent:", command)
        last_command = command

    except (serial.SerialException, OSError) as e:
        print("[ERROR] ESP32 communication failed:", e)


# =========================================================
# MAIN LOOP
# =========================================================

try:
    try:
        dashboard_port = int(os.getenv("DASHBOARD_PORT", "8000"))
        dashboard = start_dashboard(port=dashboard_port)
        print(f"[INFO] Browser cockpit available at http://127.0.0.1:{dashboard_port}")
    except OSError as error:
        print("[ERROR] Browser cockpit could not start:", error)
        print("[INFO] Continuing with the existing OpenCV window.")

    while True:

        ret, frame = cap.read()

        if not ret or frame is None:
            print("[ERROR] USB camera frame unavailable.")
            break

        current_time = time.monotonic()
        ui_driver_status = "NO FACE DETECTED"
        ui_eye_state = "UNKNOWN"
        ui_closed_duration = 0.0

        face_metrics = None
        face_landmarks = []
        if face_signals is not None:
            try:
                face_metrics = face_signals.process(frame, current_time)
                face_landmarks = face_signals.landmark_pixels()
            except Exception as error:
                face_signal_error = str(error)
                print("[ERROR] Supplementary face model stopped:", error)
                try:
                    face_signals.close()
                except Exception:
                    pass
                face_signals = None

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        faces = face_cascade.detectMultiScale(
            gray,
            scaleFactor=1.2,
            minNeighbors=5,
            minSize=(100, 100)
        )

        # -------------------------------------------------
        # NO FACE DETECTED
        # -------------------------------------------------

        if len(faces) == 0:

            # Reset eye timer, but never interrupt a
            # buzzer cycle already in progress.
            eyes_closed_start = None

            cv2.putText(
                frame,
                "NO FACE DETECTED",
                (30, 50),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (255, 255, 0),
                2
            )

        # -------------------------------------------------
        # FACE DETECTED
        # -------------------------------------------------

        else:

            ui_driver_status = "FACE DETECTED"

            # Use the largest detected face.
            x, y, w, h = max(
                faces,
                key=lambda face: face[2] * face[3]
            )

            cv2.rectangle(
                frame,
                (x, y),
                (x + w, y + h),
                (255, 0, 0),
                2
            )

            # Region containing the eyes
            roi_gray = gray[
                y:y + int(h * 0.6),
                x:x + w
            ]

            roi_color = frame[
                y:y + int(h * 0.6),
                x:x + w
            ]

            eyes = eye_cascade.detectMultiScale(
                roi_gray,
                scaleFactor=1.1,
                minNeighbors=10,
                minSize=(30, 30)
            )

            for (ex, ey, ew, eh) in eyes:
                cv2.rectangle(
                    roi_color,
                    (ex, ey),
                    (ex + ew, ey + eh),
                    (0, 255, 0),
                    2
                )

            # ---------------------------------------------
            # EYES OPEN
            # ---------------------------------------------

            if len(eyes) > 0:

                eyes_closed_start = None
                ui_eye_state = "OPEN"

                cv2.putText(
                    frame,
                    "EYES OPEN",
                    (30, 50),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    1,
                    (0, 255, 0),
                    2
                )

                # Do not switch off an active buzzer.

            # ---------------------------------------------
            # EYES CLOSED
            # ---------------------------------------------

            else:

                if eyes_closed_start is None:
                    eyes_closed_start = current_time

                closed_duration = (
                    current_time - eyes_closed_start
                )
                ui_eye_state = "CLOSED"
                ui_closed_duration = closed_duration

                cv2.putText(
                    frame,
                    f"EYES CLOSED: {closed_duration:.1f}s",
                    (30, 50),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.8,
                    (0, 165, 255),
                    2
                )

                # Trigger once after 2 seconds.
                if (
                    closed_duration >= CLOSED_TIME_THRESHOLD
                    and not buzzer_active
                ):

                    buzzer_active = True
                    buzzer_start_time = current_time

                    send_to_esp32('C')

                    print(
                        "[ALERT] Eyes closed for 2 seconds. "
                        "Buzzer activated for 5 seconds."
                    )

        if face_signals is not None and face_landmarks:
            for index in EYE_DOTS:
                if index < len(face_landmarks):
                    cv2.circle(frame, face_landmarks[index], 2, (0, 255, 0), -1)
            for index in MOUTH_DOTS:
                if index < len(face_landmarks):
                    cv2.circle(frame, face_landmarks[index], 2, (255, 0, 255), -1)

        # =================================================
        # BUZZER CONTROL
        # Keep ON for the full 5 seconds after triggering.
        # =================================================

        remaining = 0.0
        if buzzer_active:

            elapsed = time.monotonic() - buzzer_start_time
            remaining = max(0.0, BUZZER_DURATION - elapsed)

            if elapsed < BUZZER_DURATION:

                # Re-send only if required; duplicate commands
                # are suppressed by send_to_esp32().
                send_to_esp32('C')

                cv2.putText(
                    frame,
                    "DROWSINESS ALERT!",
                    (30, 95),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    1,
                    (0, 0, 255),
                    3
                )

                cv2.putText(
                    frame,
                    f"ALERT CYCLE: {remaining:.1f}s",
                    (30, 135),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.8,
                    (0, 0, 255),
                    2
                )

            else:

                send_to_esp32('O')

                buzzer_active = False
                buzzer_start_time = None

                print("[INFO] Five seconds completed. Buzzer OFF.")

        # =================================================
        # DISPLAY
        # =================================================

        if dashboard is not None:
            encoded, jpeg = cv2.imencode(
                ".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 82]
            )
            if encoded:
                dashboard.publish(
                    jpeg.tobytes(),
                    {
                        "running": True,
                        "camera_connected": True,
                        "frame_available": True,
                        "serial_port_open": bool(
                            esp32 is not None and getattr(esp32, "is_open", True)
                        ),
                        "serial_port": SERIAL_PORT,
                        "baud_rate": BAUD_RATE,
                        "camera_index": CAMERA_INDEX,
                        "camera_resolution": "640 × 480",
                        "face_detector": "OpenCV Haar Cascade",
                        "eye_detector": "OpenCV Haar Cascade",
                        "driver": ui_driver_status,
                        "eyes": ui_eye_state,
                        "closed_duration": round(ui_closed_duration, 2),
                        "alert_active": buzzer_active,
                        "buzzer_remaining": round(remaining, 2),
                        "last_command": last_command,
                        "uptime_seconds": round(time.monotonic() - monitor_started_at, 1),
                        "closed_threshold_seconds": CLOSED_TIME_THRESHOLD,
                        "buzzer_duration_seconds": BUZZER_DURATION,
                        "face_model_available": face_signals is not None,
                        "face_model_error": face_signal_error,
                        "face_model_detected": face_metrics.get("face_detected") if face_metrics else None,
                        "face_model_calibrating": face_metrics.get("calibrating") if face_metrics else None,
                        "blink_probability": face_metrics.get("blink_probability") if face_metrics else None,
                        "mouth_aspect_ratio": face_metrics.get("mouth_aspect_ratio") if face_metrics else None,
                        "yawning": face_metrics.get("yawning") if face_metrics else None,
                        "yawn_count": face_metrics.get("yawn_count") if face_metrics else None,
                        "yawns_per_minute": face_metrics.get("yawns_per_minute") if face_metrics else None,
                        "head_nod": face_metrics.get("head_nod") if face_metrics else None,
                        "head_nod_count": face_metrics.get("head_nod_count") if face_metrics else None,
                        "head_down_seconds": face_metrics.get("head_down_seconds") if face_metrics else None,
                        "pitch_drop_degrees": face_metrics.get("pitch_drop_degrees") if face_metrics else None,
                        "distracted": face_metrics.get("distracted") if face_metrics else None,
                        "distraction_alert": face_metrics.get("distraction_alert") if face_metrics else None,
                        "distraction_seconds": face_metrics.get("distraction_seconds") if face_metrics else None,
                        "distraction_count": face_metrics.get("distraction_count") if face_metrics else None,
                        "yaw_deviation_degrees": face_metrics.get("yaw_deviation_degrees") if face_metrics else None,
                        "yawn_mar_threshold": YAWN_MAR_THRESHOLD,
                        "yawn_min_seconds": YAWN_MIN_SECONDS,
                        "nod_pitch_margin_degrees": NOD_PITCH_MARGIN_DEGREES,
                        "nod_count_after_seconds": NOD_COUNT_AFTER_SECONDS,
                        "distraction_yaw_degrees": DISTRACTION_YAW_DEGREES,
                        "distraction_alert_seconds": DISTRACTION_ALERT_SECONDS,
                    },
                )
        else:
            cv2.imshow(
                "Driver Drowsiness Detection - USB Camera",
                frame
            )

            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

finally:

    print("[INFO] Closing camera...")

    if dashboard is not None:
        dashboard.stop()

    if face_signals is not None:
        try:
            face_signals.close()
        except Exception as error:
            print("[WARN] FaceLandmarker cleanup failed:", error)

    # Turn buzzer off when the program exits.
    if esp32 is not None:
        try:
            esp32.write(b'O')
            esp32.flush()
            time.sleep(0.1)
        except Exception:
            pass

    if cap is not None:
        cap.release()

    cv2.destroyAllWindows()

    if esp32 is not None:
        esp32.close()
        print("[INFO] ESP32 connection closed.")

    print("[INFO] Program terminated.")
