# Submission form answers (copy-paste)

Fill the [brackets] from your PipeGen reports before submitting. Delete the Closed Loop lines if you did not get the ESP32 working.

**Project name:** Hazard Zone Sentinel

**Track:** Track A — PipeGen (Perception)

**Bonus targeted:** Edge Optimization (INT8). [Closed Loop — only if the ESP32 node ran]

**Repository:** [github link]

**Demo video:** [YouTube unlisted / Drive link]

---

**Problem**
In warehouses, factories and construction sites, workers walk into hazard zones (forklift lanes, robot cells, open pits) and nobody notices until there is an incident. CCTV is already installed, but no one watches it live.

**Solution**
Hazard Zone Sentinel turns an existing CCTV camera into a real-time safety monitor. A PipeGen-generated DeepStream pipeline detects and tracks every person on the GPU and streams per-frame metadata over MQTT. A decision layer checks each tracked person's foot point against a hazard polygon, raises one alert per incident rather than one per frame, logs each incident with dwell time, republishes alerts on `sentinel/alerts` for downstream systems, and shows a live safety dashboard.

**PipeGen pipeline**
- Input: site CCTV video file at 1920x1080 [and USB camera]
- Tasks: person detection + multi-object tracking
- Model: [model name from PipeGen catalog]
- Precision: FP16 baseline and INT8
- Outputs: MQTT detection feed (`pipegen/detections`), JSON metadata file, on-screen display
- All five stages used: Requirement → Pipeline IR → Model → Compiler → Run

**TensorRT results** (from PipeGen's reports)
| Precision | FPS | Latency (ms) | Power (W) | Accuracy |
|---|---|---|---|---|
| FP16 | [ ] | [ ] | [ ] | [ ] |
| INT8 | [ ] | [ ] | [ ] | [ ] |

INT8 gives [x]x the throughput of FP16 at [y]% lower power for a [z]-point accuracy change, which is what makes a low-cost, always-on unit per camera practical.

**Why PipeGen is load-bearing**
Every detection, track ID and timestamp the system acts on comes from the TensorRT engine PipeGen compiled and the DeepStream app it generated. The decision layer has no other input; without the pipeline there is no system.

**Closed Loop (if done)**
A FirmGen-built ESP32 alarm node subscribes to `sentinel/alerts` over Wi-Fi. When a person enters the zone in the video, the board's warning LED and buzzer switch on in real time and switch off when the zone clears. Its PRD, frozen requirements and traceability report are in `firmgen/`.

**Evidence**
`evidence/` holds the Pipeline IR graph, FP16 and INT8 TensorRT reports, a live-run screenshot, a sample MQTT payload and the incident log from the live run.
