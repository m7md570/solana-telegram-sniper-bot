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
from cryptography.fernet import Fernet
from solders.keypair import Keypair
from solders.pubkey import Pubkey
import base58

from config import (
    DB_PATH,
    MASTER_KEY,
    PRIMARY_RPC,
    FALLBACK_RPCS,
    DEFAULT_SLIPPAGE_BPS,
    DEFAULT_PRIORITY_FEE_LAMPORTS,
    WSOL_MINT
)

# Derive 32-byte URL-safe base64 key for Fernet from MASTER_KEY
_derived_key = base64.urlsafe_b64encode(hashlib.sha256(MASTER_KEY.encode()).digest())
_cipher = Fernet(_derived_key)


def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_database():
    """Initializes SQLite database schemas for users, wallets, and trades."""
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


def get_or_create_wallet(user_id: int, username: str = "") -> Tuple[str, bool]:
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
            "INSERT INTO users (user_id, username, public_key, encrypted_secret) VALUES (?, ?, ?, ?)",
            (user_id, username or "", pubkey_str, encrypted_str)
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
            resp = requests.post(rpc, json=payload, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                lamports = data.get("result", {}).get("value", 0)
                return lamports / 1_000_000_000.0
        except Exception:
            continue

    return 0.0


def get_user_settings(user_id: int) -> Dict[str, int]:
    """Returns user's slippage and priority fee settings."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        row = cursor.execute("SELECT slippage_bps, priority_fee FROM users WHERE user_id = ?", (user_id,)).fetchone()
        if row:
            return {
                "slippage_bps": row["slippage_bps"],
                "priority_fee": row["priority_fee"]
            }
    finally:
        conn.close()
    return {
        "slippage_bps": DEFAULT_SLIPPAGE_BPS,
        "priority_fee": DEFAULT_PRIORITY_FEE_LAMPORTS
    }


def update_user_slippage(user_id: int, slippage_bps: int):
    """Updates user slippage setting."""
    conn = get_db_connection()
    try:
        conn.execute("UPDATE users SET slippage_bps = ? WHERE user_id = ?", (slippage_bps, user_id))
        conn.commit()
    finally:
        conn.close()


def get_token_accounts(public_key_str: str) -> List[Dict[str, Any]]:
    """Fetches all SPL token holdings for a given public key."""
    endpoints = [PRIMARY_RPC] + FALLBACK_RPCS
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getTokenAccountsByOwner",
        "params": [
            public_key_str,
            {"programId": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"},
            {"encoding": "jsonParsed"}
        ]
    }

    for rpc in endpoints:
        try:
            resp = requests.post(rpc, json=payload, timeout=8)
            if resp.status_code == 200:
                data = resp.json()
                tokens = []
                for item in data.get("result", {}).get("value", []):
                    info = item["account"]["data"]["parsed"]["info"]
                    amount = float(info["tokenAmount"]["uiAmount"] or 0)
                    if amount > 0:
                        tokens.append({
                            "mint": info["mint"],
                            "amount": amount,
                            "decimals": info["tokenAmount"]["decimals"]
                        })
                return tokens
        except Exception:
            continue

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
            resp = requests.post(rpc, json=payload, timeout=6)
            if resp.status_code == 200:
                bh_str = resp.json().get("result", {}).get("value", {}).get("blockhash")
                if bh_str:
                    return Hash.from_string(bh_str)
        except Exception:
            continue
    return None


def withdraw_sol(user_id: int, dest_address: str, amount_sol: float) -> Tuple[bool, str]:
    """
    Withdraws SOL from user's bot wallet to an external Solana address (e.g. Phantom).
    Returns: (is_success, tx_signature_or_error)
    """
    from solders.system_program import transfer, TransferParams
    from solders.message import MessageV0
    from solders.transaction import VersionedTransaction

    kp = get_user_keypair(user_id)
    if not kp:
        return False, "تعذر العثور على محفظة المستخدم."

    # Validate destination pubkey
    try:
        dest_pubkey = Pubkey.from_string(dest_address.strip())
    except Exception:
        return False, "عنوان المحفظة الوجهة غير صالح (Invalid Solana Address)."

    user_pubkey_str = str(kp.pubkey())
    current_bal = get_sol_balance(user_pubkey_str)

    # Required gas buffer (0.0005 SOL)
    gas_buffer = 0.0005
    if current_bal < (amount_sol + gas_buffer):
        return False, f"الرصيد غير كافٍ. المتاح: {current_bal:.4f} SOL (المطلوب: {amount_sol} SOL + الرسوم)."

    recent_bh = get_recent_blockhash()
    if not recent_bh:
        return False, "تعذر جلب Blockhash من شبكة سولانا، يرجى المحاولة بعد لحظات."

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
        return False, f"خطأ في تنفيذ التحويل: {e}"
