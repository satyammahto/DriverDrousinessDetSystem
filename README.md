# Driver Drowsiness Detection System

A simple computer-vision and IoT project that detects prolonged eye closure through a USB camera and triggers an alert using an ESP32-connected LED and buzzer.

> **Safety note:** This is an educational prototype, not a certified driver-monitoring or vehicle-safety system. Do not rely on it as the only safeguard against drowsy driving.

## Overview

The system uses Python and OpenCV to monitor a camera feed. It detects a face and searches for eyes in the upper region of the detected face. If no eyes are detected for approximately one second, the Python program sends an alert command to the ESP32 over USB serial. The ESP32 switches on the LED and buzzer. The alert runs for approximately five seconds, after which the Python program sends a command to turn the outputs off.

## Features

- USB-camera video capture using OpenCV.
- Face detection with OpenCV's Haar Cascade classifier.
- Eye detection within the detected face region.
- Supplementary facial landmark analysis via MediaPipe FaceLandmarker (yawn count, head nod, look-away distraction).
- Real-time Web Cockpit browser dashboard (`http://127.0.0.1:8000`) with live camera stream and telemetry.
- Serial communication between Python and the ESP32 at **115200 baud**.
- ESP32 output control for an LED and buzzer.
- Camera and serial-port cleanup when the program exits.
- Configurable environment options without editing code (`.env.example`).

## Hardware Required

- ESP32 development board
- USB camera/webcam
- LED
- 220 Ω resistor for the LED
- Buzzer compatible with the circuit and ESP32 output
- USB data cable for the ESP32
- Jumper wires and a computer running Python

## Hardware Connections

| Component | ESP32 connection |
|---|---|
| LED positive/anode | GPIO 4 through a 220 Ω resistor |
| LED negative/cathode | GND |
| Buzzer positive (+) | GPIO 5 |
| Buzzer negative (−) | GND |

**Important:** Confirm that your buzzer can be driven safely by the ESP32 GPIO. Some buzzers require a transistor driver or a separate power supply; do not connect a load that exceeds the GPIO pin's current limits.

## Software Requirements

- Python 3.9+
- OpenCV (`opencv-contrib-python`)
- PySerial (`pyserial`)
- MediaPipe (`mediapipe`)
- Arduino IDE
- ESP32 board support installed in Arduino IDE

## Repository Structure

```text
DriverDrousinessDetSystem/
├── .env.example                  # Template for environment settings (COM port, camera index)
├── .gitignore                    # Protects secrets, cache, venv, and local session logs
├── dt_project.py                 # Core detector loop and ESP32 serial coordinator
├── dashboard_server.py           # Loopback HTTP server streaming real-time metrics & video
├── dashboard_ui/                 # Web cockpit assets (HTML, CSS, JS)
│   ├── app.js
│   ├── index.html
│   └── styles.css
├── vision_signals.py             # Supplementary facial mesh & landmark signals
├── models/
│   └── face_landmarker.task      # MediaPipe FaceLandmarker task model
├── session_data/                 # Runtime session logs directory
├── sketch_oct25a/
│   └── sketch_oct25a.ino         # ESP32 firmware for LED and buzzer control
├── requirements.txt              # Python package requirements
├── README.md                     # Project documentation
└── WhatsApp Image ... .jpeg      # Circuit and wiring reference photos
```

## Setup and Installation

### 1. Clone the repository

```bash
git clone https://github.com/satyammahto/DriverDrousinessDetSystem.git
cd DriverDrousinessDetSystem
```

### 2. Install the Python dependencies

It is recommended to use a virtual environment.

**Windows (PowerShell):**

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

If PowerShell blocks virtual-environment activation, you can install the packages directly:

```powershell
python -m pip install -r requirements.txt
```

### 3. Upload the ESP32 firmware

1. Open `sketch_oct25a/sketch_oct25a.ino` in Arduino IDE.
2. Connect the ESP32 to your computer using a USB data cable.
3. Select the correct ESP32 board under **Tools → Board**.
4. Select the correct serial port under **Tools → Port**.
5. Upload the sketch.
6. After upload, close Arduino IDE's Serial Monitor before running the Python program, because another application holding the same serial port can prevent Python from connecting.

