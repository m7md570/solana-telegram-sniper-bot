# -*- coding: utf-8 -*-
"""
Solana Telegram Sniper & Trading Bot — Wallet Manager
Handles local user wallet generation, AES encryption, RPC balance querying,
and transaction signing for the Telegram Trading Bot.
"""

import os
import sys
import json
import time
import base64
import sqlite3
import hashlib
from typing import Optional, Dict, Any, List, Tuple
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from cryptography.fernet import Fernet
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.hash import Hash
import base58

from config import (
    DB_PATH,
    MASTER_KEY,
    PRIMARY_RPC,
    FALLBACK_RPCS,
    DEFAULT_SLIPPAGE_BPS,
    DEFAULT_PRIORITY_FEE_LAMPORTS,
    WSOL_MINT,
    BOT_VERSION,
    TOKEN_PROGRAM_ID,
    TOKEN_2022_PROGRAM_ID
)

# Derive 32-byte URL-safe base64 key for Fernet from MASTER_KEY
_derived_key = base64.urlsafe_b64encode(hashlib.sha256(MASTER_KEY.encode()).digest())
_cipher = Fernet(_derived_key)

# High-velocity connection pool session for Solana RPC (reusing TLS handshakes across calls)
_RPC_SESSION = requests.Session()
_retry_strategy = Retry(
    total=2,
    backoff_factor=0.2,
    status_forcelist=[429, 500, 502, 503, 504],
)
_adapter = HTTPAdapter(pool_connections=15, pool_maxsize=30, max_retries=_retry_strategy)
_RPC_SESSION.mount("https://", _adapter)
_RPC_SESSION.mount("http://", _adapter)
_RPC_SESSION.headers.update({"User-Agent": f"PopcornSniperBot/{BOT_VERSION} (Solana Engine)"})


def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=15.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA busy_timeout = 10000;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    return conn


def init_database():
    """Initializes SQLite database schemas for users, wallets, and trades with migrations."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                public_key TEXT UNIQUE NOT NULL,
                encrypted_secret TEXT NOT NULL,
                slippage_bps INTEGER DEFAULT 100,
                priority_fee INTEGER DEFAULT 50000,
                referrer_id INTEGER DEFAULT NULL,
                total_referrals INTEGER DEFAULT 0,
                referral_earnings_sol REAL DEFAULT 0.0,
                auto_buy_enabled INTEGER DEFAULT 0,
                auto_buy_amount REAL DEFAULT 0.1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                input_mint TEXT NOT NULL,
                output_mint TEXT NOT NULL,
                amount_in REAL NOT NULL,
                amount_out REAL NOT NULL,
                platform_fee_sol REAL NOT NULL,
                tx_signature TEXT,
                status TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS watchlist (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                token_mint TEXT NOT NULL,
                symbol TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, token_mint),
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        
        # Migration: Ensure all columns exist on older tables
        existing_cols = [r[1] for r in cursor.execute("PRAGMA table_info(users)").fetchall()]
        migrations = [
            ("referrer_id", "INTEGER DEFAULT NULL"),
            ("total_referrals", "INTEGER DEFAULT 0"),
            ("referral_earnings_sol", "REAL DEFAULT 0.0"),
            ("auto_buy_enabled", "INTEGER DEFAULT 0"),
            ("auto_buy_amount", "REAL DEFAULT 0.1"),
            ("language", "TEXT DEFAULT 'en'"),
            ("default_tp_pct", "INTEGER DEFAULT 50"),
            ("default_sl_pct", "INTEGER DEFAULT 25"),
            ("price_alerts_enabled", "INTEGER DEFAULT 1"),
            ("default_alert_pct", "REAL DEFAULT 10.0"),
            ("default_buy_amount", "REAL DEFAULT 0.1")
        ]
        for col_name, col_type in migrations:
            if col_name not in existing_cols:
                cursor.execute(f"ALTER TABLE users ADD COLUMN {col_name} {col_type}")

        # Watchlist migrations for price volatility tracking
        existing_wl_cols = [r[1] for r in cursor.execute("PRAGMA table_info(watchlist)").fetchall()]
        wl_migrations = [
            ("initial_price_usd", "REAL DEFAULT 0.0"),
            ("last_price_usd", "REAL DEFAULT 0.0"),
            ("alert_threshold_pct", "REAL DEFAULT 10.0"),
            ("last_alert_time", "REAL DEFAULT 0.0")
        ]
        for col_name, col_type in wl_migrations:
            if col_name not in existing_wl_cols:
                cursor.execute(f"ALTER TABLE watchlist ADD COLUMN {col_name} {col_type}")

        conn.commit()
    finally:
        conn.close()


# Initialize on import
init_database()


def encrypt_secret(secret_bytes: bytes) -> str:
    """Encrypts raw secret key bytes using Fernet AES cipher."""
    return _cipher.encrypt(secret_bytes).decode("ascii")


def decrypt_secret(encrypted_secret: str) -> bytes:
    """Decrypts encrypted secret string back into raw bytes."""
    return _cipher.decrypt(encrypted_secret.encode("ascii"))


def get_user_language(user_id: int) -> str:
    """Retrieves user language preference ('en' or 'ar'). Defaults to 'en'."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        row = cursor.execute("SELECT language FROM users WHERE user_id = ?", (user_id,)).fetchone()
        if row and row["language"]:
            return row["language"]
        return "en"
    except Exception:
        return "en"
    finally:
        conn.close()


