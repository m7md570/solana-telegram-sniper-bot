# -*- coding: utf-8 -*-
"""
Solana Telegram Sniper & Trading Bot — Security & Token Scanner
Analyzes token contract addresses, live DexScreener metrics, and RugCheck security audits.
"""

import re
import html
import time
import requests
from typing import Dict, Any, Optional

from config import RUGCHECK_API, DEXSCREENER_API

_SESSION = requests.Session()
_SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9"
})


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
        "price_sol": 0.0,
        "dex": "Raydium",
        "mcap": 0.0,
        "liquidity_usd": 0.0,
        "volume_24h": 0.0,
        "price_change_24h": 0.0,
        "price_change_1h": 0.0,
        "rug_score": 0,
        "status": "UNVERIFIED",
        "badge": "ℹ️ فحص أساسي (غير مفهرس)",
        "risks": [],
        "mint_authority": False,
        "freeze_authority": False,
        "top_holders_pct": 0.0,
        "is_valid": False
    }

    for attempt in range(2):
        try:
            url = f"{DEXSCREENER_API}/{mint}"
            r = _SESSION.get(url, timeout=12)
            if r.status_code == 200:
                data = r.json()
                pairs = data.get("pairs") or []
                if pairs:
                    # Sort pairs by USD liquidity to reliably audit the primary liquidity pool
                    pairs.sort(key=lambda x: float((x.get("liquidity") or {}).get("usd") or 0.0), reverse=True)
                    p = pairs[0]
                    result["symbol"] = (p.get("baseToken") or {}).get("symbol", "UNKNOWN")
                    result["name"] = (p.get("baseToken") or {}).get("name", "Unknown Token")
                    result["price_usd"] = float(p.get("priceUsd") or 0.0)
                    result["price_sol"] = float(p.get("priceNative") or 0.0)
                    result["dex"] = str(p.get("dexId") or "raydium").capitalize()
                    result["mcap"] = float(p.get("fdv") or p.get("marketCap") or 0.0)
                    result["liquidity_usd"] = float((p.get("liquidity") or {}).get("usd") or 0.0)
                    result["volume_24h"] = float((p.get("volume") or {}).get("h24") or 0.0)
                    result["price_change_24h"] = float((p.get("priceChange") or {}).get("h24") or 0.0)
                    result["price_change_1h"] = float((p.get("priceChange") or {}).get("h1") or 0.0)
                    result["is_valid"] = True
                    break
        except Exception as e:
            if attempt == 0:
                time.sleep(1)
                continue
            print(f"DexScreener fetch warning: {e}")

    # 2. Fetch Security & Audit from RugCheck
    try:
        rc_url = f"{RUGCHECK_API}/{mint}/report/summary"
        rc_resp = _SESSION.get(rc_url, timeout=7)
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
            result["status"] = "UNVERIFIED"
            result["badge"] = "ℹ️ فحص أساسي (غير مفهرس في RugCheck)"
    except Exception as e:
        print(f"RugCheck audit warning: {e}")
        result["status"] = "UNVERIFIED"
        result["badge"] = "ℹ️ فحص أساسي (خدمة RugCheck غير متاحة مؤقتاً)"

    # Fallback liquidity check
    if result["liquidity_usd"] > 0 and result["liquidity_usd"] < 1000:
        result["status"] = "WARNING"
        if "Low Liquidity Pool (<$1k)" not in result["risks"]:
            result["risks"].append("Low Liquidity Pool (<$1k)")

    return result


