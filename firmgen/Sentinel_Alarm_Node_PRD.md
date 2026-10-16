# Sentinel Alarm Node — PRD (FirmGen, ESP32)

## Objective
Firmware for an ESP32 DevKit that acts as the physical alarm for the Hazard Zone Sentinel vision system. A PipeGen pipeline detects people entering a hazard zone and publishes alerts over MQTT; this node receives them over Wi-Fi and drives a warning light and buzzer in real time.

## Hardware
- ESP32 DevKit (Wi-Fi required)
- Warning LED: on-board LED (GPIO2) or external LED on GPIO2 through a 220 ohm resistor
- Active buzzer on GPIO4 (optional; the firmware must work without it fitted)
- Status LED: external LED on GPIO5 (optional)

## Configuration
Wi-Fi SSID, Wi-Fi password, MQTT broker host and port are compile-time constants in a single config header. Default broker port 1883.

## Requirements
1. Connect to the configured Wi-Fi network after boot and retry every 5 seconds until connected.
2. Connect to the MQTT broker and subscribe to topic `sentinel/alerts` with QoS 1.
3. Reconnect automatically to Wi-Fi and MQTT if either connection drops, and resubscribe after reconnecting.
4. Parse each message on `sentinel/alerts` as JSON with fields `event` ("ENTER" or "EXIT"), `incident` (integer), `track_id` (string) and `active` (integer, number of people currently in the zone).
5. ALARM state: when `active` is greater than 0, the warning LED blinks at 4 Hz and the buzzer sounds in 200 ms on / 200 ms off pulses.
6. SAFE state: when `active` equals 0, the warning LED and buzzer are off.
7. Fail-safe: if no MQTT connection exists for more than 10 seconds, the warning LED blinks slowly at 1 Hz to show the node is offline (buzzer off).
8. Ignore malformed messages without crashing and log them.
9. Publish a heartbeat every 5 seconds to `sentinel/node/status` with JSON fields `state` ("SAFE", "ALARM" or "OFFLINE"), `uptime_s` and `rssi`.
10. Latency: the LED must enter the ALARM state within 300 ms of an ENTER message arriving.

## UART Output (115200 baud)
- Print the Wi-Fi connection result and IP address.
- Print MQTT connected and subscribed topic.
- Print every received alert as `ALERT <event> incident=<n> track=<id> active=<k>`.
- Print every state change as `STATE <old> -> <new>`.

## Acceptance Criteria
1. The board boots, joins Wi-Fi and prints its IP address on UART.
2. After `mosquitto_pub -t sentinel/alerts -m '{"event":"ENTER","incident":1,"track_id":"3","active":1}'`, the warning LED blinks and UART prints the ALERT line and `STATE SAFE -> ALARM`.
3. After `mosquitto_pub -t sentinel/alerts -m '{"event":"EXIT","incident":1,"track_id":"3","active":0}'`, the LED and buzzer turn off and UART prints `STATE ALARM -> SAFE`.
4. When the broker is stopped, the LED blinks at 1 Hz within 10 seconds and UART prints `STATE ... -> OFFLINE`; when the broker restarts the node reconnects and resubscribes on its own.
5. With the vision pipeline running, a person entering the hazard zone in the video turns the LED on in real time.

## Out of scope
BLE, OTA updates, TLS, displays, any web server on the ESP32.