def set_user_language(user_id: int, language: str) -> bool:
    """Updates user language preference ('en' or 'ar')."""
    if language not in ("en", "ar"):
        language = "en"
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET language = ? WHERE user_id = ?", (language, user_id))
        conn.commit()
        return True
    except Exception:
        return False
    finally:
        conn.close()


def get_or_create_wallet(user_id: int, username: str = "", initial_language: str = "en") -> Tuple[str, bool]:
    """
    Retrieves existing user wallet or generates a brand new one.
    Returns: (public_key_str, is_new_wallet)
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        row = cursor.execute("SELECT public_key FROM users WHERE user_id = ?", (user_id,)).fetchone()
        if row:
            return row["public_key"], False

        # Generate new Solana Keypair
        kp = Keypair()
        pubkey_str = str(kp.pubkey())
        secret_bytes = bytes(kp)
        encrypted_str = encrypt_secret(secret_bytes)

        cursor.execute(
            "INSERT INTO users (user_id, username, public_key, encrypted_secret, language) VALUES (?, ?, ?, ?, ?)",
            (user_id, username or "", pubkey_str, encrypted_str, initial_language)
        )
        conn.commit()
        return pubkey_str, True
    finally:
        conn.close()


def get_user_keypair(user_id: int) -> Optional[Keypair]:
    """Retrieves and decrypts the user Keypair for transaction signing."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        row = cursor.execute("SELECT encrypted_secret FROM users WHERE user_id = ?", (user_id,)).fetchone()
        if not row:
            return None
        secret_bytes = decrypt_secret(row["encrypted_secret"])
        return Keypair.from_bytes(secret_bytes)
    finally:
        conn.close()


def export_private_key_b58(user_id: int) -> Optional[str]:
    """Exports private key in standard Base58 format (Phantom/Solflare importable)."""
    kp = get_user_keypair(user_id)
    if not kp:
        return None
    return base58.b58encode(bytes(kp)).decode("ascii")


