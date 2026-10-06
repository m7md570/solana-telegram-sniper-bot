# -*- coding: utf-8 -*-
"""
Solana Telegram Sniper & Trading Bot — Autonomous Marketing Engine
Continuously monitors trending Solana tokens, audits security with RugCheck,
and publishes high-engagement alpha signals to X/Twitter to drive organic traders.
"""

import os
import sys
import time
import json
import subprocess
from pathlib import Path

# Ensure UTF-8 on Windows
if sys.stdout is not None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
STATE_FILE = DATA_DIR / "marketing_state.json"
POSTER_SCRIPT = Path(r"F:\قناص\06_وكيل_حُر\hurr_tools\twitter_x_poster.py")

from trending_engine import get_trending_tokens
from rugcheck_scanner import scan_token_security


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"last_post_time": 0, "posted_mints": [], "total_posts": 0}


def save_state(state: dict):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        print(f"Warning: Could not save marketing state: {e}")


def generate_marketing_post() -> tuple:
    """
    Selects the best trending Solana token and generates a viral alpha post.
    Returns: (text, mint)
    """
    state = load_state()
    posted_mints = state.get("posted_mints", [])

    tokens = get_trending_tokens(limit=8)
    if not tokens:
        return None, None

    # Pick top unposted token or most active
    target = None
    for t in tokens:
        if t["mint"] not in posted_mints:
            target = t
            break
    if not target:
        target = tokens[0]

    mint = target["mint"]
    symbol = target.get("symbol") or "SOL"
    price = target.get("price_usd", 0.0)
    change_24h = target.get("change_24h", 0.0)
    change_1h = target.get("change_1h", 0.0)
    vol = target.get("volume_24h", 0.0)
    liq = target.get("liquidity", 0.0)

    # Perform security audit
    scan = scan_token_security(mint)
    rug_score = scan.get("rug_score", 0)
    status_label = scan.get("status", "SAFE")
    emoji = "🟢" if status_label == "SAFE" else "🟡"

    vol_m = vol / 1_000_000.0 if vol >= 1_000_000 else vol / 1_000.0
    vol_unit = "M" if vol >= 1_000_000 else "K"

    post_lines = [
        f"🔥 Solana Alpha: ${symbol} Trending!",
        f"📈 24h: {change_24h:+.1f}% | Vol: ${vol_m:.1f}{vol_unit}",
        f"🛡️ RugCheck: {emoji} {status_label} ({rug_score})",
        f"",
        f"⚡ 1-Click Fast Sniper (Sub-400ms):",
        f"👉 https://t.me/PopcornSniperBot",
        f"",
        f"#Solana #{symbol} #SOL"
    ]

    post_text = "\n".join(post_lines)
    # Strict 260 character guard for free X accounts
    if len(post_text) > 260:
        post_text = post_text[:257] + "..."

    return post_text, mint


def publish_post(text: str) -> bool:
    """Invokes twitter_x_poster.py to post the tweet to X."""
    if not POSTER_SCRIPT.exists():
        print(f"❌ Poster script not found at {POSTER_SCRIPT}")
        return False

    cmd = ["py", "-3", str(POSTER_SCRIPT), "--text", text]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
        output = res.stdout.strip()
        print(f"Poster response: {output[:150]}")
        if "success" in output and "true" in output.lower():
            return True
        return False
    except Exception as e:
        print(f"Post execution failed: {e}")
        return False


def run_cycle():
    """Runs a single marketing dispatch cycle."""
    state = load_state()
    now = time.time()
    min_interval_seconds = 2 * 3600  # 2 hours cadence

    elapsed = now - state.get("last_post_time", 0)
    if elapsed < min_interval_seconds:
        remaining_mins = int((min_interval_seconds - elapsed) / 60)
        print(f"⏳ Next scheduled marketing post in {remaining_mins} minutes (Interval: 2h).", flush=True)
        return

    print("🚀 Selecting top trending Solana token for alpha announcement...", flush=True)
    text, mint = generate_marketing_post()
    if not text:
        print("⚠️ No suitable trending token discovered right now.", flush=True)
        return

    print("📢 Publishing alpha post to X/Twitter...", flush=True)
    success = publish_post(text)
    if success:
        state["last_post_time"] = now
        state["total_posts"] = state.get("total_posts", 0) + 1
        mints = state.get("posted_mints", [])
        mints.append(mint)
        state["posted_mints"] = mints[-20:]  # Keep last 20
        save_state(state)
        print("✅ Alpha marketing post successfully published to X!", flush=True)
    else:
        print("⚠️ Marketing post could not be confirmed.", flush=True)


if __name__ == "__main__":
    if "--daemon" in sys.argv:
        print("🚀 Starting Autonomous Marketing Engine Daemon (2-3 hour cadence)...", flush=True)
        while True:
            try:
                run_cycle()
            except Exception as e:
                print(f"Error in marketing cycle: {e}", flush=True)
            time.sleep(600)  # Check every 10 minutes
    else:
        run_cycle()
