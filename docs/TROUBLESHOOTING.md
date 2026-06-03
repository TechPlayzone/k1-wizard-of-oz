# Troubleshooting Guide

**K1 Wizard-of-Oz Dashboard**
Hillsborough College AI Innovation Center

---

## K1 robot not reachable

**Symptom:** `test_connection.py` reports K1 unreachable, or dashboard shows
"Robot disconnected" (red dot).

**Fixes:**
1. Confirm the K1 is powered on and fully booted (~60 seconds after power-on).
2. Confirm both your laptop and K1 are on the **same** WiFi network.
3. Run `ping <K1_IP>` from your terminal. No response = network issue.
4. Check your router's connected device list to confirm the K1's current IP.
   Update `K1_IP` in `.env` if it changed.
5. SSH into the K1 to confirm services are running:
   ```bash
   ssh booster@<K1_IP>
   booster-cli launch -c status
   ```
   If services are stopped: `booster-cli launch -c start`

---

## Whisper transcription errors or empty transcriptions

**Symptom:** K1 mic captures audio but text comes back empty or garbled.

**Fixes:**
1. Move to a quieter environment or reduce background noise.
2. Speak directly toward the K1's head where the mic array is located.
3. Try a larger Whisper model in `.env`:
   ```
   WHISPER_MODEL=medium
   ```
4. Verify ffmpeg is installed: `ffmpeg -version`
5. If audio frames are empty, the mic driver may not be loaded. SSH into the K1
   and check: `pactl list sources short`
   The `alsa_input` device should be listed.

---

## Piper TTS produces no audio from K1 speaker

**Symptom:** LLM responds but K1 is silent.

**Fixes:**
1. Confirm the voice model file exists at the path in `PIPER_VOICE_PATH`.
2. Test Piper directly from your terminal:
   ```bash
   echo "Hello" | piper --model ./voices/en_US-lessac-medium.onnx --output_file test.wav
   ```
3. Verify the WAV file was copied to the robot:
   ```bash
   ssh booster@<K1_IP> "ls -la /tmp/k1_response.wav"
   ```
4. Check K1 volume via SDK or confirm speaker is not muted.
5. Confirm espeak-ng is installed on the K1 if using the fallback pipeline:
   ```bash
   sudo apt-get install -y espeak-ng
   ```

---

## Ollama not responding

**Symptom:** Dashboard shows LLM error; backend logs `Connection refused` for Ollama.

**Fixes:**
1. Start Ollama in a separate terminal: `ollama serve`
2. Confirm the model is downloaded: `ollama list` (should show `llama3`)
3. If missing: `ollama pull llama3`
4. Check `OLLAMA_URL` in `.env` — default is `http://localhost:11434`.
   If Ollama is on a separate server, update this to its IP.
5. Test directly: `curl http://localhost:11434/api/tags`

---

## Movement commands not executing

**Symptom:** Dashboard direction buttons do nothing; no error shown.

**Fixes:**
1. Confirm robot mode is set to **Walk** in the dashboard.
   The K1 must be in Walk mode before movement commands are accepted.
2. Confirm the robot completed the DAMP → PREP → WALK startup sequence.
   Check backend logs for mode transition errors.
3. Never command movement before PREP mode has held for at least 3 seconds.
4. If the K1 is in a confined space, ensure there is at least 1 meter of
   clearance in the movement direction.

**Safety reminder:** The K1 weighs approximately 19.5 kg. Always test movement
commands with the robot on a flat, clear surface and with a person nearby to
catch it if it stumbles.

---

## API key errors (Anthropic / OpenAI)

**Symptom:** Selecting Anthropic or OpenAI shows an authentication error.

**Fixes:**
1. Confirm your API key is valid and has available credits.
2. Keys must start with `sk-ant-` (Anthropic) or `sk-` (OpenAI).
3. The K1 must be connected to a network **with internet access** when using
   cloud providers. If using an isolated hotspot, switch to Ollama.
4. Session keys are cleared on tab refresh. Re-enter the key after refreshing.

---

## Isaac Sim not connecting

**Symptom:** Clicking "Connect to simulator" opens a blank page.

**Fixes:**
1. Confirm Isaac Sim is running with streaming enabled on your server.
2. Verify `ISAAC_SERVER_IP` in `.env` matches the server running Isaac Sim.
3. Check that port 8211 is open and not blocked by a firewall:
   ```bash
   curl http://<ISAAC_SERVER_IP>:8211
   ```
4. Isaac Sim WebRTC requires a Chromium-based browser (Chrome or Edge).

---

## Still stuck?

Open an issue at: https://github.com/TechPlayzone/k1-wizard-of-oz/issues

Please include:
- Your OS and Python version
- K1 firmware version
- The full error message from the backend terminal
- Output of `python scripts/test_connection.py`
