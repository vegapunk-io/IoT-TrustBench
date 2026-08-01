# ESP32 Hardware Wiring Guide

## Parts List

| Component | Model | Qty | Cost (approx) |
|-----------|-------|-----|---------------|
| Microcontroller | ESP32 DevKit V1 | 1 | $5-8 |
| Temperature/Humidity | DHT22 (AM2302) | 1 | $3-5 |
| Gas/Smoke | MQ-2 Gas Sensor | 1 | $2-4 |
| Motion | HC-SR501 PIR Sensor | 1 | $1-2 |
| Door/Window | Magnetic Reed Switch | 1 | $1 |
| Breadboard | 830 points | 1 | $2-3 |
| Jumper Wires | Male-to-Female | ~20 | $2-3 |
| USB Cable | Micro USB / USB-C | 1 | $1-2 |

**Total Cost: ~$17-27**

## Wiring Diagram

```
ESP32 DevKit V1
===============
    3.3V  ─────┬──────────────────┬──────────────┐
                │                  │              │
    GND   ─────┼──────┬───────────┼──────────┬───┤
                │      │           │          │   │
    VIN   (5V)  ───────┼───────────┤          │   │
                │      │           │          │   │
    GPIO4 ───────────────────────────────────────┤── DHT22 DATA
    GPIO34 ──────────────────────────────────────┤── MQ-2 AOUT
    GPIO27 ──────────────────────────────────────┤── PIR OUT
    GPIO26 ──────────────────────────────────────┤── Reed Switch
    GPIO2 (LED) ─────────────────────────────────┤── Built-in LED


Component Wiring:
==================

DHT22 (Temperature + Humidity Sensor):
  VCC  → ESP32 3.3V
  GND  → ESP32 GND
  DATA → ESP32 GPIO4 (with 10K pull-up resistor to 3.3V)

MQ-2 Gas Sensor:
  VCC  → ESP32 VIN (5V)
  GND  → ESP32 GND
  AOUT → ESP32 GPIO34 (analog input)
  DOUT → (not connected)

HC-SR501 PIR Motion Sensor:
  VCC  → ESP32 VIN (5V)
  GND  → ESP32 GND
  OUT  → ESP32 GPIO27

Magnetic Reed Switch (Door/Window):
  One wire  → ESP32 GPIO26
  Other wire → ESP32 GND
  (Uses internal pull-up resistor, closes circuit when magnet is near)
```

## Detailed Pin Connections

### DHT22 Wiring
```
DHT22 Pin    ESP32 Pin
---------    ---------
VCC     →    3.3V
DATA    →    GPIO4 (with 10K pull-up to 3.3V)
NC      →    (not connected)
GND     →    GND
```

### MQ-2 Gas Sensor Wiring
```
MQ-2 Pin     ESP32 Pin
---------    ---------
VCC     →    VIN (5V)
GND     →    GND
AOUT    →    GPIO34 (analog)
DOUT    →    (not connected)
```

### PIR Motion Sensor Wiring
```
PIR Pin      ESP32 Pin
---------    ---------
VCC     →    VIN (5V)
GND     →    GND
OUT     →    GPIO27

Adjust sensitivity and delay with onboard potentiometers.
```

### Reed Switch Wiring
```
Reed Switch    ESP32 Pin
-----------    ---------
Pin 1      →   GPIO26
Pin 2      →   GND

(NO - Normally Open: circuit closes when magnet is near)
```

## Software Setup

### 1. Install Arduino IDE
Download from: https://www.arduino.cc/en/software

### 2. Install ESP32 Board
1. Open Arduino IDE → File → Preferences
2. Additional Board Manager URLs: `https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json`
3. Tools → Board → Board Manager → Search "esp32" → Install

### 3. Install Libraries
Sketch → Include Library → Manage Libraries:
- `DHT sensor library` (by Adafruit)
- `Adafruit Unified Sensor`
- `ArduinoJson` (by Benoit Blanchon)

### 4. Configure the Sketch
Edit `esp32_sensor_node.ino`:
```cpp
const char* WIFI_SSID     = "YOUR_WIFI_SSID";      // Your WiFi name
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";   // Your WiFi password
const char* SERVER_URL    = "http://192.168.1.100:8000/api/hardware";  // Your PC's IP
const char* DEVICE_ID     = "ESP32-NODE-001";       // Unique device name
```

### 5. Find Your PC's IP Address
Open Command Prompt and run: `ipconfig`
Look for "IPv4 Address" (e.g., 192.168.1.100)

### 6. Upload to ESP32
1. Connect ESP32 via USB
2. Tools → Board → ESP32 Dev Module
3. Tools → Port → Select your COM port
4. Click Upload

### 7. Open Serial Monitor
Tools → Serial Monitor → Set baud rate to 115200

## Troubleshooting

| Problem | Solution |
|---------|----------|
| WiFi won't connect | Check SSID/password, ensure 2.4GHz network |
| DHT22 reads NaN | Check wiring, add 10K pull-up resistor |
| MQ-2 always reads 0 | Ensure VCC connected to 5V (VIN), not 3.3V |
| No data on server | Check server IP, ensure firewall allows port 8000 |
| Door shows "open" always | Reed switch orientation - swap wires |
| Motion always triggers | Adjust PIR sensitivity potentiometer (CW = less sensitive) |
