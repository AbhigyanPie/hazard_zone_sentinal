#!/usr/bin/env python3
"""Hazard Zone Sentinel - decision + action layer on top of a PipeGen/DeepStream pipeline.

Reads PipeGen's detection metadata (MQTT or a JSON/JSONL file), decides when a person
enters the hazard zone, logs incidents, republishes alerts over MQTT and serves a live
dashboard at http://localhost:8080.

  python3 sentinel.py --mqtt localhost --topic pipegen/detections
  python3 sentinel.py --json /home/me/pipegen_out/metadata.jsonl
  python3 sentinel.py --demo                    # UI check, no GPU
  python3 sentinel.py --demo --mqtt localhost   # also publishes alerts (ESP32 test)
"""
import argparse, json, os, random, threading, time
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

ap = argparse.ArgumentParser()
ap.add_argument("--mqtt", help="MQTT broker host")
ap.add_argument("--port", type=int, default=1883)
ap.add_argument("--topic", default="pipegen/#")
ap.add_argument("--alert-topic", default="sentinel/alerts")
ap.add_argument("--json", help="tail a JSON/JSONL metadata file instead of MQTT")
ap.add_argument("--demo", action="store_true", help="simulated detections, no GPU needed")
ap.add_argument("--size", default="1920x1080", help="frame size of the pipeline output")
ap.add_argument("--zone", default="0.55,0.35;0.95,0.35;0.95,0.95;0.55,0.95",
                help="hazard polygon, normalized x,y pairs")
ap.add_argument("--label", default="person")
ap.add_argument("--grace", type=float, default=2.0, help="seconds out of zone before incident closes")
ap.add_argument("--log", default="incidents.jsonl")
ap.add_argument("--http", type=int, default=8080)
a = ap.parse_args()

W, H = map(int, a.size.lower().split("x"))
zone = [tuple(map(float, p.split(","))) for p in a.zone.split(";")]
lock = threading.Lock()
st = {"objs": [], "inzone": 0, "total": 0, "open": {}, "log": [], "msgs": 0, "t0": time.time(), "last": 0}
pub = None


def inside(x, y, poly):
    ok, n = False, len(poly)
    for i in range(n):
        (x1, y1), (x2, y2) = poly[i], poly[(i + 1) % n]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            ok = not ok
    return ok


def parse(m):
    """Normalize DeepStream minimal/full schemas and generic detection JSON to
    [(id, label, l, t, r, b)] in pixels."""
    out = []
    for o in m.get("objects", []) if isinstance(m.get("objects"), list) else []:
        if isinstance(o, str):  # minimal schema: "id|l|t|r|b|label|..."
            f = o.split("|")
            if len(f) >= 6:
                out.append((f[0], f[5].lower(), *map(float, f[1:5])))
        elif isinstance(o, dict):
            out.append(fromdict(o))
    if isinstance(m.get("object"), dict):  # full schema, one object per message
        out.append(fromdict(m["object"]))
    for k in ("detections", "objs"):
        for o in m.get(k, []) or []:
            out.append(fromdict(o))
    return [o for o in out if o]


def fromdict(o):
    id_ = str(o.get("id", o.get("track_id", o.get("object_id", "?"))))
    lab = str(o.get("label", o.get("class", o.get("obj_label", "")))).lower()
    if not lab and "person" in o:
        lab = "person"
    b = o.get("bbox", o.get("rect_params", o))
    if isinstance(b, list) and len(b) == 4:
        l, t, w, h = map(float, b)
        return (id_, lab, l, t, l + w, t + h)
    if "topleftx" in b:
        return (id_, lab, b["topleftx"], b["toplefty"], b["bottomrightx"], b["bottomrighty"])
    if "left" in b:
        l, t = float(b["left"]), float(b["top"])
        return (id_, lab, l, t, l + float(b["width"]), t + float(b["height"]))
    return None


def handle(m):
    objs, now = parse(m), time.time()
    seen, view, n = set(), [], 0
    for id_, lab, l, t, r, b in objs:
        hit = a.label in lab and inside((l + r) / 2 / W, b / H, zone)  # foot point
        view.append({"id": id_, "lab": lab, "box": [l / W, t / H, r / W, b / H], "hit": hit})
        if not hit:
            continue
        n += 1
        seen.add(id_)
        with lock:
            inc = st["open"].get(id_)
            if inc:
                inc["last"] = now
                continue
            st["total"] += 1
            inc = {"n": st["total"], "id": id_, "start": now, "last": now,
                   "ts": time.strftime("%H:%M:%S"), "sensor": m.get("sensorId", m.get("sensor", "cam0"))}
            st["open"][id_] = inc
        emit("ENTER", inc)
    with lock:
        for id_, inc in list(st["open"].items()):
            if id_ not in seen and now - inc["last"] > a.grace:
                del st["open"][id_]
                emit("EXIT", inc)
        st.update(objs=view, inzone=n, last=now)
        st["msgs"] += 1


