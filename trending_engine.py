# -*- coding: utf-8 -*-
"""
Solana Telegram Sniper & Trading Bot — Trending Engine
Discovers and monitors viral, high-velocity Solana memecoins in real-time
via DexScreener Boosts and Volume Analytics.
"""

import time
import html
import requests
from typing import List, Dict, Any

_TRENDING_CACHE = {
    "timestamp": 0,
    "data": []
}
CACHE_TTL_SECONDS = 30

_SESSION = requests.Session()
_SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9"
})


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
        r = _SESSION.get(boost_url, timeout=7)
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
                    resp = _SESSION.get(pair_url, timeout=6)
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


def format_trending_list(tokens: List[Dict[str, Any]], lang: str = "en") -> str:
    """Formats an executive HTML card of top trending Solana tokens in English or Arabic."""
    import html
    if not tokens:
        if lang == "ar":
            return "⚠️ <b>تعذر جلب العملات الرائجة حالياً، يرجى المحاولة بعد قليل.</b>"
        return "⚠️ <b>Could not fetch trending tokens right now. Please try again shortly.</b>"

    if lang == "ar":
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
    else:
        lines = [
            "🔥 <b>Top Trending Solana Tokens (Live DexScreener Radar)</b> ⚡",
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
                f"   💵 Price: <code>${price:.8f}</code> | Liq: <code>${liq:,.0f}</code>",
                f"   📊 24h Vol: <code>${vol:,.0f}</code>",
                f"   📋 CA: <code>{mint}</code>",
                ""
            ])

        lines.extend([
            "━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "💡 <i>Tap any button below to inspect security & instant-snipe!</i> 👇"
        ])

    return "\n".join(lines)


def get_top_gainers(limit: int = 5) -> List[Dict[str, Any]]:
    """
    Scans trending Solana tokens and ranks them by highest short-term momentum (change_1h / change_24h).
    Filters out tokens with negligible liquidity (< $10,000) to ensure tradeability.
    """
    tokens = get_trending_tokens(limit=15)
    liquid_tokens = [t for t in tokens if t.get("liquidity", 0.0) >= 10_000]
    # Sort by 1h momentum first, then 24h momentum
    sorted_gainers = sorted(liquid_tokens, key=lambda x: (x.get("change_1h", 0.0), x.get("change_24h", 0.0)), reverse=True)
    return sorted_gainers[:limit]


def format_gainers_list(tokens: List[Dict[str, Any]], lang: str = "en") -> str:
    """Formats an executive card of the highest velocity gainers on Solana."""
    import html
    if not tokens:
        if lang == "ar":
            return "⚠️ <b>لم يتم رصد عملات صاعدة بزخم كافٍ حالياً. يرجى المحاولة بعد قليل.</b>"
        return "⚠️ <b>No high-velocity gainers detected at the moment. Please try again shortly.</b>"

    if lang == "ar":
        lines = [
            "🚀 <b>رادار العملات الأكثر صعوداً وزخماً (Top Gainers & Surge)</b> ⚡",
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

            lines.extend([
                f"{idx}. <b>${sym}</b> 🟢 <code>{c1:+.1f}% (1h)</code> | <code>{c24:+.1f}% (24h)</code>",
                f"   💵 السعر: <code>${price:.8f}</code> | السيولة: <code>${liq:,.0f}</code>",
                f"   📊 حجم 24h: <code>${vol:,.0f}</code>",
                f"   📋 العقد: <code>{mint}</code>",
                ""
            ])
        lines.extend([
            "━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "💡 <i>اقتنص الصعود اللحظي بنقرة واحدة عبر الأزرار أدناه!</i> 👇"
        ])
    else:
        lines = [
            "🚀 <b>Solana High-Velocity Gainers & Surge Radar</b> ⚡",
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

            lines.extend([
                f"{idx}. <b>${sym}</b> 🟢 <code>{c1:+.1f}% (1h)</code> | <code>{c24:+.1f}% (24h)</code>",
                f"   💵 Price: <code>${price:.8f}</code> | Liq: <code>${liq:,.0f}</code>",
                f"   📊 24h Vol: <code>${vol:,.0f}</code>",
                f"   📋 CA: <code>{mint}</code>",
                ""
            ])
        lines.extend([
            "━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "💡 <i>Ride the momentum! Tap below to inspect security & instant-snipe!</i> 👇"
        ])

    return "\n".join(lines)
