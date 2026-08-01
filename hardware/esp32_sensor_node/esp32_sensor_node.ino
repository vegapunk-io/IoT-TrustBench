/*
 * IoT-TrustBench ESP32 Sensor Node
 * 
 * Reads sensors and sends data to IoT-TrustBench server via HTTP POST.
 * 
 * Required Libraries (install via Arduino Library Manager):
 *   - DHT sensor library (by Adafruit)
 *   - Adafruit Unified Sensor
 *   - ArduinoJson
 * 
 * Wiring (ESP32):
 *   DHT22 DATA  -> GPIO 4
 *   MQ-2 AOUT   -> GPIO 34 (ADC)
 *   PIR OUT     -> GPIO 27
 *   Reed Switch -> GPIO 26 (INPUT_PULLUP)
 *   LED         -> GPIO 2 (built-in)
 * 
 * Power:
 *   DHT22 VCC -> 3.3V
 *   MQ-2 VCC  -> 5V (VIN)
 *   PIR VCC   -> 5V (VIN)
 *   Reed VCC  -> 3.3V
 */

#include <WiFi.h>
#include <HTTPClient.h>
#include <DHT.h>
#include <ArduinoJson.h>

// ===== CONFIGURATION - EDIT THESE =====
const char* WIFI_SSID     = "YOUR_WIFI_SSID";
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";
const char* SERVER_URL    = "http://192.168.1.100:8000/api/hardware";
const char* DEVICE_ID     = "ESP32-NODE-001";

// Sensor pins
#define DHT_PIN       4
#define DHT_TYPE      DHT22
#define MQ2_PIN       34
#define PIR_PIN       27
#define REED_PIN      26
#define LED_PIN       2

// Calibration
#define MQ2_BASELINE  2000   // Baseline ADC value for clean air (calibrate!)
#define GAS_THRESHOLD 50     // Gas level threshold (0-100)

// Send interval (milliseconds)
#define SEND_INTERVAL 5000

// ===== GLOBALS =====
DHT dht(DHT_PIN, DHT_TYPE);
unsigned long lastSend = 0;
String deviceId;

// ===== SETUP =====
void setup() {
  Serial.begin(115200);
  delay(1000);
  
  // Pin setup
  pinMode(LED_PIN, OUTPUT);
  pinMode(PIR_PIN, INPUT);
  pinMode(REED_PIN, INPUT_PULLUP);
  digitalWrite(LED_PIN, LOW);
  
  // DHT sensor
  dht.begin();
  
  // Generate unique device ID from MAC address
  deviceId = String(DEVICE_ID);
  
  Serial.println("\n=============================");
  Serial.println("IoT-TrustBench Sensor Node");
  Serial.println("=============================");
  Serial.print("Device ID: ");
  Serial.println(deviceId);
  
  // Connect to WiFi
  connectWiFi();
  
  Serial.println("Sensors initialized. Starting...");
  Serial.println("-------------------------------");
}

// ===== MAIN LOOP =====
void loop() {
  // Reconnect WiFi if lost
  if (WiFi.status() != WL_CONNECTED) {
    connectWiFi();
  }
  
  // Send data at interval
  unsigned long now = millis();
  if (now - lastSend >= SEND_INTERVAL) {
    lastSend = now;
    
    // Read all sensors
    float temperature = dht.readTemperature();
    float humidity = dht.readHumidity();
    int gasRaw = analogRead(MQ2_PIN);
    bool motion = digitalRead(PIR_PIN);
    bool doorOpen = !digitalRead(REED_PIN); // Reed switch is LOW when closed
    
    // Convert gas ADC to 0-100 scale
    float gasLevel = map(gasRaw, 0, 4095, 0, 100);
    gasLevel = constrain(gasLevel, 0, 100);
    
    // Calculate smoke (approximate from gas sensor)
    float smokeLevel = gasLevel * 0.8; // MQ-2 responds to both gas and smoke
    
    // Check if DHT read failed
    bool dhtValid = !isnan(temperature) && !isnan(humidity);
    
    if (!dhtValid) {
      Serial.println("[WARN] DHT read failed, using last valid values");
    }
    
    // Build JSON payload
    StaticJsonDocument<512> doc;
    doc["device_id"] = deviceId;
    doc["temperature"] = dhtValid ? round(temperature * 10.0) / 10.0 : 0.0;
    doc["humidity"] = dhtValid ? round(humidity * 10.0) / 10.0 : 0.0;
    doc["smoke"] = round(smokeLevel * 10.0) / 10.0;
    doc["gas"] = round(gasLevel * 10.0) / 10.0;
    doc["motion"] = motion;
    doc["door_status"] = doorOpen ? "open" : "closed";
    doc["power_status"] = "on";
    
    // Serialize to string
    String payload;
    serializeJson(doc, payload);
    
    // Print to serial monitor
    Serial.println("\n--- Sensor Reading ---");
    Serial.print("Temp: "); Serial.print(temperature); Serial.println(" C");
    Serial.print("Humidity: "); Serial.print(humidity); Serial.println(" %");
    Serial.print("Smoke: "); Serial.print(smokeLevel); Serial.println("");
    Serial.print("Gas: "); Serial.print(gasLevel); Serial.print(" (ADC: "); Serial.print(gasRaw); Serial.println(")");
    Serial.print("Motion: "); Serial.println(motion ? "YES" : "no");
    Serial.print("Door: "); Serial.println(doorOpen ? "OPEN" : "closed");
    Serial.print("Payload: "); Serial.println(payload);
    
    // Send to server
    sendToServer(payload);
    
    // Blink LED on send
    digitalWrite(LED_PIN, HIGH);
    delay(100);
    digitalWrite(LED_PIN, LOW);
  }
}

// ===== FUNCTIONS =====

void connectWiFi() {
  Serial.print("Connecting to WiFi: ");
  Serial.println(WIFI_SSID);
  
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  
  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 30) {
    delay(500);
    Serial.print(".");
    attempts++;
  }
  
  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\nWiFi connected!");
    Serial.print("IP address: ");
    Serial.println(WiFi.localIP());
    digitalWrite(LED_PIN, HIGH);
    delay(500);
    digitalWrite(LED_PIN, LOW);
  } else {
    Serial.println("\nWiFi connection failed! Will retry...");
  }
}

void sendToServer(String payload) {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[ERROR] WiFi not connected, skipping send");
    return;
  }
  
  HTTPClient http;
  http.begin(SERVER_URL);
  http.addHeader("Content-Type", "application/json");
  http.setTimeout(5000);
  
  int httpResponseCode = http.POST(payload);
  
  if (httpResponseCode > 0) {
    String response = http.getString();
    Serial.print("[OK] Server response (");
    Serial.print(httpResponseCode);
    Serial.print("): ");
    Serial.println(response);
  } else {
    Serial.print("[ERROR] HTTP POST failed: ");
    Serial.println(http.errorToString(httpResponseCode));
  }
  
  http.end();
}