def extract_token_mint(text: str) -> Optional[str]:
    """
    Extracts a valid Solana Mint address from raw text or various platform URLs:
    DexScreener, Pump.fun, Solscan, Birdeye, Photon, or plain Base58.
    """
    import re
    if not text:
        return None
    text = text.strip()

    # 1. URL Matching
    patterns = [
        r"dexscreener\.com/solana/([1-9A-HJ-NP-Za-km-z]{32,44})",
        r"pump\.fun/coin/([1-9A-HJ-NP-Za-km-z]{32,44})",
        r"pump\.fun/([1-9A-HJ-NP-Za-km-z]{32,44})",
        r"solscan\.io/token/([1-9A-HJ-NP-Za-km-z]{32,44})",
        r"solanatracker\.io/token/([1-9A-HJ-NP-Za-km-z]{32,44})",
        r"birdeye\.so/token/([1-9A-HJ-NP-Za-km-z]{32,44})",
        r"gmgn\.ai/sol/token/([1-9A-HJ-NP-Za-km-z]{32,44})",
        r"bullx\.io/terminal\?.*(?:address|token)=([1-9A-HJ-NP-Za-km-z]{32,44})",
        r"photon-sol\.tinyastro\.io/.*(?:token|r/@)([1-9A-HJ-NP-Za-km-z]{32,44})",
        r"raydium\.io/swap/\?.*outputMint=([1-9A-HJ-NP-Za-km-z]{32,44})",
        r"axiom\.trade/(?:t|trade)/([1-9A-HJ-NP-Za-km-z]{32,44})",
        r"dextools\.io/app/(?:[a-zA-Z0-9_\-]+/)?solana/pair-explorer/([1-9A-HJ-NP-Za-km-z]{32,44})",
        r"solview\.app/token/([1-9A-HJ-NP-Za-km-z]{32,44})",
        r"rugcheck\.xyz/tokens/([1-9A-HJ-NP-Za-km-z]{32,44})",
        r"jup\.ag/(?:swap|tokens)/(?:[^\s/]+-)?([1-9A-HJ-NP-Za-km-z]{32,44})"
    ]
    for pat in patterns:
        m = re.search(pat, text, re.I)
        if m:
            return m.group(1)

    # 2. Raw Base58 Address
    base58_pat = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")
    if base58_pat.match(text):
        return text

    # 3. Search for any word that matches Base58 32-44 chars
    for token in text.split():
        clean = re.sub(r"[^\w]", "", token)
        if 32 <= len(clean) <= 44 and base58_pat.match(clean):
            return clean

    return None


