# Hazard Zone Sentinel

**Track A — PipeGen (Perception)** · Workplace Safety Sentinel · Bonus: Edge Optimization (INT8), optional Closed Loop with a FirmGen ESP32 alarm node

Turn any existing CCTV camera into a real-time safety monitor that flags workers entering danger zones.

## Problem
On factory floors, in warehouses and on construction sites, workers walk into hazard zones (forklift lanes, robotic cells, open pits) and nobody notices until something goes wrong. CCTV exists, but no one watches it live.

## How it works: see → decide → act
```
Site camera / video
        │
        ▼
PipeGen DeepStream app ── TensorRT person detector (FP16 / INT8) + tracker      SEE
        │  MQTT  pipegen/detections   (bbox + track ID per frame)
        ▼
sentinel.py ── foot point inside hazard polygon? one incident per track         DECIDE
        ├──► incidents.jsonl          (who, when, dwell time)
        ├──► live dashboard :8080     (zone, boxes, incident log)
        └──► MQTT  sentinel/alerts  ──► ESP32 alarm node (FirmGen): LED + buzzer  ACT
```

PipeGen is load-bearing: every detection, track ID and timestamp the system acts on comes from the TensorRT engine PipeGen compiled and the DeepStream app it generated.

## PipeGen pipeline
| Stage | Choice |
|---|---|
| Input | Site CCTV video at 1920x1080 (or USB camera) |
| Tasks | Person detection + multi-object tracking |
| Model | Person detector from the PipeGen catalog |
| Precision | FP16 baseline, INT8 for Edge Optimization |
| Outputs | MQTT detection feed, JSON metadata file, on-screen display |

Build steps, the exact Requirement prompt and the screenshot checklist are in [`prompts/PIPEGEN_STEPS.md`](prompts/PIPEGEN_STEPS.md). Results are in [`SUBMISSION.md`](SUBMISSION.md); screenshots and logs are in [`evidence/`](evidence/).

## Run
```bash
pip install paho-mqtt
sudo apt install -y mosquitto mosquitto-clients

# 1. PipeGen-generated DeepStream app
cd pipegen_export && ./run.sh

# 2. Decision layer + dashboard (http://localhost:8080)
python3 sentinel.py --mqtt localhost --topic 'pipegen/#' --size 1920x1080 \
  --zone "0.55,0.35;0.95,0.35;0.95,0.95;0.55,0.95"

# fallback: read PipeGen's JSON metadata file instead of MQTT
python3 sentinel.py --json pipegen_export/<metadata>.json --size 1920x1080

# no GPU: simulated detections (UI and ESP32 test only)
python3 sentinel.py --demo --mqtt localhost
```
`--zone` is a normalized polygon (0–1 for x and y). `--size` must match the pipeline's output resolution.

Alert payload on `sentinel/alerts`:
```json
{"event": "ENTER", "incident": 3, "track_id": "17", "sensor": "cam0",
 "time": "2026-10-16T21:42:10", "dwell_s": 0.0, "active": 1}
```

## Closed Loop (optional): FirmGen ESP32 alarm node
[`firmgen/Sentinel_Alarm_Node_PRD.pdf`](firmgen/) is the PRD to upload in FirmGen (I have a document). The node joins Wi-Fi, subscribes to `sentinel/alerts`, blinks the warning LED and pulses a buzzer while `active > 0`, and shows a slow blink when offline.

Let the ESP32 reach the broker on your laptop:
```bash
printf "listener 1883 0.0.0.0\nallow_anonymous true\n" | sudo tee /etc/mosquitto/conf.d/lan.conf
sudo systemctl restart mosquitto
hostname -I   # put this IP in the PRD config as the broker host
```
Laptop and ESP32 must be on the same 2.4 GHz Wi-Fi (a phone hotspot works).

## Repo
| Path | Contents |
|---|---|
| `pipegen_export/` | PipeGen export: DeepStream app, configs, `run.sh`, engine reports |
| `sentinel.py` | Decision, incident log, MQTT alert republish, dashboard |
| `prompts/` | PipeGen Requirement prompt and stage guide |
| `firmgen/` | ESP32 alarm node PRD and FirmGen project (Closed Loop) |
| `evidence/` | Screenshots, reports, sample payload, incident log |
| `SUBMISSION.md` | Project description for the submission form |
# hazard_zone_sentinal
