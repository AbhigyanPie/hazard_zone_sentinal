# PipeGen build guide — Hazard Zone Sentinel

Target: about 75 minutes. Take every screenshot as you go; you cannot recreate them later.

## 0. Before you open PipeGen (10 min)
- `pipegen --version` prints `0.5.1`. Sign in with your CraftifAI account.
- X11 desktop session (not Wayland): `echo $XDG_SESSION_TYPE` should print `x11`.
- Video under `/home`: download a free warehouse, factory or construction CCTV-style clip with people walking (Pexels: search "warehouse workers" or "factory workers walking"). Save as `/home/<you>/videos/site.mp4`. 30–90 s, 1080p, static camera angle.
- MQTT broker: `sudo apt install -y mosquitto mosquitto-clients && sudo systemctl start mosquitto`

## 1. Requirement
Paste this:

> Build a workplace safety pipeline for a fixed warehouse CCTV camera. Detect people in every frame, track them with persistent track IDs, and run in real time on the GPU. Input is the video file /home/<you>/videos/site.mp4 (later a USB camera). For every frame, publish the bounding boxes, class labels and track IDs as JSON over MQTT to localhost:1883 on topic pipegen/detections, also write the same metadata to a JSON file, and show an on-screen display with boxes and track IDs. Optimize for edge deployment: compile the detector to TensorRT and compare FP16 and INT8.

If it asks follow-ups: resolution 1920x1080, one stream, class = person, tracker = NvDCF or IOU (whatever it defaults to), MQTT payload = DeepStream JSON (minimal or full, both work).

## 2. Pipeline IR
- Check the graph: source → decoder → streammux → nvinfer (person detector) → tracker → OSD → sinks, plus a message broker / MQTT branch.
- If there is no MQTT/msgbroker node, ask PipeGen in this stage to add one before moving on.
- SCREENSHOT the node graph → `evidence/01_pipeline_ir.png`

## 3. Model
- Choose a person detector from the catalog (PeopleNet or a YOLO person/COCO detector). If none fits, use Deep Search with "person detection onnx".
- SCREENSHOT the chosen model → `evidence/02_model.png`

## 4. Compiler
- Compile FP16 first. SCREENSHOT the speed/power report → `evidence/03_trt_fp16.png`
- Compile INT8 (Edge Optimization bonus). SCREENSHOT the report → `evidence/04_trt_int8.png`
- Note FPS, latency, power and accuracy for both; they go in SUBMISSION.md.
- If INT8 calibration fails or eats more than 20 minutes, skip it and keep FP16. FP16 alone meets the mandatory requirement.

## 5. Run
- Run the generated app (`run.sh`) on `site.mp4`. You should see boxes and IDs on people.
- In a second terminal: `mosquitto_sub -t 'pipegen/#' -C 1` → confirm JSON arrives. Save one message: `mosquitto_sub -t 'pipegen/#' -C 1 > evidence/sample_payload.json`
- In a third terminal: `python3 sentinel.py --mqtt localhost --topic 'pipegen/#' --size 1920x1080`
- Open http://localhost:8080. Adjust `--zone` so the red polygon covers a walkway people actually cross.
- SCREENSHOT the video window and dashboard side by side → `evidence/05_live_run.png`
- SCREEN RECORD 60 s (OBS or `Ctrl+Alt+Shift+R` on GNOME) → upload to YouTube unlisted or Drive.
- Copy `incidents.jsonl` → `evidence/incidents.jsonl`

## 6. Export
- Export the PipeGen project folder into `pipegen_export/` in this repo (configs, run.sh, engine reports).

## If MQTT won't work
Use PipeGen's JSON metadata file instead:
`python3 sentinel.py --json /path/to/metadata.json --size 1920x1080`
If the dashboard stays empty, paste `evidence/sample_payload.json` (or the first lines of the JSON file) to Claude and the parser will be adjusted.