def get_sol_balance(public_key_str: str) -> float:
    """Queries SOL balance in SOL (not lamports) with multi-RPC fallback."""
    endpoints = [PRIMARY_RPC] + FALLBACK_RPCS
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getBalance",
        "params": [public_key_str]
    }

    for rpc in endpoints:
        try:
            resp = _RPC_SESSION.post(rpc, json=payload, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                lamports = data.get("result", {}).get("value", 0)
                return lamports / 1_000_000_000.0
        except Exception:
            continue

    return 0.0


def get_user_settings(user_id: int) -> Dict[str, Any]:
    """Returns user's slippage, priority fee, TP, SL, and default buy amount settings."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        row = cursor.execute("SELECT slippage_bps, priority_fee, default_tp_pct, default_sl_pct, default_buy_amount FROM users WHERE user_id = ?", (user_id,)).fetchone()
        if row:
            buy_amt = float(row["default_buy_amount"]) if "default_buy_amount" in row.keys() and row["default_buy_amount"] is not None else 0.1
            return {
                "slippage_bps": row["slippage_bps"] or DEFAULT_SLIPPAGE_BPS,
                "priority_fee": row["priority_fee"] or DEFAULT_PRIORITY_FEE_LAMPORTS,
                "default_tp_pct": row["default_tp_pct"] or 50,
                "default_sl_pct": row["default_sl_pct"] or 25,
                "default_buy_amount": buy_amt
            }
    finally:
        conn.close()
    return {
        "slippage_bps": DEFAULT_SLIPPAGE_BPS,
        "priority_fee": DEFAULT_PRIORITY_FEE_LAMPORTS,
        "default_tp_pct": 50,
        "default_sl_pct": 25,
        "default_buy_amount": 0.1
    }


def get_user_default_buy_amount(user_id: int) -> float:
    """Returns the user's default quick-snipe buy amount in SOL (default: 0.1 SOL)."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        row = cursor.execute("SELECT default_buy_amount FROM users WHERE user_id = ?", (user_id,)).fetchone()
        if row and "default_buy_amount" in row.keys() and row["default_buy_amount"] is not None:
            return float(row["default_buy_amount"])
    finally:
        conn.close()
    return 0.1


def update_user_default_buy_amount(user_id: int, amount: float) -> bool:
    """Updates user's default quick-buy amount setting in SOL."""
    if amount <= 0:
        return False
    conn = get_db_connection()
    try:
        conn.execute("UPDATE users SET default_buy_amount = ? WHERE user_id = ?", (amount, user_id))
        conn.commit()
        return True
    finally:
        conn.close()


def update_user_slippage(user_id: int, slippage_bps: int):
    """Updates user slippage setting."""
    conn = get_db_connection()
    try:
        conn.execute("UPDATE users SET slippage_bps = ? WHERE user_id = ?", (slippage_bps, user_id))
        conn.commit()
    finally:
        conn.close()


def update_user_priority_fee(user_id: int, priority_fee_lamports: int):
    """Updates user transaction priority fee setting in lamports."""
    conn = get_db_connection()
    try:
        conn.execute("UPDATE users SET priority_fee = ? WHERE user_id = ?", (priority_fee_lamports, user_id))
        conn.commit()
    finally:
        conn.close()


def reset_user_settings_to_defaults(user_id: int) -> bool:
    """Resets user trading parameters (slippage, priority fee, TP/SL, auto-buy, quick buy size) to recommended factory defaults."""
    conn = get_db_connection()
    try:
        conn.execute("""
            UPDATE users SET 
                slippage_bps = ?,
                priority_fee = ?,
                default_tp_pct = 50,
                default_sl_pct = 25,
                auto_buy_enabled = 0,
                auto_buy_amount = 0.1,
                default_buy_amount = 0.1
            WHERE user_id = ?
        """, (DEFAULT_SLIPPAGE_BPS, DEFAULT_PRIORITY_FEE_LAMPORTS, user_id))
        conn.commit()
        return True
    except Exception as e:
        print(f"Error resetting user settings: {e}")
        return False
    finally:
        conn.close()


def update_user_tp(user_id: int, tp_pct: int):
    """Updates user default Take-Profit target percentage."""
    conn = get_db_connection()
    try:
        conn.execute("UPDATE users SET default_tp_pct = ? WHERE user_id = ?", (tp_pct, user_id))
        conn.commit()
    finally:
        conn.close()


def update_user_sl(user_id: int, sl_pct: int):
    """Updates user default Stop-Loss limit percentage."""
    conn = get_db_connection()
    try:
        conn.execute("UPDATE users SET default_sl_pct = ? WHERE user_id = ?", (sl_pct, user_id))
        conn.commit()
    finally:
        conn.close()


def get_token_accounts(public_key_str: str) -> List[Dict[str, Any]]:
    """Fetches all SPL (legacy & Token-2022) token holdings for a given public key."""
    endpoints = [PRIMARY_RPC] + FALLBACK_RPCS
    programs = [TOKEN_PROGRAM_ID, TOKEN_2022_PROGRAM_ID]

    for rpc in endpoints:
        rpc_tokens = []
        rpc_success = True
        seen_mints = set()
        for prog in programs:
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getTokenAccountsByOwner",
                "params": [
                    public_key_str,
                    {"programId": prog},
                    {"encoding": "jsonParsed"}
                ]
            }
            try:
                resp = _RPC_SESSION.post(rpc, json=payload, timeout=8)
                if resp.status_code == 200:
                    data = resp.json()
                    for item in data.get("result", {}).get("value", []):
                        info = item["account"]["data"]["parsed"]["info"]
                        amount = float(info["tokenAmount"]["uiAmount"] or 0)
                        mint = info["mint"]
                        if amount > 0 and mint not in seen_mints:
                            seen_mints.add(mint)
                            rpc_tokens.append({
                                "mint": mint,
                                "amount": amount,
                                "decimals": info["tokenAmount"]["decimals"],
                                "program": prog
                            })
                else:
                    rpc_success = False
                    break
            except Exception:
                rpc_success = False
                break

        if rpc_success or rpc_tokens:
            return rpc_tokens

    return []


