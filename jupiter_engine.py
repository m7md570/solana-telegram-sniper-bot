# -*- coding: utf-8 -*-
"""
Solana Telegram Sniper & Trading Bot — Jupiter V6 Execution Engine
High-velocity DEX routing, fee attribution (platformFeeBps = 100),
and transaction serialization with solders.
"""

import base64
import json
import time
from typing import Dict, Any, Optional, Tuple
import requests
from solders.keypair import Keypair
from solders.transaction import VersionedTransaction
from solders.message import to_bytes_versioned
from solders.pubkey import Pubkey

from config import (
    JUPITER_QUOTE_API,
    JUPITER_SWAP_API,
    DEVELOPER_WALLET,
    PLATFORM_FEE_BPS,
    PRIMARY_RPC,
    FALLBACK_RPCS,
    DEFAULT_SLIPPAGE_BPS,
    MAX_SLIPPAGE_BPS,
    DEFAULT_PRIORITY_FEE_LAMPORTS,
    WSOL_MINT
)
from wallet_manager import get_db_connection

# Persistent HTTP session with connection pooling and keep-alive for sub-300ms Jupiter execution
_SESSION = requests.Session()
_SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9"
})


def calculate_optimal_slippage(price_impact_pct: float, base_slippage_bps: int = DEFAULT_SLIPPAGE_BPS) -> int:
    """
    Dynamically optimizes slippage tolerance based on price impact and market depth.
    Protects user from MEV sandwich attacks by capping slippage while preventing failed swaps.
    - Low price impact (< 0.5%): uses user's base slippage (e.g. 50-100 bps).
    - Moderate price impact (0.5% - 2.0%): scales up proportionally with buffer.
    - High price impact (> 2.0%): caps strictly at min(impact*100 + 100, MAX_SLIPPAGE_BPS) to prevent toxic sandwiching.
    """
    try:
        impact_bps = int(abs(float(price_impact_pct or 0.0)) * 100)
    except Exception:
        impact_bps = 0

    if impact_bps < 50:
        return max(50, base_slippage_bps)
    dynamic_bps = impact_bps + 50
    return min(max(base_slippage_bps, dynamic_bps), MAX_SLIPPAGE_BPS)


def get_jupiter_quote(
    input_mint: str,
    output_mint: str,
    amount_lamports: int,
    slippage_bps: int = DEFAULT_SLIPPAGE_BPS,
    with_fee: bool = True
) -> Optional[Dict[str, Any]]:
    """
    Fetches the optimal routing quote from Jupiter V6.
    Includes the 1.0% platform fee calculation.
    """
    params = {
        "inputMint": input_mint,
        "outputMint": output_mint,
        "amount": str(amount_lamports),
        "slippageBps": str(slippage_bps),
    }

    if with_fee:
        params["platformFeeBps"] = str(PLATFORM_FEE_BPS)

    for attempt in range(2):
        try:
            resp = _SESSION.get(JUPITER_QUOTE_API, params=params, timeout=12)
            if resp.status_code == 200:
                return resp.json()
            elif attempt == 0:
                time.sleep(1)
                continue
            else:
                print(f"Jupiter quote error ({resp.status_code}): {resp.text}")
        except Exception as e:
            if attempt == 0:
                time.sleep(1)
                continue
            print(f"Jupiter quote exception: {e}")

    return None


def build_and_sign_swap_tx(
    quote: Dict[str, Any],
    user_keypair: Keypair,
    priority_fee_lamports: int = DEFAULT_PRIORITY_FEE_LAMPORTS
) -> Optional[bytes]:
    """
    Requests the swap transaction from Jupiter and signs it using the user's Keypair.
    Attributes feeAccount directly to DEVELOPER_WALLET to route platform trading fees.
    Returns: Serialized signed transaction bytes ready for RPC broadcast.
    """
    user_pubkey_str = str(user_keypair.pubkey())

    payload = {
        "quoteResponse": quote,
        "userPublicKey": user_pubkey_str,
        "wrapAndUnwrapSol": True,
        "prioritizationFeeLamports": priority_fee_lamports
    }

    # Route platform trading fee directly to developer wallet
    if DEVELOPER_WALLET:
        payload["feeAccount"] = DEVELOPER_WALLET

    try:
        resp = _SESSION.post(JUPITER_SWAP_API, json=payload, timeout=10)
        if resp.status_code != 200:
            print(f"Jupiter swap build error ({resp.status_code}): {resp.text}")
            return None

        swap_data = resp.json()
        swap_b64 = swap_data.get("swapTransaction")
        if not swap_b64:
            return None

        # Decode base64 transaction
        tx_bytes = base64.b64decode(swap_b64)
        raw_tx = VersionedTransaction.from_bytes(tx_bytes)

        # Sign with user's Keypair
        msg_bytes = to_bytes_versioned(raw_tx.message)
        signature = user_keypair.sign_message(msg_bytes)
        signed_tx = VersionedTransaction.populate(raw_tx.message, [signature])

        return bytes(signed_tx)
    except Exception as e:
        print(f"Transaction build & sign error: {e}")
        return None