def emit(kind, inc):
    rec = {"event": kind, "incident": inc["n"], "track_id": inc["id"], "sensor": inc["sensor"],
           "time": time.strftime("%Y-%m-%dT%H:%M:%S"),
           "dwell_s": round(inc["last"] - inc["start"], 1), "active": len(st["open"])}
    print(("\033[91m[ALERT]" if kind == "ENTER" else "\033[92m[CLEAR]") + "\033[0m", json.dumps(rec), flush=True)
    with open(a.log, "a") as f:
        f.write(json.dumps(rec) + "\n")
    st["log"] = ([rec] + st["log"])[:25]
    if pub:
        pub.publish(a.alert_topic, json.dumps(rec), qos=1)


def on_raw(raw):
    try:
        m = json.loads(raw)
    except Exception:
        return
    for x in m if isinstance(m, list) else [m]:
        if isinstance(x, dict):
            handle(x)


def run_mqtt():
    global pub
    import paho.mqtt.client as mqtt
    try:
        c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    except AttributeError:
        c = mqtt.Client()
    c.on_connect = lambda c, *_: (c.subscribe(a.topic), print(f"subscribed {a.topic}"))
    c.on_message = lambda c, u, msg: on_raw(msg.payload) if not msg.topic.startswith(a.alert_topic) else None
    c.connect(a.mqtt, a.port, 60)
    pub = c
    c.loop_forever()


def run_file():
    while not os.path.exists(a.json):
        time.sleep(0.5)
    with open(a.json) as f:
        buf = f.read()
        try:  # whole-file JSON (array or single object)
            json.loads(buf)
            on_raw(buf)
        except Exception:  # JSONL
            for ln in buf.splitlines():
                on_raw(ln)
        while True:
            ln = f.readline()
            if ln:
                on_raw(ln)
            else:
                time.sleep(0.05)


def run_demo():
    ppl = [{"id": str(i), "x": random.uniform(0.05, 0.9), "y": random.uniform(0.4, 0.9),
            "vx": random.uniform(-0.01, 0.01), "vy": random.uniform(-0.004, 0.004)} for i in range(5)]
    while True:
        objs = []
        for p in ppl:
            p["x"] = min(max(p["x"] + p["vx"], 0.02), 0.95)
            p["y"] = min(max(p["y"] + p["vy"], 0.35), 0.98)
            if p["x"] in (0.02, 0.95): p["vx"] *= -1
            if p["y"] in (0.35, 0.98): p["vy"] *= -1
            l, b = p["x"] * W, p["y"] * H
            objs.append(f'{p["id"]}|{l - 40:.0f}|{b - 220:.0f}|{l + 40:.0f}|{b:.0f}|Person')
        handle({"sensorId": "demo-cam", "objects": objs})
        time.sleep(1 / 15)


