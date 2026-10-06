# -*- coding: utf-8 -*-
"""
Solana Telegram Sniper & Trading Bot — Trending Engine
Discovers and monitors viral, high-velocity Solana memecoins in real-time
via DexScreener Boosts and Volume Analytics.
"""

import time
import requests
from typing import List, Dict, Any

_TRENDING_CACHE = {
    "timestamp": 0,
    "data": []
}
CACHE_TTL_SECONDS = 30


def get_trending_tokens(limit: int = 5) -> List[Dict[str, Any]]:
    """
    Fetches top trending and boosted Solana tokens from DexScreener.
    Caches results for 30 seconds to ensure ultra-low latency.
    """
    global _TRENDING_CACHE
    now = time.time()

    if (now - _TRENDING_CACHE["timestamp"]) < CACHE_TTL_SECONDS and _TRENDING_CACHE["data"]:
        return _TRENDING_CACHE["data"][:limit]

    trending = []
    try:
        boost_url = "https://api.dexscreener.com/token-boosts/top/v1"
        r = requests.get(boost_url, timeout=6)
        if r.status_code == 200:
            boosts = r.json()
            sol_mints = [x.get("tokenAddress") for x in boosts if x.get("chainId") == "solana"]

            # Deduplicate mints while preserving order
            seen = set()
            unique_mints = []
            for m in sol_mints:
                if m and m not in seen:
                    seen.add(m)
                    unique_mints.append(m)

            for mint in unique_mints[:limit]:
                try:
                    pair_url = f"https://api.dexscreener.com/latest/dex/tokens/{mint}"
                    resp = requests.get(pair_url, timeout=5)
                    if resp.status_code == 200:
                        pairs = resp.json().get("pairs", [])
                        if pairs:
                            p = pairs[0]
                            symbol = p.get("baseToken", {}).get("symbol", "UNKNOWN")
                            name = p.get("baseToken", {}).get("name", "Unknown Token")
                            price = float(p.get("priceUsd") or 0.0)
                            change_24h = float(p.get("priceChange", {}).get("h24") or 0.0)
                            change_1h = float(p.get("priceChange", {}).get("h1") or 0.0)
                            vol = float(p.get("volume", {}).get("h24") or 0.0)
                            liq = float(p.get("liquidity", {}).get("usd") or 0.0)
                            fdv = float(p.get("fdv") or p.get("marketCap") or 0.0)

                            trending.append({
                                "mint": mint,
                                "symbol": symbol,
                                "name": name,
                                "price_usd": price,
                                "change_1h": change_1h,
                                "change_24h": change_24h,
                                "volume_24h": vol,
                                "liquidity": liq,
                                "fdv": fdv
                            })
                except Exception as e:
                    print(f"Error fetching pair for {mint}: {e}")
                    continue

        if trending:
            _TRENDING_CACHE["timestamp"] = now
            _TRENDING_CACHE["data"] = trending
    except Exception as e:
        print(f"Error fetching trending boosts: {e}")

    return trending[:limit]


def format_trending_list(tokens: List[Dict[str, Any]]) -> str:
    """Formats an executive HTML card of top trending Solana tokens."""
    import html
    if not tokens:
        return "⚠️ <b>تعذر جلب العملات الرائجة حالياً، يرجى المحاولة بعد قليل.</b>"

    lines = [
        "🔥 <b>أكثر عملات سولانا رواجاً وزخماً الآن (Top Trending)</b> ⚡",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━"
    ]

    for idx, t in enumerate(tokens, 1):
        sym = html.escape(t["symbol"])
        mint = t["mint"]
        price = t["price_usd"]
        c24 = t["change_24h"]
        c1 = t["change_1h"]
        vol = t["volume_24h"]
        liq = t["liquidity"]
        emoji = "🚀" if c24 >= 0 else "🔻"

        lines.extend([
            f"{idx}. <b>${sym}</b> {emoji} <code>{c24:+.1f}% (24h)</code> | <code>{c1:+.1f}% (1h)</code>",
            f"   💵 السعر: <code>${price:.8f}</code> | السيولة: <code>${liq:,.0f}</code>",
            f"   📊 حجم التداول: <code>${vol:,.0f}</code>",
            f"   📋 العقد: <code>{mint}</code>",
            ""
        ])

    lines.extend([
        "━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "💡 <i>اضغط على أي زر أدناه لقنص العملة وفحص أمانها فورياً!</i> 👇"
    ])

    return "\n".join(lines)