def format_token_card(scan: Dict[str, Any], lang: str = "en") -> str:
    """Formats an executive Telegram card using robust HTML in English or Arabic."""
    import html
    symbol = html.escape(scan.get("symbol") or "TOKEN")
    name = html.escape(scan.get("name") or symbol or "Unknown Token")
    price = float(scan.get("price_usd") or 0.0)
    price_sol = float(scan.get("price_sol") or 0.0)
    dex = scan.get("dex", "Raydium")
    mcap = float(scan.get("mcap") or 0.0)
    liq = float(scan.get("liquidity_usd") or 0.0)
    change = float(scan.get("price_change_24h") or 0.0)
    change_1h = float(scan.get("price_change_1h") or 0.0)
    score = int(scan.get("rug_score") or 0)
    mint = scan.get("mint") or ""
    status = scan.get("status", "SAFE")

    change_emoji = "📈" if change >= 0 else "📉"
    price_sol_str = f" (<code>{price_sol:.6f} SOL</code>)" if price_sol > 0 else ""

    if lang == "ar":
        if status == "SAFE":
            badge = f"🟢 آمن (درجة الخطر: {score})"
        elif status == "WARNING":
            badge = f"🟡 مخاطرة متوسطة (درجة الخطر: {score})"
        elif status == "DANGER":
            badge = f"🔴 خطر شديد / فخ (درجة الخطر: {score})"
        elif status == "UNVERIFIED":
            badge = "ℹ️ فحص أساسي (غير مفهرس في RugCheck)"
        else:
            badge = "ℹ️ فحص أساسي"

        lines = [
            f"🎯 <b>بطاقة العملة</b>: ${symbol} ({name})",
            f"━━━━━━━━━━━━━━━━━━━━━━",
            f"💵 <b>السعر الحالي</b>: <code>${price:.8f}</code>{price_sol_str}",
            f"{change_emoji} <b>التغير اللحظي</b>: <code>{change:+.2f}% (24h)</code> | <code>{change_1h:+.2f}% (1h)</code>",
            f"🏛️ <b>المنصة المضيفة (DEX)</b>: <code>{dex}</code>",
            f"💎 <b>القيمة السوقية (MCap)</b>: <code>${mcap:,.0f}</code>",
            f"💧 <b>السيولة المتوفرة</b>: <code>${liq:,.0f}</code>",
            f"",
            f"🛡️ <b>فحص الأمان والتحقق</b>:",
            f"• تقييم الأمان: {badge}",
        ]

        if scan.get("freeze_authority"):
            lines.append("• ⚠️ <b>تحذير</b>: إمكانية تجميد المحافظ (Freeze Authority) مفعلة!")
        if scan.get("mint_authority"):
            lines.append("• ⚠️ <b>تحذير</b>: إمكانية طباعة عملات جديدة (Mint Authority) مفعلة!")

        if scan.get("risks"):
            safe_risks = [html.escape(r) for r in scan["risks"][:3]]
            risk_str = ", ".join(safe_risks)
            lines.append(f"• الملاحظات: <code>{risk_str}</code>")

        lines.extend([
            f"",
            f"📋 <b>العقد الذكي (CA)</b>:",
            f"<code>{mint}</code>",
            f"",
            f"⚡ <b>اختر كمية الشراء الفوري بنقرة واحدة أدناه:</b> 👇"
        ])
    else:
        if status == "SAFE":
            badge = f"🟢 Safe (Risk Score: {score})"
        elif status == "WARNING":
            badge = f"🟡 Warning / Medium Risk (Risk Score: {score})"
        elif status == "DANGER":
            badge = f"🔴 High Risk / Danger (Risk Score: {score})"
        elif status == "UNVERIFIED":
            badge = "ℹ️ Basic Audit (Unindexed on RugCheck)"
        else:
            badge = "ℹ️ Basic Audit"

        lines = [
            f"🎯 <b>Token Card</b>: ${symbol} ({name})",
            f"━━━━━━━━━━━━━━━━━━━━━━",
            f"💵 <b>Current Price</b>: <code>${price:.8f}</code>{price_sol_str}",
            f"{change_emoji} <b>Price Momentum</b>: <code>{change:+.2f}% (24h)</code> | <code>{change_1h:+.2f}% (1h)</code>",
            f"🏛️ <b>DEX Venue</b>: <code>{dex}</code>",
            f"💎 <b>Market Cap (MCap)</b>: <code>${mcap:,.0f}</code>",
            f"💧 <b>Liquidity</b>: <code>${liq:,.0f}</code>",
            f"",
            f"🛡️ <b>Security & RugCheck Audit</b>:",
            f"• Risk Assessment: {badge}",
        ]

        if scan.get("freeze_authority"):
            lines.append("• ⚠️ <b>WARNING</b>: Freeze Authority is ENABLED (Blacklist risk)!")
        if scan.get("mint_authority"):
            lines.append("• ⚠️ <b>WARNING</b>: Mint Authority is ENABLED (Dumping / minting risk)!")

        if scan.get("risks"):
            safe_risks = [html.escape(r) for r in scan["risks"][:3]]
            risk_str = ", ".join(safe_risks)
            lines.append(f"• Flags: <code>{risk_str}</code>")

        lines.extend([
            f"",
            f"📋 <b>Contract Address (CA)</b>:",
            f"<code>{mint}</code>",
            f"",
            f"⚡ <b>Select 1-Click Buy Amount Below:</b> 👇"
        ])

    return "\n".join(lines)


def search_solana_token(query: str) -> Optional[Dict[str, Any]]:
    """
    Searches DexScreener API for Solana tokens matching the ticker or name.
    Returns the top matching pair with highest liquidity, or None if not found.
    """
    if not query:
        return None
    clean_query = query.strip().lstrip("$")
    if not clean_query:
        return None
    try:
        url = "https://api.dexscreener.com/latest/dex/search"
        resp = _SESSION.get(url, params={"q": clean_query}, timeout=6)
        if resp.status_code == 200:
            data = resp.json()
            raw_pairs = data.get("pairs") or []
            pairs = [p for p in raw_pairs if isinstance(p, dict) and p.get("chainId") == "solana"]
            if pairs:
                pairs.sort(key=lambda x: float((x.get("liquidity") or {}).get("usd", 0) or 0), reverse=True)
                top = pairs[0]
                base = top.get("baseToken") or {}
                mint = base.get("address")
                if mint:
                    return {
                        "mint": mint,
                        "symbol": base.get("symbol", clean_query.upper()),
                        "name": base.get("name", clean_query),
                        "price_usd": float(top.get("priceUsd", 0) or 0),
                        "liquidity_usd": float((top.get("liquidity") or {}).get("usd", 0) or 0),
                        "volume_24h": float((top.get("volume") or {}).get("h24", 0) or 0),
                        "url": top.get("url", "")
                    }
    except Exception:
        pass
    return None
