# -*- coding: utf-8 -*-
"""
Solana Telegram Sniper & Trading Bot — Local AI Coprocessor Client
Connects directly to the local unconstrained model (LM Studio / Qwen 27B) running
on the user's dedicated NVIDIA RTX 4070 GPU (http://127.0.0.1:45645/v1/chat/completions).

Provides:
- Real-time token alpha verdicts for Telegram cards.
- Viral, algorithmic Twitter/X marketing copy synthesis.
- Autonomous code audit & reasoning assistance.
"""

import requests
import json
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger("LocalAICoprocessor")

DEFAULT_LOCAL_ENDPOINT = "http://127.0.0.1:45645/v1/chat/completions"
DEFAULT_MODEL_NAME = "qwen3.8-27b-heretic-abliterated-uncensored"
LOCAL_REQUEST_TIMEOUT = 18  # seconds


def is_local_model_online(endpoint: str = DEFAULT_LOCAL_ENDPOINT) -> bool:
    """Checks whether the local model inference server is responsive."""
    try:
        base_url = endpoint.replace("/chat/completions", "/models")
        r = requests.get(base_url, timeout=3)
        return r.status_code == 200
    except Exception:
        return False


def query_local_ai(prompt: str, system_prompt: str = "", max_tokens: int = 500, temperature: float = 0.7) -> Optional[str]:
    """
    Sends an inference query to the local model on LM Studio.
    Extracts either content or reasoning_content cleanly.
    """
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": DEFAULT_MODEL_NAME,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature
    }

    try:
        resp = requests.post(DEFAULT_LOCAL_ENDPOINT, json=payload, timeout=LOCAL_REQUEST_TIMEOUT)
        if resp.status_code == 200:
            data = resp.json()
            choices = data.get("choices") or []
            if choices:
                msg = choices[0].get("message") or {}
                content = (msg.get("content") or "").strip()
                if content:
                    return content
                # Fallback to reasoning_content if content was truncated by length
                reasoning = (msg.get("reasoning_content") or "").strip()
                if reasoning:
                    lines = [ln.strip() for ln in reasoning.split("\n") if ln.strip()]
                    return lines[-1] if lines else reasoning[:200]
    except Exception as e:
        logger.debug(f"Local AI inference bypassed or offline: {e}")
    return None


def get_token_ai_verdict(symbol: str, change_24h: float, volume_24h: float, liquidity_usd: float, rug_score: int, status: str) -> str:
    """
    Generates a punchy institutional alpha verdict for a token.
    Falls back gracefully to algorithmic evaluation if local LLM is busy.
    """
    vol_str = f"${volume_24h/1e6:.1f}M" if volume_24h >= 1e6 else f"${volume_24h/1e3:.1f}K"
    liq_str = f"${liquidity_usd/1e6:.1f}M" if liquidity_usd >= 1e6 else f"${liquidity_usd/1e3:.1f}K"

    prompt = (
        f"Token: ${symbol}\n"
        f"24h Price Change: {change_24h:+.1f}%\n"
        f"24h Volume: {vol_str}\n"
        f"Liquidity: {liq_str}\n"
        f"Security: {status} (RugCheck Score: {rug_score})\n\n"
        f"Provide a 1-sentence, high-impact institutional trading verdict."
    )
    system = "You are an elite quantitative Solana sniper bot. Give direct, objective trading intelligence."

    ai_response = query_local_ai(prompt, system_prompt=system, max_tokens=400, temperature=0.6)
    if ai_response:
        # Clean quotes and markdown artifacts
        clean = ai_response.replace('"', '').replace('**', '').strip()
        if len(clean) > 200:
            clean = clean[:197] + "..."
        return clean

    # Algorithmic fallback
    if status == "SAFE" and change_24h > 10.0:
        return f"Bullish momentum (+{change_24h:.1f}%) backed by solid security score ({rug_score}); scale in with disciplined stop-loss."
    elif status != "SAFE":
        return f"Caution advised: elevated contract risk detected ({status}); sniper entry only with minimal size."
    else:
        return f"Consolidating market structure with {vol_str} 24h volume; monitor breakout levels before sizing up."


def generate_viral_alpha_tweet(symbol: str, change_24h: float, volume_24h: float, rug_score: int, status: str, mint: str) -> str:
    """
    Synthesizes a viral, high-converting X/Twitter post using the local model.
    Falls back to high-engagement template if local model is offline.
    """
    vol_str = f"${volume_24h/1e6:.1f}M" if volume_24h >= 1e6 else f"${volume_24h/1e3:.1f}K"
    bot_url = f"https://t.me/PopcornSniperBot?start=token_{mint}"

    prompt = (
        f"Write a viral crypto tweet for Solana traders:\n"
        f"Token: ${symbol}\n"
        f"24h Gain: {change_24h:+.1f}%\n"
        f"24h Volume: {vol_str}\n"
        f"Audit: {status} ({rug_score})\n"
        f"Include link: {bot_url}\n"
        f"Max 240 characters total. Use hype emojis, hashtags #Solana #{symbol}."
    )
    system = "You are a viral Solana crypto marketing strategist."

    ai_tweet = query_local_ai(prompt, system_prompt=system, max_tokens=450, temperature=0.8)
    if ai_tweet and len(ai_tweet) <= 260 and "http" in ai_tweet:
        return ai_tweet.strip()

    # Algorithmic viral fallback
    emoji = "🟢" if status == "SAFE" else "🟡"
    lines = [
        f"🔥 Solana Alpha: ${symbol} Breaking Out!",
        f"📈 24h: {change_24h:+.1f}% | Vol: {vol_str}",
        f"🛡️ RugCheck: {emoji} {status} ({rug_score})",
        f"",
        f"⚡ 1-Click Fast Sniper:",
        f"👉 {bot_url}",
        f"",
        f"#Solana #{symbol} #Jupiter"
    ]
    tweet = "\n".join(lines)
    if len(tweet) > 260:
        tweet = tweet[:257] + "..."
    return tweet


def audit_code_with_local_ai(code_snippet: str, file_context: str = "") -> Optional[str]:
    """
    Leverages the local unconstrained 27B model to review code snippets,
    detect edge-case bugs, security vulnerabilities, or propose optimizations.
    """
    prompt = (
        f"File Context: {file_context}\n\n"
        f"Code:\n```python\n{code_snippet[:2500]}\n```\n\n"
        f"Analyze this code. Identify any subtle bugs, edge cases, or optimizations. "
        f"Provide a concise technical recommendation in 2-3 sentences."
    )
    system = "You are a senior principal security engineer and Python performance auditor."
    return query_local_ai(prompt, system_prompt=system, max_tokens=550, temperature=0.5)

