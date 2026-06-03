"""
llm_router.py
Routes a user message to the selected LLM provider and returns the text response.

Supported providers:
    "ollama"    — local Llama 3 via Ollama (no API key required)
    "anthropic" — Anthropic Claude (session API key required)
    "openai"    — OpenAI GPT-4o (session API key required)

Usage:
    from llm_router import get_llm_response
    response = get_llm_response(
        provider="ollama",
        message="Hello, what can you do?",
        api_key=None,          # not needed for Ollama
        conversation_history=[]
    )
"""

import requests
from config import cfg

# ── System prompt sent to every LLM ──────────────────────────────────────────
# Instructs the model to respond as K1 and to embed action tags for movement.
SYSTEM_PROMPT = """
You are K1, a Booster Robotics humanoid robot at the Hillsborough College 
AI Innovation Center in Tampa, Florida. You are friendly, professional, and 
enthusiastic about helping students and educators learn about robotics and AI.

Keep your responses concise — 2 to 3 sentences maximum unless asked a detailed 
question. Speak in first person as the robot.

When your response calls for a physical action, append ONE action tag at the 
very end of your response using this exact format:
    [ACTION:wave]
    [ACTION:nod]
    [ACTION:thumbs_up]
    [ACTION:walk_forward]
    [ACTION:walk_backward]
    [ACTION:turn_left]
    [ACTION:turn_right]
    [ACTION:stop]

Only use an action tag when it genuinely fits the response. Never use more than 
one action tag per response.

Examples:
    User: "Can you greet everyone?"
    K1:   "Hello everyone, welcome to the AI Innovation Center! [ACTION:wave]"

    User: "Do you agree that robotics will change education?"
    K1:   "Absolutely, robotics and AI are transforming how students learn. [ACTION:nod]"
"""


def get_llm_response(
    provider: str,
    message: str,
    api_key: str | None = None,
    conversation_history: list[dict] | None = None,
) -> str:
    """
    Route a message to the appropriate LLM and return the text response.

    Args:
        provider:             "ollama" | "anthropic" | "openai"
        message:              The user's typed message
        api_key:              Session API key (required for anthropic/openai)
        conversation_history: List of prior {"role": ..., "content": ...} dicts

    Returns:
        The LLM's text response as a string.

    Raises:
        ValueError:  Unknown provider or missing API key
        RuntimeError: LLM call failed
    """
    history = conversation_history or []

    if provider == "ollama":
        return _call_ollama(message, history)
    elif provider == "anthropic":
        if not api_key:
            raise ValueError("Anthropic provider requires a session API key.")
        return _call_anthropic(message, history, api_key)
    elif provider == "openai":
        if not api_key:
            raise ValueError("OpenAI provider requires a session API key.")
        return _call_openai(message, history, api_key)
    else:
        raise ValueError(f"Unknown LLM provider: '{provider}'. "
                         f"Choose 'ollama', 'anthropic', or 'openai'.")


# ── Ollama ────────────────────────────────────────────────────────────────────

def _call_ollama(message: str, history: list[dict]) -> str:
    messages = _build_messages(message, history)
    try:
        response = requests.post(
            f"{cfg.OLLAMA_URL}/api/chat",
            json={
                "model":    cfg.OLLAMA_MODEL,
                "messages": messages,
                "stream":   False,
            },
            timeout=60,
        )
        response.raise_for_status()
        return response.json()["message"]["content"].strip()
    except requests.exceptions.ConnectionError:
        raise RuntimeError(
            f"Cannot reach Ollama at {cfg.OLLAMA_URL}. "
            "Is Ollama running? Try: ollama serve"
        )
    except Exception as e:
        raise RuntimeError(f"Ollama error: {e}")


# ── Anthropic ─────────────────────────────────────────────────────────────────

def _call_anthropic(message: str, history: list[dict], api_key: str) -> str:
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        messages = _build_messages(message, history, include_system=False)
        response = client.messages.create(
            model=cfg.ANTHROPIC_MODEL,
            max_tokens=512,
            system=SYSTEM_PROMPT.strip(),
            messages=messages,
        )
        return response.content[0].text.strip()
    except Exception as e:
        raise RuntimeError(f"Anthropic error: {e}")


# ── OpenAI ────────────────────────────────────────────────────────────────────

def _call_openai(message: str, history: list[dict], api_key: str) -> str:
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        messages = _build_messages(message, history)
        response = client.chat.completions.create(
            model=cfg.OPENAI_MODEL,
            messages=messages,
            max_tokens=512,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        raise RuntimeError(f"OpenAI error: {e}")


# ── Shared message builder ────────────────────────────────────────────────────

def _build_messages(
    message: str,
    history: list[dict],
    include_system: bool = True,
) -> list[dict]:
    """
    Build the messages array for the LLM call.
    Prepends the system prompt and appends the current user message.
    """
    messages = []
    if include_system:
        messages.append({"role": "system", "content": SYSTEM_PROMPT.strip()})
    messages.extend(history)
    messages.append({"role": "user", "content": message})
    return messages


# ── Action tag parser ─────────────────────────────────────────────────────────

def extract_action(response_text: str) -> tuple[str, str | None]:
    """
    Parse an action tag out of the LLM response.

    Returns:
        (clean_text, action_name)
        e.g. ("Hello everyone! ", "wave")
        or   ("Just answering a question.", None)
    """
    import re
    pattern = r"\[ACTION:(\w+)\]"
    match = re.search(pattern, response_text)
    if match:
        action = match.group(1)
        clean  = re.sub(pattern, "", response_text).strip()
        return clean, action
    return response_text.strip(), None
