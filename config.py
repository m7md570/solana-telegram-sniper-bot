# -*- coding: utf-8 -*-
"""
Solana Telegram Sniper & Trading Bot — Configuration
Core engine settings, developer fee routing, and RPC endpoints.
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# Auto-load .env file if present
ENV_FILE = BASE_DIR / ".env"
if ENV_FILE.exists():
    with open(ENV_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ[k.strip()] = v.strip().strip('"').strip("'")

# ==============================================================================
# 🎯 DEVELOPER MONETIZATION & PLATFORM FEES
# ==============================================================================
# The on-chain Solana payout wallet receiving all trading commissions
DEVELOPER_WALLET = "7kz1mcQcaZhYzFUHBFHH6s5tGrDHc7gNhN5WAUyXyq5r"

# Platform fee in Basis Points (100 BPS = 1.00%)
# Automatically deducted on every Jupiter Swap instruction
PLATFORM_FEE_BPS = 100

# ==============================================================================
# 🌐 SOLANA RPC & INFRASTRUCTURE
# ==============================================================================
PRIMARY_RPC = os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")
FALLBACK_RPCS = [
    "https://api.mainnet.solana.com",
    "https://solana-rpc.publicnode.com",
]

# Standard Solana Native Mint (Wrapped SOL)
WSOL_MINT = "So11111111111111111111111111111111111111112"
USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"

# ==============================================================================
# ⚡ JUPITER & RUGCHECK APIS
# ==============================================================================
JUPITER_QUOTE_API = "https://public.jupiterapi.com/quote"
JUPITER_SWAP_API = "https://public.jupiterapi.com/swap"
JUPITER_PRICE_API = "https://api.jup.ag/price/v2"

RUGCHECK_API = "https://api.rugcheck.xyz/v1/tokens"
DEXSCREENER_API = "https://api.dexscreener.com/latest/dex/tokens"

# ==============================================================================
# 🤖 TELEGRAM BOT & SECURITY
# ==============================================================================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

# Master encryption key for user keypairs (AES-256)
MASTER_KEY = os.getenv("BOT_MASTER_KEY", "solana_sniper_super_secret_master_key_2026_secure")

# Database & Storage
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
DB_PATH = DATA_DIR / "bot_database.sqlite"

# Trading Defaults
DEFAULT_SLIPPAGE_BPS = 100     # 1% slippage
MAX_SLIPPAGE_BPS = 1500        # 15% slippage cap
DEFAULT_PRIORITY_FEE_LAMPORTS = 50_000  # 0.00005 SOL priority fee for fast landing

# System Version & Token Programs
BOT_VERSION = "v3.38.0"
TOKEN_PROGRAM_ID = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
TOKEN_2022_PROGRAM_ID = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"
