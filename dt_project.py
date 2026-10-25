
import cv2
import serial
import time

# =========================================================
# ESP32 SERIAL CONNECTION
# =========================================================

SERIAL_PORT = "COM8"
BAUD_RATE = 115200

esp32 = None

try:
    print("[INFO] Connecting to ESP32...")

    esp32 = serial.Serial(
        port=SERIAL_PORT,
        baudrate=BAUD_RATE,
        timeout=1,
        write_timeout=1
    )

    time.sleep(2)
    esp32.reset_input_buffer()
    esp32.reset_output_buffer()

    print("[SUCCESS] ESP32 connected on COM8")

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
CAMERA_INDEX = 0

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

CLOSED_TIME_THRESHOLD = 1.0
BUZZER_DURATION = 5.0

eyes_closed_start = None
buzzer_start_time = None
buzzer_active = False

last_command = None


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
    while True:

        ret, frame = cap.read()

        if not ret or frame is None:
            print("[ERROR] USB camera frame unavailable.")
            break

        current_time = time.monotonic()

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

                cv2.putText(
                    frame,
                    f"EYES CLOSED: {closed_duration:.1f}s",
                    (30, 50),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.8,
                    (0, 165, 255),
                    2
                )

                # Trigger once after 1 second.
                if (
                    closed_duration >= CLOSED_TIME_THRESHOLD
                    and not buzzer_active
                ):

                    buzzer_active = True
                    buzzer_start_time = current_time

                    send_to_esp32('C')

                    print(
                        "[ALERT] Eyes closed for 1 second. "
                        "Buzzer activated for 5 seconds."
                    )

        # =================================================
        # BUZZER CONTROL
        # Keep ON for the full 5 seconds after triggering.
        # =================================================

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
                    f"BUZZER ON: {remaining:.1f}s",
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

        cv2.imshow(
            "Driver Drowsiness Detection - USB Camera",
            frame
        )

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

finally:

    print("[INFO] Closing camera...")

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