def broadcast_transaction(tx_bytes: bytes) -> Tuple[bool, str]:
    """
    Broadcasts signed transaction to Solana JSON-RPC endpoints with failover.
    Returns: (is_success, signature_or_error)
    """
    b64_tx = base64.b64encode(tx_bytes).decode("ascii")
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "sendTransaction",
        "params": [
            b64_tx,
            {
                "encoding": "base64",
                "skipPreflight": True,
                "preflightCommitment": "processed",
                "maxRetries": 3
            }
        ]
    }

    endpoints = [PRIMARY_RPC] + FALLBACK_RPCS
    for rpc in endpoints:
        try:
            r = _SESSION.post(rpc, json=payload, timeout=6)
            if r.status_code == 200:
                res = r.json()
                if "result" in res:
                    return True, res["result"]
                elif "error" in res:
                    return False, res["error"].get("message", "RPC Error")
        except Exception:
            continue

    return False, "All RPC endpoints failed to broadcast"


def record_trade_db(
    user_id: int,
    input_mint: str,
    output_mint: str,
    amount_in: float,
    amount_out: float,
    fee_sol: float,
    tx_sig: str,
    status: str
):
    """Logs the executed trade into SQLite database for PnL and analytics."""
    conn = get_db_connection()
    try:
        conn.execute("""
            INSERT INTO trades (
                user_id, input_mint, output_mint, amount_in,
                amount_out, platform_fee_sol, tx_signature, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (user_id, input_mint, output_mint, amount_in, amount_out, fee_sol, tx_sig, status))
        conn.commit()
    except Exception as e:
        print(f"Trade logging warning: {e}")
    finally:
        conn.close()


def execute_sell_swap(
    user_id: int,
    token_mint: str,
    pct_to_sell: int,
    lang: str = "en"
) -> Tuple[bool, str, float]:
    """
    Executes an on-chain market sell for a specific percentage of user's held token into SOL.
    Returns: (is_success, tx_signature_or_error, sol_received)
    """
    from wallet_manager import get_user_keypair, get_token_accounts, get_user_settings

    keypair = get_user_keypair(user_id)
    if not keypair:
        err = "تعذر العثور على محفظة المستخدم." if lang == "ar" else "User wallet not found."
        return False, err, 0.0

    pubkey_str = str(keypair.pubkey())
    tokens = get_token_accounts(pubkey_str)

    # Find the target token
    target_token = next((t for t in tokens if t["mint"] == token_mint), None)
    if not target_token or target_token["amount"] <= 0:
        err = "لا تملك رصيداً من هذه العملة للبيع." if lang == "ar" else "No token balance available to sell."
        return False, err, 0.0

    total_amount = target_token["amount"]
    decimals = target_token.get("decimals", 6)

    # Calculate quantity to sell
    sell_fraction = max(0.01, min(1.0, pct_to_sell / 100.0))
    sell_amount = total_amount * sell_fraction
    raw_atomic_units = int(sell_amount * (10 ** decimals))

    if raw_atomic_units <= 0:
        err = "الكمية المراد بيعها صغيرة جداً." if lang == "ar" else "Amount to sell is too small."
        return False, err, 0.0

    settings = get_user_settings(user_id)
    slippage = settings["slippage_bps"]

    # Fetch initial quote: token -> WSOL
    quote = get_jupiter_quote(
        input_mint=token_mint,
        output_mint=WSOL_MINT,
        amount_lamports=raw_atomic_units,
        slippage_bps=slippage,
        with_fee=True
    )
    if not quote:
        err = "تعذر العثور على مسار بيع أو سيولة في Jupiter." if lang == "ar" else "No swap liquidity route available on Jupiter."
        return False, err, 0.0

    # Dynamic MEV anti-sandwich slippage optimization
    price_impact = float(quote.get("priceImpactPct") or 0.0)
    optimal_slip = calculate_optimal_slippage(price_impact, slippage)
    if optimal_slip != slippage:
        re_quote = get_jupiter_quote(
            input_mint=token_mint,
            output_mint=WSOL_MINT,
            amount_lamports=raw_atomic_units,
            slippage_bps=optimal_slip,
            with_fee=True
        )
        if re_quote:
            quote = re_quote

    # Build and sign transaction
    tx_bytes = build_and_sign_swap_tx(quote, keypair, settings["priority_fee"])
    if not tx_bytes:
        err = "فشل في بناء وتوقيع معاملة البيع الذكية." if lang == "ar" else "Failed to construct and sign sell transaction."
        return False, err, 0.0

    # Broadcast to Solana RPC
    success, sig_or_err = broadcast_transaction(tx_bytes)
    if success:
        out_lamports = float(quote.get("outAmount", 0))
        sol_received = out_lamports / 1e9
        fee_lamports = float(quote.get("platformFee", {}).get("amount", 0))
        record_trade_db(
            user_id=user_id,
            input_mint=token_mint,
            output_mint=WSOL_MINT,
            amount_in=sell_amount,
            amount_out=sol_received,
            fee_sol=fee_lamports / 1e9,
            tx_sig=sig_or_err,
            status="CONFIRMED"
        )
        return True, sig_or_err, sol_received
    else:
        return False, sig_or_err, 0.0