The firmware initializes serial communication at **115200 baud**, matching the Python script.

### 4. Configuration (Safe Environment Settings)

You can configure settings using environment variables or by copying `.env.example` to `.env`:

```powershell
Copy-Item .env.example .env
```

Key configuration options:
- `SERIAL_PORT`: COM port assigned to ESP32 (e.g. `COM8`, `COM3`, `/dev/ttyUSB0`)
- `BAUD_RATE`: Serial baud rate (default: `115200`)
- `CAMERA_INDEX`: Camera device index (default: `0`)
- `DASHBOARD_PORT`: Local browser dashboard port (default: `8000`)
- `CLOSED_TIME_THRESHOLD`: Eye closure time threshold before trigger (default: `2.0` seconds)
- `BUZZER_DURATION`: Duration the buzzer stays active (default: `5.0` seconds)

The `.env` file is excluded in `.gitignore` so your personal port settings and any future credentials remain private and will not be pushed to GitHub.

### 5. Connect the camera and run the Python program

Close other applications that may be using the webcam, then run:

```bash
python dt_project.py
```

A window named **Driver Drowsiness Detection - USB Camera** should open. Press **Q** while the camera window is focused to stop the program.

## How It Works

1. **Connect:** Python attempts to connect to the configured ESP32 serial port.
2. **Capture:** OpenCV opens camera index `0` and reads video frames.
3. **Detect face:** A Haar Cascade face classifier searches each frame.
4. **Detect eyes:** When a face is found, a second Haar Cascade classifier searches the upper portion of that face.
5. **Track closure:** If no eyes are detected, the program starts a timer. If eyes remain undetected for about one second, it triggers the alert.
6. **Send alert:** Python sends the character `C` to the ESP32. The ESP32 turns on the LED and buzzer.
7. **Stop alert:** After about five seconds, Python sends `O`; the ESP32 turns off both outputs.
8. **Exit safely:** When the program closes, it attempts to turn the outputs off, releases the camera, and closes the serial connection.

### Serial command reference

| Command | ESP32 action |
|---|---|
| `C` | Turn LED and buzzer ON |
| `O` | Turn LED and buzzer OFF |

## Troubleshooting

### ESP32 serial connection fails

- Check the selected COM port in Windows Device Manager or Arduino IDE.
- Update `SERIAL_PORT` in `dt_project.py` to the current port.
- Use a USB cable that supports data, not just charging.
- Close Arduino IDE Serial Monitor and any other application using the port.
- Ensure the ESP32 firmware and Python script both use **115200 baud**.

### Buzzer or LED does not activate

- Confirm the sketch was uploaded to the correct ESP32 board and port.
- Check LED polarity, the 220 Ω resistor, GND connections, and buzzer polarity.
- Verify that the Python terminal logs `[ESP32] Sent: C` when an alert is triggered.
- Test the LED and buzzer wiring independently. Some buzzers need a suitable driver circuit and cannot be powered directly from a GPIO pin.

### Camera does not open

- Confirm the webcam is connected and recognized by the operating system.
- Close applications that might already be using the camera.
- The current program uses camera index `0`; if your intended USB camera uses a different index, change `CAMERA_INDEX` in `dt_project.py`.
- Check camera permissions and USB connections.

### Detection is inconsistent

This prototype uses Haar Cascade detection, which may miss eyes due to lighting, glasses, head pose, camera placement, or partial occlusion. Keep the camera steady, ensure the face is well lit, and position the camera so the face and eyes are visible.

## Limitations

- Eye detection relies on Haar Cascade classifiers, not a trained drowsiness-classification model.
- Failure to detect eyes is treated as possible eye closure; it can also occur because of lighting, pose, or occlusion.
- The fixed time thresholds may not be suitable for every person or driving scenario.
- Performance depends on camera quality, positioning, lighting, and hardware.
- This prototype has not been validated for use in real vehicles.

## Future Improvements

- Use facial landmarks or a dedicated eye-state model to improve robustness.
- Add a configurable threshold and calibration step.
- Log alert events and detection confidence.
- Add more robust serial reconnection and hardware diagnostics.
- Evaluate detection performance under different lighting and head-pose conditions.

## License

No license is currently specified in this repository. Add a license file if you intend to define how others may use, modify, or distribute this project.
