// ---------------------------------------------------------
// ESP32 Eye Detection Alert Firmware
// Hardware Pins:
//   - LED: Pin GPIO 4 (via 220 ohm resistor to GND)
//   - Buzzer: Pin GPIO 5 (Positive pin to GPIO 5, Negative to GND)
// ---------------------------------------------------------

#define LED_PIN 4      // Output pin for LED
#define BUZZER_PIN 5   // Output pin for Buzzer

void setup() {
  // Initialize Serial Communication at 115200 baud rate to match Python script
  Serial.begin(115200);
  
  // Set GPIO pins as outputs
  pinMode(LED_PIN, OUTPUT);
  pinMode(BUZZER_PIN, OUTPUT);
  
  // Start with all outputs OFF
  digitalWrite(LED_PIN, LOW);
  digitalWrite(BUZZER_PIN, LOW);

  // Optional startup confirmation signal (Blink LED/Buzzer once on startup)
  digitalWrite(LED_PIN, HIGH);
  digitalWrite(BUZZER_PIN, HIGH);
  delay(200);
  digitalWrite(LED_PIN, LOW);
  digitalWrite(BUZZER_PIN, LOW);
}

void loop() {
  // Check if data is available on Serial port
  if (Serial.available() > 0) {
    char command = Serial.read(); // Read the character sent from Python
    
    if (command == 'C') {
      // Eyes CLOSED -> Turn ON LED and trigger Buzzer
      digitalWrite(LED_PIN, HIGH);
      digitalWrite(BUZZER_PIN, HIGH);
    } 
    else if (command == 'O') {
      // Eyes OPEN -> Turn OFF LED and Buzzer
      digitalWrite(LED_PIN, LOW);
      digitalWrite(BUZZER_PIN, LOW);
    }
  }
}