def get_recent_blockhash() -> Optional[Any]:
    """Fetches the latest finalized blockhash from Solana RPC."""
    from solders.hash import Hash
    endpoints = [PRIMARY_RPC] + FALLBACK_RPCS
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getLatestBlockhash",
        "params": [{"commitment": "finalized"}]
    }

    for rpc in endpoints:
        try:
            resp = _RPC_SESSION.post(rpc, json=payload, timeout=6)
            if resp.status_code == 200:
                bh_str = resp.json().get("result", {}).get("value", {}).get("blockhash")
                if bh_str:
                    return Hash.from_string(bh_str)
        except Exception:
            continue
    return None


def withdraw_sol(user_id: int, dest_address: str, amount_sol: float, lang: str = "en") -> Tuple[bool, str]:
    """
    Withdraws SOL from user's bot wallet to an external Solana address (e.g. Phantom).
    Returns: (is_success, tx_signature_or_error)
    """
    from solders.system_program import transfer, TransferParams
    from solders.message import MessageV0
    from solders.transaction import VersionedTransaction

    kp = get_user_keypair(user_id)
    if not kp:
        err = "تعذر العثور على محفظة المستخدم." if lang == "ar" else "User wallet not found."
        return False, err

    # Validate destination pubkey
    try:
        dest_pubkey = Pubkey.from_string(dest_address.strip())
    except Exception:
        err = "عنوان المحفظة الوجهة غير صالح (Invalid Solana Address)." if lang == "ar" else "Invalid Solana destination address."
        return False, err

    user_pubkey_str = str(kp.pubkey())
    current_bal = get_sol_balance(user_pubkey_str)

    # Required gas buffer (0.0005 SOL)
    gas_buffer = 0.0005
    if current_bal < (amount_sol + gas_buffer):
        if lang == "ar":
            err = f"الرصيد غير كافٍ. المتاح: {current_bal:.4f} SOL (المطلوب: {amount_sol} SOL + الرسوم)."
        else:
            err = f"Insufficient balance. Available: {current_bal:.4f} SOL (Required: {amount_sol} SOL + fees)."
        return False, err

    recent_bh = get_recent_blockhash()
    if not recent_bh:
        err = "تعذر جلب Blockhash من شبكة سولانا، يرجى المحاولة بعد لحظات." if lang == "ar" else "Failed to fetch blockhash from Solana network. Please retry."
        return False, err

    lamports = int(amount_sol * 1_000_000_000)
    try:
        ix = transfer(TransferParams(
            from_pubkey=kp.pubkey(),
            to_pubkey=dest_pubkey,
            lamports=lamports
        ))

        msg = MessageV0.try_compile(
            payer=kp.pubkey(),
            instructions=[ix],
            address_lookup_table_accounts=[],
            recent_blockhash=recent_bh
        )
        sig = kp.sign_message(bytes(msg))
        signed_tx = VersionedTransaction.populate(msg, [sig])

        # Broadcast via jupiter_engine.broadcast_transaction
        from jupiter_engine import broadcast_transaction
        success, sig_or_err = broadcast_transaction(bytes(signed_tx))
        return success, sig_or_err
    except Exception as e:
        err = f"خطأ في تنفيذ التحويل: {e}" if lang == "ar" else f"Transfer execution error: {e}"
        return False, err


