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
    DEFAULT_PRIORITY_FEE_LAMPORTS,
    WSOL_MINT
)
from wallet_manager import get_db_connection


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

    try:
        resp = requests.get(JUPITER_QUOTE_API, params=params, timeout=8)
        if resp.status_code == 200:
            return resp.json()
        else:
            print(f"Jupiter quote error ({resp.status_code}): {resp.text}")
    except Exception as e:
        print(f"Jupiter quote exception: {e}")

    return None


def build_and_sign_swap_tx(
    quote: Dict[str, Any],
    user_keypair: Keypair,
    priority_fee_lamports: int = DEFAULT_PRIORITY_FEE_LAMPORTS
) -> Optional[bytes]:
    """
    Requests the swap transaction from Jupiter and signs it using the user's Keypair.
    Returns: Serialized signed transaction bytes ready for RPC broadcast.
    """
    user_pubkey_str = str(user_keypair.pubkey())

    payload = {
        "quoteResponse": quote,
        "userPublicKey": user_pubkey_str,
        "wrapAndUnwrapSol": True,
        "prioritizationFeeLamports": priority_fee_lamports
    }

    try:
        resp = requests.post(JUPITER_SWAP_API, json=payload, timeout=10)
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
            r = requests.post(rpc, json=payload, timeout=6)
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
    try:
        with get_db_connection() as conn:
            conn.execute("""
                INSERT INTO trades (
                    user_id, input_mint, output_mint, amount_in,
                    amount_out, platform_fee_sol, tx_signature, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (user_id, input_mint, output_mint, amount_in, amount_out, fee_sol, tx_sig, status))
            conn.commit()
    except Exception as e:
        print(f"Trade logging warning: {e}")
