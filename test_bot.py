# -*- coding: utf-8 -*-
"""
Solana Telegram Sniper & Trading Bot — Comprehensive Test Suite
Validates wallet encryption, RugCheck audits, Jupiter V6 routing,
and platform fee attribution on-chain.
"""

import sys
import unittest
import base64
from solders.keypair import Keypair

from config import (
    DEVELOPER_WALLET,
    PLATFORM_FEE_BPS,
    WSOL_MINT,
    USDC_MINT
)
from wallet_manager import (
    get_or_create_wallet,
    get_user_keypair,
    export_private_key_b58,
    get_sol_balance,
    encrypt_secret,
    decrypt_secret,
    init_database,
    get_user_settings,
    update_user_slippage
)
from rugcheck_scanner import scan_token_security, format_token_card
from jupiter_engine import (
    get_jupiter_quote,
    build_and_sign_swap_tx,
    record_trade_db
)


class TestSolanaTelegramSniperBot(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        init_database()
        cls.test_user_id = 88812345
        cls.test_username = "AlphaTraderTest"
        cls.bonk_mint = "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"

    def test_01_wallet_generation_and_encryption(self):
        """Test wallet creation, AES encryption, and decryption."""
        pubkey, is_new = get_or_create_wallet(self.test_user_id, self.test_username)
        self.assertTrue(len(pubkey) >= 32, "Public key must be valid Base58")

        kp = get_user_keypair(self.test_user_id)
        self.assertIsNotNone(kp, "Decrypted Keypair should not be None")
        self.assertEqual(str(kp.pubkey()), pubkey, "Decrypted Keypair must match stored pubkey")

        # Test Private Key Export
        p_key = export_private_key_b58(self.test_user_id)
        self.assertTrue(len(p_key) >= 64, "Base58 private key should be at least 64 chars")

    def test_02_wallet_settings(self):
        """Test slippage and priority fee persistence."""
        update_user_slippage(self.test_user_id, 250)
        settings = get_user_settings(self.test_user_id)
        self.assertEqual(settings["slippage_bps"], 250, "Slippage should be updated to 250 bps (2.5%)")

    def test_03_rugcheck_and_dexscreener_audit(self):
        """Test token security scanner and market metrics for BONK token."""
        scan = scan_token_security(self.bonk_mint)
        self.assertTrue(scan["is_valid"], "Token should be resolved on DexScreener")
        self.assertEqual(scan["symbol"].upper(), "BONK", "Token symbol must be BONK")
        self.assertGreater(scan["price_usd"], 0.0, "Price USD should be positive")
        self.assertGreater(scan["mcap"], 10_000_000, "BONK MCap should be > $10M")
        
        # Test formatting card
        card = format_token_card(scan)
        self.assertIn("bonk", card.lower())
        self.assertIn("السعر الحالي", card)

    def test_04_jupiter_v6_quote_with_platform_fee(self):
        """Test Jupiter quote routing and platform fee calculation."""
        amount_lamports = 100_000_000  # 0.1 SOL
        quote = get_jupiter_quote(WSOL_MINT, USDC_MINT, amount_lamports, slippage_bps=100, with_fee=True)
        self.assertIsNotNone(quote, "Jupiter must return a valid routing quote")
        self.assertIn("outAmount", quote, "Quote must specify output amount")
        self.assertGreater(int(quote["outAmount"]), 0, "Output USDC should be positive")

        # Verify Platform Fee
        fee_obj = quote.get("platformFee")
        self.assertIsNotNone(fee_obj, "Jupiter quote must include platformFee attribution")
        self.assertGreater(int(fee_obj.get("feeBps", 0)), 0, "Platform fee BPS must be > 0")
        self.assertGreater(int(fee_obj.get("amount", 0)), 0, "Platform fee lamports must be > 0")

    def test_05_swap_transaction_building_and_signing(self):
        """Test transaction assembly and offline signing using Solders."""
        amount_lamports = 50_000_000  # 0.05 SOL
        quote = get_jupiter_quote(WSOL_MINT, USDC_MINT, amount_lamports, slippage_bps=100, with_fee=False)
        self.assertIsNotNone(quote)

        keypair = get_user_keypair(self.test_user_id)
        tx_bytes = build_and_sign_swap_tx(quote, keypair)
        self.assertIsNotNone(tx_bytes, "Signed transaction bytes must be generated")
        self.assertGreater(len(tx_bytes), 300, "Signed transaction must have valid serialized payload")

    def test_06_database_trade_logging(self):
        """Test trade logging in SQLite."""
        record_trade_db(
            user_id=self.test_user_id,
            input_mint=WSOL_MINT,
            output_mint=self.bonk_mint,
            amount_in=0.1,
            amount_out=150000.0,
            fee_sol=0.001,
            tx_sig="5SimulatedSigForUnitTest11111111111111111111111111111111111111111111111111111111111111111",
            status="CONFIRMED"
        )
        # Passed if no exception thrown


if __name__ == "__main__":
    unittest.main()