def record_referral(new_user_id: int, referrer_id: int) -> bool:
    """Links a new user to their referrer."""
    if new_user_id == referrer_id:
        return False
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        # Verify referrer exists
        ref_row = cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (referrer_id,)).fetchone()
        if not ref_row:
            return False

        # Check if user already has a referrer
        user_row = cursor.execute("SELECT referrer_id FROM users WHERE user_id = ?", (new_user_id,)).fetchone()
        if user_row and user_row["referrer_id"] is None:
            cursor.execute("UPDATE users SET referrer_id = ? WHERE user_id = ?", (referrer_id, new_user_id))
            cursor.execute("UPDATE users SET total_referrals = total_referrals + 1 WHERE user_id = ?", (referrer_id,))
            conn.commit()
            return True
        return False
    finally:
        conn.close()


def get_referral_stats(user_id: int) -> Dict[str, Any]:
    """Retrieves referral count and total earned SOL for a user."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        row = cursor.execute("SELECT total_referrals, referral_earnings_sol FROM users WHERE user_id = ?", (user_id,)).fetchone()
        if row:
            return {
                "total_referrals": row["total_referrals"] or 0,
                "earnings_sol": row["referral_earnings_sol"] or 0.0
            }
        return {"total_referrals": 0, "earnings_sol": 0.0}
    finally:
        conn.close()


def get_auto_buy_settings(user_id: int) -> Tuple[bool, float]:
    """Returns (is_enabled, amount_sol) for auto-buy."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        row = cursor.execute("SELECT auto_buy_enabled, auto_buy_amount FROM users WHERE user_id = ?", (user_id,)).fetchone()
        if row:
            return bool(row["auto_buy_enabled"]), float(row["auto_buy_amount"] or 0.1)
        return False, 0.1
    finally:
        conn.close()


def toggle_auto_buy(user_id: int) -> bool:
    """Toggles auto-buy enabled state and returns new state."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        row = cursor.execute("SELECT auto_buy_enabled FROM users WHERE user_id = ?", (user_id,)).fetchone()
        current = bool(row["auto_buy_enabled"]) if row else False
        new_state = not current
        cursor.execute("UPDATE users SET auto_buy_enabled = ? WHERE user_id = ?", (1 if new_state else 0, user_id))
        conn.commit()
        return new_state
    finally:
        conn.close()


def set_auto_buy_status(user_id: int, enabled: bool):
    """Explicitly sets auto-buy enabled status."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET auto_buy_enabled = ? WHERE user_id = ?", (1 if enabled else 0, user_id))
        conn.commit()
    finally:
        conn.close()


