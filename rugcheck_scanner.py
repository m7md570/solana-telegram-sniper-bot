# -*- coding: utf-8 -*-
"""
Solana Telegram Sniper & Trading Bot — Security & Token Scanner
Analyzes token contract addresses, live DexScreener metrics, and RugCheck security audits.
"""

import requests
from typing import Dict, Any, Optional

from config import RUGCHECK_API, DEXSCREENER_API


def scan_token_security(mint: str) -> Dict[str, Any]:
    """
    Performs comprehensive security and financial audit on a Solana token mint.
    Fetches real-time price, liquidity, market cap, and rugcheck risks.
    """
    result = {
        "mint": mint,
        "symbol": "UNKNOWN",
        "name": "Unknown Token",
        "price_usd": 0.0,
        "mcap": 0.0,
        "liquidity_usd": 0.0,
        "volume_24h": 0.0,
        "price_change_24h": 0.0,
        "rug_score": 0,
        "status": "SAFE",
        "badge": "🛡️ آمن (Safe)",
        "risks": [],
        "mint_authority": False,
        "freeze_authority": False,
        "top_holders_pct": 0.0,
        "is_valid": False
    }

    # 1. Fetch Market & Financial Data from DexScreener
    try:
        url = f"{DEXSCREENER_API}/{mint}"
        r = requests.get(url, timeout=6)
        if r.status_code == 200:
            data = r.json()
            pairs = data.get("pairs") or []
            if pairs:
                p = pairs[0]
                result["symbol"] = p.get("baseToken", {}).get("symbol", "UNKNOWN")
                result["name"] = p.get("baseToken", {}).get("name", "Unknown Token")
                result["price_usd"] = float(p.get("priceUsd") or 0.0)
                result["mcap"] = float(p.get("fdv") or p.get("marketCap") or 0.0)
                result["liquidity_usd"] = float(p.get("liquidity", {}).get("usd") or 0.0)
                result["volume_24h"] = float(p.get("volume", {}).get("h24") or 0.0)
                result["price_change_24h"] = float(p.get("priceChange", {}).get("h24") or 0.0)
                result["is_valid"] = True
    except Exception as e:
        print(f"DexScreener fetch warning: {e}")

    # 2. Fetch Security & Audit from RugCheck
    try:
        rc_url = f"{RUGCHECK_API}/{mint}/report/summary"
        rc_resp = requests.get(rc_url, timeout=6)
        if rc_resp.status_code == 200:
            rc_data = rc_resp.json()
            score = rc_data.get("score", 0)
            result["rug_score"] = score
            raw_risks = rc_data.get("risks", [])
            risk_names = [rk.get("name", "") for rk in raw_risks]
            result["risks"] = risk_names

            # Check critical red flags
            for rk in raw_risks:
                name = rk.get("name", "").lower()
                if "freeze" in name:
                    result["freeze_authority"] = True
                if "mint" in name:
                    result["mint_authority"] = True

            # Determine badge & status based on score
            if score < 350:
                result["status"] = "SAFE"
                result["badge"] = f"🟢 آمن (درجة الخطر: {score})"
            elif score < 900:
                result["status"] = "WARNING"
                result["badge"] = f"🟡 مخاطرة متوسطة (درجة الخطر: {score})"
            else:
                result["status"] = "DANGER"
                result["badge"] = f"🔴 خطر شديد / فخ (درجة الخطر: {score})"
        else:
            result["badge"] = "ℹ️ فحص أساسي (غير مفهرس في RugCheck)"
    except Exception as e:
        print(f"RugCheck audit warning: {e}")

    return result


def format_token_card(scan: Dict[str, Any]) -> str:
    """Formats an executive Arabic Telegram card for the audited token."""
    symbol = scan["symbol"]
    name = scan["name"]
    price = scan["price_usd"]
    mcap = scan["mcap"]
    liq = scan["liquidity_usd"]
    change = scan["price_change_24h"]
    badge = scan["badge"]
    mint = scan["mint"]

    change_emoji = "📈" if change >= 0 else "📉"

    lines = [
        f"🎯 *بطاقة العملة*: ${symbol} ({name})",
        f"━━━━━━━━━━━━━━━━━━━━━━",
        f"💵 *السعر الحالي*: `${price:.8f}`",
        f"{change_emoji} *التغير 24h*: `{change:+.2f}%`",
        f"💎 *القيمة السوقية (MCap)*: `${mcap:,.0f}`",
        f"💧 *السيولة المتوفرة*: `${liq:,.0f}`",
        f"",
        f"🛡️ *فحص الأمان والتحقق*:",
        f"• تقييم الأمان: {badge}",
    ]

    if scan.get("freeze_authority"):
        lines.append("• ⚠️ تحذير: إمكانية تجميد المحافظ (Freeze Authority) مفعلة!")
    if scan.get("mint_authority"):
        lines.append("• ⚠️ تحذير: إمكانية طباعة عملات جديدة (Mint Authority) مفعلة!")

    if scan.get("risks"):
        risk_str = ", ".join(scan["risks"][:3])
        lines.append(f"• الملاحظات: `{risk_str}`")

    lines.extend([
        f"",
        f"📋 *العقد الذكي (CA)*:",
        f"`{mint}`",
        f"",
        f"⚡ *اختر كمية الشراء الفوري بنقرة واحدة أدناه:* 👇"
    ])

    return "\n".join(lines)
