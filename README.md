# IoT-TrustBench

A Software-Based Framework to Evaluate Safe LLM Decisions Using Simulated IoT Sensor Data.

## Features

- **Virtual IoT Simulation** - Generate realistic sensor data without hardware
- **Safety Classification** - Deterministic rules classify 6 event types
- **100% Accuracy** - All 6 classes classified correctly (600/600 samples)
- **0 Dangerous Errors** - Emergency events never misclassified as normal
- **Hardware Integration** - Connect real ESP32 sensor nodes
- **Web Dashboard** - Professional modern UI with charts and metrics
- **Batch Testing** - Run 100+ scenarios with confusion matrix
- **API Documentation** - Auto-generated Swagger docs at `/docs`

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Start server
python run.py

# Open browser
http://localhost:8000
```

## Decision Classes

| Class | Description | Action |
|-------|-------------|--------|
| **Normal** | All readings safe | None |
| **Emergency** | Multiple danger indicators | Alert |
| **Sensor Fault** | One sensor abnormal, others disagree | Verify |
| **Spoofing** | Invalid data or unknown device | Block |
| **Offline** | Data missing or stale | Wait |
| **Uncertain** | Evidence insufficient | Human verify |

## Hardware Integration

### Required Parts
- ESP32 DevKit V1 (~$5-8)
- DHT22 Temperature/Humidity Sensor (~$3-5)
- MQ-2 Gas/Smoke Sensor (~$2-4)
- HC-SR501 PIR Motion Sensor (~$1-2)
- Magnetic Reed Switch (~$1)
- Jumper wires + breadboard (~$5)

**Total: ~$17-27**

### Wiring
```
DHT22 DATA → ESP32 GPIO4
MQ-2 AOUT  → ESP32 GPIO34
PIR OUT    → ESP32 GPIO27
Reed Switch → ESP32 GPIO26
```

### Setup
1. Open `hardware/esp32_sensor_node/esp32_sensor_node.ino` in Arduino IDE
2. Edit WiFi SSID, password, and server IP
3. Upload to ESP32
4. Open Serial Monitor at 115200 baud
5. View live data at `http://localhost:8000/hardware`

Full wiring guide: `hardware/WIRING_GUIDE.md`

## Project Structure

```
iot_trustbench/
├── core/
│   ├── sensor_simulator.py   # Virtual sensor data generation
│   ├── data_validator.py     # Range, timestamp, device validation
│   ├── safety_engine.py      # Deterministic classification rules
│   └── llm_explainer.py      # LLM explanation generation
├── api/
│   └── app.py                # FastAPI application
├── database/
│   └── db.py                 # SQLite operations
├── static/css/style.css      # Modern CSS design system
├── templates/                # Jinja2 HTML templates
│   ├── base.html             # Base layout with sidebar
│   ├── home.html             # Dashboard overview
│   ├── live.html             # Live simulation
│   ├── scenarios.html        # Batch test runner
│   ├── history.html          # Decision history
│   ├── evaluation.html       # Metrics + charts
│   └── hardware.html         # Hardware integration
├── scenarios/
│   └── test_scenarios.json   # 100 labelled scenarios
└── tests/
    ├── test_core.py          # Unit tests (10 tests)
    └── test_batch.py         # Batch evaluation
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/simulate` | Run simulated test |
| POST | `/api/hardware` | Receive hardware data |
| GET | `/api/hardware/readings` | Hardware reading history |
| GET | `/api/hardware/devices` | Connected devices |
| GET | `/api/hardware/latest` | Latest hardware reading |
| GET | `/api/scenarios` | List scenarios |
| GET | `/api/decisions` | Decision history |
| POST | `/api/batch-test` | Run batch evaluation |
| GET | `/api/evaluation` | Accuracy metrics |
| POST | `/api/reset-history` | Clear all data |

## Technology Stack

- **Backend:** Python 3 + FastAPI
- **Frontend:** HTML + CSS + Bootstrap Icons + Chart.js
- **Database:** SQLite
- **Hardware:** ESP32 + DHT22 + MQ-2 + PIR + Reed Switch
- **LLM:** Gemini API / OpenAI / Local fallback

## Dashboard Pages

- **Dashboard** (`/`) - Overview, quick actions, decision classes
- **Live Simulation** (`/live`) - Run individual tests with gauge
- **Scenarios** (`/scenarios`) - Batch test with confusion matrix
- **History** (`/history`) - Past decisions with filters
- **Evaluation** (`/evaluation`) - 4 charts: bar, doughnut, F1, radar
- **Hardware** (`/hardware`) - Real-time ESP32 sensor data
- **API Docs** (`/docs`) - Swagger documentation

## Testing

```bash
# Unit tests
python -m pytest iot_trustbench/tests/test_core.py -v

# Batch evaluation (100 tests)
python iot_trustbench/tests/test_batch.py

# Full system test
python test_full.py
```

## LLM Configuration (Optional)

```bash
set LLM_BACKEND=gemini
set LLM_API_KEY=your_api_key
set LLM_MODEL=gemini-2.0-flash
```

Supported: `gemini`, `openai`, `local` (default, no API needed)

## License

Educational project for IoT safety research.