def set_auto_buy_amount(user_id: int, amount_sol: float):
    """Sets the auto-buy amount in SOL."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET auto_buy_amount = ? WHERE user_id = ?", (amount_sol, user_id))
        conn.commit()
    finally:
        conn.close()


def get_user_trade_stats(user_id: int) -> Dict[str, Any]:
    """Retrieves aggregated trade statistics and recent history for a user."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        trades = cursor.execute(
            "SELECT id, input_mint, output_mint, amount_in, amount_out, platform_fee_sol, tx_signature, status, created_at "
            "FROM trades WHERE user_id = ? ORDER BY id DESC LIMIT 10",
            (user_id,)
        ).fetchall()
        
        total_volume = cursor.execute(
            """
            SELECT COALESCE(SUM(
                CASE 
                    WHEN input_mint = ? THEN amount_in
                    WHEN output_mint = ? THEN amount_out
                    ELSE amount_in
                END
            ), 0.0) FROM trades WHERE user_id = ? AND status = 'CONFIRMED'
            """,
            (WSOL_MINT, WSOL_MINT, user_id)
        ).fetchone()[0]

        total_fees = cursor.execute(
            "SELECT COALESCE(SUM(platform_fee_sol), 0.0) FROM trades WHERE user_id = ? AND status = 'CONFIRMED'",
            (user_id,)
        ).fetchone()[0]

        trade_count = cursor.execute(
            "SELECT COUNT(*) FROM trades WHERE user_id = ?",
            (user_id,)
        ).fetchone()[0]

        confirmed_count = cursor.execute(
            "SELECT COUNT(*) FROM trades WHERE user_id = ? AND status = 'CONFIRMED'",
            (user_id,)
        ).fetchone()[0]

        rate = (confirmed_count / trade_count * 100.0) if trade_count > 0 else 100.0

        return {
            "total_trades": trade_count,
            "confirmed_trades": confirmed_count,
            "success_rate_pct": round(rate, 1),
            "total_volume_sol": float(total_volume or 0.0),
            "total_fees_sol": float(total_fees or 0.0),
            "recent_trades": [dict(r) for r in trades]
        }
    finally:
        conn.close()