PAGE = r"""<!doctype html><html><head><meta charset="utf-8"><title>Hazard Zone Sentinel</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
:root{--bg:#0d0f12;--card:#161a1f;--line:#252b33;--tx:#e8ecf1;--mu:#8a95a3;--red:#ff4d4f;--grn:#3ddc84}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--tx);font:14px/1.4 system-ui,sans-serif}
.w{max-width:1100px;margin:auto;padding:20px 16px}h1{font-size:18px;margin:0 0 4px}.mu{color:var(--mu)}
.top{display:flex;justify-content:space-between;align-items:end;margin-bottom:16px}
.st{padding:6px 12px;border-radius:99px;font-weight:600;background:#1d3a2a;color:var(--grn)}
.st.on{background:#4a1416;color:var(--red);animation:p 1s infinite}@keyframes p{50%{opacity:.6}}
.g{display:grid;grid-template-columns:2fr 1fr;gap:16px}@media(max-width:800px){.g{grid-template-columns:1fr}}
.c{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px}
canvas{width:100%;aspect-ratio:16/9;background:#090b0d;border-radius:8px;display:block}
.k{display:grid;grid-template-columns:repeat(2,1fr);gap:10px;margin-bottom:12px}
.k div{background:#0f1216;border-radius:8px;padding:10px}.k b{display:block;font-size:24px}
table{width:100%;border-collapse:collapse;font-size:13px}td{padding:6px 4px;border-top:1px solid var(--line)}
.E{color:var(--red)}.X{color:var(--grn)}
</style></head><body><div class="w">
<div class="top"><div><h1>Hazard Zone Sentinel</h1><div class="mu">PipeGen / DeepStream perception &rarr; zone decision &rarr; MQTT alert</div></div>
<div id="st" class="st">ZONE CLEAR</div></div>
<div class="g"><div class="c"><canvas id="cv" width="1280" height="720"></canvas></div>
<div class="c"><div class="k"><div><span class="mu">People in frame</span><b id="pf">0</b></div>
<div><span class="mu">In hazard zone</span><b id="pz">0</b></div>
<div><span class="mu">Incidents</span><b id="ti">0</b></div><div><span class="mu">Msg/s</span><b id="mr">0</b></div></div>
<div class="mu" style="margin-bottom:6px">Incident log</div><table id="lg"></table></div></div></div>
<script>
const Z=__ZONE__,cv=document.getElementById('cv'),x=cv.getContext('2d'),$=i=>document.getElementById(i);
const es=new EventSource('/events');
es.onmessage=e=>{const s=JSON.parse(e.data),W=cv.width,H=cv.height;
x.clearRect(0,0,W,H);x.beginPath();Z.forEach(([a,b],i)=>i?x.lineTo(a*W,b*H):x.moveTo(a*W,b*H));x.closePath();
x.fillStyle=s.inzone?'rgba(255,77,79,.18)':'rgba(255,196,0,.08)';x.fill();x.setLineDash([10,6]);x.lineWidth=2;
x.strokeStyle=s.inzone?'#ff4d4f':'#ffc400';x.stroke();x.setLineDash([]);
s.objs.forEach(o=>{const[l,t,r,b]=o.box;x.strokeStyle=o.hit?'#ff4d4f':'#3ddc84';x.lineWidth=3;
x.strokeRect(l*W,t*H,(r-l)*W,(b-t)*H);x.fillStyle=x.strokeStyle;x.font='20px system-ui';x.fillText(o.lab+' #'+o.id,l*W,t*H-6)});
$('pf').textContent=s.objs.length;$('pz').textContent=s.inzone;$('ti').textContent=s.total;$('mr').textContent=s.rate;
$('st').className='st'+(s.inzone?' on':'');$('st').textContent=s.inzone?'BREACH \u2014 '+s.inzone+' IN ZONE':'ZONE CLEAR';
$('lg').innerHTML=s.log.map(r=>`<tr><td class="${r.event[0]}">${r.event}</td><td>#${r.incident}</td><td>track ${r.track_id}</td><td class="mu">${r.time.slice(11)}${r.event=='EXIT'?' \u00b7 '+r.dwell_s+'s':''}</td></tr>`).join('')};
</script></body></html>"""


class Hd(BaseHTTPRequestHandler):
    def log_message(self, *_): pass

    def do_GET(self):
        if self.path == "/events":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            try:
                while True:
                    with lock:
                        el = max(time.time() - st["t0"], 1)
                        s = {"objs": st["objs"] if time.time() - st["last"] < 2 else [],
                             "inzone": st["inzone"] if time.time() - st["last"] < 2 else 0,
                             "total": st["total"], "log": st["log"], "rate": round(st["msgs"] / el, 1)}
                    self.wfile.write(f"data: {json.dumps(s)}\n\n".encode())
                    self.wfile.flush()
                    time.sleep(0.1)
            except (BrokenPipeError, ConnectionResetError):
                return
        body = PAGE.replace("__ZONE__", json.dumps(zone)).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    src = run_demo if a.demo else run_file if a.json else run_mqtt if a.mqtt else None
    if not src:
        ap.error("pass --mqtt HOST, --json FILE or --demo")
    if a.demo and a.mqtt:  # demo detections, real MQTT alerts (test the ESP32 node without a GPU)
        import paho.mqtt.client as mqtt
        try:
            pub = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        except AttributeError:
            pub = mqtt.Client()
        pub.connect(a.mqtt, a.port, 60)
        pub.loop_start()
    threading.Thread(target=src, daemon=True).start()
    print(f"dashboard: http://localhost:{a.http}")
    ThreadingHTTPServer(("0.0.0.0", a.http), Hd).serve_forever()
