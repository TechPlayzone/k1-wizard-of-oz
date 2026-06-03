# API Reference

**K1 Wizard-of-Oz Dashboard — Flask Backend**
Hillsborough College AI Innovation Center

Base URL: `http://localhost:5000`

---

## Chat

### POST /api/chat/send

Send a typed message, get an LLM response, and speak it through the K1.

**Request**
```json
{
  "message":  "Can you wave hello?",
  "provider": "ollama",
  "history": [
    { "role": "user",      "content": "What is your name?" },
    { "role": "assistant", "content": "I am K1..." }
  ]
}
```
`provider` and `history` are optional. Provider defaults to `LLM_PROVIDER` in `.env`.

**Response**
```json
{
  "response":       "Hello everyone! [ACTION:wave]",
  "clean_response": "Hello everyone!",
  "action":         "wave",
  "provider":       "ollama",
  "tts_ok":         true
}
```

---

## Robot movement

### POST /api/robot/move

Execute a movement command from the direction pad.

**Request**
```json
{ "command": "walk_forward", "duration": 2.0 }
```

| command | description |
|---|---|
| `walk_forward` | Walk forward for `duration` seconds |
| `walk_backward` | Walk backward for `duration` seconds |
| `turn_left` | Rotate counter-clockwise |
| `turn_right` | Rotate clockwise |
| `stop` | Halt all motion immediately |

`duration` is optional (defaults to 2.0 seconds).

**Response**
```json
{ "ok": true, "command": "walk_forward" }
```

---

### POST /api/robot/mode

Set the robot's operating mode.

**Request**
```json
{ "mode": "walk" }
```

| mode | description |
|---|---|
| `walk` | Transition through Prep → Walk (robot stands and enables movement) |
| `damp` | Motors relax — safe resting state |

**Response**
```json
{ "ok": true, "mode": "walk" }
```

---

### GET /api/robot/status

Returns current robot status for the dashboard status strip.

**Response**
```json
{
  "connected":  true,
  "mode":       "walk",
  "battery":    87,
  "latency_ms": 24
}
```

---

## Gestures

### POST /api/robot/gesture

Trigger a pre-built gesture.

**Request**
```json
{ "gesture": "wave" }
```

| gesture | description |
|---|---|
| `wave` | Right arm wave |
| `nod` | Head nod |
| `thumbs_up` | Right arm thumbs up |

**Response**
```json
{ "ok": true, "gesture": "wave" }
```

---

## Session API keys

### POST /api/session/set-key

Store a session-scoped API key. Stored in memory only — never written to disk.
Cleared automatically when the server restarts or the user logs out.

**Request**
```json
{ "provider": "anthropic", "api_key": "sk-ant-..." }
```

**Response**
```json
{ "ok": true, "provider": "anthropic" }
```

---

### POST /api/session/clear-key

Remove the API key for a specific provider.

**Request**
```json
{ "provider": "openai" }
```

---

### POST /api/session/logout

Clear all session API keys for the current browser session.

---

## Admin

All admin endpoints require a valid admin session (obtained via `/api/admin/login`).

### POST /api/admin/login

**Request**
```json
{ "password": "your-admin-password" }
```

**Response**
```json
{ "ok": true }
```

Returns `401` if password is incorrect.

---

### GET /api/admin/config

Returns current runtime config (no secrets included).

---

### POST /api/admin/config

Update K1 IP or default LLM provider at runtime (no restart required).

**Request**
```json
{ "k1_ip": "192.168.0.200", "llm_provider": "anthropic" }
```

---

## Error format

All error responses follow this format:

```json
{ "error": "Human-readable description of what went wrong." }
```

| HTTP status | meaning |
|---|---|
| 400 | Missing or invalid request data |
| 401 | Missing or incorrect API key / admin password |
| 403 | Admin endpoint accessed without admin session |
| 500 | LLM, TTS, or robot error |