def record_trade(
    user_id: int,
    input_mint: str,
    output_mint: str,
    amount_in: float,
    amount_out: float,
    fee_sol: float = 0.0,
    tx_sig: str = "",
    status: str = "CONFIRMED",
    platform_fee_sol: float = None,
    tx_signature: str = None
) -> bool:
    """Logs the executed trade into SQLite database for PnL, audits, and CSV export."""
    actual_fee = platform_fee_sol if platform_fee_sol is not None else fee_sol
    actual_sig = tx_signature if tx_signature is not None else tx_sig
    conn = get_db_connection()
    try:
        conn.execute("""
            INSERT INTO trades (
                user_id, input_mint, output_mint, amount_in,
                amount_out, platform_fee_sol, tx_signature, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (user_id, input_mint, output_mint, amount_in, amount_out, actual_fee, actual_sig, status))
        conn.commit()
        return True
    finally:
        conn.close()


record_trade_db = record_trade


def get_all_user_trades(user_id: int) -> List[Dict[str, Any]]:
    """Retrieves all historical trade executions for a user ordered newest to oldest."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        rows = cursor.execute(
            "SELECT id, input_mint, output_mint, amount_in, amount_out, platform_fee_sol, tx_signature, status, created_at "
            "FROM trades WHERE user_id = ? ORDER BY id DESC",
            (user_id,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def generate_trades_csv_bytes(user_id: int) -> bytes:
    """Generates standard RFC 4180 CSV bytes (UTF-8 with BOM) containing all trade records."""
    import csv
    import io

    trades = get_all_user_trades(user_id)
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow([
        "Trade ID",
        "Timestamp (UTC)",
        "Type",
        "Input Mint",
        "Output Mint",
        "Amount In",
        "Amount Out",
        "Platform Fee (SOL)",
        "Status",
        "Tx Signature",
        "Solscan URL"
    ])
    for tr in trades:
        in_m = tr.get("input_mint", "")
        out_m = tr.get("output_mint", "")
        trade_type = "BUY" if in_m == WSOL_MINT else "SELL"
        sig = tr.get("tx_signature") or ""
        solscan_url = f"https://solscan.io/tx/{sig}" if sig else ""
        writer.writerow([
            tr.get("id"),
            tr.get("created_at"),
            trade_type,
            in_m,
            out_m,
            tr.get("amount_in"),
            tr.get("amount_out"),
            tr.get("platform_fee_sol"),
            tr.get("status"),
            sig,
            solscan_url
        ])
    return output.getvalue().encode("utf-8-sig")


def add_to_watchlist(user_id: int, token_mint: str, symbol: str, current_price: float = 0.0) -> bool:
    """Adds a token to user's personal watchlist with initial tracking price and user's threshold."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        u_row = cursor.execute("SELECT default_alert_pct FROM users WHERE user_id = ?", (user_id,)).fetchone()
        default_th = float(u_row["default_alert_pct"]) if u_row and "default_alert_pct" in u_row.keys() and u_row["default_alert_pct"] is not None else 10.0
        cursor.execute(
            """INSERT INTO watchlist (user_id, token_mint, symbol, initial_price_usd, last_price_usd, alert_threshold_pct, last_alert_time)
               VALUES (?, ?, ?, ?, ?, ?, 0.0)
               ON CONFLICT(user_id, token_mint) DO UPDATE SET 
               symbol = excluded.symbol,
               last_price_usd = CASE WHEN excluded.last_price_usd > 0 THEN excluded.last_price_usd ELSE watchlist.last_price_usd END""",
            (user_id, token_mint, symbol.upper(), current_price, current_price, default_th)
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def remove_from_watchlist(user_id: int, token_mint: str) -> bool:
    """Removes a token from user's watchlist."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM watchlist WHERE user_id = ? AND token_mint = ?",
            (user_id, token_mint)
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def clear_user_watchlist(user_id: int) -> int:
    """Removes all tracked tokens from a user's watchlist and returns count of removed items."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM watchlist WHERE user_id = ?", (user_id,))
        conn.commit()
        return cursor.rowcount or 0
    finally:
        conn.close()


def is_token_in_watchlist(user_id: int, token_mint: str) -> bool:
    """Returns True if the token is currently saved in user's watchlist."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        row = cursor.execute(
            "SELECT 1 FROM watchlist WHERE user_id = ? AND token_mint = ?",
            (user_id, token_mint)
        ).fetchone()
        return bool(row)
    finally:
        conn.close()


def get_user_watchlist(user_id: int) -> List[Dict[str, Any]]:
    """Retrieves all tracked tokens for a user with price history."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        rows = cursor.execute(
            "SELECT token_mint, symbol, initial_price_usd, last_price_usd, alert_threshold_pct, created_at "
            "FROM watchlist WHERE user_id = ? ORDER BY id DESC",
            (user_id,)
        ).fetchall()
        return [{
            "mint": r["token_mint"],
            "symbol": r["symbol"],
            "initial_price": float(r["initial_price_usd"] or 0.0),
            "last_price": float(r["last_price_usd"] or 0.0),
            "threshold_pct": float(r["alert_threshold_pct"] or 10.0),
            "created_at": r["created_at"]
        } for r in rows]
    finally:
        conn.close()


def get_all_active_watchlist_subscriptions() -> List[Dict[str, Any]]:
    """Retrieves all active watchlist entries across users who have price alerts enabled."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        rows = cursor.execute(
            """SELECT w.user_id, w.token_mint, w.symbol, w.initial_price_usd, w.last_price_usd,
                      w.alert_threshold_pct, w.last_alert_time, COALESCE(u.language, 'en') as language
               FROM watchlist w
               LEFT JOIN users u ON w.user_id = u.user_id
               WHERE COALESCE(u.price_alerts_enabled, 1) = 1"""
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def update_watchlist_price_and_alert(user_id: int, token_mint: str, new_price: float, record_alert: bool = False):
    """Updates the last recorded price and optionally the last alerted timestamp."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        if record_alert:
            cursor.execute(
                "UPDATE watchlist SET last_price_usd = ?, last_alert_time = ? WHERE user_id = ? AND token_mint = ?",
                (new_price, time.time(), user_id, token_mint)
            )
        else:
            cursor.execute(
                "UPDATE watchlist SET last_price_usd = ? WHERE user_id = ? AND token_mint = ?",
                (new_price, user_id, token_mint)
            )
        conn.commit()
    finally:
        conn.close()


def toggle_price_alerts(user_id: int) -> bool:
    """Toggles user's price alert subscription status."""
    get_or_create_wallet(user_id)
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        row = cursor.execute("SELECT price_alerts_enabled FROM users WHERE user_id = ?", (user_id,)).fetchone()
        current = bool(row["price_alerts_enabled"]) if row and row["price_alerts_enabled"] is not None else True
        new_val = 0 if current else 1
        cursor.execute("UPDATE users SET price_alerts_enabled = ? WHERE user_id = ?", (new_val, user_id))
        conn.commit()
        return bool(new_val)
    finally:
        conn.close()


def get_price_alerts_status(user_id: int) -> bool:
    """Returns True if price alerts are enabled for this user."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        row = cursor.execute("SELECT price_alerts_enabled FROM users WHERE user_id = ?", (user_id,)).fetchone()
        if row and row["price_alerts_enabled"] is not None:
            return bool(row["price_alerts_enabled"])
        return True
    finally:
        conn.close()


def set_price_alerts_status(user_id: int, enabled: bool) -> bool:
    """Explicitly enables or disables price alerts for a user."""
    get_or_create_wallet(user_id)
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        val = 1 if enabled else 0
        cursor.execute("UPDATE users SET price_alerts_enabled = ? WHERE user_id = ?", (val, user_id))
        conn.commit()
        return bool(val)
    finally:
        conn.close()


def get_user_alert_settings(user_id: int) -> Tuple[bool, float]:
    """Returns (alerts_enabled, threshold_pct) for the user."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        row = cursor.execute("SELECT price_alerts_enabled, default_alert_pct FROM users WHERE user_id = ?", (user_id,)).fetchone()
        if row:
            enabled = bool(row["price_alerts_enabled"]) if row["price_alerts_enabled"] is not None else True
            pct = float(row["default_alert_pct"]) if "default_alert_pct" in row.keys() and row["default_alert_pct"] is not None else 10.0
            return enabled, pct
        return True, 10.0
    finally:
        conn.close()


def update_user_alert_threshold(user_id: int, threshold_pct: float) -> bool:
    """Updates user's default volatility alert threshold percentage and syncs watchlist."""
    get_or_create_wallet(user_id)
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET default_alert_pct = ? WHERE user_id = ?", (threshold_pct, user_id))
        cursor.execute("UPDATE watchlist SET alert_threshold_pct = ? WHERE user_id = ?", (threshold_pct, user_id))
        conn.commit()
        return True
    finally:
        conn.close()


def generate_deposit_qr_buffer(pubkey: str):
    """
    Generates an in-memory PNG QR code buffer for the specified Solana public key.
    Uses standard solana:<pubkey> URI scheme compatible with Phantom, Solflare, OKX, and Binance.
    """
    import io
    import qrcode
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8,
        border=2,
    )
    qr.add_data(f"solana:{pubkey}")
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf



