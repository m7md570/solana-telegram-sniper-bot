# -*- coding: utf-8 -*-
"""
Solana Telegram Sniper & Trading Bot — Comprehensive Test Suite
Validates wallet encryption, RugCheck audits, Jupiter V6 routing,
and platform fee attribution on-chain.
"""

import sys
import time
import os
import sys
import time
import tempfile
import unittest
import base64
from solders.keypair import Keypair

from config import (
    DEVELOPER_WALLET,
    PLATFORM_FEE_BPS,
    WSOL_MINT,
    USDC_MINT
)
import wallet_manager
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

MOCK_TEST_BOT_TOKEN = "1111111111:AAFakeBotTokenForUnitTestingPurposes123"

# Completely isolate test execution database from live production database
TEST_DB_PATH = os.path.join(tempfile.gettempdir(), "test_sniper_bot.sqlite")
if os.path.exists(TEST_DB_PATH):
    try:
        os.remove(TEST_DB_PATH)
    except Exception:
        pass
wallet_manager.DB_PATH = TEST_DB_PATH


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
        
        # Test formatting card (both English and Arabic)
        card_en = format_token_card(scan, lang="en")
        self.assertIn("bonk", card_en.lower())
        self.assertIn("Current Price", card_en)

        card_ar = format_token_card(scan, lang="ar")
        self.assertIn("السعر الحالي", card_ar)

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

    def test_07_extract_token_mint_urls(self):
        """Test extracting token CA from various platform URLs."""
        from rugcheck_scanner import extract_token_mint
        raw_ca = "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"
        url1 = f"https://dexscreener.com/solana/{raw_ca}"
        url2 = f"https://pump.fun/coin/{raw_ca}"
        url3 = f"Check this gem: {raw_ca} to the moon!"

        self.assertEqual(extract_token_mint(raw_ca), raw_ca)
        self.assertEqual(extract_token_mint(url1), raw_ca)
        self.assertEqual(extract_token_mint(url2), raw_ca)
        self.assertEqual(extract_token_mint(url3), raw_ca)

    def test_08_trending_engine(self):
        """Test trending Solana tokens fetcher and HTML formatting."""
        from trending_engine import get_trending_tokens, format_trending_list
        tokens = get_trending_tokens(limit=3)
        card_en = format_trending_list(tokens, lang="en")
        self.assertIn("Trending", card_en)
        card_ar = format_trending_list(tokens, lang="ar")
        self.assertIn("سولانا", card_ar)

    def test_09_referral_system(self):
        """Test referral attribution and statistics."""
        from wallet_manager import record_referral, get_referral_stats, get_or_create_wallet
        rand_suffix = int(time.time() * 1000) % 1000000
        user_a = 770000 + rand_suffix
        user_b = 880000 + rand_suffix
        get_or_create_wallet(user_a, f"UserA_{rand_suffix}")
        get_or_create_wallet(user_b, f"UserB_{rand_suffix}")

        self.assertTrue(record_referral(user_b, user_a), "User B should be referred by User A")
        stats = get_referral_stats(user_a)
        self.assertGreaterEqual(stats["total_referrals"], 1, "User A must have at least 1 referral")

    def test_10_autobuy_settings(self):
        """Test toggling auto-buy mode and setting buy amount."""
        from wallet_manager import get_auto_buy_settings, toggle_auto_buy, set_auto_buy_amount
        set_auto_buy_amount(self.test_user_id, 0.25)
        new_state = toggle_auto_buy(self.test_user_id)
        is_enabled, amt = get_auto_buy_settings(self.test_user_id)
        self.assertEqual(amt, 0.25)
        self.assertEqual(is_enabled, new_state)

    def test_11_i18n_bilingual_engine(self):
        """Test dual language (English & Arabic) localization engine."""
        from i18n import t
        from wallet_manager import get_user_language, set_user_language
        from trending_engine import format_trending_list
        from rugcheck_scanner import format_token_card

        # Check English translations
        en_title = t("welcome_title", "en")
        self.assertIn("Welcome", en_title)

        # Check Arabic translations
        ar_title = t("welcome_title", "ar")
        self.assertIn("مرحباً", ar_title)

        # Check language persistence
        set_user_language(self.test_user_id, "ar")
        self.assertEqual(get_user_language(self.test_user_id), "ar")
        set_user_language(self.test_user_id, "en")
        self.assertEqual(get_user_language(self.test_user_id), "en")

        # Check English card formatting
        dummy_scan = {
            "mint": "So11111111111111111111111111111111111111112",
            "symbol": "SOL",
            "name": "Wrapped SOL",
            "price_usd": 150.0,
            "mcap": 70000000000.0,
            "liquidity_usd": 50000000.0,
            "price_change_24h": 5.2,
            "rug_score": 0,
            "status": "SAFE"
        }
        en_card = format_token_card(dummy_scan, lang="en")
        self.assertIn("Token Card", en_card)
        self.assertIn("Current Price", en_card)

    def test_12_search_solana_token(self):
        """Test DexScreener token search by ticker or name."""
        from rugcheck_scanner import search_solana_token
        result = search_solana_token("bonk")
        self.assertIsNotNone(result, "Search for 'bonk' should return a token")
        self.assertTrue(len(result["mint"]) >= 32, "Mint address must be valid Base58")
        self.assertEqual(result["symbol"].upper(), "BONK")
        self.assertGreater(result["liquidity_usd"], 50000)

    def test_13_bilingual_errors_and_routing(self):
        """Test that localized error strings correctly return English vs Arabic."""
        from wallet_manager import withdraw_sol
        from jupiter_engine import execute_sell_swap

        # Test withdraw error in English
        ok_en, err_en = withdraw_sol(self.test_user_id, "invalid_address", 0.1, lang="en")
        self.assertFalse(ok_en)
        self.assertIn("Invalid Solana", err_en)

        # Test withdraw error in Arabic
        ok_ar, err_ar = withdraw_sol(self.test_user_id, "invalid_address", 0.1, lang="ar")
        self.assertFalse(ok_ar)
        self.assertIn("غير صالح", err_ar)

        # Test sell swap error in English
        ok_sell_en, err_sell_en, _ = execute_sell_swap(self.test_user_id, self.bonk_mint, 50, lang="en")
        self.assertFalse(ok_sell_en)
        self.assertIn("No token balance", err_sell_en)

        # Test sell swap error in Arabic
        ok_sell_ar, err_sell_ar, _ = execute_sell_swap(self.test_user_id, self.bonk_mint, 50, lang="ar")
        self.assertFalse(ok_sell_ar)
        self.assertIn("لا تملك رصيداً", err_sell_ar)

    def test_14_watchlist_crud(self):
        """Test watchlist adding, retrieval, and removal."""
        from wallet_manager import add_to_watchlist, get_user_watchlist, remove_from_watchlist
        test_uid = 99988877
        test_mint = "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"
        test_sym = "BONK"

        # Clean slate
        remove_from_watchlist(test_uid, test_mint)

        # Add to watchlist
        self.assertTrue(add_to_watchlist(test_uid, test_mint, test_sym))
        wl = get_user_watchlist(test_uid)
        self.assertEqual(len(wl), 1)
        self.assertEqual(wl[0]["mint"], test_mint)
        self.assertEqual(wl[0]["symbol"], "BONK")

        # Duplicate should be ignored safely
        add_to_watchlist(test_uid, test_mint, test_sym)
        self.assertEqual(len(get_user_watchlist(test_uid)), 1)

        # Remove from watchlist
        self.assertTrue(remove_from_watchlist(test_uid, test_mint))
        self.assertEqual(len(get_user_watchlist(test_uid)), 0)

    def test_15_priority_fee_management(self):
        """Test user priority fee updates and tier persistence."""
        from wallet_manager import update_user_priority_fee, get_user_settings
        test_uid = 77112233
        get_or_create_wallet(test_uid, "GasTester")

        update_user_priority_fee(test_uid, 250_000)
        s = get_user_settings(test_uid)
        self.assertEqual(s["priority_fee"], 250_000, "Priority fee must update to 250,000 lamports")

        update_user_priority_fee(test_uid, 1_000_000)
        s2 = get_user_settings(test_uid)
        self.assertEqual(s2["priority_fee"], 1_000_000, "Priority fee must update to 1,000,000 lamports")

    def test_16_optimal_slippage_and_mev_protection(self):
        """Test dynamic slippage calculation and MEV sandwich protection."""
        from jupiter_engine import calculate_optimal_slippage
        from config import MAX_SLIPPAGE_BPS

        # Low price impact: should use base slippage
        slip_low = calculate_optimal_slippage(price_impact_pct=0.1, base_slippage_bps=100)
        self.assertEqual(slip_low, 100)

        # Moderate price impact: should scale with buffer
        slip_mod = calculate_optimal_slippage(price_impact_pct=1.5, base_slippage_bps=100)
        self.assertEqual(slip_mod, 200)  # 150 + 50

        # Very high price impact: must be capped at MAX_SLIPPAGE_BPS (1500)
        slip_high = calculate_optimal_slippage(price_impact_pct=25.0, base_slippage_bps=100)
        self.assertEqual(slip_high, MAX_SLIPPAGE_BPS)

    def test_17_jupiter_swap_with_fee_account(self):
        """Test that swap transaction builder attaches developer feeAccount."""
        from jupiter_engine import get_jupiter_quote, build_and_sign_swap_tx
        from config import DEVELOPER_WALLET

        quote = get_jupiter_quote(WSOL_MINT, USDC_MINT, 50_000_000, slippage_bps=100, with_fee=True)
        self.assertIsNotNone(quote)

        kp = get_user_keypair(self.test_user_id)
        tx_bytes = build_and_sign_swap_tx(quote, kp, priority_fee_lamports=50_000)
        self.assertIsNotNone(tx_bytes, "Signed transaction with feeAccount must be built")
        self.assertGreater(len(tx_bytes), 300)

    def test_18_sell_and_gas_i18n(self):
        """Test bilingual localization for sell and priority gas settings."""
        from i18n import t

        # English
        help_en = t("sell_syntax_help", "en")
        self.assertIn("/sell", help_en)
        gas_title_en = t("gas_title", "en")
        self.assertIn("Priority Gas", gas_title_en)

        # Arabic
        help_ar = t("sell_syntax_help", "ar")
        self.assertIn("/sell", help_ar)
        gas_title_ar = t("gas_title", "ar")
        self.assertIn("الغاز", gas_title_ar)

    def test_19_viral_share_keyboard(self):
        """Test token card keyboard generation and viral referral link construction."""
        from telegram_bot import get_token_card_keyboard
        test_uid = 99887766
        kb_en = get_token_card_keyboard(self.bonk_mint, user_lang="en", user_id=test_uid, symbol="BONK")
        self.assertIsNotNone(kb_en)

        # Verify share button URL contains referral parameter
        buttons = [btn for row in kb_en.inline_keyboard for btn in row]
        share_btn = next((b for b in buttons if "Share" in b.text), None)
        self.assertIsNotNone(share_btn, "Share button must be present in card keyboard")
        self.assertIn(f"ref_{test_uid}", share_btn.url, "Share link must encode referral parameter")

        # Verify Arabic version
        kb_ar = get_token_card_keyboard(self.bonk_mint, user_lang="ar", user_id=test_uid, symbol="BONK")
        buttons_ar = [btn for row in kb_ar.inline_keyboard for btn in row]
        share_btn_ar = next((b for b in buttons_ar if "مشاركة" in b.text), None)
        self.assertIsNotNone(share_btn_ar)
        self.assertIn(f"ref_{test_uid}", share_btn_ar.url)

    def test_20_trade_history_and_session_pooling(self):
        """Test trade history stats retrieval, i18n keys, and HTTP session pooling."""
        from jupiter_engine import _SESSION, record_trade_db
        from wallet_manager import get_user_trade_stats
        from i18n import t

        # Verify persistent session
        self.assertIsNotNone(_SESSION)
        self.assertIn("User-Agent", _SESSION.headers)

        # Record dummy trade for test user
        record_trade_db(
            user_id=self.test_user_id,
            input_mint=WSOL_MINT,
            output_mint=self.bonk_mint,
            amount_in=0.05,
            amount_out=1500000.0,
            fee_sol=0.0005,
            tx_sig="5UfvXzTestSignatureTradeHistory11111111111111111111",
            status="CONFIRMED"
        )

        stats = get_user_trade_stats(self.test_user_id)
        self.assertGreaterEqual(stats["total_trades"], 1)
        self.assertGreater(len(stats["recent_trades"]), 0)
        recent_trade = stats["recent_trades"][0]
        self.assertEqual(recent_trade["input_mint"], WSOL_MINT)
        self.assertEqual(recent_trade["output_mint"], self.bonk_mint)

        # Verify i18n keys
        title_en = t("trades_history_title", "en")
        title_ar = t("trades_history_title", "ar")
        self.assertIn("Trade History", title_en)
        self.assertIn("سجل الصفقات", title_ar)

    def test_21_top_gainers_and_surge_radar(self):
        """Test top gainers calculation, ranking, format card, and i18n keys."""
        from trending_engine import get_top_gainers, format_gainers_list
        from i18n import t

        # Fetch gainers
        gainers = get_top_gainers(limit=3)
        self.assertIsInstance(gainers, list)

        # Test format card
        mock_gainers = [
            {
                "mint": self.bonk_mint,
                "symbol": "BONK",
                "name": "Bonk",
                "price_usd": 0.000025,
                "change_1h": 12.5,
                "change_24h": 45.2,
                "volume_24h": 5000000.0,
                "liquidity": 1200000.0,
                "fdv": 1500000000.0
            }
        ]
        card_en = format_gainers_list(mock_gainers, lang="en")
        card_ar = format_gainers_list(mock_gainers, lang="ar")
        self.assertIn("Surge Radar", card_en)
        self.assertIn("رادار العملات الأكثر صعوداً", card_ar)
        self.assertIn("BONK", card_en)
        self.assertIn("BONK", card_ar)

        # Verify i18n keys
        self.assertIn("Surge", t("btn_surge", "en"))
        self.assertIn("Surge", t("btn_surge", "ar"))

    def test_22_tp_sl_settings_and_commands(self):
        """Test Take-Profit and Stop-Loss settings persistence, card formatting, and i18n."""
        from wallet_manager import update_user_tp, update_user_sl, get_user_settings
        from telegram_bot import build_settings_card
        from i18n import t

        # Update and check persistence
        update_user_tp(self.test_user_id, 75)
        update_user_sl(self.test_user_id, 30)

        settings = get_user_settings(self.test_user_id)
        self.assertEqual(settings["default_tp_pct"], 75)
        self.assertEqual(settings["default_sl_pct"], 30)

        # Test settings card English & Arabic
        text_en, kb_en = build_settings_card(self.test_user_id, user_lang="en")
        self.assertIn("+75%", text_en)
        self.assertIn("-30%", text_en)
        self.assertIn("Take-Profit", text_en)
        self.assertIn("Stop-Loss", text_en)

        text_ar, kb_ar = build_settings_card(self.test_user_id, user_lang="ar")
        self.assertIn("+75%", text_ar)
        self.assertIn("-30%", text_ar)
        self.assertIn("جني الأرباح", text_ar)
        self.assertIn("وقف الخسارة", text_ar)

        # Verify buttons exist in keyboard
        buttons = [btn for row in kb_en.inline_keyboard for btn in row]
        tp_btn = next((b for b in buttons if b.callback_data == "tp_50"), None)
        sl_btn = next((b for b in buttons if b.callback_data == "sl_25"), None)
        self.assertIsNotNone(tp_btn, "TP button must be present in settings keyboard")
        self.assertIsNotNone(sl_btn, "SL button must be present in settings keyboard")

        # Verify i18n updates
        self.assertIn("+50%", t("tp_updated", "en", pct=50))
        self.assertIn("+50%", t("tp_updated", "ar", pct=50))
        self.assertIn("-25%", t("sl_updated", "en", pct=25))
        self.assertIn("-25%", t("sl_updated", "ar", pct=25))

    def test_23_batch_prices_and_volatility_alerts(self):
        """Test DexScreener multi-token batch price querying and watchlist price tracking."""
        from trending_engine import get_batch_token_prices
        from wallet_manager import (
            add_to_watchlist,
            get_user_watchlist,
            get_all_active_watchlist_subscriptions,
            update_watchlist_price_and_alert,
            remove_from_watchlist
        )

        test_uid = 88991122
        mint1 = "So11111111111111111111111111111111111111112"
        mint2 = "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"

        # 1. Batch price fetch
        prices = get_batch_token_prices([mint1, mint2])
        self.assertIn(mint1, prices)
        self.assertGreater(prices[mint1]["price_usd"], 0.0)

        # 2. Add with price
        remove_from_watchlist(test_uid, mint1)
        add_to_watchlist(test_uid, mint1, "SOL", current_price=150.0)
        wl = get_user_watchlist(test_uid)
        self.assertEqual(len(wl), 1)
        self.assertEqual(wl[0]["initial_price"], 150.0)

        # 3. Active subscriptions
        subs = get_all_active_watchlist_subscriptions()
        user_subs = [s for s in subs if s["user_id"] == test_uid]
        self.assertEqual(len(user_subs), 1)
        self.assertEqual(user_subs[0]["token_mint"], mint1)

        # 4. Update price & alert
        update_watchlist_price_and_alert(test_uid, mint1, 175.0, record_alert=True)
        wl_updated = get_user_watchlist(test_uid)
        self.assertEqual(wl_updated[0]["last_price"], 175.0)

        # Cleanup
        remove_from_watchlist(test_uid, mint1)

    def test_24_price_alerts_settings_and_i18n(self):
        """Test price alert toggling, settings card integration, and bilingual localization."""
        from wallet_manager import (
            toggle_price_alerts,
            get_price_alerts_status,
            set_price_alerts_status
        )
        from telegram_bot import build_settings_card
        from i18n import t

        test_uid = 88991133
        # Explicit enable & disable
        set_price_alerts_status(test_uid, True)
        self.assertTrue(get_price_alerts_status(test_uid))

        set_price_alerts_status(test_uid, False)
        self.assertFalse(get_price_alerts_status(test_uid))

        # Toggle back to True
        new_state = toggle_price_alerts(test_uid)
        self.assertTrue(new_state)
        self.assertTrue(get_price_alerts_status(test_uid))

        # Check settings card formatting
        text_en, kb_en = build_settings_card(test_uid, user_lang="en")
        self.assertIn("Price Movement Alerts:", text_en)
        self.assertIn("ENABLED", text_en)

        buttons_en = [btn for row in kb_en.inline_keyboard for btn in row]
        alert_btn = next((b for b in buttons_en if b.callback_data == "toggle_alerts"), None)
        self.assertIsNotNone(alert_btn)
        self.assertIn("Alerts: ON", alert_btn.text)

        text_ar, kb_ar = build_settings_card(test_uid, user_lang="ar")
        self.assertIn("تنبيهات تقلبات الأسعار:", text_ar)
        self.assertIn("مفعلة", text_ar)

        # i18n keys check
        self.assertIn("ALERT", t("price_alert_title", "en"))
        self.assertIn("تنبيه", t("price_alert_title", "ar"))
        self.assertIn("ENABLED", t("alerts_toggled", "en", status="ENABLED"))
        self.assertIn("مفعلة", t("alerts_toggled", "ar", status="مفعلة"))

    def test_25_render_positions_portfolio(self):
        """Test interactive positions portfolio card generation, valuations, and 1-click Sell buttons."""
        import asyncio
        from unittest.mock import AsyncMock, patch
        from telegram_bot import render_positions

        test_uid = 99881122
        get_or_create_wallet(test_uid, "PortfolioTester")

        mock_target = AsyncMock()

        # 1. Test empty portfolio
        asyncio.run(render_positions(mock_target, test_uid, user_lang="en", is_edit=False))
        self.assertTrue(mock_target.reply_text.called)
        empty_msg = mock_target.reply_text.call_args[0][0]
        self.assertIn("Open Token Positions", empty_msg)
        self.assertIn("No open token holdings found", empty_msg)

        # 2. Test populated portfolio with mock SPL holdings
        mock_target.reset_mock()
        mock_tokens = [
            {"mint": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263", "amount": 1000000.0, "decimals": 5}
        ]
        with patch("telegram_bot.get_token_accounts", return_value=mock_tokens):
            asyncio.run(render_positions(mock_target, test_uid, user_lang="en", is_edit=False))
            self.assertTrue(mock_target.reply_text.called)
            pop_msg = mock_target.reply_text.call_args[0][0]
            reply_markup = mock_target.reply_text.call_args[1]["reply_markup"]

            self.assertIn("1,000,000.00", pop_msg)
            self.assertIn("Total Estimated Value", pop_msg)

            # Verify 1-click sell buttons in keyboard
            all_buttons = [btn for row in reply_markup.inline_keyboard for btn in row]
            sell_50 = next((b for b in all_buttons if b.callback_data == "sell_DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263_50"), None)
            sell_100 = next((b for b in all_buttons if b.callback_data == "sell_DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263_100"), None)
            inspect_btn = next((b for b in all_buttons if b.callback_data == "inspect_DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"), None)

            self.assertIsNotNone(sell_50, "Sell 50% button must be generated")
            self.assertIsNotNone(sell_100, "Sell 100% button must be generated")
            self.assertIsNotNone(inspect_btn, "Inspect button must be generated")

    def test_26_network_ping_and_audit_commands(self):
        """Test Solana RPC latency benchmark, ping card formatting, and audit command."""
        import asyncio
        from unittest.mock import AsyncMock
        from telegram_bot import benchmark_network_latency, render_network_ping
        from i18n import t

        # 1. Benchmark latency measurement
        bench = benchmark_network_latency()
        self.assertIn("rpc_ms", bench)
        self.assertIn("jup_ms", bench)
        self.assertGreater(bench["rpc_ms"], 0.0)

        # 2. Render network ping card
        mock_target = AsyncMock()
        asyncio.run(render_network_ping(mock_target, self.test_user_id, user_lang="en", is_edit=False))
        self.assertTrue(mock_target.reply_text.called)
        msg_en = mock_target.reply_text.call_args[0][0]
        self.assertIn("Latency Benchmark", msg_en)
        self.assertIn("Primary RPC", msg_en)

        # 3. Test Arabic ping card
        mock_target.reset_mock()
        asyncio.run(render_network_ping(mock_target, self.test_user_id, user_lang="ar", is_edit=False))
        self.assertTrue(mock_target.reply_text.called)
        msg_ar = mock_target.reply_text.call_args[0][0]
        self.assertIn("رادار سرعة واستجابة", msg_ar)

        # 4. Check i18n keys
        self.assertIn("Latency", t("btn_ping", "en"))
        self.assertIn("استجابة", t("btn_ping", "ar"))

    def test_27_panic_sell_all_engine(self):
        """Test emergency panic sell-all confirmation, liquidation execution, and bilingual i18n."""
        import asyncio
        from unittest.mock import AsyncMock, patch
        from telegram_bot import render_panic_confirm, execute_panic_sell_all, render_positions
        from i18n import t

        test_uid = 99881133
        get_or_create_wallet(test_uid, "PanicTester")
        mock_target = AsyncMock()

        # 1. Test render_panic_confirm with NO positions
        asyncio.run(render_panic_confirm(mock_target, test_uid, user_lang="en", is_edit=False))
        self.assertTrue(mock_target.reply_text.called)
        msg_empty = mock_target.reply_text.call_args[0][0]
        self.assertIn("No open token holdings found", msg_empty)

        # 2. Test render_panic_confirm WITH positions
        mock_target.reset_mock()
        mock_tokens = [
            {"mint": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263", "amount": 1000000.0, "decimals": 5},
            {"mint": "7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU", "amount": 500.0, "decimals": 6}
        ]
        with patch("telegram_bot.get_token_accounts", return_value=mock_tokens):
            asyncio.run(render_panic_confirm(mock_target, test_uid, user_lang="en", is_edit=False))
            self.assertTrue(mock_target.reply_text.called)
            confirm_msg = mock_target.reply_text.call_args[0][0]
            self.assertIn("EMERGENCY PANIC SELL-ALL", confirm_msg)
            self.assertIn("2 tokens", confirm_msg)

            # Check execute button present
            reply_markup = mock_target.reply_text.call_args[1]["reply_markup"]
            all_btns = [b for row in reply_markup.inline_keyboard for b in row]
            exec_btn = next((b for b in all_btns if b.callback_data == "btn_panic_execute"), None)
            self.assertIsNotNone(exec_btn, "btn_panic_execute must be present")

        # 3. Test execute_panic_sell_all execution
        mock_target.reset_mock()
        with patch("telegram_bot.get_token_accounts", return_value=mock_tokens), \
             patch("telegram_bot.execute_sell_swap", return_value=(True, "mock_panic_tx_sig", 0.05)):
            asyncio.run(execute_panic_sell_all(mock_target, test_uid, user_lang="en"))
            edited_mock = mock_target.edit_message_text if mock_target.edit_message_text.called else mock_target.edit_text
            self.assertTrue(edited_mock.called)
            final_call = edited_mock.call_args_list[-1]
            success_text = final_call[0][0]
            self.assertIn("EMERGENCY LIQUIDATION COMPLETED", success_text)
            self.assertIn("2/2 positions", success_text)
            self.assertIn("0.1000 SOL", success_text)

        # 4. Check render_positions has btn_panic_confirm button
        mock_target.reset_mock()
        with patch("telegram_bot.get_token_accounts", return_value=mock_tokens):
            asyncio.run(render_positions(mock_target, test_uid, user_lang="en", is_edit=False))
            self.assertTrue(mock_target.reply_text.called)
            pos_markup = mock_target.reply_text.call_args[1]["reply_markup"]
            all_pos_btns = [b for row in pos_markup.inline_keyboard for b in row]
            panic_btn = next((b for b in all_pos_btns if b.callback_data == "btn_panic_confirm"), None)
            self.assertIsNotNone(panic_btn, "btn_panic_confirm must be present in positions card")

        # 5. Check bilingual i18n keys
        self.assertIn("PANIC", t("panic_confirm_title", "en"))
        self.assertIn("طوارئ", t("panic_confirm_title", "ar"))
        self.assertIn("COMPLETED", t("panic_success_title", "en"))
        self.assertIn("بنجاح", t("panic_success_title", "ar"))

    def test_28_precision_slippage_and_autobuy_suite(self):
        """Test precision custom slippage, auto-buy commands, price card radar, and bilingual i18n."""
        import asyncio
        from unittest.mock import AsyncMock, MagicMock
        from telegram_bot import slippage_command, autobuy_command, price_command
        from wallet_manager import get_user_settings, get_auto_buy_settings
        from i18n import t

        test_uid = 99881144
        get_or_create_wallet(test_uid, "PrecisionTester")

        # 1. Test custom slippage command: 1.5% -> 150 bps
        mock_update = MagicMock()
        mock_update.effective_user.id = test_uid
        mock_update.message.reply_text = AsyncMock()
        mock_context = MagicMock()
        mock_context.args = ["1.5%"]
        asyncio.run(slippage_command(mock_update, mock_context))
        st = get_user_settings(test_uid)
        self.assertEqual(st["slippage_bps"], 150, "Slippage should be set to 150 bps")

        # 2. Test slippage invalid bounds
        mock_context.args = ["60"]  # > 50%
        mock_update.message.reply_text.reset_mock()
        asyncio.run(slippage_command(mock_update, mock_context))
        err_msg = mock_update.message.reply_text.call_args[0][0]
        self.assertIn("0.1%", err_msg)

        # 3. Test autobuy command: /autobuy 0.25
        mock_context.args = ["0.25"]
        asyncio.run(autobuy_command(mock_update, mock_context))
        en, amt = get_auto_buy_settings(test_uid)
        self.assertTrue(en)
        self.assertEqual(amt, 0.25)

        # 4. Test autobuy toggle to off: /autobuy off
        mock_context.args = ["off"]
        asyncio.run(autobuy_command(mock_update, mock_context))
        en, _ = get_auto_buy_settings(test_uid)
        self.assertFalse(en)

        # 5. Test price command
        mock_update.message.reply_text = AsyncMock()
        mock_status = AsyncMock()
        mock_update.message.reply_text.return_value = mock_status
        mock_context.args = ["BONK"]
        asyncio.run(price_command(mock_update, mock_context))
        self.assertTrue(mock_status.edit_text.called)
        card_text = mock_status.edit_text.call_args[0][0]
        self.assertIn("BONK", card_text.upper())
        self.assertIn("Price", card_text)

        # 6. Verify i18n keys in both languages
        self.assertIn("Slippage", t("slippage_syntax_help", "en"))
        self.assertIn("الانزلاق", t("slippage_syntax_help", "ar"))
        self.assertIn("Auto-Buy", t("autobuy_status_title", "en"))
        self.assertIn("التلقائي", t("autobuy_status_title", "ar"))
        self.assertIn("Price", t("price_card_title", "en"))
        self.assertIn("سعر", t("price_card_title", "ar"))

    def test_29_smart_withdrawal_and_wallet_holdings_preview(self):
        """Test smart withdrawal (all/max support, swapped args) and wallet holdings preview."""
        import asyncio
        from unittest.mock import AsyncMock, MagicMock, patch
        from telegram_bot import withdraw_command, wallet_command

        test_uid = 99881155
        pubkey, _ = get_or_create_wallet(test_uid, "WithdrawTester")

        mock_update = MagicMock()
        mock_update.effective_user.id = test_uid
        mock_update.message.reply_text = AsyncMock()
        mock_status = AsyncMock()
        mock_update.message.reply_text.return_value = mock_status
        mock_context = MagicMock()

        dest_addr = "7kz1mcQcaZhYzFUHBFHH6s5tGrDHc7gNhN5WAUyXyq5r"

        # 1. Test withdraw with 'all' keyword
        mock_context.args = [dest_addr, "all"]
        with patch("telegram_bot.get_sol_balance", return_value=0.5), \
             patch("telegram_bot.withdraw_sol", return_value=(True, "mock_withdraw_sig")):
            asyncio.run(withdraw_command(mock_update, mock_context))
            self.assertTrue(mock_status.edit_text.called)
            success_msg = mock_status.edit_text.call_args[0][0]
            self.assertIn("Successfully Withdrawn", success_msg)
            self.assertIn("0.4992 SOL", success_msg)

        # 2. Test withdraw with swapped arguments: /withdraw all <dest_addr>
        mock_status.reset_mock()
        mock_context.args = ["all", dest_addr]
        with patch("telegram_bot.get_sol_balance", return_value=1.0), \
             patch("telegram_bot.withdraw_sol", return_value=(True, "mock_withdraw_sig_2")):
            asyncio.run(withdraw_command(mock_update, mock_context))
            self.assertTrue(mock_status.edit_text.called)
            success_msg = mock_status.edit_text.call_args[0][0]
            self.assertIn("Successfully Withdrawn", success_msg)
            self.assertIn("0.9992 SOL", success_msg)

        # 3. Test wallet_command shows open token holdings preview and positions button
        mock_update.message.reply_text.reset_mock()
        mock_tokens = [
            {"mint": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263", "amount": 10000.0, "decimals": 5}
        ]
        with patch("telegram_bot.get_token_accounts", return_value=mock_tokens), \
             patch("telegram_bot.get_sol_balance", return_value=0.25):
            asyncio.run(wallet_command(mock_update, mock_context))
            self.assertTrue(mock_update.message.reply_text.called)
            w_text = mock_update.message.reply_text.call_args[0][0]
            w_kb = mock_update.message.reply_text.call_args[1]["reply_markup"]

            self.assertIn("1 positions", w_text)
            all_btns = [b for row in w_kb.inline_keyboard for b in row]
            pos_btn = next((b for b in all_btns if b.callback_data == "btn_positions"), None)
            self.assertIsNotNone(pos_btn, "btn_positions must be in wallet keyboard")

    def test_30_batch_watchlist_and_untrack_command(self):
        """Test batch watchlist price rendering, untrack/remove command, and DEX terminal URL parsing."""
        import asyncio
        from unittest.mock import AsyncMock, MagicMock, patch
        from telegram_bot import render_watchlist, untrack_command
        from rugcheck_scanner import extract_token_mint
        from wallet_manager import add_to_watchlist, get_user_watchlist

        test_uid = 99881166
        get_or_create_wallet(test_uid, "WatchlistTester")
        test_mint = "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"

        # 1. Test URL parsing for GMGN, BullX, Photon, and Raydium
        gmgn_url = f"https://gmgn.ai/sol/token/{test_mint}"
        bullx_url = f"https://bullx.io/terminal?chainId=1399811149&address={test_mint}"
        photon_url = f"https://photon-sol.tinyastro.io/en/r/@{test_mint}"
        raydium_url = f"https://raydium.io/swap/?inputMint=sol&outputMint={test_mint}"

        self.assertEqual(extract_token_mint(gmgn_url), test_mint)
        self.assertEqual(extract_token_mint(bullx_url), test_mint)
        self.assertEqual(extract_token_mint(photon_url), test_mint)
        self.assertEqual(extract_token_mint(raydium_url), test_mint)

        # 2. Add to watchlist and test render_watchlist with batch prices
        add_to_watchlist(test_uid, test_mint, "BONK", current_price=0.000025)
        mock_target = AsyncMock()

        mock_batch_prices = {
            test_mint: {
                "symbol": "BONK",
                "name": "Bonk",
                "price_usd": 0.000028,
                "change_24h": 12.5,
                "change_1h": 1.2,
                "liquidity": 5000000.0
            }
        }
        with patch("telegram_bot.get_batch_token_prices", return_value=mock_batch_prices):
            asyncio.run(render_watchlist(mock_target, test_uid, user_lang="en", is_edit=False))
            self.assertTrue(mock_target.reply_text.called)
            wl_text = mock_target.reply_text.call_args[0][0]
            self.assertIn("BONK", wl_text)
            self.assertIn("0.000028", wl_text)
            self.assertIn("+12.5%", wl_text)

        # 3. Test untrack_command
        mock_update = MagicMock()
        mock_update.effective_user.id = test_uid
        mock_update.message.reply_text = AsyncMock()
        mock_context = MagicMock()
        mock_context.args = ["BONK"]

        asyncio.run(untrack_command(mock_update, mock_context))
        self.assertTrue(mock_update.message.reply_text.called)
        reply = mock_update.message.reply_text.call_args[0][0]
        self.assertIn("Removed", reply)
        self.assertIn("BONK", reply)

        # Confirm removal from database
        items = get_user_watchlist(test_uid)
        self.assertEqual(len(items), 0)

    def test_31_smart_buy_and_sell_argument_resolution(self):
        """Test flexible argument orders and default amounts for /buy and /sell."""
        import asyncio
        from unittest.mock import AsyncMock, MagicMock, patch
        from telegram_bot import buy_command, sell_command

        test_uid = 99881177
        get_or_create_wallet(test_uid, "SmartTrader")
        test_mint = "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"

        mock_update = MagicMock()
        mock_update.effective_user.id = test_uid
        mock_update.message.reply_text = AsyncMock()
        mock_status = AsyncMock()
        mock_update.message.reply_text.return_value = mock_status
        mock_context = MagicMock()

        # 1. Test /sell 50 bonk (swapped args: percent first, token second)
        mock_context.args = ["50", "bonk"]
        with patch("telegram_bot.search_solana_token", return_value={"mint": test_mint, "symbol": "BONK"}), \
             patch("telegram_bot.execute_sell_swap", return_value=(True, "mock_sell_sig", 0.05)):
            asyncio.run(sell_command(mock_update, mock_context))
            self.assertTrue(mock_status.edit_text.called)
            sell_msg = mock_status.edit_text.call_args[0][0]
            self.assertIn("Sell Swap Executed", sell_msg)
            self.assertIn("0.0500 SOL", sell_msg)

        # 2. Test /sell all bonk (keyword 'all' with token)
        mock_status.reset_mock()
        mock_context.args = ["all", "bonk"]
        with patch("telegram_bot.search_solana_token", return_value={"mint": test_mint, "symbol": "BONK"}), \
             patch("telegram_bot.execute_sell_swap", return_value=(True, "mock_sell_all_sig", 0.12)):
            asyncio.run(sell_command(mock_update, mock_context))
            self.assertTrue(mock_status.edit_text.called)
            sell_all_msg = mock_status.edit_text.call_args[0][0]
            self.assertIn("Sell Swap Executed", sell_all_msg)
            self.assertIn("0.1200 SOL", sell_all_msg)

        # 3. Test /buy 0.05 bonk (amount first, token second)
        mock_status.reset_mock()
        mock_context.args = ["0.05", "bonk"]
        mock_quote = {"outAmount": "1000000000", "platformFee": {"amount": "500000"}}
        with patch("telegram_bot.search_solana_token", return_value={"mint": test_mint, "symbol": "BONK"}), \
             patch("telegram_bot.get_sol_balance", return_value=1.0), \
             patch("telegram_bot.execute_buy_swap", return_value=(True, "mock_buy_sig", 1000000000.0, 0.0005)):
            asyncio.run(buy_command(mock_update, mock_context))
            self.assertTrue(mock_status.edit_text.called)
            buy_msg = mock_status.edit_text.call_args[0][0]
            self.assertIn("Buy Swap Executed", buy_msg)
            self.assertIn("0.05 SOL", buy_msg)

    def test_32_custom_sell_and_cancel_command(self):
        """Test custom sell percentage prompt, handle_text_message execution, and /cancel command."""
        import asyncio
        from unittest.mock import AsyncMock, MagicMock, patch
        from telegram_bot import get_token_card_keyboard, callback_router, handle_text_message, cancel_command

        test_uid = 99881188
        get_or_create_wallet(test_uid, "CustomSeller")
        test_mint = "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"

        # 1. Test get_token_card_keyboard has custom_sell button
        kb = get_token_card_keyboard(test_mint, user_lang="en", user_id=test_uid, symbol="BONK")
        all_btns = [b for row in kb.inline_keyboard for b in row]
        custom_sell_btn = next((b for b in all_btns if b.callback_data == f"custom_sell_{test_mint}"), None)
        self.assertIsNotNone(custom_sell_btn, "Custom sell button must be present in token keyboard")

        # 2. Test callback_router triggers custom_sell prompt
        mock_query = MagicMock()
        mock_query.data = f"custom_sell_{test_mint}"
        mock_query.from_user.id = test_uid
        mock_query.answer = AsyncMock()
        mock_query.message.reply_text = AsyncMock()
        mock_context = MagicMock()
        mock_context.user_data = {}

        mock_update = MagicMock()
        mock_update.callback_query = mock_query

        with patch("telegram_bot.scan_token_security", return_value={"symbol": "BONK"}):
            asyncio.run(callback_router(mock_update, mock_context))
            self.assertEqual(mock_context.user_data.get("awaiting_custom_sell"), test_mint)
            self.assertTrue(mock_query.message.reply_text.called)
            prompt_msg = mock_query.message.reply_text.call_args[0][0]
            self.assertIn("percentage", prompt_msg.lower())

        # 3. Test handle_text_message executes custom sell (e.g. 75%)
        mock_msg = MagicMock()
        mock_msg.text = "75%"
        mock_status = AsyncMock()
        mock_msg.reply_text = AsyncMock(return_value=mock_status)

        mock_text_update = MagicMock()
        mock_text_update.effective_user.id = test_uid
        mock_text_update.message = mock_msg

        with patch("telegram_bot.execute_sell_swap", return_value=(True, "mock_custom_sell_sig", 0.075)):
            asyncio.run(handle_text_message(mock_text_update, mock_context))
            self.assertNotIn("awaiting_custom_sell", mock_context.user_data)
            self.assertTrue(mock_status.edit_text.called)
            succ_msg = mock_status.edit_text.call_args[0][0]
            self.assertIn("Custom Sell Swap Executed", succ_msg)
            self.assertIn("0.0750 SOL", succ_msg)

        # 4. Test cancel_command clears pending states
        mock_context.user_data = {"awaiting_custom_buy": test_mint}
        mock_cancel_update = MagicMock()
        mock_cancel_update.effective_user.id = test_uid
        mock_cancel_update.message.reply_text = AsyncMock()

        asyncio.run(cancel_command(mock_cancel_update, mock_context))
        self.assertNotIn("awaiting_custom_buy", mock_context.user_data)
        self.assertTrue(mock_cancel_update.message.reply_text.called)
        cancel_reply = mock_cancel_update.message.reply_text.call_args[0][0]
        self.assertIn("cancelled", cancel_reply.lower())

    def test_33_dex_venue_sol_price_and_momentum(self):
        """Test DEX venue (Raydium/Pump.fun), native SOL price, and 1h momentum card formatting."""
        from rugcheck_scanner import format_token_card

        mock_scan = {
            "mint": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",
            "symbol": "BONK",
            "name": "Bonk",
            "price_usd": 0.000028,
            "price_sol": 0.000000185,
            "dex": "Raydium",
            "mcap": 1800000000.0,
            "liquidity_usd": 15000000.0,
            "volume_24h": 45000000.0,
            "price_change_24h": 14.5,
            "price_change_1h": 2.3,
            "rug_score": 120,
            "status": "SAFE",
            "badge": "🟢 Safe",
            "risks": [],
            "mint_authority": False,
            "freeze_authority": False
        }

        # 1. Test English card contains DEX venue, SOL price, and 1h change
        card_en = format_token_card(mock_scan, lang="en")
        self.assertIn("DEX Venue", card_en)
        self.assertIn("Raydium", card_en)
        self.assertIn("0.000000 SOL", card_en)
        self.assertIn("+2.30% (1h)", card_en)
        self.assertIn("+14.50% (24h)", card_en)

        # 2. Test Arabic card contains corresponding localized labels
        card_ar = format_token_card(mock_scan, lang="ar")
        self.assertIn("المنصة المضيفة (DEX)", card_ar)
        self.assertIn("Raydium", card_ar)
        self.assertIn("0.000000 SOL", card_ar)
        self.assertIn("+2.30% (1h)", card_ar)
        self.assertIn("+14.50% (24h)", card_ar)

    def test_34_deposit_qr_code_generator(self):
        """Test in-memory Solana deposit QR code generation with solana:<pubkey> standard."""
        from wallet_manager import generate_deposit_qr_buffer
        pubkey = "7kz1mcQcaZhYzFUHBFHH6s5tGrDHc7gNhN5WAUyXyq5r"
        buf = generate_deposit_qr_buffer(pubkey)
        self.assertIsNotNone(buf)
        data = buf.getvalue()
        self.assertGreater(len(data), 300)
        # Check standard PNG magic bytes: \x89PNG\r\n\x1a\n
        self.assertTrue(data.startswith(b"\x89PNG\r\n\x1a\n"))

    def test_35_solana_network_gas_radar(self):
        """Test real-time Solana network priority fee and gas radar logic."""
        from jupiter_engine import get_network_gas_fees
        gas_data = get_network_gas_fees()
        self.assertIn("median_micro_lamports", gas_data)
        self.assertIn("p95_micro_lamports", gas_data)
        self.assertIn("congestion", gas_data)
        self.assertIn("recommended_normal", gas_data)
        self.assertIn("recommended_turbo", gas_data)
        self.assertIn("recommended_ultra", gas_data)
        self.assertGreaterEqual(gas_data["median_micro_lamports"], 0)
        self.assertGreaterEqual(gas_data["p95_micro_lamports"], 0)
        self.assertGreaterEqual(gas_data["recommended_ultra"], gas_data["recommended_turbo"])
        self.assertGreaterEqual(gas_data["recommended_turbo"], gas_data["recommended_normal"])

    def test_36_onboarding_tour_and_guide(self):
        """Test /tour and onboarding guide response structure and keyboard."""
        import asyncio
        from unittest.mock import AsyncMock, MagicMock
        from telegram_bot import tour_command

        mock_update = MagicMock()
        mock_user = MagicMock()
        mock_user.id = 99881122
        mock_update.effective_user = mock_user
        mock_update.message.reply_text = AsyncMock()

        mock_context = MagicMock()

        asyncio.run(tour_command(mock_update, mock_context))

        mock_update.message.reply_text.assert_called_once()
        text_arg = mock_update.message.reply_text.call_args[0][0]
        kb_arg = mock_update.message.reply_text.call_args[1].get("reply_markup")

        self.assertIn("Quick Tour", text_arg)
        self.assertIn("Step 1", text_arg)
        self.assertIn("Step 2", text_arg)
        self.assertIn("Step 3", text_arg)
        self.assertIsNotNone(kb_arg)

    def test_37_main_menu_keyboard_features(self):
        """Test main menu dashboard keyboard contains 1-tap QR deposit and tour buttons."""
        from telegram_bot import get_main_menu_keyboard
        kb_en = get_main_menu_keyboard(88812345, lang="en")
        all_callbacks = [btn.callback_data for row in kb_en.inline_keyboard for btn in row if btn.callback_data]
        self.assertIn("btn_tour", all_callbacks)
        self.assertIn("btn_show_qr", all_callbacks)
        self.assertIn("btn_gas_fees", all_callbacks)
        self.assertIn("btn_snipe_guide", all_callbacks)

        kb_ar = get_main_menu_keyboard(88812345, lang="ar")
        all_callbacks_ar = [btn.callback_data for row in kb_ar.inline_keyboard for btn in row if btn.callback_data]
        self.assertIn("btn_tour", all_callbacks_ar)
        self.assertIn("btn_show_qr", all_callbacks_ar)

    def test_38_command_aliases_and_balance_badges(self):
        """Test build_welcome_text balance status badges for funded and empty states."""
        from unittest.mock import MagicMock
        from telegram_bot import build_welcome_text

        mock_user = MagicMock()
        mock_user.username = "TestTrader"
        mock_user.first_name = "Test"

        # 1. Zero balance state (should have deposit guidance)
        card_empty = build_welcome_text(mock_user, "7kz1mcQcaZhYzFUHBFHH6s5tGrDHc7gNhN5WAUyXyq5r", 0.0, "2026-10-07 18:00:00", lang="en")
        self.assertIn("0.0000 SOL", card_empty)
        self.assertIn("Tap [📲 Deposit QR] below", card_empty)

        card_empty_ar = build_welcome_text(mock_user, "7kz1mcQcaZhYzFUHBFHH6s5tGrDHc7gNhN5WAUyXyq5r", 0.0, "2026-10-07 18:00:00", lang="ar")
        self.assertIn("0.0000 SOL", card_empty_ar)
        self.assertIn("اضغط [📲 رمز QR للإيداع]", card_empty_ar)

        # 2. Funded state (should have ready badge)
        card_funded = build_welcome_text(mock_user, "7kz1mcQcaZhYzFUHBFHH6s5tGrDHc7gNhN5WAUyXyq5r", 0.5, "2026-10-07 18:00:00", lang="en")
        self.assertIn("0.5000 SOL", card_funded)
        self.assertIn("Ready to snipe!", card_funded)

    def test_39_status_and_telemetry_commands(self):
        """Test /status and /fees command generation and menu keyboard links."""
        import asyncio
        from unittest.mock import AsyncMock, MagicMock
        from telegram_bot import (
            get_cluster_telemetry,
            status_command,
            fees_command,
            get_main_menu_keyboard,
            BOT_VERSION
        )

        # 1. Telemetry verification
        telem = get_cluster_telemetry()
        self.assertEqual(telem["bot_version"], BOT_VERSION)
        self.assertIn("Mainnet", telem["cluster"])
        self.assertEqual(telem["developer_wallet"], "7kz1mcQcaZhYzFUHBFHH6s5tGrDHc7gNhN5WAUyXyq5r")
        self.assertEqual(telem["fee_pct"], 1.0)

        # 2. Status command reply test
        mock_update = MagicMock()
        mock_user = MagicMock()
        mock_user.id = 88812345
        mock_update.effective_user = mock_user
        mock_update.message.reply_text = AsyncMock()
        mock_context = MagicMock()

        asyncio.run(status_command(mock_update, mock_context))
        mock_update.message.reply_text.assert_called_once()
        text_status = mock_update.message.reply_text.call_args[0][0]
        self.assertIn("Cluster Status", text_status)
        self.assertIn(BOT_VERSION, text_status)

        # 3. Fees command reply test
        mock_update.message.reply_text.reset_mock()
        asyncio.run(fees_command(mock_update, mock_context))
        mock_update.message.reply_text.assert_called_once()
        text_fees = mock_update.message.reply_text.call_args[0][0]
        self.assertIn("Fee Schedule", text_fees)
        self.assertIn("1.0%", text_fees)
        self.assertIn("25%", text_fees)

        # 4. Keyboard presence check
        kb = get_main_menu_keyboard(88812345, lang="en")
        callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row if btn.callback_data]
        self.assertIn("btn_status", callbacks)
        self.assertIn("btn_fee_info", callbacks)

    def test_40_polished_bounty_deliverables(self):
        """Test GibWork bounty deliverable synthesis formats raw CAs with professional context."""
        import sys
        sys.path.append(r"F:\قناص\06_وكيل_حُر\hurr_tools")
        import gibwork_executor

        # Task with raw CA in requirements
        task_rekees = {
            "title": "Follow, Quote Post & Join the Rekees ($RKS) Telegram",
            "requirements_snippet": "Quote post this post with the CA as your caption: 9ZrGHKCdX2Bf5GWiGb9wSGGdBTMoZQqdEyzChapwE2Cx"
        }
        tweet_rekees = gibwork_executor.synthesize_task_tweet(task_rekees)
        self.assertIn("9ZrGHKCdX2Bf5GWiGb9wSGGdBTMoZQqdEyzChapwE2Cx", tweet_rekees)
        self.assertIn("$RKS (Rekees)", tweet_rekees)
        self.assertIn("#Solana", tweet_rekees)
        # Verify it's never naked CA alone
        self.assertNotEqual(tweet_rekees.strip(), "9ZrGHKCdX2Bf5GWiGb9wSGGdBTMoZQqdEyzChapwE2Cx")

        # Test execute_best_task helper exists and is callable
        self.assertTrue(hasattr(gibwork_executor, "execute_best_task"))
        res = gibwork_executor.execute_best_task(dry_run=True)
        self.assertIn("success", res)

    def test_41_i18n_help_commands_completeness(self):
        """Test that /status, /fees, /tour, and /qr commands are documented in both English and Arabic help cards."""
        from i18n import t

        help_en = t("help_body", "en")
        self.assertIn("/status", help_en)
        self.assertIn("/fees", help_en)
        self.assertIn("/tour", help_en)
        self.assertIn("/qr", help_en)

        help_ar = t("help_body", "ar")
        self.assertIn("/status", help_ar)
        self.assertIn("/fees", help_ar)
        self.assertIn("/tour", help_ar)
        self.assertIn("/qr", help_ar)

    def test_42_connection_pooling_and_fast_rpc_queries(self):
        """Test wallet_manager _RPC_SESSION connection pool and get_sol_balance speed."""
        import wallet_manager
        self.assertTrue(hasattr(wallet_manager, "_RPC_SESSION"))
        self.assertIsNotNone(wallet_manager._RPC_SESSION)

        # Test balance query uses pooled session and returns valid float
        pubkey = "7kz1mcQcaZhYzFUHBFHH6s5tGrDHc7gNhN5WAUyXyq5r"
        bal = wallet_manager.get_sol_balance(pubkey)
        self.assertIsInstance(bal, float)
        self.assertGreaterEqual(bal, 0.0)

        # Test token accounts uses pooled session
        tokens = wallet_manager.get_token_accounts(pubkey)
        self.assertIsInstance(tokens, list)

    def test_43_batch_trending_tokens_engine(self):
        """Test trending_engine single-request batch API and list formatting."""
        from trending_engine import get_trending_tokens, format_trending_list

        tokens = get_trending_tokens(limit=3)
        self.assertIsInstance(tokens, list)
        if tokens:
            t0 = tokens[0]
            self.assertIn("mint", t0)
            self.assertIn("symbol", t0)
            self.assertIn("price_usd", t0)

            # Test English and Arabic formatted lists
            card_en = format_trending_list(tokens, lang="en")
            self.assertIn("Top Trending", card_en)
            self.assertIn(t0["symbol"], card_en)

            card_ar = format_trending_list(tokens, lang="ar")
            self.assertIn("أكثر عملات سولانا رواجاً", card_ar)
            self.assertIn(t0["symbol"], card_ar)

    def test_44_primary_pool_selection_and_token_card_audit(self):
        """Test rugcheck_scanner reliably sorts and selects the primary pool with highest liquidity."""
        from rugcheck_scanner import scan_token_security, format_token_card

        scan = scan_token_security(self.bonk_mint)
        self.assertTrue(scan["is_valid"])
        self.assertEqual(scan["mint"], self.bonk_mint)
        self.assertEqual(scan["symbol"].upper(), "BONK")
        self.assertGreater(scan["liquidity_usd"], 10_000.0)

        card_en = format_token_card(scan, lang="en")
        self.assertIn("Token Card", card_en)
        self.assertIn("BONK", card_en.upper())

        card_ar = format_token_card(scan, lang="ar")
        self.assertIn("بطاقة العملة", card_ar)
        self.assertIn("BONK", card_ar.upper())

    def test_45_broadcast_transaction_failover_resilience(self):
        """Test broadcast_transaction fails over to secondary RPCs if primary node errors."""
        from unittest.mock import patch, MagicMock
        from jupiter_engine import broadcast_transaction

        mock_tx = b"mock_serialized_signed_tx_bytes_12345"

        # Scenario 1: Primary fails with node error, secondary succeeds
        resp_err = MagicMock(status_code=200)
        resp_err.json.return_value = {"jsonrpc": "2.0", "error": {"code": -32002, "message": "Node desynced"}}
        resp_ok = MagicMock(status_code=200)
        resp_ok.json.return_value = {"jsonrpc": "2.0", "result": "5VERnSgToi6MockSignatureOk123456789"}

        with patch("jupiter_engine._SESSION.post", side_effect=[resp_err, resp_ok]):
            success, sig = broadcast_transaction(mock_tx)
            self.assertTrue(success)
            self.assertEqual(sig, "5VERnSgToi6MockSignatureOk123456789")

        # Scenario 2: All nodes fail
        with patch("jupiter_engine._SESSION.post", return_value=resp_err):
            success, err = broadcast_transaction(mock_tx)
            self.assertFalse(success)
            self.assertEqual(err, "Node desynced")

    def test_46_execute_buy_swap_pipeline(self):
        """Test jupiter_engine.execute_buy_swap validation, MEV routing, broadcast, and DB logging."""
        from unittest.mock import patch, MagicMock
        from jupiter_engine import execute_buy_swap
        from wallet_manager import get_or_create_wallet

        test_uid = 99881199
        pubkey, _ = get_or_create_wallet(test_uid, "BuyTester")

        # 1. Invalid amount <= 0
        ok, err, out, fee = execute_buy_swap(test_uid, self.bonk_mint, 0.0, lang="en")
        self.assertFalse(ok)
        self.assertIn("greater than zero", err)

        # 2. Insufficient balance
        with patch("wallet_manager.get_sol_balance", return_value=0.01):
            ok, err, out, fee = execute_buy_swap(test_uid, self.bonk_mint, 0.1, lang="en")
            self.assertFalse(ok)
            self.assertIn("Insufficient SOL balance", err)

        # 3. Successful buy swap execution
        mock_quote = {
            "outAmount": "500000000",
            "priceImpactPct": "0.1",
            "platformFee": {"amount": "1000000"}  # 0.001 SOL
        }
        with patch("wallet_manager.get_sol_balance", return_value=1.5), \
             patch("jupiter_engine.get_jupiter_quote", return_value=mock_quote), \
             patch("jupiter_engine.build_and_sign_swap_tx", return_value=b"mock_signed_buy_tx"), \
             patch("jupiter_engine.broadcast_transaction", return_value=(True, "5VERnSgBuySuccessTxSig12345")):
            ok, sig, out_amt, fee_sol = execute_buy_swap(test_uid, self.bonk_mint, 0.1, lang="en")
            self.assertTrue(ok)
            self.assertEqual(sig, "5VERnSgBuySuccessTxSig12345")
            self.assertEqual(out_amt, 500000000.0)
            self.assertAlmostEqual(fee_sol, 0.001, places=5)

        # 4. Broadcast failure propagation
        with patch("wallet_manager.get_sol_balance", return_value=1.5), \
             patch("jupiter_engine.get_jupiter_quote", return_value=mock_quote), \
             patch("jupiter_engine.build_and_sign_swap_tx", return_value=b"mock_signed_buy_tx"), \
             patch("jupiter_engine.broadcast_transaction", return_value=(False, "Simulation failed: slippage exceeded")):
            ok, err, out_amt, fee_sol = execute_buy_swap(test_uid, self.bonk_mint, 0.1, lang="en")
            self.assertFalse(ok)
            self.assertIn("Simulation failed", err)

    def test_47_export_command_and_batch_pricing_liquidity_fix(self):
        """Test export_command security flow, i18n guide sync, and batch pricing primary pool selection."""
        import asyncio
        from unittest.mock import AsyncMock, MagicMock, patch
        from telegram_bot import export_command
        from trending_engine import get_batch_token_prices
        from i18n import t

        test_uid = 99881200
        get_or_create_wallet(test_uid, "ExportTester")

        # 1. Test export_command in English
        mock_update = MagicMock()
        mock_update.effective_user.id = test_uid
        mock_update.message.reply_text = AsyncMock()
        mock_context = MagicMock()

        asyncio.run(export_command(mock_update, mock_context))
        self.assertTrue(mock_update.message.reply_text.called)
        msg_text = mock_update.message.reply_text.call_args[0][0]
        self.assertIn("Private Key", msg_text)
        self.assertIn("STRICT SECURITY WARNING", msg_text)

        # 2. Test i18n help guide includes /export in both languages
        help_en = t("help_body", "en")
        help_ar = t("help_body", "ar")
        self.assertIn("/export", help_en)
        self.assertIn("/export", help_ar)

        # 3. Test get_batch_token_prices selects highest-liquidity pair
        mock_pairs_response = MagicMock(status_code=200)
        mock_pairs_response.json.return_value = {
            "pairs": [
                {
                    "baseToken": {"address": self.bonk_mint, "symbol": "BONK", "name": "Bonk"},
                    "priceUsd": "0.000010",
                    "priceChange": {"h24": 5.0, "h1": 1.0},
                    "liquidity": {"usd": 500.0}  # Low/dead liquidity pair
                },
                {
                    "baseToken": {"address": self.bonk_mint, "symbol": "BONK", "name": "Bonk"},
                    "priceUsd": "0.000028",
                    "priceChange": {"h24": 12.0, "h1": 2.5},
                    "liquidity": {"usd": 15000000.0}  # True primary pool
                }
            ]
        }
        with patch("trending_engine._SESSION.get", return_value=mock_pairs_response):
            prices = get_batch_token_prices([self.bonk_mint])
            self.assertIn(self.bonk_mint, prices)
            self.assertEqual(prices[self.bonk_mint]["price_usd"], 0.000028)
            self.assertEqual(prices[self.bonk_mint]["liquidity"], 15000000.0)

    def test_48_exact_pnl_volume_and_fee_accounting(self):
        """Test exact SOL volume calculation on both buy and sell trades, fee tracking, and /pnl display."""
        import asyncio
        from unittest.mock import AsyncMock, MagicMock
        from jupiter_engine import record_trade_db
        from wallet_manager import get_user_trade_stats, get_or_create_wallet
        from telegram_bot import pnl_command

        test_uid = 99881211
        get_or_create_wallet(test_uid, "PnLTester")

        # Record a BUY trade: 0.20 SOL in -> 5,000,000 BONK out (fee: 0.002 SOL)
        record_trade_db(
            user_id=test_uid,
            input_mint=WSOL_MINT,
            output_mint=self.bonk_mint,
            amount_in=0.20,
            amount_out=5000000.0,
            fee_sol=0.002,
            tx_sig="5UfvXzTestSignatureBuyTrade11111111111111111111",
            status="CONFIRMED"
        )

        # Record a SELL trade: 5,000,000 BONK in -> 0.35 SOL out (fee: 0.0035 SOL)
        record_trade_db(
            user_id=test_uid,
            input_mint=self.bonk_mint,
            output_mint=WSOL_MINT,
            amount_in=5000000.0,
            amount_out=0.35,
            fee_sol=0.0035,
            tx_sig="5UfvXzTestSignatureSellTrade2222222222222222222",
            status="CONFIRMED"
        )

        stats = get_user_trade_stats(test_uid)
        self.assertEqual(stats["total_trades"], 2)
        # Volume must strictly be 0.20 + 0.35 = 0.55 SOL (NOT 5,000,000.20 SOL!)
        self.assertAlmostEqual(stats["total_volume_sol"], 0.55, places=4)
        # Total platform fees must be 0.002 + 0.0035 = 0.0055 SOL
        self.assertAlmostEqual(stats["total_fees_sol"], 0.0055, places=5)

        # Test pnl_command renders properly
        mock_update = MagicMock()
        mock_update.effective_user.id = test_uid
        mock_update.effective_user.username = "PnLKing"
        mock_update.message.reply_text = AsyncMock()
        mock_context = MagicMock()

        asyncio.run(pnl_command(mock_update, mock_context))
        self.assertTrue(mock_update.message.reply_text.called)
        card_text = mock_update.message.reply_text.call_args[0][0]
        self.assertIn("0.550 SOL", card_text)
        self.assertIn("0.00550 SOL", card_text)
        self.assertIn("2", card_text)

    def test_49_reset_command_and_viral_pnl_share(self):
        """Test reset_user_settings_to_defaults, /reset command, viral X intent share, and i18n sync."""
        import asyncio
        from unittest.mock import AsyncMock, MagicMock
        from wallet_manager import (
            get_or_create_wallet,
            get_user_settings,
            update_user_slippage,
            update_user_priority_fee,
            set_auto_buy_status,
            get_auto_buy_settings,
            reset_user_settings_to_defaults
        )
        from telegram_bot import reset_command, pnl_command
        from i18n import t

        test_uid = 99881222
        get_or_create_wallet(test_uid, "ResetTester")

        # 1. Modify settings away from defaults
        update_user_slippage(test_uid, 500)
        update_user_priority_fee(test_uid, 250_000)
        set_auto_buy_status(test_uid, True)

        st = get_user_settings(test_uid)
        self.assertEqual(st["slippage_bps"], 500)
        self.assertEqual(st["priority_fee"], 250_000)
        auto_en, _ = get_auto_buy_settings(test_uid)
        self.assertTrue(auto_en)

        # 2. Reset settings to factory defaults
        ok = reset_user_settings_to_defaults(test_uid)
        self.assertTrue(ok)
        st_reset = get_user_settings(test_uid)
        self.assertEqual(st_reset["slippage_bps"], 100)
        self.assertEqual(st_reset["priority_fee"], 50_000)
        auto_en_reset, auto_amt_reset = get_auto_buy_settings(test_uid)
        self.assertFalse(auto_en_reset)
        self.assertEqual(auto_amt_reset, 0.1)

        # 3. Test reset_command message output
        mock_update = MagicMock()
        mock_update.effective_user.id = test_uid
        mock_update.message.reply_text = AsyncMock()
        mock_context = MagicMock()

        asyncio.run(reset_command(mock_update, mock_context))
        self.assertTrue(mock_update.message.reply_text.called)
        reset_text = mock_update.message.reply_text.call_args[0][0]
        self.assertIn("Trading Settings Reset", reset_text)
        self.assertIn("1.0%", reset_text)

        # 4. Test viral PnL share URL in keyboard
        mock_update.message.reply_text.reset_mock()
        mock_context.bot = MagicMock()
        mock_context.bot.username = "PopcornSniperBot"

        asyncio.run(pnl_command(mock_update, mock_context))
        self.assertTrue(mock_update.message.reply_text.called)
        kb = mock_update.message.reply_text.call_args[1]["reply_markup"]
        all_btns = [b for row in kb.inline_keyboard for b in row]
        share_btn = next((b for b in all_btns if b.url and "twitter.com/intent/tweet" in b.url), None)
        self.assertIsNotNone(share_btn, "Share on X / Twitter button must be in PnL keyboard")
        self.assertIn("PopcornSniperBot", share_btn.url)

        # 5. Verify /reset in help guides
        self.assertIn("/reset", t("help_body", "en"))
        self.assertIn("/reset", t("help_body", "ar"))

    def test_50_aliases_and_dex_url_patterns(self):
        """Test URL parsing for Axiom, DexTools, Solview, RugCheck, Jupiter, and trending aliases."""
        from rugcheck_scanner import extract_token_mint
        from telegram_bot import build_application
        from telegram.ext import CommandHandler

        test_mint = "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"

        # 1. Test multi-DEX URL parsing
        axiom_url = f"https://axiom.trade/trade/{test_mint}"
        axiom_short = f"https://axiom.trade/t/{test_mint}"
        dextools_url = f"https://www.dextools.io/app/en/solana/pair-explorer/{test_mint}"
        solview_url = f"https://solview.app/token/{test_mint}"
        rugcheck_url = f"https://rugcheck.xyz/tokens/{test_mint}"
        jup_url = f"https://jup.ag/swap/SOL-{test_mint}"

        self.assertEqual(extract_token_mint(axiom_url), test_mint)
        self.assertEqual(extract_token_mint(axiom_short), test_mint)
        self.assertEqual(extract_token_mint(dextools_url), test_mint)
        self.assertEqual(extract_token_mint(solview_url), test_mint)
        self.assertEqual(extract_token_mint(rugcheck_url), test_mint)
        self.assertEqual(extract_token_mint(jup_url), test_mint)

        # 2. Test CommandHandler registration for aliases
        app = build_application(MOCK_TEST_BOT_TOKEN)
        command_handlers = [h for h in app.handlers[0] if isinstance(h, CommandHandler)]
        registered_commands = set()
        for h in command_handlers:
            registered_commands.update(h.commands)

        self.assertIn("trending", registered_commands)
        self.assertIn("tokens", registered_commands)
        self.assertIn("coins", registered_commands)
        self.assertIn("hot", registered_commands)
        self.assertIn("reset", registered_commands)
        self.assertIn("defaults", registered_commands)
        self.assertIn("export", registered_commands)
        self.assertIn("backup", registered_commands)

    def test_51_version_command_and_unverified_rugcheck_status(self):
        """Test /version command, /about alias, and honest UNVERIFIED RugCheck handling."""
        import asyncio
        from unittest.mock import AsyncMock, MagicMock
        from telegram_bot import version_command, build_application
        from telegram.ext import CommandHandler
        from rugcheck_scanner import format_token_card

        # 1. Test /version command reply
        mock_update = MagicMock()
        mock_update.effective_user.id = 77123999
        mock_update.message.reply_text = AsyncMock()
        mock_context = MagicMock()

        from config import BOT_VERSION
        asyncio.run(version_command(mock_update, mock_context))
        self.assertTrue(mock_update.message.reply_text.called)
        card_text = mock_update.message.reply_text.call_args[0][0]
        self.assertIn(BOT_VERSION, card_text)
        self.assertIn("Jupiter V6", card_text)
        self.assertIn("AES-256", card_text)
        self.assertIn("Token-2022", card_text)

        kb = mock_update.message.reply_text.call_args[1]["reply_markup"]
        all_btns = [b for row in kb.inline_keyboard for b in row]
        gh_btn = next((b for b in all_btns if b.url and "github.com" in b.url), None)
        self.assertIsNotNone(gh_btn, "GitHub releases button must be present in /version card")

        # 2. Test command registration
        app = build_application(MOCK_TEST_BOT_TOKEN)
        command_handlers = [h for h in app.handlers[0] if isinstance(h, CommandHandler)]
        registered_commands = set()
        for h in command_handlers:
            registered_commands.update(h.commands)

        self.assertIn("version", registered_commands)
        self.assertIn("about", registered_commands)

        # 3. Test format_token_card with UNVERIFIED status
        unverified_scan = {
            "mint": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            "symbol": "USDC",
            "name": "USD Coin",
            "price_usd": 1.0,
            "mcap": 1_000_000_000,
            "liquidity_usd": 50_000_000,
            "price_change_24h": 0.0,
            "status": "UNVERIFIED",
            "rug_score": 0,
            "risks": []
        }
        card_en = format_token_card(unverified_scan, lang="en")
        self.assertIn("Basic Audit (Unindexed on RugCheck)", card_en)
        card_ar = format_token_card(unverified_scan, lang="ar")
        self.assertIn("فحص أساسي (غير مفهرس في RugCheck)", card_ar)

    def test_52_token_2022_support_and_config_bot_version(self):
        """Test Token-2022 multi-program portfolio discovery and BOT_VERSION config single-source-of-truth."""
        from unittest.mock import patch, MagicMock
        from config import BOT_VERSION, TOKEN_PROGRAM_ID, TOKEN_2022_PROGRAM_ID
        from wallet_manager import get_token_accounts

        self.assertTrue(BOT_VERSION.startswith("v3."))
        self.assertEqual(TOKEN_PROGRAM_ID, "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA")
        self.assertEqual(TOKEN_2022_PROGRAM_ID, "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb")

        # Mock multi-program RPC response
        mock_resp_spl = MagicMock()
        mock_resp_spl.status_code = 200
        mock_resp_spl.json.return_value = {
            "result": {
                "value": [
                    {
                        "account": {
                            "data": {
                                "parsed": {
                                    "info": {
                                        "mint": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",
                                        "tokenAmount": {"uiAmount": 500000.0, "decimals": 5}
                                    }
                                }
                            }
                        }
                    }
                ]
            }
        }

        mock_resp_2022 = MagicMock()
        mock_resp_2022.status_code = 200
        mock_resp_2022.json.return_value = {
            "result": {
                "value": [
                    {
                        "account": {
                            "data": {
                                "parsed": {
                                    "info": {
                                        "mint": "2022TokenMintAddress11111111111111111111111111",
                                        "tokenAmount": {"uiAmount": 1250.75, "decimals": 6}
                                    }
                                }
                            }
                        }
                    }
                ]
            }
        }

        def mock_post(url, json=None, timeout=None):
            prog = json["params"][1]["programId"]
            if prog == TOKEN_PROGRAM_ID:
                return mock_resp_spl
            else:
                return mock_resp_2022

        with patch("wallet_manager._RPC_SESSION.post", side_effect=mock_post):
            tokens = get_token_accounts("7kz1mcQcaZhYzFUHBFHH6s5tGrDHc7gNhN5WAUyXyq5r")
            self.assertEqual(len(tokens), 2, "Must aggregate holdings across both SPL and Token-2022 programs")
            
            spl_tok = next((t for t in tokens if t["mint"] == "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"), None)
            self.assertIsNotNone(spl_tok)
            self.assertEqual(spl_tok["amount"], 500000.0)
            self.assertEqual(spl_tok["program"], TOKEN_PROGRAM_ID)

            tok_2022 = next((t for t in tokens if t["mint"] == "2022TokenMintAddress11111111111111111111111111"), None)
            self.assertIsNotNone(tok_2022)
            self.assertEqual(tok_2022["amount"], 1250.75)
            self.assertEqual(tok_2022["program"], TOKEN_2022_PROGRAM_ID)

    def test_53_viral_referral_push_notifications_and_x_share(self):
        """Test instant Telegram push notifications to referrers and viral 1-click X share buttons."""
        import asyncio
        from unittest.mock import AsyncMock, MagicMock
        from telegram_bot import start_command, referral_command
        from wallet_manager import get_or_create_wallet, set_user_language

        referrer_uid = 55443322
        new_user_uid = 99118822

        get_or_create_wallet(referrer_uid, "TopReferrer", initial_language="en")
        set_user_language(referrer_uid, "en")

        # 1. Test start_command with referral parameter triggering push notification
        mock_update = MagicMock()
        mock_new_user = MagicMock()
        mock_new_user.id = new_user_uid
        mock_new_user.username = "LuckyTrader"
        mock_new_user.language_code = "en"
        mock_update.effective_user = mock_new_user
        mock_update.message.reply_text = AsyncMock()

        mock_context = MagicMock()
        mock_context.args = [f"ref_{referrer_uid}"]
        mock_context.bot.send_message = AsyncMock()

        asyncio.run(start_command(mock_update, mock_context))

        # Referrer must have received instant Telegram alert
        mock_context.bot.send_message.assert_called_once()
        call_kwargs = mock_context.bot.send_message.call_args[1]
        self.assertEqual(call_kwargs["chat_id"], referrer_uid)
        self.assertIn("New Referral Joined", call_kwargs["text"])
        self.assertIn("@LuckyTrader", call_kwargs["text"])
        self.assertIn("25%", call_kwargs["text"])

        # 2. Test referral_command keyboard includes X / Twitter share intent
        mock_update_ref = MagicMock()
        mock_update_ref.effective_user.id = referrer_uid
        mock_update_ref.message.reply_text = AsyncMock()
        mock_context_ref = MagicMock()
        mock_context_ref.bot.username = "PopcornSniperBot"

        asyncio.run(referral_command(mock_update_ref, mock_context_ref))
        self.assertTrue(mock_update_ref.message.reply_text.called)
        kb = mock_update_ref.message.reply_text.call_args[1]["reply_markup"]
        all_btns = [b for row in kb.inline_keyboard for b in row]
        x_btn = next((b for b in all_btns if b.url and "twitter.com/intent/tweet" in b.url), None)
        self.assertIsNotNone(x_btn, "Share on X button must be present in /referral card")
        self.assertIn(f"ref_{referrer_uid}", x_btn.url)

    def test_54_smart_sell_portfolio_fallback_and_buy_deposit_keyboard(self):
        """Test smart /sell empty args renders open positions and /buy insufficient SOL attaches deposit QR keyboard."""
        import asyncio
        from unittest.mock import AsyncMock, MagicMock, patch
        from telegram_bot import sell_command, buy_command
        from wallet_manager import get_or_create_wallet, set_user_language

        test_uid = 77112233
        get_or_create_wallet(test_uid, "SmartTrader", initial_language="en")
        set_user_language(test_uid, "en")

        # 1. Test /sell without args when user holds tokens -> renders positions portfolio
        mock_update = MagicMock()
        mock_update.effective_user.id = test_uid
        mock_update.message.reply_text = AsyncMock()
        mock_context = MagicMock()
        mock_context.args = []

        fake_holdings = [{"mint": "TokenMintAddress123", "amount": 1000.0, "program": "Tokenkeg"}]
        with patch("telegram_bot.get_token_accounts", return_value=fake_holdings), \
             patch("telegram_bot.render_positions", new_callable=AsyncMock) as mock_render:
            asyncio.run(sell_command(mock_update, mock_context))
            mock_render.assert_called_once_with(mock_update.message, test_uid, "en", is_edit=False)

        # 2. Test /sell without args when user has 0 tokens -> shows syntax help
        with patch("telegram_bot.get_token_accounts", return_value=[]):
            asyncio.run(sell_command(mock_update, mock_context))
            self.assertTrue(mock_update.message.reply_text.called)
            syntax_text = mock_update.message.reply_text.call_args[0][0]
            self.assertIn("/sell [CONTRACT_OR_TICKER]", syntax_text)

        # 3. Test /buy with insufficient SOL balance attaches deposit keyboard
        mock_update_buy = MagicMock()
        mock_update_buy.effective_user.id = test_uid
        mock_update_buy.message.reply_text = AsyncMock()
        mock_context_buy = MagicMock()
        mock_context_buy.args = ["0.1", self.bonk_mint]

        with patch("telegram_bot.get_sol_balance", return_value=0.0):
            asyncio.run(buy_command(mock_update_buy, mock_context_buy))
            self.assertTrue(mock_update_buy.message.reply_text.called)
            kwargs = mock_update_buy.message.reply_text.call_args[1]
            self.assertIn("reply_markup", kwargs)
            kb = kwargs["reply_markup"]
            buttons = [b for row in kb.inline_keyboard for b in row]
            callback_datas = [b.callback_data for b in buttons]
            self.assertIn("btn_qr", callback_datas)
            self.assertIn("btn_refresh", callback_datas)

    def test_55_interactive_help_keyboard_and_version_documentation(self):
        """Test /help command attaches interactive quick-action navigation keyboard and /version is documented in i18n."""
        import asyncio
        from unittest.mock import AsyncMock, MagicMock
        from telegram_bot import help_command
        from wallet_manager import get_or_create_wallet, set_user_language
        from i18n import t

        test_uid = 33221199
        get_or_create_wallet(test_uid, "HelpTester", initial_language="en")
        set_user_language(test_uid, "en")

        mock_update = MagicMock()
        mock_update.effective_user.id = test_uid
        mock_update.message.reply_text = AsyncMock()
        mock_context = MagicMock()

        asyncio.run(help_command(mock_update, mock_context))
        self.assertTrue(mock_update.message.reply_text.called)
        kwargs = mock_update.message.reply_text.call_args[1]
        self.assertIn("reply_markup", kwargs)
        kb = kwargs["reply_markup"]
        all_buttons = [b for row in kb.inline_keyboard for b in row]
        callback_datas = [b.callback_data for b in all_buttons]
        self.assertIn("btn_refresh", callback_datas)
        self.assertIn("btn_wallet", callback_datas)
        self.assertIn("btn_trending", callback_datas)
        self.assertIn("btn_settings", callback_datas)
        self.assertIn("btn_referral", callback_datas)
        self.assertIn("btn_status", callback_datas)

        # Verify /version is documented in both English and Arabic help bodies
        help_en = t("help_body", "en")
        help_ar = t("help_body", "ar")
        self.assertIn("/version", help_en)
        self.assertIn("/version", help_ar)

    def test_56_trending_resilient_fallback_and_refresh_button(self):
        """Test get_trending_tokens resilient fallback to top memecoins when boosts fail, and trending inline refresh keyboard."""
        import asyncio
        from unittest.mock import AsyncMock, MagicMock, patch
        from trending_engine import get_trending_tokens, _TRENDING_CACHE, FALLBACK_TRENDING_MINTS
        from telegram_bot import trending_command
        from wallet_manager import get_or_create_wallet, set_user_language

        test_uid = 44556677
        get_or_create_wallet(test_uid, "TrendingTester", initial_language="en")
        set_user_language(test_uid, "en")

        # 1. Clear cache to force live fetch
        _TRENDING_CACHE["timestamp"] = 0
        _TRENDING_CACHE["data"] = []

        # Mock boosts endpoint returning 500 error, but batch tokens endpoint returning BONK pair
        mock_fail_resp = MagicMock(status_code=500)
        mock_batch_resp = MagicMock(status_code=200)
        mock_batch_resp.json.return_value = {
            "pairs": [
                {
                    "baseToken": {"address": self.bonk_mint, "symbol": "BONK", "name": "Bonk"},
                    "priceUsd": "0.000025",
                    "priceChange": {"h24": 15.0, "h1": 2.0},
                    "volume": {"h24": 50000000.0},
                    "liquidity": {"usd": 12000000.0},
                    "fdv": 1500000000.0
                }
            ]
        }

        def mock_get(url, timeout=None):
            if "token-boosts" in url:
                return mock_fail_resp
            return mock_batch_resp

        with patch("trending_engine._SESSION.get", side_effect=mock_get):
            tokens = get_trending_tokens(limit=1)
            self.assertEqual(len(tokens), 1)
            self.assertEqual(tokens[0]["mint"], self.bonk_mint)
            self.assertEqual(tokens[0]["symbol"], "BONK")

        # 2. Test trending_command attaches both 'btn_trending' and 'btn_refresh' buttons
        mock_update = MagicMock()
        mock_update.effective_user.id = test_uid
        mock_status_msg = MagicMock()
        mock_status_msg.edit_text = AsyncMock()
        mock_update.message.reply_text = AsyncMock(return_value=mock_status_msg)
        mock_context = MagicMock()

        with patch("telegram_bot.get_trending_tokens", return_value=tokens):
            asyncio.run(trending_command(mock_update, mock_context))
            self.assertTrue(mock_status_msg.edit_text.called)
            kwargs = mock_status_msg.edit_text.call_args[1]
            self.assertIn("reply_markup", kwargs)
            kb = kwargs["reply_markup"]
            all_buttons = [b for row in kb.inline_keyboard for b in row]
            callback_datas = [b.callback_data for b in all_buttons]
            self.assertIn("btn_trending", callback_datas)
            self.assertIn("btn_refresh", callback_datas)

    def test_57_empty_positions_conversion_keyboard(self):
        """Test render_positions with 0 tokens attaches high-conversion action keyboard (trending, deposit QR, refresh)."""
        import asyncio
        from unittest.mock import AsyncMock, MagicMock, patch
        from telegram_bot import render_positions
        from wallet_manager import get_or_create_wallet, set_user_language

        test_uid = 88776655
        get_or_create_wallet(test_uid, "EmptyHoldingsUser", initial_language="en")
        set_user_language(test_uid, "en")

        # 1. Test non-edit mode
        mock_msg = MagicMock()
        mock_msg.reply_text = AsyncMock()

        with patch("telegram_bot.get_token_accounts", return_value=[]):
            asyncio.run(render_positions(mock_msg, test_uid, "en", is_edit=False))
            self.assertTrue(mock_msg.reply_text.called)
            kwargs = mock_msg.reply_text.call_args[1]
            self.assertIn("reply_markup", kwargs)
            kb = kwargs["reply_markup"]
            buttons = [b for row in kb.inline_keyboard for b in row]
            callback_datas = [b.callback_data for b in buttons]
            self.assertIn("btn_trending", callback_datas)
            self.assertIn("btn_show_qr", callback_datas)
            self.assertIn("btn_positions", callback_datas)
            self.assertIn("btn_refresh", callback_datas)

        # 2. Test edit mode
        mock_query = MagicMock()
        with patch("telegram_bot.get_token_accounts", return_value=[]), \
             patch("telegram_bot.safe_edit_text", new_callable=AsyncMock) as mock_edit:
            asyncio.run(render_positions(mock_query, test_uid, "ar", is_edit=True))
            mock_edit.assert_called_once()
            call_kwargs = mock_edit.call_args[1]
            self.assertIn("reply_markup", call_kwargs)
            kb_ar = call_kwargs["reply_markup"]
            buttons_ar = [b for row in kb_ar.inline_keyboard for b in row]
            cb_ar = [b.callback_data for b in buttons_ar]
            self.assertIn("btn_trending", cb_ar)
            self.assertIn("btn_show_qr", cb_ar)
            self.assertIn("btn_positions", cb_ar)
            self.assertIn("btn_refresh", cb_ar)

    def test_58_wallet_navigation_harmonization_and_btn_pnl_share(self):
        """Test wallet_command attaches both refresh and back buttons, and btn_pnl callback includes viral X share button."""
        import asyncio
        from unittest.mock import AsyncMock, MagicMock, patch
        from telegram_bot import wallet_command
        from wallet_manager import get_or_create_wallet, set_user_language

        test_uid = 11223344
        get_or_create_wallet(test_uid, "HarmonizedTester", initial_language="en")
        set_user_language(test_uid, "en")

        # 1. Test wallet_command in English attaches both btn_wallet and btn_refresh
        mock_update = MagicMock()
        mock_update.effective_user.id = test_uid
        mock_update.message.reply_text = AsyncMock()
        mock_context = MagicMock()

        asyncio.run(wallet_command(mock_update, mock_context))
        self.assertTrue(mock_update.message.reply_text.called)
        kwargs = mock_update.message.reply_text.call_args[1]
        self.assertIn("reply_markup", kwargs)
        kb = kwargs["reply_markup"]
        all_buttons = [b for row in kb.inline_keyboard for b in row]
        callback_datas = [b.callback_data for b in all_buttons]
        self.assertIn("btn_wallet", callback_datas)
        self.assertIn("btn_refresh", callback_datas)

        # 2. Test wallet_command in Arabic attaches both btn_wallet and btn_refresh
        set_user_language(test_uid, "ar")
        mock_update_ar = MagicMock()
        mock_update_ar.effective_user.id = test_uid
        mock_update_ar.message.reply_text = AsyncMock()

        asyncio.run(wallet_command(mock_update_ar, mock_context))
        self.assertTrue(mock_update_ar.message.reply_text.called)
        kwargs_ar = mock_update_ar.message.reply_text.call_args[1]
        kb_ar = kwargs_ar["reply_markup"]
        all_buttons_ar = [b for row in kb_ar.inline_keyboard for b in row]
        cb_ar = [b.callback_data for b in all_buttons_ar]
        self.assertIn("btn_wallet", cb_ar)
        self.assertIn("btn_refresh", cb_ar)

    def test_59_search_direct_ca_and_not_found_keyboard(self):
        """Test search_command direct CA detection and not-found fallback action keyboard."""
        import asyncio
        from unittest.mock import AsyncMock, MagicMock, patch
        from telegram_bot import search_command
        from wallet_manager import get_or_create_wallet, set_user_language

        test_uid = 55667788
        get_or_create_wallet(test_uid, "SearchTester", initial_language="en")
        set_user_language(test_uid, "en")

        # 1. Test search with direct CA
        mock_update = MagicMock()
        mock_update.effective_user.id = test_uid
        mock_status = MagicMock()
        mock_status.edit_text = AsyncMock()
        mock_update.message.reply_text = AsyncMock(return_value=mock_status)
        mock_context = MagicMock()
        mock_context.args = [self.bonk_mint]

        fake_scan = {
            "mint": self.bonk_mint,
            "symbol": "BONK",
            "name": "Bonk",
            "price_usd": 0.000025,
            "price_change_24h": 10.0,
            "liquidity_usd": 15000000.0,
            "mcap": 1500000000.0,
            "status": "SAFE",
            "rug_score": 100,
            "risks": []
        }

        with patch("telegram_bot.scan_token_security", return_value=fake_scan):
            asyncio.run(search_command(mock_update, mock_context))
            self.assertTrue(mock_status.edit_text.called)
            card_call = mock_status.edit_text.call_args[0][0]
            self.assertIn("BONK", card_call)

        # 2. Test search when token not found attaches action keyboard
        mock_update_fail = MagicMock()
        mock_update_fail.effective_user.id = test_uid
        mock_status_fail = MagicMock()
        mock_status_fail.edit_text = AsyncMock()
        mock_update_fail.message.reply_text = AsyncMock(return_value=mock_status_fail)
        mock_context_fail = MagicMock()
        mock_context_fail.args = ["nonexistent_coin_xyz_123"]

        with patch("telegram_bot.search_solana_token", return_value=None):
            asyncio.run(search_command(mock_update_fail, mock_context_fail))
            self.assertTrue(mock_status_fail.edit_text.called)
            fail_kwargs = mock_status_fail.edit_text.call_args[1]
            self.assertIn("reply_markup", fail_kwargs)
            kb = fail_kwargs["reply_markup"]
            buttons = [b for row in kb.inline_keyboard for b in row]
            cb_data = [b.callback_data for b in buttons]
            self.assertIn("btn_trending", cb_data)
            self.assertIn("btn_refresh", cb_data)

    def test_60_watchlist_action_keyboard_and_empty_trending_link(self):
        """Test render_watchlist with 0 tokens attaches trending button, and track_command attaches action buttons."""
        import asyncio
        from unittest.mock import AsyncMock, MagicMock, patch
        from telegram_bot import render_watchlist, track_command
        from wallet_manager import get_or_create_wallet, set_user_language

        test_uid = 66778899
        get_or_create_wallet(test_uid, "WatchlistTester", initial_language="en")
        set_user_language(test_uid, "en")

        # 1. Test empty watchlist attaches btn_trending and btn_refresh
        mock_msg = MagicMock()
        mock_msg.reply_text = AsyncMock()

        with patch("telegram_bot.get_user_watchlist", return_value=[]):
            asyncio.run(render_watchlist(mock_msg, test_uid, "en", is_edit=False))
            self.assertTrue(mock_msg.reply_text.called)
            kwargs = mock_msg.reply_text.call_args[1]
            self.assertIn("reply_markup", kwargs)
            kb = kwargs["reply_markup"]
            buttons = [b for row in kb.inline_keyboard for b in row]
            cb_data = [b.callback_data for b in buttons]
            self.assertIn("btn_trending", cb_data)
            self.assertIn("btn_refresh", cb_data)

        # 2. Test track_command attaches btn_watchlist, inspect, and btn_refresh
        mock_update = MagicMock()
        mock_update.effective_user.id = test_uid
        mock_update.message.reply_text = AsyncMock()
        mock_context = MagicMock()
        mock_context.args = ["bonk"]

        fake_matched = {"mint": self.bonk_mint, "symbol": "BONK"}
        fake_scan = {"symbol": "BONK", "price_usd": 0.000025}

        with patch("telegram_bot.search_solana_token", return_value=fake_matched), \
             patch("telegram_bot.scan_token_security", return_value=fake_scan), \
             patch("telegram_bot.add_to_watchlist") as mock_add:
            asyncio.run(track_command(mock_update, mock_context))
            self.assertTrue(mock_update.message.reply_text.called)
            mock_add.assert_called_once_with(test_uid, self.bonk_mint, "BONK", current_price=0.000025)
            track_kwargs = mock_update.message.reply_text.call_args[1]
            self.assertIn("reply_markup", track_kwargs)
            track_kb = track_kwargs["reply_markup"]
            all_b = [b for row in track_kb.inline_keyboard for b in row]
            cb_list = [b.callback_data for b in all_b]
            self.assertIn("btn_watchlist", cb_list)
            self.assertIn(f"inspect_{self.bonk_mint}", cb_list)
            self.assertIn("btn_refresh", cb_list)

    def test_61_status_card_release_url_button(self):
        """Test render_status_card embeds direct GitHub release link button and bilingual labels."""
        import asyncio
        from unittest.mock import AsyncMock, MagicMock
        from telegram_bot import render_status_card
        from config import BOT_VERSION

        mock_target = MagicMock()
        mock_target.reply_text = AsyncMock()
        test_uid = 99881122

        # 1. Test English status card
        asyncio.run(render_status_card(mock_target, test_uid, user_lang="en", is_edit=False))
        self.assertTrue(mock_target.reply_text.called)
        call_args = mock_target.reply_text.call_args
        card_text_en = call_args[0][0]
        self.assertIn("Cluster Status & Bot Telemetry", card_text_en)
        self.assertIn(BOT_VERSION, card_text_en)

        kb_en = call_args[1]["reply_markup"]
        all_btns_en = [btn for row in kb_en.inline_keyboard for btn in row]
        rel_btn_en = next((b for b in all_btns_en if b.url and f"releases/tag/{BOT_VERSION}" in b.url), None)
        self.assertIsNotNone(rel_btn_en, "Release URL button must exist in English status keyboard")
        self.assertIn(BOT_VERSION, rel_btn_en.text)
        self.assertIn("Release", rel_btn_en.text)

        # 2. Test Arabic status card
        mock_target.reply_text.reset_mock()
        asyncio.run(render_status_card(mock_target, test_uid, user_lang="ar", is_edit=False))
        self.assertTrue(mock_target.reply_text.called)
        call_args_ar = mock_target.reply_text.call_args
        card_text_ar = call_args_ar[0][0]
        self.assertIn("حالة الشبكة والمنظومة", card_text_ar)
        self.assertIn(BOT_VERSION, card_text_ar)

        kb_ar = call_args_ar[1]["reply_markup"]
        all_btns_ar = [btn for row in kb_ar.inline_keyboard for btn in row]
        rel_btn_ar = next((b for b in all_btns_ar if b.url and f"releases/tag/{BOT_VERSION}" in b.url), None)
        self.assertIsNotNone(rel_btn_ar, "Release URL button must exist in Arabic status keyboard")
        self.assertIn(BOT_VERSION, rel_btn_ar.text)
        self.assertIn("الإصدار", rel_btn_ar.text)

    def test_62_fees_card_referral_link_and_withdraw_guide_actions(self):
        """Test render_fees_card embeds 1-click referral button and btn_withdraw_guide attaches deposit/wallet actions."""
        import asyncio
        from unittest.mock import AsyncMock, MagicMock, patch
        from telegram_bot import render_fees_card, callback_router

        # 1. Test render_fees_card includes btn_referral in keyboard
        mock_target = MagicMock()
        mock_target.reply_text = AsyncMock()
        test_uid = 99881133

        asyncio.run(render_fees_card(mock_target, test_uid, user_lang="en", is_edit=False))
        self.assertTrue(mock_target.reply_text.called)
        call_args = mock_target.reply_text.call_args
        kb_fees = call_args[1]["reply_markup"]
        fees_cbs = [b.callback_data for row in kb_fees.inline_keyboard for b in row if b.callback_data]
        self.assertIn("btn_referral", fees_cbs)
        self.assertIn("btn_status", fees_cbs)
        self.assertIn("btn_gas_fees", fees_cbs)

        # 2. Test btn_withdraw_guide attaches QR code deposit button when balance is low (< 0.005 SOL)
        mock_query_low = MagicMock()
        mock_query_low.from_user.id = test_uid
        mock_query_low.data = "btn_withdraw_guide"
        mock_query_low.edit_message_text = AsyncMock()
        mock_query_low.answer = AsyncMock()
        mock_update = MagicMock(callback_query=mock_query_low)
        mock_context = MagicMock()

        with patch("telegram_bot.get_sol_balance", return_value=0.0):
            asyncio.run(callback_router(mock_update, mock_context))
            self.assertTrue(mock_query_low.edit_message_text.called)
            edit_args = mock_query_low.edit_message_text.call_args
            kb_low = edit_args[1]["reply_markup"]
            low_cbs = [b.callback_data for row in kb_low.inline_keyboard for b in row if b.callback_data]
            self.assertIn("btn_qr", low_cbs)
            self.assertIn("btn_wallet", low_cbs)

        # 3. Test btn_withdraw_guide attaches refresh button when balance is funded (>= 0.005 SOL)
        mock_query_high = MagicMock()
        mock_query_high.from_user.id = test_uid
        mock_query_high.data = "btn_withdraw_guide"
        mock_query_high.edit_message_text = AsyncMock()
        mock_query_high.answer = AsyncMock()
        mock_update_high = MagicMock(callback_query=mock_query_high)

        with patch("telegram_bot.get_sol_balance", return_value=1.5):
            asyncio.run(callback_router(mock_update_high, mock_context))
            self.assertTrue(mock_query_high.edit_message_text.called)
            edit_args_high = mock_query_high.edit_message_text.call_args
            kb_high = edit_args_high[1]["reply_markup"]
            high_cbs = [b.callback_data for row in kb_high.inline_keyboard for b in row if b.callback_data]
            self.assertIn("btn_withdraw_guide", high_cbs)
            self.assertIn("btn_wallet", high_cbs)

    def test_63_referral_parity_and_refresh_action(self):
        """Test referral_command and btn_referral feature parity with live refresh and viral X/Telegram links."""
        import asyncio
        from unittest.mock import AsyncMock, MagicMock
        from telegram_bot import referral_command, callback_router

        test_uid = 99881144

        # 1. Test /referral command keyboard has both share links, refresh button, and back button
        mock_update_cmd = MagicMock()
        mock_update_cmd.effective_user.id = test_uid
        mock_update_cmd.message.reply_text = AsyncMock()
        mock_context = MagicMock()
        mock_context.bot.username = "PopcornSniperBot"

        asyncio.run(referral_command(mock_update_cmd, mock_context))
        self.assertTrue(mock_update_cmd.message.reply_text.called)
        kb_cmd = mock_update_cmd.message.reply_text.call_args[1]["reply_markup"]
        all_btns_cmd = [b for row in kb_cmd.inline_keyboard for b in row]
        urls_cmd = [b.url for b in all_btns_cmd if b.url]
        cbs_cmd = [b.callback_data for b in all_btns_cmd if b.callback_data]

        self.assertTrue(any("t.me/share/url" in u for u in urls_cmd))
        self.assertTrue(any("twitter.com/intent/tweet" in u for u in urls_cmd))
        self.assertIn("btn_referral", cbs_cmd)
        self.assertIn("btn_refresh", cbs_cmd)

        # 2. Test btn_referral inline callback handler has matching keyboard
        mock_query = MagicMock()
        mock_query.from_user.id = test_uid
        mock_query.data = "btn_referral"
        mock_query.edit_message_text = AsyncMock()
        mock_query.answer = AsyncMock()
        mock_update_cb = MagicMock(callback_query=mock_query)

        asyncio.run(callback_router(mock_update_cb, mock_context))
        self.assertTrue(mock_query.edit_message_text.called)
        kb_cb = mock_query.edit_message_text.call_args[1]["reply_markup"]
        all_btns_cb = [b for row in kb_cb.inline_keyboard for b in row]
        urls_cb = [b.url for b in all_btns_cb if b.url]
        cbs_cb = [b.callback_data for b in all_btns_cb if b.callback_data]

        self.assertTrue(any("t.me/share/url" in u for u in urls_cb))
        self.assertTrue(any("twitter.com/intent/tweet" in u for u in urls_cb))
        self.assertIn("btn_referral", cbs_cb)
        self.assertIn("btn_refresh", cbs_cb)

    def test_64_trending_resilience_and_marketing_generation(self):
        """Test trending engine handles DexScreener null pairs safely and marketing autopilot builds verified alpha posts."""
        from unittest.mock import patch, MagicMock
        from trending_engine import get_trending_tokens
        import trending_engine
        from marketing_autopilot import generate_marketing_post

        # Reset cache for isolated test
        trending_engine._TRENDING_CACHE["timestamp"] = 0
        trending_engine._TRENDING_CACHE["data"] = []

        # 1. Test null pairs response from DexScreener batch endpoint does not raise TypeError
        mock_resp_null = MagicMock()
        mock_resp_null.status_code = 200
        mock_resp_null.json.return_value = {"schemaVersion": "1.0.0", "pairs": None}

        # Mock single token fallback response
        mock_resp_single = MagicMock()
        mock_resp_single.status_code = 200
        mock_resp_single.json.return_value = {
            "pairs": [
                {
                    "baseToken": {"address": self.bonk_mint, "symbol": "BONK", "name": "Bonk"},
                    "priceUsd": "0.000025",
                    "priceChange": {"h1": "1.5", "h24": "12.4"},
                    "volume": {"h24": "5000000"},
                    "liquidity": {"usd": "1200000"},
                    "marketCap": "1500000000"
                }
            ]
        }

        def mock_get(url, *args, **kwargs):
            if "token-boosts" in url:
                mock_b = MagicMock()
                mock_b.status_code = 200
                mock_b.json.return_value = []
                return mock_b
            if "," in url:
                return mock_resp_null
            return mock_resp_single

        with patch.object(trending_engine._SESSION, "get", side_effect=mock_get):
            tokens = get_trending_tokens(limit=2)
            self.assertIsInstance(tokens, list)
            self.assertGreater(len(tokens), 0)
            self.assertEqual(tokens[0]["symbol"], "BONK")
            self.assertEqual(tokens[0]["price_usd"], 0.000025)

        # 2. Test marketing alpha post generation
        fake_trending = [
            {
                "mint": self.bonk_mint,
                "symbol": "BONK",
                "price_usd": 0.000025,
                "change_24h": 12.4,
                "change_1h": 1.5,
                "volume_24h": 5_000_000,
                "liquidity": 1_200_000
            }
        ]
        fake_scan = {"rug_score": 0, "status": "SAFE"}

        with patch("marketing_autopilot.get_trending_tokens", return_value=fake_trending), \
             patch("marketing_autopilot.scan_token_security", return_value=fake_scan):
            post_text, mint = generate_marketing_post()
            self.assertIsNotNone(post_text)
            self.assertEqual(mint, self.bonk_mint)
            self.assertIn("$BONK Trending", post_text)
            self.assertIn("RugCheck: 🟢 SAFE", post_text)
            self.assertLessEqual(len(post_text), 260)

    def test_65_universal_english_social_previews(self):
        """Test bot_post_init synchronizes English descriptions for both global and Arabic locales."""
        import asyncio
        from unittest.mock import AsyncMock, MagicMock
        from telegram_bot import bot_post_init

        mock_app = MagicMock()
        mock_app.bot.set_my_description = AsyncMock()
        mock_app.bot.set_my_short_description = AsyncMock()
        mock_app.bot.set_my_commands = AsyncMock()

        asyncio.run(bot_post_init(mock_app))

        # Check set_my_description calls
        desc_calls = mock_app.bot.set_my_description.call_args_list
        desc_langs = [c.kwargs.get("language_code") for c in desc_calls]
        self.assertIn("", desc_langs, "Default global description must be set")
        self.assertIn("ar", desc_langs, "Arabic locale must be synced with English description")
        for c in desc_calls:
            self.assertIn("Ultra-fast Solana Sniper", c.args[0])

        # Check set_my_short_description calls
        short_calls = mock_app.bot.set_my_short_description.call_args_list
        short_langs = [c.kwargs.get("language_code") for c in short_calls]
        self.assertIn("", short_langs, "Default global short description must be set")
        self.assertIn("ar", short_langs, "Arabic locale must be synced with English short description")
        for c in short_calls:
            self.assertIn("Ultra-fast Solana Sniper", c.args[0])

    def test_66_surge_radar_resilience_and_empty_state_action(self):
        """Test render_surge_radar renders snipe buttons when gainers exist and explore trending when empty."""
        import asyncio
        from unittest.mock import AsyncMock, MagicMock, patch
        from telegram_bot import render_surge_radar

        test_uid = 99881155

        # 1. Test populated gainers renders 1-click inspect buttons
        mock_target_pop = MagicMock()
        mock_target_pop.reply_text = AsyncMock()

        fake_gainers = [
            {
                "mint": self.bonk_mint,
                "symbol": "BONK",
                "price_usd": 0.000025,
                "change_1h": 15.2,
                "change_24h": 40.0,
                "volume_24h": 5000000,
                "liquidity": 1200000
            }
        ]

        with patch("telegram_bot.get_top_gainers", return_value=fake_gainers):
            asyncio.run(render_surge_radar(mock_target_pop, test_uid, user_lang="en", is_edit=False))
            self.assertTrue(mock_target_pop.reply_text.called)
            kb = mock_target_pop.reply_text.call_args[1]["reply_markup"]
            all_cbs = [b.callback_data for row in kb.inline_keyboard for b in row if b.callback_data]
            self.assertIn(f"inspect_{self.bonk_mint}", all_cbs)
            self.assertIn("btn_surge", all_cbs)
            self.assertIn("btn_refresh", all_cbs)

        # 2. Test empty gainers renders explore trending action button
        mock_target_empty = MagicMock()
        mock_target_empty.reply_text = AsyncMock()

        with patch("telegram_bot.get_top_gainers", return_value=[]):
            asyncio.run(render_surge_radar(mock_target_empty, test_uid, user_lang="en", is_edit=False))
            self.assertTrue(mock_target_empty.reply_text.called)
            kb_empty = mock_target_empty.reply_text.call_args[1]["reply_markup"]
            empty_cbs = [b.callback_data for row in kb_empty.inline_keyboard for b in row if b.callback_data]
            self.assertIn("btn_trending", empty_cbs)
            self.assertIn("btn_surge", empty_cbs)
            self.assertIn("btn_refresh", empty_cbs)

    def test_67_pnl_live_refresh_action_and_parity(self):
        """Test PnL card includes live refresh button with bilingual labels and callback routing parity."""
        import asyncio
        from unittest.mock import MagicMock, AsyncMock, patch
        from telegram_bot import pnl_command, callback_router

        # 1. Test /pnl command in English
        mock_update_en = MagicMock()
        mock_update_en.effective_user.id = 9998881
        mock_update_en.effective_chat.id = 9998881
        mock_update_en.effective_user.username = "TraderJoe"
        mock_update_en.message.reply_text = AsyncMock()
        mock_context = MagicMock()

        with patch("telegram_bot.get_user_language", return_value="en"):
            asyncio.run(pnl_command(mock_update_en, mock_context))
            self.assertTrue(mock_update_en.message.reply_text.called)
            kb = mock_update_en.message.reply_text.call_args[1]["reply_markup"]
            all_btns = [b for row in kb.inline_keyboard for b in row]
            refresh_btn = next((b for b in all_btns if b.callback_data == "btn_pnl"), None)
            self.assertIsNotNone(refresh_btn, "btn_pnl refresh button must be present in /pnl keyboard")
            self.assertIn("Refresh PnL", refresh_btn.text)

        # 2. Test /pnl command in Arabic
        mock_update_ar = MagicMock()
        mock_update_ar.effective_user.id = 9998882
        mock_update_ar.effective_chat.id = 9998882
        mock_update_ar.effective_user.username = "TraderAli"
        mock_update_ar.message.reply_text = AsyncMock()

        with patch("telegram_bot.get_user_language", return_value="ar"):
            asyncio.run(pnl_command(mock_update_ar, mock_context))
            self.assertTrue(mock_update_ar.message.reply_text.called)
            kb_ar = mock_update_ar.message.reply_text.call_args[1]["reply_markup"]
            all_btns_ar = [b for row in kb_ar.inline_keyboard for b in row]
            refresh_btn_ar = next((b for b in all_btns_ar if b.callback_data == "btn_pnl"), None)
            self.assertIsNotNone(refresh_btn_ar, "btn_pnl refresh button must be present in Arabic /pnl keyboard")
            self.assertIn("تحديث الأرباح", refresh_btn_ar.text)

        # 3. Test callback_router btn_pnl action
        mock_query_cb = MagicMock()
        mock_query_cb.from_user.id = 9998883
        mock_query_cb.from_user.username = "TraderCb"
        mock_query_cb.data = "btn_pnl"
        mock_query_cb.answer = AsyncMock()
        mock_query_cb.edit_message_text = AsyncMock()
        mock_update_cb = MagicMock(callback_query=mock_query_cb)

        with patch("telegram_bot.get_user_language", return_value="en"):
            asyncio.run(callback_router(mock_update_cb, mock_context))
            self.assertTrue(mock_query_cb.answer.called)
            self.assertTrue(mock_query_cb.edit_message_text.called)
            kb_cb = mock_query_cb.edit_message_text.call_args[1]["reply_markup"]
            cb_btns = [b for row in kb_cb.inline_keyboard for b in row]
            refresh_cb_btn = next((b for b in cb_btns if b.callback_data == "btn_pnl"), None)
            self.assertIsNotNone(refresh_cb_btn, "btn_pnl callback must provide live refresh button")

    def test_68_help_card_parity_and_callback_routing(self):
        """Test render_help_card quick actions parity, build_settings_card btn_help, and callback routing."""
        import asyncio
        from unittest.mock import MagicMock, AsyncMock, patch
        from telegram_bot import render_help_card, help_command, build_settings_card, callback_router

        # 1. Test render_help_card in English
        mock_target = MagicMock()
        mock_target.reply_text = AsyncMock()
        test_uid = 99887711

        asyncio.run(render_help_card(mock_target, test_uid, user_lang="en", is_edit=False))
        self.assertTrue(mock_target.reply_text.called)
        kb_en = mock_target.reply_text.call_args[1]["reply_markup"]
        all_cbs = [b.callback_data for row in kb_en.inline_keyboard for b in row if b.callback_data]
        self.assertIn("btn_refresh", all_cbs)
        self.assertIn("btn_wallet", all_cbs)
        self.assertIn("btn_trending", all_cbs)
        self.assertIn("btn_settings", all_cbs)
        self.assertIn("btn_referral", all_cbs)
        self.assertIn("btn_status", all_cbs)
        self.assertIn("btn_tour", all_cbs)

        # 2. Test build_settings_card includes btn_help button
        _, kb_settings = build_settings_card(test_uid, "en")
        settings_cbs = [b.callback_data for row in kb_settings.inline_keyboard for b in row if b.callback_data]
        self.assertIn("btn_help", settings_cbs, "btn_help must be present in settings keyboard")

        # 3. Test callback_router btn_help
        mock_query = MagicMock()
        mock_query.from_user.id = test_uid
        mock_query.data = "btn_help"
        mock_query.answer = AsyncMock()
        mock_query.edit_message_text = AsyncMock()
        mock_update = MagicMock(callback_query=mock_query)
        mock_context = MagicMock()

        with patch("telegram_bot.get_user_language", return_value="en"):
            asyncio.run(callback_router(mock_update, mock_context))
            self.assertTrue(mock_query.answer.called)
            self.assertTrue(mock_query.edit_message_text.called)
            kb_edited = mock_query.edit_message_text.call_args[1]["reply_markup"]
            edited_cbs = [b.callback_data for row in kb_edited.inline_keyboard for b in row if b.callback_data]
            self.assertIn("btn_tour", edited_cbs)
            self.assertIn("btn_status", edited_cbs)

    def test_69_gas_card_radar_parity_and_cli_args(self):
        """Test render_gas_card active checkmarks, gas_command CLI arg parsing, and contextual callback routing."""
        import asyncio
        from unittest.mock import MagicMock, AsyncMock, patch
        from telegram_bot import render_gas_card, gas_command, callback_router
        from wallet_manager import get_or_create_wallet, get_user_settings, update_user_priority_fee

        test_uid = 99886655
        get_or_create_wallet(test_uid)
        update_user_priority_fee(test_uid, 50000)

        # 1. Test render_gas_card has Normal checked (✅)
        mock_target = MagicMock()
        mock_target.reply_text = AsyncMock()

        asyncio.run(render_gas_card(mock_target, test_uid, user_lang="en", is_edit=False))
        self.assertTrue(mock_target.reply_text.called)
        kb = mock_target.reply_text.call_args[1]["reply_markup"]
        all_btns = [b for row in kb.inline_keyboard for b in row]
        normal_btn = next((b for b in all_btns if b.callback_data == "gas_50000"), None)
        self.assertIsNotNone(normal_btn)
        self.assertIn("✅", normal_btn.text)

        # 2. Test gas_command with CLI arg "turbo" updates user priority fee to 250000
        mock_update_cmd = MagicMock()
        mock_update_cmd.effective_user.id = test_uid
        mock_update_cmd.message.reply_text = AsyncMock()
        mock_context = MagicMock()
        mock_context.args = ["turbo"]

        asyncio.run(gas_command(mock_update_cmd, mock_context))
        new_settings = get_user_settings(test_uid)
        self.assertEqual(new_settings["priority_fee"], 250000)
        kb_cmd = mock_update_cmd.message.reply_text.call_args[1]["reply_markup"]
        all_btns_cmd = [b for row in kb_cmd.inline_keyboard for b in row]
        turbo_btn = next((b for b in all_btns_cmd if b.callback_data == "gas_250000"), None)
        self.assertIsNotNone(turbo_btn)
        self.assertIn("✅", turbo_btn.text)

        # 3. Test callback_router with btn_gas_fees
        mock_query_cb = MagicMock()
        mock_query_cb.from_user.id = test_uid
        mock_query_cb.data = "btn_gas_fees"
        mock_query_cb.answer = AsyncMock()
        mock_query_cb.edit_message_text = AsyncMock()
        mock_update_cb = MagicMock(callback_query=mock_query_cb)

        with patch("telegram_bot.get_user_language", return_value="en"):
            asyncio.run(callback_router(mock_update_cb, mock_context))
            self.assertTrue(mock_query_cb.edit_message_text.called)
            kb_fees = mock_query_cb.edit_message_text.call_args[1]["reply_markup"]
            fees_cbs = [b.callback_data for row in kb_fees.inline_keyboard for b in row if b.callback_data]
            self.assertIn("gas_50000", fees_cbs)
            self.assertIn("btn_gas_fees", fees_cbs)

    def test_70_slippage_card_radar_parity_and_cli_args(self):
        """Test render_slippage_card checkmarks, slippage_command CLI args, and in-place callback routing."""
        import asyncio
        from unittest.mock import MagicMock, AsyncMock, patch
        from telegram_bot import render_slippage_card, slippage_command, callback_router
        from wallet_manager import get_or_create_wallet, get_user_settings, update_user_slippage

        test_uid = 99885544
        get_or_create_wallet(test_uid)
        update_user_slippage(test_uid, 100)

        # 1. Test render_slippage_card has 1.0% checked (✅)
        mock_target = MagicMock()
        mock_target.reply_text = AsyncMock()

        asyncio.run(render_slippage_card(mock_target, test_uid, user_lang="en", is_edit=False))
        self.assertTrue(mock_target.reply_text.called)
        kb = mock_target.reply_text.call_args[1]["reply_markup"]
        all_btns = [b for row in kb.inline_keyboard for b in row]
        slip100_btn = next((b for b in all_btns if b.callback_data == "slip_100"), None)
        self.assertIsNotNone(slip100_btn)
        self.assertIn("✅", slip100_btn.text)

        # 2. Test slippage_command with CLI arg "0.5" updates slippage to 50 BPS
        mock_update_cmd = MagicMock()
        mock_update_cmd.effective_user.id = test_uid
        mock_update_cmd.message.reply_text = AsyncMock()
        mock_context = MagicMock()
        mock_context.args = ["0.5"]

        asyncio.run(slippage_command(mock_update_cmd, mock_context))
        new_settings = get_user_settings(test_uid)
        self.assertEqual(new_settings["slippage_bps"], 50)
        kb_cmd = mock_update_cmd.message.reply_text.call_args[1]["reply_markup"]
        all_btns_cmd = [b for row in kb_cmd.inline_keyboard for b in row]
        slip50_btn = next((b for b in all_btns_cmd if b.callback_data == "slip_50"), None)
        self.assertIsNotNone(slip50_btn)
        self.assertIn("✅", slip50_btn.text)

        # 3. Test callback_router with btn_slippage
        mock_query_cb = MagicMock()
        mock_query_cb.from_user.id = test_uid
        mock_query_cb.data = "btn_slippage"
        mock_query_cb.answer = AsyncMock()
        mock_query_cb.edit_message_text = AsyncMock()
        mock_update_cb = MagicMock(callback_query=mock_query_cb)

        with patch("telegram_bot.get_user_language", return_value="en"):
            asyncio.run(callback_router(mock_update_cb, mock_context))
            self.assertTrue(mock_query_cb.edit_message_text.called)
            kb_slip = mock_query_cb.edit_message_text.call_args[1]["reply_markup"]
            slip_cbs = [b.callback_data for row in kb_slip.inline_keyboard for b in row if b.callback_data]
            self.assertIn("slip_50", slip_cbs)
            self.assertIn("btn_slippage", slip_cbs)

    def test_71_tp_sl_card_radar_parity_and_cli_args(self):
        """Test render_tp_card and render_sl_card checkmarks, CLI args parsing, and callback router parity."""
        import asyncio
        from unittest.mock import MagicMock, AsyncMock, patch
        from telegram_bot import render_tp_card, render_sl_card, tp_command, sl_command, callback_router
        from wallet_manager import get_or_create_wallet, get_user_settings, update_user_tp, update_user_sl

        test_uid = 99884433
        get_or_create_wallet(test_uid)
        update_user_tp(test_uid, 50)
        update_user_sl(test_uid, 25)

        # 1. Test render_tp_card has +50% checked (✅)
        mock_target = MagicMock()
        mock_target.reply_text = AsyncMock()

        asyncio.run(render_tp_card(mock_target, test_uid, user_lang="en", is_edit=False))
        self.assertTrue(mock_target.reply_text.called)
        kb_tp = mock_target.reply_text.call_args[1]["reply_markup"]
        all_tp_btns = [b for row in kb_tp.inline_keyboard for b in row]
        tp50_btn = next((b for b in all_tp_btns if b.callback_data == "tp_50"), None)
        self.assertIsNotNone(tp50_btn)
        self.assertIn("✅", tp50_btn.text)

        # 2. Test tp_command with CLI arg "100" updates TP setting to 100%
        mock_update_tp = MagicMock()
        mock_update_tp.effective_user.id = test_uid
        mock_update_tp.message.reply_text = AsyncMock()
        mock_context_tp = MagicMock()
        mock_context_tp.args = ["100"]

        asyncio.run(tp_command(mock_update_tp, mock_context_tp))
        settings_tp = get_user_settings(test_uid)
        self.assertEqual(settings_tp["default_tp_pct"], 100)
        kb_tp_cmd = mock_update_tp.message.reply_text.call_args[1]["reply_markup"]
        all_tp_cmd_btns = [b for row in kb_tp_cmd.inline_keyboard for b in row]
        tp100_btn = next((b for b in all_tp_cmd_btns if b.callback_data == "tp_100"), None)
        self.assertIsNotNone(tp100_btn)
        self.assertIn("✅", tp100_btn.text)

        # 3. Test render_sl_card has -25% checked (✅)
        mock_target_sl = MagicMock()
        mock_target_sl.reply_text = AsyncMock()

        asyncio.run(render_sl_card(mock_target_sl, test_uid, user_lang="en", is_edit=False))
        self.assertTrue(mock_target_sl.reply_text.called)
        kb_sl = mock_target_sl.reply_text.call_args[1]["reply_markup"]
        all_sl_btns = [b for row in kb_sl.inline_keyboard for b in row]
        sl25_btn = next((b for b in all_sl_btns if b.callback_data == "sl_25"), None)
        self.assertIsNotNone(sl25_btn)
        self.assertIn("✅", sl25_btn.text)

        # 4. Test sl_command with CLI arg "50" updates SL setting to 50%
        mock_update_sl = MagicMock()
        mock_update_sl.effective_user.id = test_uid
        mock_update_sl.message.reply_text = AsyncMock()
        mock_context_sl = MagicMock()
        mock_context_sl.args = ["50"]

        asyncio.run(sl_command(mock_update_sl, mock_context_sl))
        settings_sl = get_user_settings(test_uid)
        self.assertEqual(settings_sl["default_sl_pct"], 50)
        kb_sl_cmd = mock_update_sl.message.reply_text.call_args[1]["reply_markup"]
        all_sl_cmd_btns = [b for row in kb_sl_cmd.inline_keyboard for b in row]
        sl50_btn = next((b for b in all_sl_cmd_btns if b.callback_data == "sl_50"), None)
        self.assertIsNotNone(sl50_btn)
        self.assertIn("✅", sl50_btn.text)

        # 5. Test callback_router routing with btn_tp and btn_sl
        mock_query_tp = MagicMock()
        mock_query_tp.from_user.id = test_uid
        mock_query_tp.data = "btn_tp"
        mock_query_tp.answer = AsyncMock()
        mock_query_tp.edit_message_text = AsyncMock()
        mock_update_cb_tp = MagicMock(callback_query=mock_query_tp)

        mock_context = MagicMock()
        with patch("telegram_bot.get_user_language", return_value="en"):
            asyncio.run(callback_router(mock_update_cb_tp, mock_context))
            self.assertTrue(mock_query_tp.edit_message_text.called)
            kb_cb_tp = mock_query_tp.edit_message_text.call_args[1]["reply_markup"]
            tp_cbs = [b.callback_data for row in kb_cb_tp.inline_keyboard for b in row if b.callback_data]
            self.assertIn("tp_50", tp_cbs)
            self.assertIn("btn_tp", tp_cbs)

    def test_72_autobuy_card_radar_parity_and_cli_args(self):
        """Test render_autobuy_card dynamic checkmarks across presets, /autobuy CLI args, and callback routing."""
        import asyncio
        from unittest.mock import AsyncMock, MagicMock, patch
        from telegram_bot import render_autobuy_card, autobuy_command, callback_router
        from wallet_manager import (
            get_or_create_wallet,
            get_auto_buy_settings,
            set_auto_buy_amount,
            set_auto_buy_status,
        )

        test_uid = 44556677
        get_or_create_wallet(test_uid, "AutoBuyRadarTester", initial_language="en")

        # 1. When enabled with 0.1 SOL, render_autobuy_card has 0.1 SOL checked (✅)
        set_auto_buy_amount(test_uid, 0.1)
        set_auto_buy_status(test_uid, True)

        mock_target = MagicMock()
        mock_target.reply_text = AsyncMock()

        asyncio.run(render_autobuy_card(mock_target, test_uid, user_lang="en", is_edit=False))
        self.assertTrue(mock_target.reply_text.called)
        card_text, kwargs = mock_target.reply_text.call_args[0][0], mock_target.reply_text.call_args[1]
        self.assertIn("Auto-Buy", card_text)
        self.assertIn("ENABLED 🟢", card_text)

        kb = kwargs["reply_markup"]
        all_btns = [b for row in kb.inline_keyboard for b in row]
        b01 = next((b for b in all_btns if b.callback_data == "set_auto_amt_0.1"), None)
        self.assertIsNotNone(b01)
        self.assertIn("✅", b01.text)

        b05 = next((b for b in all_btns if b.callback_data == "set_auto_amt_0.5"), None)
        self.assertIsNotNone(b05)
        self.assertNotIn("✅", b05.text)

        # 2. When disabled, no amount has checkmark and toggle button offers enabling
        set_auto_buy_status(test_uid, False)
        mock_target.reply_text.reset_mock()

        asyncio.run(render_autobuy_card(mock_target, test_uid, user_lang="en", is_edit=False))
        self.assertTrue(mock_target.reply_text.called)
        card_text_dis, kwargs_dis = mock_target.reply_text.call_args[0][0], mock_target.reply_text.call_args[1]
        self.assertIn("DISABLED ⚪", card_text_dis)

        kb_dis = kwargs_dis["reply_markup"]
        all_btns_dis = [b for row in kb_dis.inline_keyboard for b in row]
        b01_dis = next((b for b in all_btns_dis if b.callback_data == "set_auto_amt_0.1"), None)
        self.assertIsNotNone(b01_dis)
        self.assertNotIn("✅", b01_dis.text)

        toggle_btn = next((b for b in all_btns_dis if b.callback_data == "toggle_autobuy"), None)
        self.assertIsNotNone(toggle_btn)
        self.assertIn("Enable Auto-Buy", toggle_btn.text)

        # 3. Test autobuy_command CLI arg "0.5" enables auto-buy, sets 0.5 SOL, and renders card with 0.5 SOL ✅
        mock_update = MagicMock()
        mock_update.effective_user.id = test_uid
        mock_update.message.reply_text = AsyncMock()
        mock_context = MagicMock()
        mock_context.args = ["0.5"]

        asyncio.run(autobuy_command(mock_update, mock_context))
        enabled, amt = get_auto_buy_settings(test_uid)
        self.assertTrue(enabled)
        self.assertEqual(amt, 0.5)

        kb_cmd = mock_update.message.reply_text.call_args[1]["reply_markup"]
        all_cmd_btns = [b for row in kb_cmd.inline_keyboard for b in row]
        b05_cmd = next((b for b in all_cmd_btns if b.callback_data == "set_auto_amt_0.5"), None)
        self.assertIsNotNone(b05_cmd)
        self.assertIn("✅", b05_cmd.text)

        # 4. Test callback_router routing with btn_autobuy and set_auto_amt_1.0
        mock_query = MagicMock()
        mock_query.from_user.id = test_uid
        mock_query.data = "btn_autobuy"
        mock_query.answer = AsyncMock()
        mock_query.edit_message_text = AsyncMock()
        mock_update_cb = MagicMock(callback_query=mock_query)

        mock_ctx = MagicMock()
        with patch("telegram_bot.get_user_language", return_value="en"):
            asyncio.run(callback_router(mock_update_cb, mock_ctx))
            self.assertTrue(mock_query.edit_message_text.called)
            kb_cb = mock_query.edit_message_text.call_args[1]["reply_markup"]
            cb_datas = [b.callback_data for row in kb_cb.inline_keyboard for b in row if b.callback_data]
            self.assertIn("toggle_autobuy", cb_datas)
            self.assertIn("set_auto_amt_1.0", cb_datas)
            self.assertIn("btn_autobuy", cb_datas)

    def test_73_alerts_card_radar_parity_and_cli_args(self):
        """Test render_alerts_card dynamic checkmarks across volatility tiers, /alerts CLI args, and callback routing."""
        import asyncio
        from unittest.mock import AsyncMock, MagicMock, patch
        from telegram_bot import render_alerts_card, alerts_command, callback_router
        from wallet_manager import (
            get_or_create_wallet,
            get_user_alert_settings,
            set_price_alerts_status,
            update_user_alert_threshold
        )

        test_uid = 55667788
        get_or_create_wallet(test_uid, "AlertRadarTester", initial_language="en")

        # 1. When enabled with 10% threshold, render_alerts_card has ±10% checked (✅)
        update_user_alert_threshold(test_uid, 10.0)
        set_price_alerts_status(test_uid, True)

        mock_target = MagicMock()
        mock_target.reply_text = AsyncMock()

        asyncio.run(render_alerts_card(mock_target, test_uid, user_lang="en", is_edit=False))
        self.assertTrue(mock_target.reply_text.called)
        card_text, kwargs = mock_target.reply_text.call_args[0][0], mock_target.reply_text.call_args[1]
        self.assertIn("Price Movement & Volatility Alert Radar", card_text)
        self.assertIn("ENABLED 🟢", card_text)

        kb = kwargs["reply_markup"]
        all_btns = [b for row in kb.inline_keyboard for b in row]
        p10 = next((b for b in all_btns if b.callback_data == "alert_pct_10"), None)
        self.assertIsNotNone(p10)
        self.assertIn("✅", p10.text)

        p20 = next((b for b in all_btns if b.callback_data == "alert_pct_20"), None)
        self.assertIsNotNone(p20)
        self.assertNotIn("✅", p20.text)

        # 2. When disabled, no threshold has checkmark and toggle button offers enabling
        set_price_alerts_status(test_uid, False)
        mock_target.reply_text.reset_mock()

        asyncio.run(render_alerts_card(mock_target, test_uid, user_lang="en", is_edit=False))
        self.assertTrue(mock_target.reply_text.called)
        card_text_dis, kwargs_dis = mock_target.reply_text.call_args[0][0], mock_target.reply_text.call_args[1]
        self.assertIn("DISABLED ⚪", card_text_dis)

        kb_dis = kwargs_dis["reply_markup"]
        all_btns_dis = [b for row in kb_dis.inline_keyboard for b in row]
        p10_dis = next((b for b in all_btns_dis if b.callback_data == "alert_pct_10"), None)
        self.assertIsNotNone(p10_dis)
        self.assertNotIn("✅", p10_dis.text)

        toggle_btn = next((b for b in all_btns_dis if b.callback_data == "toggle_alerts"), None)
        self.assertIsNotNone(toggle_btn)
        self.assertIn("Enable Alerts", toggle_btn.text)

        # 3. Test alerts_command CLI arg "20" enables alerts, sets 20% threshold, and renders card with ±20% ✅
        mock_update = MagicMock()
        mock_update.effective_user.id = test_uid
        mock_update.message.reply_text = AsyncMock()
        mock_context = MagicMock()
        mock_context.args = ["20"]

        asyncio.run(alerts_command(mock_update, mock_context))
        enabled, th = get_user_alert_settings(test_uid)
        self.assertTrue(enabled)
        self.assertEqual(th, 20.0)

        kb_cmd = mock_update.message.reply_text.call_args[1]["reply_markup"]
        all_cmd_btns = [b for row in kb_cmd.inline_keyboard for b in row]
        p20_cmd = next((b for b in all_cmd_btns if b.callback_data == "alert_pct_20"), None)
        self.assertIsNotNone(p20_cmd)
        self.assertIn("✅", p20_cmd.text)

        # 4. Test alerts_command CLI arg "off" disables alerts
        mock_context.args = ["off"]
        asyncio.run(alerts_command(mock_update, mock_context))
        enabled_off, _ = get_user_alert_settings(test_uid)
        self.assertFalse(enabled_off)

        # 5. Test callback_router routing with btn_alerts and alert_pct_50
        mock_query = MagicMock()
        mock_query.from_user.id = test_uid
        mock_query.data = "btn_alerts"
        mock_query.answer = AsyncMock()
        mock_query.edit_message_text = AsyncMock()
        mock_update_cb = MagicMock(callback_query=mock_query)

        mock_ctx = MagicMock()
        with patch("telegram_bot.get_user_language", return_value="en"):
            asyncio.run(callback_router(mock_update_cb, mock_ctx))
            self.assertTrue(mock_query.edit_message_text.called)
            kb_cb = mock_query.edit_message_text.call_args[1]["reply_markup"]
            cb_datas = [b.callback_data for row in kb_cb.inline_keyboard for b in row if b.callback_data]
            self.assertIn("toggle_alerts", cb_datas)
            self.assertIn("alert_pct_50", cb_datas)
            self.assertIn("btn_alerts", cb_datas)

    def test_74_token_card_interactive_state_and_x_sharing(self):
        """Test get_token_card_keyboard dynamic tracking state, X sharing link, live refresh, and watchlist alert button."""
        from telegram_bot import get_token_card_keyboard, render_watchlist
        from wallet_manager import (
            get_or_create_wallet,
            add_to_watchlist,
            remove_from_watchlist,
            is_token_in_watchlist
        )
        import asyncio
        from unittest.mock import AsyncMock, MagicMock

        test_uid = 77889900
        test_mint = "Token11111111111111111111111111111111111111"
        get_or_create_wallet(test_uid, "InteractiveCardTester", initial_language="en")

        # 1. When token is not in watchlist, keyboard shows Track button
        remove_from_watchlist(test_uid, test_mint)
        self.assertFalse(is_token_in_watchlist(test_uid, test_mint))

        kb_untracked = get_token_card_keyboard(test_mint, user_lang="en", user_id=test_uid, symbol="TEST")
        all_btns_untracked = [b for row in kb_untracked.inline_keyboard for b in row]

        track_btn = next((b for b in all_btns_untracked if b.callback_data == f"track_{test_mint}"), None)
        self.assertIsNotNone(track_btn)
        self.assertIn("Track", track_btn.text)

        # Verify X / Twitter share button
        x_btn = next((b for b in all_btns_untracked if b.url and "twitter.com/intent/tweet" in b.url), None)
        self.assertIsNotNone(x_btn)
        self.assertIn("Share on X", x_btn.text)
        self.assertIn(test_mint, x_btn.url)

        # Verify Refresh Quote button
        refresh_quote_btn = next((b for b in all_btns_untracked if b.callback_data == f"inspect_{test_mint}"), None)
        self.assertIsNotNone(refresh_quote_btn)
        self.assertIn("Refresh", refresh_quote_btn.text)

        # 2. When token is tracked in watchlist, keyboard dynamically switches to Untrack
        add_to_watchlist(test_uid, test_mint, "TEST", current_price=1.25)
        self.assertTrue(is_token_in_watchlist(test_uid, test_mint))

        kb_tracked = get_token_card_keyboard(test_mint, user_lang="en", user_id=test_uid, symbol="TEST")
        all_btns_tracked = [b for row in kb_tracked.inline_keyboard for b in row]

        untrack_btn = next((b for b in all_btns_tracked if b.callback_data == f"untrack_{test_mint}"), None)
        self.assertIsNotNone(untrack_btn)
        self.assertIn("Untrack", untrack_btn.text)

        # 3. Test render_watchlist embeds btn_alerts in populated view
        mock_target = MagicMock()
        mock_target.reply_text = AsyncMock()

        asyncio.run(render_watchlist(mock_target, test_uid, user_lang="en", is_edit=False))
        self.assertTrue(mock_target.reply_text.called)
        wl_kb = mock_target.reply_text.call_args[1]["reply_markup"]
        all_wl_btns = [b for row in wl_kb.inline_keyboard for b in row]
        alert_radar_btn = next((b for b in all_wl_btns if b.callback_data == "btn_alerts"), None)
        self.assertIsNotNone(alert_radar_btn)
        self.assertIn("Alert Radar", alert_radar_btn.text)

    def test_75_trade_history_csv_export_and_cli(self):
        """Test full trade history retrieval, RFC 4180 CSV generation, and /history csv export dispatch."""
        from telegram_bot import render_trade_history, send_trades_csv_export, history_command
        from wallet_manager import (
            get_or_create_wallet,
            record_trade,
            get_all_user_trades,
            generate_trades_csv_bytes
        )
        import asyncio
        from unittest.mock import AsyncMock, MagicMock

        test_uid = 99881122
        get_or_create_wallet(test_uid, "CSVExportTester", initial_language="en")

        # 1. Record 2 sample trades
        record_trade(
            user_id=test_uid,
            input_mint="So11111111111111111111111111111111111111112",
            output_mint="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            amount_in=1.5,
            amount_out=210.0,
            platform_fee_sol=0.015,
            tx_signature="sig_buy_test_123"
        )
        record_trade(
            user_id=test_uid,
            input_mint="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            output_mint="So11111111111111111111111111111111111111112",
            amount_in=210.0,
            amount_out=1.8,
            platform_fee_sol=0.018,
            tx_signature="sig_sell_test_456"
        )

        all_trades = get_all_user_trades(test_uid)
        self.assertGreaterEqual(len(all_trades), 2)

        # 2. Test generate_trades_csv_bytes produces valid RFC 4180 CSV
        csv_bytes = generate_trades_csv_bytes(test_uid)
        self.assertTrue(csv_bytes.startswith(b'\xef\xbb\xbf'))  # UTF-8 BOM
        csv_text = csv_bytes.decode("utf-8-sig")
        self.assertIn("Trade ID,Timestamp (UTC),Type,Input Mint,Output Mint,Amount In,Amount Out,Platform Fee (SOL),Status,Tx Signature,Solscan URL", csv_text)
        self.assertIn("BUY", csv_text)
        self.assertIn("SELL", csv_text)
        self.assertIn("sig_buy_test_123", csv_text)
        self.assertIn("https://solscan.io/tx/sig_buy_test_123", csv_text)

        # 3. Test render_trade_history embeds btn_export_trades_csv
        mock_target = MagicMock()
        mock_target.reply_text = AsyncMock()

        asyncio.run(render_trade_history(mock_target, test_uid, user_lang="en", is_edit=False))
        self.assertTrue(mock_target.reply_text.called)
        card_kb = mock_target.reply_text.call_args[1]["reply_markup"]
        all_card_btns = [b for row in card_kb.inline_keyboard for b in row]
        export_btn = next((b for b in all_card_btns if b.callback_data == "btn_export_trades_csv"), None)
        self.assertIsNotNone(export_btn)
        self.assertIn("Export", export_btn.text)

        # 4. Test send_trades_csv_export dispatches document
        mock_doc_target = MagicMock()
        mock_doc_target.reply_document = AsyncMock()

        asyncio.run(send_trades_csv_export(mock_doc_target, test_uid, user_lang="en"))
        self.assertTrue(mock_doc_target.reply_document.called)
        call_kwargs = mock_doc_target.reply_document.call_args[1]
        self.assertTrue(call_kwargs["filename"].startswith(f"popcorn_trades_{test_uid}"))
        self.assertIn(".csv", call_kwargs["filename"])
        self.assertIn("Trade History Export Ready", call_kwargs["caption"])

        # 5. Test history_command with args=['csv']
        mock_cmd_update = MagicMock()
        mock_cmd_update.effective_user.id = test_uid
        mock_cmd_update.message.reply_document = AsyncMock()
        mock_cmd_context = MagicMock()
        mock_cmd_context.args = ["csv"]

        asyncio.run(history_command(mock_cmd_update, mock_cmd_context))
        self.assertTrue(mock_cmd_update.message.reply_document.called)

    def test_76_settings_card_dynamic_checkmarks_and_reset_button(self):
        """Test build_settings_card dynamic checkmarks for slip, gas, tp, sl and reset defaults button."""
        from telegram_bot import build_settings_card, callback_router
        from wallet_manager import (
            get_or_create_wallet,
            update_user_slippage,
            update_user_priority_fee,
            update_user_tp,
            update_user_sl,
            reset_user_settings_to_defaults,
            get_user_settings
        )
        import asyncio
        from unittest.mock import AsyncMock, MagicMock

        test_uid = 99882244
        get_or_create_wallet(test_uid, "SettingsCheckmarkTester", initial_language="en")
        reset_user_settings_to_defaults(test_uid)

        # 1. Default settings: 100 bps (1.0%), 50000 lamports (Normal), +50% TP, -25% SL
        _, kb_def = build_settings_card(test_uid, user_lang="en")
        all_btns = [b for row in kb_def.inline_keyboard for b in row]

        slip_100_btn = next((b for b in all_btns if b.callback_data == "slip_100"), None)
        slip_50_btn = next((b for b in all_btns if b.callback_data == "slip_50"), None)
        self.assertIsNotNone(slip_100_btn)
        self.assertTrue(slip_100_btn.text.startswith("✅"))
        self.assertFalse(slip_50_btn.text.startswith("✅"))

        gas_norm_btn = next((b for b in all_btns if b.callback_data == "gas_50000"), None)
        gas_turbo_btn = next((b for b in all_btns if b.callback_data == "gas_250000"), None)
        self.assertTrue(gas_norm_btn.text.startswith("✅"))
        self.assertFalse(gas_turbo_btn.text.startswith("✅"))

        tp_50_btn = next((b for b in all_btns if b.callback_data == "tp_50"), None)
        sl_25_btn = next((b for b in all_btns if b.callback_data == "sl_25"), None)
        self.assertTrue(tp_50_btn.text.startswith("✅"))
        self.assertTrue(sl_25_btn.text.startswith("✅"))

        # 2. Check reset button and autobuy button exist
        reset_btn = next((b for b in all_btns if b.callback_data == "btn_reset_defaults"), None)
        autobuy_btn = next((b for b in all_btns if b.callback_data == "btn_autobuy"), None)
        self.assertIsNotNone(reset_btn)
        self.assertIsNotNone(autobuy_btn)
        self.assertIn("Reset Defaults", reset_btn.text)

        # 3. Modify settings and verify checkmark moves
        update_user_slippage(test_uid, 200)
        update_user_priority_fee(test_uid, 250000)
        update_user_tp(test_uid, 100)
        update_user_sl(test_uid, 50)

        _, kb_mod = build_settings_card(test_uid, user_lang="en")
        mod_btns = [b for row in kb_mod.inline_keyboard for b in row]

        mod_slip_200 = next((b for b in mod_btns if b.callback_data == "slip_200"), None)
        mod_gas_turbo = next((b for b in mod_btns if b.callback_data == "gas_250000"), None)
        mod_tp_100 = next((b for b in mod_btns if b.callback_data == "tp_100"), None)
        mod_sl_50 = next((b for b in mod_btns if b.callback_data == "sl_50"), None)

        self.assertTrue(mod_slip_200.text.startswith("✅"))
        self.assertTrue(mod_gas_turbo.text.startswith("✅"))
        self.assertTrue(mod_tp_100.text.startswith("✅"))
        self.assertTrue(mod_sl_50.text.startswith("✅"))

        # 4. Test callback btn_reset_defaults resets user settings back
        mock_query = MagicMock()
        mock_query.from_user.id = test_uid
        mock_query.data = "btn_reset_defaults"
        mock_query.answer = AsyncMock()
        mock_query.edit_message_text = AsyncMock()
        mock_query.message.edit_text = AsyncMock()

        mock_update = MagicMock()
        mock_update.callback_query = mock_query
        mock_update.effective_user.id = test_uid
        mock_context = MagicMock()

        asyncio.run(callback_router(mock_update, mock_context))
        self.assertTrue(mock_query.answer.called)

        # Verify settings restored in DB
        restored = get_user_settings(test_uid)
        self.assertEqual(restored["slippage_bps"], 100)
        self.assertEqual(restored["priority_fee"], 50000)
        self.assertEqual(restored["default_tp_pct"], 50)
        self.assertEqual(restored["default_sl_pct"], 25)

    def test_77_interactive_withdraw_radar_and_callback(self):
        """Test render_withdraw_card formatting, gas reserve accounting, /withdraw command without args, and callback routing."""
        from telegram_bot import render_withdraw_card, withdraw_command, callback_router
        from wallet_manager import get_or_create_wallet
        import asyncio
        from unittest.mock import AsyncMock, MagicMock, patch

        test_uid = 99883355
        pubkey, _ = get_or_create_wallet(test_uid, "WithdrawRadarTester", initial_language="en")

        # 1. Test render_withdraw_card with mocked balance
        with patch("telegram_bot.get_sol_balance", return_value=0.50):
            mock_target = MagicMock()
            mock_target.reply_text = AsyncMock()

            asyncio.run(render_withdraw_card(mock_target, test_uid, user_lang="en", is_edit=False))
            self.assertTrue(mock_target.reply_text.called)
            card_text = mock_target.reply_text.call_args[0][0]
            self.assertIn("Fast SOL Withdrawal Radar", card_text)
            self.assertIn("0.5000 SOL", card_text)
            self.assertIn("Gas Reserve (Auto-Kept):", card_text)
            self.assertIn("0.005 SOL", card_text)
            self.assertIn("0.4950 SOL", card_text)
            self.assertIn("/withdraw", card_text)

            kb = mock_target.reply_text.call_args[1]["reply_markup"]
            all_btns = [b for row in kb.inline_keyboard for b in row]
            refresh_btn = next((b for b in all_btns if b.callback_data == "btn_withdraw"), None)
            qr_btn = next((b for b in all_btns if b.callback_data == "btn_show_qr"), None)
            wallet_btn = next((b for b in all_btns if b.callback_data == "btn_wallet"), None)
            self.assertIsNotNone(refresh_btn)
            self.assertIsNotNone(qr_btn)
            self.assertIsNotNone(wallet_btn)

        # 2. Test withdraw_command without args routes to render_withdraw_card
        with patch("telegram_bot.get_sol_balance", return_value=0.20):
            mock_cmd_update = MagicMock()
            mock_cmd_update.effective_user.id = test_uid
            mock_cmd_update.message.reply_text = AsyncMock()
            mock_cmd_context = MagicMock()
            mock_cmd_context.args = []

            asyncio.run(withdraw_command(mock_cmd_update, mock_cmd_context))
            self.assertTrue(mock_cmd_update.message.reply_text.called)
            card_text_cmd = mock_cmd_update.message.reply_text.call_args[0][0]
            self.assertIn("Fast SOL Withdrawal Radar", card_text_cmd)

        # 3. Test callback_router routes btn_withdraw
        with patch("telegram_bot.get_sol_balance", return_value=0.20):
            mock_query = MagicMock()
            mock_query.from_user.id = test_uid
            mock_query.data = "btn_withdraw"
            mock_query.answer = AsyncMock()
            mock_query.edit_message_text = AsyncMock()
            mock_query.message.edit_text = AsyncMock()

            mock_update = MagicMock()
            mock_update.callback_query = mock_query
            mock_update.effective_user.id = test_uid
            mock_ctx = MagicMock()

            asyncio.run(callback_router(mock_update, mock_ctx))
            self.assertTrue(mock_query.edit_message_text.called or mock_query.message.edit_text.called)

    def test_78_quick_buy_presets_radar_and_cli(self):
        """Test quick-buy presets radar formatting, dynamic checkmarks, DB persistence, and /presets CLI."""
        from telegram_bot import render_presets_card, presets_command, build_application, callback_router
        from wallet_manager import (
            get_or_create_wallet,
            get_user_default_buy_amount,
            update_user_default_buy_amount,
            reset_user_settings_to_defaults
        )
        import asyncio
        from unittest.mock import AsyncMock, MagicMock
        from telegram.ext import CommandHandler

        test_uid = 99112233
        get_or_create_wallet(test_uid, "PresetsTester", initial_language="en")
        reset_user_settings_to_defaults(test_uid)

        # 1. Test DB default value and updates
        self.assertEqual(get_user_default_buy_amount(test_uid), 0.1)
        self.assertTrue(update_user_default_buy_amount(test_uid, 0.25))
        self.assertEqual(get_user_default_buy_amount(test_uid), 0.25)

        # 2. Test render_presets_card in English with active checkmark on 0.25 SOL
        mock_target = MagicMock()
        mock_target.reply_text = AsyncMock()
        asyncio.run(render_presets_card(mock_target, test_uid, "en", is_edit=False))
        self.assertTrue(mock_target.reply_text.called)

        card_text = mock_target.reply_text.call_args[0][0]
        self.assertIn("Quick-Snipe Buy Presets Radar", card_text)
        self.assertIn("0.25 SOL", card_text)

        kb = mock_target.reply_text.call_args[1]["reply_markup"]
        all_btns = [b for row in kb.inline_keyboard for b in row]
        btn_025 = next((b for b in all_btns if b.callback_data == "preset_buy_0.25"), None)
        btn_010 = next((b for b in all_btns if b.callback_data == "preset_buy_0.10"), None)
        self.assertIsNotNone(btn_025)
        self.assertIsNotNone(btn_010)
        self.assertTrue(btn_025.text.endswith("✅"))
        self.assertFalse(btn_010.text.endswith("✅"))

        # Check navigation buttons
        self.assertIsNotNone(next((b for b in all_btns if b.callback_data == "btn_autobuy"), None))
        self.assertIsNotNone(next((b for b in all_btns if b.callback_data == "btn_settings"), None))
        self.assertIsNotNone(next((b for b in all_btns if b.callback_data == "btn_presets"), None))

        # 3. Test presets_command with argument updates default amount
        mock_cmd_update = MagicMock()
        mock_cmd_update.effective_user.id = test_uid
        mock_cmd_update.message.reply_text = AsyncMock()
        mock_cmd_ctx = MagicMock()
        mock_cmd_ctx.args = ["0.50"]

        asyncio.run(presets_command(mock_cmd_update, mock_cmd_ctx))
        self.assertEqual(get_user_default_buy_amount(test_uid), 0.50)
        self.assertTrue(mock_cmd_update.message.reply_text.called)

        # 4. Test presets_command with no args renders presets card
        mock_cmd_ctx.args = []
        mock_cmd_update.message.reply_text.reset_mock()
        asyncio.run(presets_command(mock_cmd_update, mock_cmd_ctx))
        self.assertTrue(mock_cmd_update.message.reply_text.called)
        card_text_noargs = mock_cmd_update.message.reply_text.call_args[0][0]
        self.assertIn("Quick-Snipe Buy Presets Radar", card_text_noargs)

        # 5. Test callback_router routes btn_presets and preset_buy_1.00
        mock_query = MagicMock()
        mock_query.from_user.id = test_uid
        mock_query.data = "preset_buy_1.00"
        mock_query.answer = AsyncMock()
        mock_query.edit_message_text = AsyncMock()
        mock_query.message.edit_text = AsyncMock()

        mock_update = MagicMock()
        mock_update.callback_query = mock_query
        mock_update.effective_user.id = test_uid
        mock_ctx = MagicMock()

        asyncio.run(callback_router(mock_update, mock_ctx))
        self.assertEqual(get_user_default_buy_amount(test_uid), 1.00)
        self.assertTrue(mock_query.answer.called)

        # 6. Test CommandHandler registration for presets, preset, and quickbuy
        app = build_application(MOCK_TEST_BOT_TOKEN)
        command_handlers = [h for h in app.handlers[0] if isinstance(h, CommandHandler)]
        registered_commands = set()
        for h in command_handlers:
            registered_commands.update(h.commands)

        self.assertIn("presets", registered_commands)
        self.assertIn("preset", registered_commands)
        self.assertIn("quickbuy", registered_commands)

    def test_79_pnl_card_unification_and_viral_actions(self):
        """Test render_pnl_card unification, confirmed trade metrics, Telegram share intent, and CSV export action."""
        from telegram_bot import render_pnl_card, pnl_command, callback_router
        from wallet_manager import (
            get_or_create_wallet,
            record_trade_db,
            get_user_trade_stats,
            WSOL_MINT
        )
        import asyncio
        from unittest.mock import AsyncMock, MagicMock

        test_uid = 99223344
        get_or_create_wallet(test_uid, "PnLUnifiedTester", initial_language="en")

        # 1. Record 2 trades: 1 confirmed, 1 pending/failed
        record_trade_db(
            user_id=test_uid,
            input_mint=WSOL_MINT,
            output_mint="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            amount_in=0.10,
            amount_out=15.0,
            fee_sol=0.001,
            tx_sig="sig_conf_1",
            status="CONFIRMED"
        )
        record_trade_db(
            user_id=test_uid,
            input_mint=WSOL_MINT,
            output_mint="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            amount_in=0.05,
            amount_out=0.0,
            fee_sol=0.0,
            tx_sig="sig_fail_1",
            status="FAILED"
        )

        stats = get_user_trade_stats(test_uid)
        self.assertEqual(stats["total_trades"], 2)
        self.assertEqual(stats["confirmed_trades"], 1)
        self.assertEqual(stats["success_rate_pct"], 50.0)

        # 2. Test render_pnl_card in English
        mock_user = MagicMock()
        mock_user.username = "PnLChamp"
        mock_target = MagicMock()
        mock_target.reply_text = AsyncMock()

        asyncio.run(render_pnl_card(mock_target, mock_user, test_uid, "en", is_edit=False, bot_username="PopcornSniperBot"))
        self.assertTrue(mock_target.reply_text.called)

        card_text_en = mock_target.reply_text.call_args[0][0]
        self.assertIn("Trading PnL & Performance", card_text_en)
        self.assertIn("0.100 SOL", card_text_en)

        kb = mock_target.reply_text.call_args[1]["reply_markup"]
        all_btns = [b for row in kb.inline_keyboard for b in row]

        # Verify X share button and Telegram share button
        x_btn = next((b for b in all_btns if b.url and "twitter.com/intent/tweet" in b.url), None)
        tg_btn = next((b for b in all_btns if b.url and "t.me/share/url" in b.url), None)
        csv_btn = next((b for b in all_btns if b.callback_data == "btn_history_csv"), None)
        refresh_btn = next((b for b in all_btns if b.callback_data == "btn_pnl"), None)
        hist_btn = next((b for b in all_btns if b.callback_data == "btn_history"), None)
        pos_btn = next((b for b in all_btns if b.callback_data == "btn_positions"), None)

        self.assertIsNotNone(x_btn, "X share button must exist in PnL keyboard")
        self.assertIsNotNone(tg_btn, "Telegram share button must exist in PnL keyboard")
        self.assertIsNotNone(csv_btn, "CSV export button must exist in PnL keyboard")
        self.assertIsNotNone(refresh_btn, "Live refresh button must exist in PnL keyboard")
        self.assertIsNotNone(hist_btn)
        self.assertIsNotNone(pos_btn)

        # 3. Test render_pnl_card in Arabic
        mock_target_ar = MagicMock()
        mock_target_ar.reply_text = AsyncMock()
        asyncio.run(render_pnl_card(mock_target_ar, mock_user, test_uid, "ar", is_edit=False, bot_username="PopcornSniperBot"))
        card_text_ar = mock_target_ar.reply_text.call_args[0][0]
        self.assertIn("بطاقة أداء وأرباح التداول", card_text_ar)

        kb_ar = mock_target_ar.reply_text.call_args[1]["reply_markup"]
        all_btns_ar = [b for row in kb_ar.inline_keyboard for b in row]
        csv_btn_ar = next((b for b in all_btns_ar if b.callback_data == "btn_history_csv"), None)
        self.assertIsNotNone(csv_btn_ar)
        self.assertIn("تصدير", csv_btn_ar.text)

    def test_80_watchlist_clear_all_and_untrack_all_cli(self):
        """Test clear_user_watchlist persistence, render_watchlist clear button, /untrack all CLI, and /clearwatchlist."""
        from telegram_bot import (
            render_watchlist,
            untrack_command,
            clear_watchlist_command,
            callback_router,
            build_application
        )
        from wallet_manager import (
            get_or_create_wallet,
            add_to_watchlist,
            get_user_watchlist,
            clear_user_watchlist
        )
        import asyncio
        from unittest.mock import AsyncMock, MagicMock
        from telegram.ext import CommandHandler

        test_uid = 99334455
        get_or_create_wallet(test_uid, "WatchlistClearTester", initial_language="en")
        clear_user_watchlist(test_uid)

        # 1. Test clear_user_watchlist DB persistence
        add_to_watchlist(test_uid, "mint_1", "AAA", 1.0)
        add_to_watchlist(test_uid, "mint_2", "BBB", 2.0)
        add_to_watchlist(test_uid, "mint_3", "CCC", 3.0)
        self.assertEqual(len(get_user_watchlist(test_uid)), 3)

        cleared_count = clear_user_watchlist(test_uid)
        self.assertEqual(cleared_count, 3)
        self.assertEqual(len(get_user_watchlist(test_uid)), 0)

        # 2. Test render_watchlist has Clear All button and commands hint when populated
        add_to_watchlist(test_uid, "mint_1", "AAA", 1.0)
        mock_target = MagicMock()
        mock_target.reply_text = AsyncMock()

        asyncio.run(render_watchlist(mock_target, test_uid, "en", is_edit=False))
        self.assertTrue(mock_target.reply_text.called)

        wl_text = mock_target.reply_text.call_args[0][0]
        self.assertIn("/untrack all", wl_text)

        kb = mock_target.reply_text.call_args[1]["reply_markup"]
        all_btns = [b for row in kb.inline_keyboard for b in row]
        clear_btn = next((b for b in all_btns if b.callback_data == "btn_clear_watchlist"), None)
        self.assertIsNotNone(clear_btn, "Clear All button must be present in watchlist keyboard")
        self.assertIn("Clear All", clear_btn.text)

        # 3. Test untrack_command with 'all' argument
        mock_cmd_update = MagicMock()
        mock_cmd_update.effective_user.id = test_uid
        mock_cmd_update.message.reply_text = AsyncMock()
        mock_cmd_ctx = MagicMock()
        mock_cmd_ctx.args = ["all"]

        asyncio.run(untrack_command(mock_cmd_update, mock_cmd_ctx))
        self.assertTrue(mock_cmd_update.message.reply_text.called)
        reply_all = mock_cmd_update.message.reply_text.call_args[0][0]
        self.assertIn("Cleared all 1 tokens", reply_all)
        self.assertEqual(len(get_user_watchlist(test_uid)), 0)

        # 4. Test clear_watchlist_command directly
        add_to_watchlist(test_uid, "mint_1", "AAA", 1.0)
        add_to_watchlist(test_uid, "mint_2", "BBB", 2.0)
        mock_cmd_update.message.reply_text.reset_mock()

        asyncio.run(clear_watchlist_command(mock_cmd_update, mock_cmd_ctx))
        self.assertTrue(mock_cmd_update.message.reply_text.called)
        reply_cmd = mock_cmd_update.message.reply_text.call_args[0][0]
        self.assertIn("Cleared all 2 tokens", reply_cmd)
        self.assertEqual(len(get_user_watchlist(test_uid)), 0)

        # 5. Test callback_router btn_clear_watchlist
        add_to_watchlist(test_uid, "mint_1", "AAA", 1.0)
        mock_query = MagicMock()
        mock_query.from_user.id = test_uid
        mock_query.data = "btn_clear_watchlist"
        mock_query.answer = AsyncMock()
        mock_query.edit_message_text = AsyncMock()
        mock_query.message.edit_text = AsyncMock()

        mock_update = MagicMock()
        mock_update.callback_query = mock_query
        mock_update.effective_user.id = test_uid

        asyncio.run(callback_router(mock_update, mock_cmd_ctx))
        self.assertTrue(mock_query.answer.called)
        self.assertEqual(len(get_user_watchlist(test_uid)), 0)

        # 6. Test CommandHandler registration for clearwatchlist and purge
        app = build_application(MOCK_TEST_BOT_TOKEN)
        command_handlers = [h for h in app.handlers[0] if isinstance(h, CommandHandler)]
        registered_commands = set()
        for h in command_handlers:
            registered_commands.update(h.commands)

        self.assertIn("clearwatchlist", registered_commands)
        self.assertIn("purge", registered_commands)

    def test_81_positions_pnl_shortcut_and_direct_panic_cli(self):
        """Test render_positions PnL shortcut button, commands hint, and direct /panic now CLI execution."""
        from telegram_bot import render_positions, panic_command, execute_panic_sell_all
        from wallet_manager import get_or_create_wallet
        import asyncio
        from unittest.mock import AsyncMock, MagicMock, patch

        test_uid = 99445566
        get_or_create_wallet(test_uid, "PositionsTester", initial_language="en")

        mock_tokens = [
            {"mint": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263", "amount": 500000.0, "decimals": 5}
        ]

        # 1. Test render_positions contains btn_pnl shortcut button and commands hint
        mock_target = MagicMock()
        mock_target.reply_text = AsyncMock()
        with patch("telegram_bot.get_token_accounts", return_value=mock_tokens):
            asyncio.run(render_positions(mock_target, test_uid, "en", is_edit=False))
            self.assertTrue(mock_target.reply_text.called)

            pos_text = mock_target.reply_text.call_args[0][0]
            self.assertIn("/panic", pos_text)
            self.assertIn("/pnl", pos_text)

            kb = mock_target.reply_text.call_args[1]["reply_markup"]
            all_btns = [b for row in kb.inline_keyboard for b in row]

            pnl_btn = next((b for b in all_btns if b.callback_data == "btn_pnl"), None)
            panic_btn = next((b for b in all_btns if b.callback_data == "btn_panic_confirm"), None)
            refresh_btn = next((b for b in all_btns if b.callback_data == "btn_positions"), None)

            self.assertIsNotNone(pnl_btn, "btn_pnl shortcut must exist in positions keyboard")
            self.assertIsNotNone(panic_btn)
            self.assertIsNotNone(refresh_btn)
            self.assertIn("PnL", pnl_btn.text)

        # 2. Test panic_command with no args shows confirmation warning card
        mock_cmd_update = MagicMock()
        mock_cmd_update.effective_user.id = test_uid
        mock_cmd_update.message.reply_text = AsyncMock()
        mock_cmd_ctx = MagicMock()
        mock_cmd_ctx.args = []

        with patch("telegram_bot.get_token_accounts", return_value=mock_tokens):
            asyncio.run(panic_command(mock_cmd_update, mock_cmd_ctx))
            self.assertTrue(mock_cmd_update.message.reply_text.called)
            warn_text = mock_cmd_update.message.reply_text.call_args[0][0]
            self.assertIn("PANIC", warn_text)

        # 3. Test panic_command with 'now' arg executes immediate liquidation directly
        mock_cmd_ctx.args = ["now"]
        with patch("telegram_bot.execute_panic_sell_all", new_callable=AsyncMock) as mock_panic_exec:
            asyncio.run(panic_command(mock_cmd_update, mock_cmd_ctx))
            mock_panic_exec.assert_called_once_with(mock_cmd_update.message, test_uid, "en")

    def test_82_interactive_price_radar_and_quickbuy_flow(self):
        """Test render_price_card, dynamic track/untrack button, watchlist price shortcut, and /p, /c, /scan aliases."""
        from telegram_bot import (
            render_price_card,
            price_command,
            render_watchlist,
            callback_router,
            build_application
        )
        from wallet_manager import (
            get_or_create_wallet,
            add_to_watchlist,
            remove_from_watchlist,
            update_user_default_buy_amount
        )
        from telegram.ext import CommandHandler
        import asyncio
        from unittest.mock import AsyncMock, MagicMock, patch

        test_uid = 99556677
        get_or_create_wallet(test_uid, "PriceRadarTester", initial_language="en")
        update_user_default_buy_amount(test_uid, 0.25)
        test_mint = "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"  # BONK

        # 1. Test render_price_card with default buy size (0.25 SOL) and untracked state
        remove_from_watchlist(test_uid, test_mint)
        mock_target = MagicMock()
        mock_target.reply_text = AsyncMock()

        asyncio.run(render_price_card(mock_target, test_uid, "en", test_mint, is_edit=False))
        self.assertTrue(mock_target.reply_text.called)

        card_text = mock_target.reply_text.call_args[0][0]
        self.assertIn("Token Price & Liquidity Radar", card_text)
        self.assertIn(test_mint, card_text)

        kb = mock_target.reply_text.call_args[1]["reply_markup"]
        all_btns = [b for row in kb.inline_keyboard for b in row]

        quick_buy_btn = next((b for b in all_btns if b.callback_data == f"buy_{test_mint}_0.25"), None)
        snipe_btn = next((b for b in all_btns if b.callback_data == f"inspect_{test_mint}"), None)
        track_btn = next((b for b in all_btns if b.callback_data == f"track_{test_mint}"), None)
        refresh_btn = next((b for b in all_btns if b.callback_data == f"price_{test_mint}"), None)

        self.assertIsNotNone(quick_buy_btn, "Quick buy button must use user configured amount 0.25 SOL")
        self.assertIsNotNone(snipe_btn, "Inspect & Snipe button must exist")
        self.assertIsNotNone(track_btn, "Track button must exist when token is untracked")
        self.assertIsNotNone(refresh_btn, "Refresh price callback button must exist")

        # 2. Test render_price_card when token is already tracked flips to untrack
        add_to_watchlist(test_uid, test_mint, "BONK", 0.00002)
        mock_target_tracked = MagicMock()
        mock_target_tracked.reply_text = AsyncMock()

        asyncio.run(render_price_card(mock_target_tracked, test_uid, "en", test_mint, is_edit=False))
        kb_tracked = mock_target_tracked.reply_text.call_args[1]["reply_markup"]
        all_btns_tracked = [b for row in kb_tracked.inline_keyboard for b in row]
        untrack_btn = next((b for b in all_btns_tracked if b.callback_data == f"untrack_{test_mint}"), None)
        self.assertIsNotNone(untrack_btn, "Track button must flip to Untrack when token is in watchlist")
        self.assertIn("Untrack", untrack_btn.text)

        # 3. Test watchlist item includes Price button shortcut
        mock_wl_target = MagicMock()
        mock_wl_target.reply_text = AsyncMock()
        asyncio.run(render_watchlist(mock_wl_target, test_uid, "en", is_edit=False))
        wl_kb = mock_wl_target.reply_text.call_args[1]["reply_markup"]
        all_wl_btns = [b for row in wl_kb.inline_keyboard for b in row]
        price_wl_btn = next((b for b in all_wl_btns if b.callback_data == f"price_{test_mint}"), None)
        self.assertIsNotNone(price_wl_btn, "Watchlist row must contain direct 💵 Price shortcut button")

        # 4. Test callback_router handles price_ callback
        mock_query = MagicMock()
        mock_query.from_user.id = test_uid
        mock_query.data = f"price_{test_mint}"
        mock_query.answer = AsyncMock()
        mock_query.message.reply_chat_action = AsyncMock()
        mock_query.edit_message_text = AsyncMock()
        mock_query.message.edit_text = AsyncMock()

        mock_update = MagicMock()
        mock_update.callback_query = mock_query
        mock_ctx = MagicMock()
        mock_ctx.bot.username = "PopcornSniperBot"

        asyncio.run(callback_router(mock_update, mock_ctx))
        self.assertTrue(mock_query.answer.called)

        # 5. Test CommandHandler registration for /p, /c, and /scan
        app = build_application(MOCK_TEST_BOT_TOKEN)
        command_handlers = [h for h in app.handlers[0] if isinstance(h, CommandHandler)]
        registered_commands = set()
        for h in command_handlers:
            registered_commands.update(h.commands)

        self.assertIn("p", registered_commands)
        self.assertIn("c", registered_commands)
        self.assertIn("scan", registered_commands)

    def test_83_jupiter_quote_simulation_and_wallet_cockpit(self):
        """Test render_wallet_card cockpit, render_quote_card swap simulation, quote_command, and /quote, /sim aliases."""
        from telegram_bot import (
            render_wallet_card,
            render_quote_card,
            quote_command,
            callback_router,
            build_application,
            get_token_card_keyboard
        )
        from wallet_manager import get_or_create_wallet
        from telegram.ext import CommandHandler
        import asyncio
        from unittest.mock import AsyncMock, MagicMock, patch

        test_uid = 99667788
        get_or_create_wallet(test_uid, "QuoteTester", initial_language="en")
        test_mint = "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"  # BONK

        # 1. Test render_wallet_card
        mock_wallet_target = MagicMock()
        mock_wallet_target.reply_text = AsyncMock()
        asyncio.run(render_wallet_card(mock_wallet_target, test_uid, "en", is_edit=False))
        self.assertTrue(mock_wallet_target.reply_text.called)
        w_text = mock_wallet_target.reply_text.call_args[0][0]
        self.assertIn("Solana Trading Wallet & Deposit", w_text)
        self.assertIn("Available Balance", w_text)

        w_kb = mock_wallet_target.reply_text.call_args[1]["reply_markup"]
        all_w_btns = [b for row in w_kb.inline_keyboard for b in row]
        self.assertTrue(any(b.callback_data == "btn_show_qr" for b in all_w_btns))
        self.assertTrue(any(b.callback_data == "btn_wallet" for b in all_w_btns))

        # 2. Test render_quote_card with mocked Jupiter Quote API
        mock_quote_data = {
            "inAmount": "100000000",
            "outAmount": "332663340000",
            "otherAmountThreshold": "329336700000",
            "priceImpactPct": "0.00026",
            "routePlan": [{"swapInfo": {"label": "Whirlpool"}}],
            "platformFee": {"amount": "1000000"}
        }

        mock_quote_target = MagicMock()
        mock_quote_target.reply_text = AsyncMock()

        with patch("telegram_bot.get_jupiter_quote", return_value=mock_quote_data), \
             patch("telegram_bot.get_token_decimals", return_value=5):
            asyncio.run(render_quote_card(mock_quote_target, test_uid, "en", test_mint, 0.1, is_edit=False))
            self.assertTrue(mock_quote_target.reply_text.called)
            q_text = mock_quote_target.reply_text.call_args[0][0]
            self.assertIn("Jupiter V6 Swap Simulation Quote", q_text)
            self.assertIn("0.1000 SOL", q_text)
            self.assertIn("Whirlpool", q_text)

            q_kb = mock_quote_target.reply_text.call_args[1]["reply_markup"]
            all_q_btns = [b for row in q_kb.inline_keyboard for b in row]
            exec_btn = next((b for b in all_q_btns if b.callback_data == f"buy_{test_mint}_0.1"), None)
            radar_btn = next((b for b in all_q_btns if b.callback_data == f"price_{test_mint}"), None)
            refresh_sim_btn = next((b for b in all_q_btns if b.callback_data == f"quote_{test_mint}_0.1"), None)

            self.assertIsNotNone(exec_btn, "1-click execution buy button must exist on quote simulation card")
            self.assertIsNotNone(radar_btn, "Price radar button must exist on quote simulation card")
            self.assertIsNotNone(refresh_sim_btn, "Refresh simulation button must exist")

        # 3. Test quote_command CLI invocation
        mock_cmd_update = MagicMock()
        mock_cmd_update.effective_user.id = test_uid
        mock_status_msg = AsyncMock()
        mock_cmd_update.message.reply_text = AsyncMock(return_value=mock_status_msg)
        mock_cmd_ctx = MagicMock()
        mock_cmd_ctx.args = ["0.1", "BONK"]

        with patch("telegram_bot.render_quote_card", new_callable=AsyncMock) as mock_render_q:
            asyncio.run(quote_command(mock_cmd_update, mock_cmd_ctx))
            self.assertTrue(mock_cmd_update.message.reply_text.called)
            mock_render_q.assert_called_once()

        # 4. Test callback_router quote_ routing
        mock_cb_query = MagicMock()
        mock_cb_query.from_user.id = test_uid
        mock_cb_query.data = f"quote_{test_mint}_0.25"
        mock_cb_query.answer = AsyncMock()
        mock_cb_query.message.reply_chat_action = AsyncMock()
        mock_cb_update = MagicMock()
        mock_cb_update.callback_query = mock_cb_query

        with patch("telegram_bot.render_quote_card", new_callable=AsyncMock) as mock_render_q2:
            asyncio.run(callback_router(mock_cb_update, mock_cmd_ctx))
            mock_render_q2.assert_called_once_with(mock_cb_query, test_uid, "en", test_mint, 0.25, is_edit=True)

        # 5. Test CommandHandler registration for quote, sim, simulate
        app = build_application(MOCK_TEST_BOT_TOKEN)
        command_handlers = [h for h in app.handlers[0] if isinstance(h, CommandHandler)]
        registered_commands = set()
        for h in command_handlers:
            registered_commands.update(h.commands)

        self.assertIn("quote", registered_commands)
        self.assertIn("sim", registered_commands)
        self.assertIn("simulate", registered_commands)

        # 6. Test get_token_card_keyboard embeds price radar button
        token_kb = get_token_card_keyboard(test_mint, "en", test_uid, "BONK")
        all_t_btns = [b for row in token_kb.inline_keyboard for b in row]
        self.assertTrue(any(b.callback_data == f"price_{test_mint}" for b in all_t_btns))

    def test_84_interactive_swap_tiers_positions_shortcuts_and_resilient_quotes(self):
        """Test v3.60.0 interactive swap size tiers, positions shortcuts, and resilient quote arg parsing."""
        import asyncio
        from unittest.mock import patch, MagicMock, AsyncMock
        from telegram_bot import render_quote_card, render_positions, render_price_card, quote_command
        from wallet_manager import get_or_create_wallet

        test_uid = 99881184
        get_or_create_wallet(test_uid, "Tester84")
        test_mint = "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"

        # 1. Test render_quote_card produces interactive swap size tiers
        mock_target = MagicMock()
        mock_target.data = f"quote_{test_mint}_0.1"
        mock_target.edit_message_text = AsyncMock()

        mock_quote_res = {
            "outAmount": "18234050000",
            "otherAmountThreshold": "18051710000",
            "priceImpactPct": "0.02",
            "routePlan": [{"swapInfo": {"label": "Orca Whirlpool"}}],
            "platformFee": {"amount": "100000"}
        }

        with patch("telegram_bot.get_jupiter_quote", return_value=mock_quote_res), \
             patch("telegram_bot.get_token_decimals", return_value=5), \
             patch("telegram_bot.scan_token_security", return_value={"symbol": "BONK", "name": "Bonk", "price_usd": 0.00002}):
            asyncio.run(render_quote_card(mock_target, test_uid, "en", test_mint, 0.1, is_edit=True))
            self.assertTrue(mock_target.edit_message_text.called)
            kb = mock_target.edit_message_text.call_args[1]["reply_markup"]
            all_btns = [b for row in kb.inline_keyboard for b in row]

            # Verify tier buttons exist and active tier is marked with green dot
            tier_01_btn = next((b for b in all_btns if b.callback_data == f"quote_{test_mint}_0.1"), None)
            tier_05_btn = next((b for b in all_btns if b.callback_data == f"quote_{test_mint}_0.5"), None)
            self.assertIsNotNone(tier_01_btn)
            self.assertIn("🟢 0.1 SOL", tier_01_btn.text)
            self.assertIsNotNone(tier_05_btn)
            self.assertEqual("0.5 SOL", tier_05_btn.text)

            # Verify RugCheck inspect button on quote card
            rug_btn = next((b for b in all_btns if b.callback_data == f"inspect_{test_mint}"), None)
            self.assertIsNotNone(rug_btn)

        # 2. Test render_positions produces Quote and Price shortcuts
        mock_pos_target = AsyncMock()
        dummy_tokens = [{"mint": test_mint, "amount": 1000.0}]
        mock_batch_prices = {test_mint: {"symbol": "BONK", "price_usd": 0.00002, "change_24h": 5.0}}

        with patch("telegram_bot.get_token_accounts", return_value=dummy_tokens), \
             patch("telegram_bot.get_batch_token_prices", return_value=mock_batch_prices):
            asyncio.run(render_positions(mock_pos_target, test_uid, "en", is_edit=False))
            self.assertTrue(mock_pos_target.reply_text.called)
            kb_pos = mock_pos_target.reply_text.call_args[1]["reply_markup"]
            all_pos_btns = [b for row in kb_pos.inline_keyboard for b in row]

            quote_btn = next((b for b in all_pos_btns if b.callback_data == f"quote_{test_mint}"), None)
            price_btn = next((b for b in all_pos_btns if b.callback_data == f"price_{test_mint}"), None)
            self.assertIsNotNone(quote_btn, "Positions card must embed 1-click Quote shortcut")
            self.assertIsNotNone(price_btn, "Positions card must embed 1-click Price shortcut")

        # 3. Test render_price_card embeds Quote Sim button
        mock_price_target = AsyncMock()
        with patch("telegram_bot.scan_token_security", return_value={"symbol": "BONK", "name": "Bonk", "price_usd": 0.00002, "price_change_24h": 5.0, "liquidity_usd": 1000000, "mcap": 5000000, "volume_24h": 200000}):
            asyncio.run(render_price_card(mock_price_target, test_uid, "en", test_mint, is_edit=False))
            self.assertTrue(mock_price_target.reply_text.called)
            kb_price = mock_price_target.reply_text.call_args[1]["reply_markup"]
            all_price_btns = [b for row in kb_price.inline_keyboard for b in row]
            quote_sim_btn = next((b for b in all_price_btns if b.callback_data.startswith(f"quote_{test_mint}_")), None)
            self.assertIsNotNone(quote_sim_btn, "Price card must embed 1-click Quote Sim button")

        # 4. Test quote_command resilient arg parsing with reversed order: /quote BONK 0.5
        mock_cmd_update = MagicMock()
        mock_cmd_update.effective_user.id = test_uid
        mock_status_msg = AsyncMock()
        mock_cmd_update.message.reply_text = AsyncMock(return_value=mock_status_msg)
        mock_cmd_ctx = MagicMock()
        mock_cmd_ctx.args = ["BONK", "0.5"]

        with patch("telegram_bot.render_quote_card", new_callable=AsyncMock) as mock_render_q:
            asyncio.run(quote_command(mock_cmd_update, mock_cmd_ctx))
            self.assertTrue(mock_cmd_update.message.reply_text.called)
            call_args = mock_render_q.call_args[0]
            self.assertEqual(call_args[4], 0.5, "quote_command must extract 0.5 even when passed after ticker")

    def test_85_trending_surge_shortcuts_and_token_card_quote_navigation(self):
        """Test v3.61.0 trending/surge shortcuts and token card quote simulation navigation."""
        import asyncio
        from unittest.mock import patch, MagicMock, AsyncMock
        from telegram_bot import render_trending_radar, render_surge_radar, get_token_card_keyboard
        from wallet_manager import get_or_create_wallet

        test_uid = 99881185
        get_or_create_wallet(test_uid, "Tester85")
        test_mint = "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"

        dummy_trending = [
            {
                "symbol": "BONK",
                "mint": test_mint,
                "price_usd": 0.00002,
                "change_24h": 12.5,
                "change_1h": 2.1,
                "volume_24h": 500000,
                "liquidity": 1000000
            }
        ]

        # 1. Test render_trending_radar produces Snipe, Price, and Quote shortcuts
        mock_trend_target = AsyncMock()
        with patch("telegram_bot.get_trending_tokens", return_value=dummy_trending):
            asyncio.run(render_trending_radar(mock_trend_target, test_uid, "en", is_edit=False))
            self.assertTrue(mock_trend_target.edit_text.called or mock_trend_target.reply_text.called)
            call = mock_trend_target.edit_text if mock_trend_target.edit_text.called else mock_trend_target.reply_text
            kb = call.call_args[1]["reply_markup"]
            all_btns = [b for row in kb.inline_keyboard for b in row]

            snipe_btn = next((b for b in all_btns if b.callback_data == f"inspect_{test_mint}"), None)
            price_btn = next((b for b in all_btns if b.callback_data == f"price_{test_mint}"), None)
            quote_btn = next((b for b in all_btns if b.callback_data == f"quote_{test_mint}"), None)
            surge_link = next((b for b in all_btns if b.callback_data == "btn_surge"), None)

            self.assertIsNotNone(snipe_btn, "Trending radar must contain 1-click Snipe button")
            self.assertIsNotNone(price_btn, "Trending radar must contain 1-click Price button")
            self.assertIsNotNone(quote_btn, "Trending radar must contain 1-click Quote button")
            self.assertIsNotNone(surge_link, "Trending radar must contain Top Gainers link")

        # 2. Test render_surge_radar produces Snipe, Price, and Quote shortcuts
        mock_surge_target = AsyncMock()
        with patch("telegram_bot.get_top_gainers", return_value=dummy_trending):
            asyncio.run(render_surge_radar(mock_surge_target, test_uid, "en", is_edit=False))
            self.assertTrue(mock_surge_target.edit_text.called or mock_surge_target.reply_text.called)
            call_s = mock_surge_target.edit_text if mock_surge_target.edit_text.called else mock_surge_target.reply_text
            kb_s = call_s.call_args[1]["reply_markup"]
            all_s_btns = [b for row in kb_s.inline_keyboard for b in row]

            s_snipe = next((b for b in all_s_btns if b.callback_data == f"inspect_{test_mint}"), None)
            s_price = next((b for b in all_s_btns if b.callback_data == f"price_{test_mint}"), None)
            s_quote = next((b for b in all_s_btns if b.callback_data == f"quote_{test_mint}"), None)

            self.assertIsNotNone(s_snipe, "Surge radar must contain 1-click Snipe button")
            self.assertIsNotNone(s_price, "Surge radar must contain 1-click Price button")
            self.assertIsNotNone(s_quote, "Surge radar must contain 1-click Quote button")

        # 3. Test get_token_card_keyboard embeds Quote Sim button
        token_kb = get_token_card_keyboard(test_mint, "en", test_uid, "BONK")
        all_t_btns = [b for row in token_kb.inline_keyboard for b in row]
        token_quote_btn = next((b for b in all_t_btns if b.callback_data == f"quote_{test_mint}"), None)
        self.assertIsNotNone(token_quote_btn, "Token audit card must embed 1-click Quote button")

    def test_86_watchlist_quote_and_resilient_search(self):
        """Test v3.62.0 watchlist quote shortcut, 24h avg pulse metric, and resilient DexScreener search."""
        import asyncio
        from unittest.mock import patch, MagicMock, AsyncMock
        from rugcheck_scanner import search_solana_token
        from telegram_bot import render_watchlist
        from wallet_manager import add_to_watchlist, get_user_watchlist

        test_uid = 99881186
        test_mint = "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"
        add_to_watchlist(test_uid, test_mint, "BONK", 0.00002)

        # 1. Test DexScreener null pairs resilience
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"pairs": None}
        with patch("rugcheck_scanner._SESSION.get", return_value=mock_resp):
            res = search_solana_token("nonexistent_exotic_token")
            self.assertIsNone(res, "Null pairs from DexScreener must return None safely without raising TypeError")

        # 2. Test render_watchlist incorporates 1-click Quote button and 24h Avg Pulse
        mock_target = AsyncMock()
        dummy_batch = {
            test_mint: {
                "price_usd": 0.000025,
                "change_24h": 25.0
            }
        }
        with patch("telegram_bot.get_batch_token_prices", return_value=dummy_batch):
            asyncio.run(render_watchlist(mock_target, test_uid, "en", is_edit=False))
            self.assertTrue(mock_target.edit_text.called or mock_target.reply_text.called)
            call = mock_target.edit_text if mock_target.edit_text.called else mock_target.reply_text
            msg_text = call.call_args[0][0]
            kb = call.call_args[1]["reply_markup"]

            self.assertIn("24h Avg Pulse", msg_text)
            self.assertIn("+25.00%", msg_text)

            all_btns = [b for row in kb.inline_keyboard for b in row]
            quote_btn = next((b for b in all_btns if b.callback_data == f"quote_{test_mint}"), None)
            self.assertIsNotNone(quote_btn, "Watchlist item must contain 1-click Quote shortcut")

    def test_87_full_stack_latency_benchmark_radar(self):
        """Test v3.63.0 full-stack latency radar measuring RPC, Jupiter V6, RugCheck, and DexScreener."""
        import asyncio
        from unittest.mock import patch, MagicMock, AsyncMock
        from telegram_bot import benchmark_network_latency, render_network_ping

        # 1. Mock network responses for all 4 layers
        mock_rpc_resp = MagicMock(status_code=200)
        mock_jup_resp = MagicMock(status_code=200)
        mock_rug_resp = MagicMock(status_code=200)
        mock_dex_resp = MagicMock(status_code=200)

        def mock_get(url, *args, **kwargs):
            if "jupiter" in url:
                return mock_jup_resp
            elif "rugcheck" in url:
                return mock_rug_resp
            elif "dexscreener" in url:
                return mock_dex_resp
            return MagicMock(status_code=200)

        with patch("jupiter_engine._SESSION.post", return_value=mock_rpc_resp), \
             patch("jupiter_engine._SESSION.get", side_effect=mock_get):
            bench = benchmark_network_latency()
            self.assertIn("rpc_ms", bench)
            self.assertIn("jup_ms", bench)
            self.assertIn("rug_ms", bench)
            self.assertIn("dex_ms", bench)
            self.assertTrue(bench["rpc_ok"])
            self.assertTrue(bench["jup_ok"])
            self.assertTrue(bench["rug_ok"])
            self.assertTrue(bench["dex_ok"])

            # 2. Render English ping card
            mock_target = AsyncMock()
            asyncio.run(render_network_ping(mock_target, 99881187, "en", is_edit=False))
            self.assertTrue(mock_target.reply_text.called)
            msg_en = mock_target.reply_text.call_args[0][0]
            self.assertIn("Primary RPC", msg_en)
            self.assertIn("Jupiter V6 Routing", msg_en)
            self.assertIn("RugCheck Auditor", msg_en)
            self.assertIn("DexScreener Feed", msg_en)

            # 3. Render Arabic ping card
            mock_target.reset_mock()
            asyncio.run(render_network_ping(mock_target, 99881187, "ar", is_edit=False))
            self.assertTrue(mock_target.reply_text.called)
            msg_ar = mock_target.reply_text.call_args[0][0]
            self.assertIn("خادم سولانا الرئيسي", msg_ar)
            self.assertIn("مسارات توجيه Jupiter V6", msg_ar)
            self.assertIn("فاحص أمان RugCheck", msg_ar)
            self.assertIn("بث أسعار DexScreener", msg_ar)

    def test_88_version_card_navigation_and_help_quote_docs(self):
        """Test v3.64.0 render_version_card navigation, help menu btn_version routing, and /quote help documentation."""
        import asyncio
        from unittest.mock import patch, MagicMock, AsyncMock
        from telegram_bot import render_version_card, render_help_card
        from i18n import t

        test_uid = 99881188

        # 1. Test render_version_card navigation buttons (Releases, Latency, Back)
        mock_v_target = AsyncMock()
        asyncio.run(render_version_card(mock_v_target, test_uid, "en", is_edit=False))
        self.assertTrue(mock_v_target.reply_text.called)
        v_call = mock_v_target.reply_text
        v_text = v_call.call_args[0][0]
        v_kb = v_call.call_args[1]["reply_markup"]
        all_v_btns = [b for row in v_kb.inline_keyboard for b in row]

        self.assertIn("Software Release:", v_text)
        self.assertIn("Production", v_text)
        self.assertIsNotNone(next((b for b in all_v_btns if b.url and "releases" in b.url), None))
        self.assertIsNotNone(next((b for b in all_v_btns if b.callback_data == "btn_ping"), None))
        self.assertIsNotNone(next((b for b in all_v_btns if b.callback_data == "btn_help"), None))

        # 2. Test render_help_card contains btn_version and btn_ping
        mock_h_target = AsyncMock()
        asyncio.run(render_help_card(mock_h_target, test_uid, "en", is_edit=False))
        self.assertTrue(mock_h_target.reply_text.called)
        h_kb = mock_h_target.reply_text.call_args[1]["reply_markup"]
        all_h_btns = [b for row in h_kb.inline_keyboard for b in row]

        self.assertIsNotNone(next((b for b in all_h_btns if b.callback_data == "btn_version"), None))
        self.assertIsNotNone(next((b for b in all_h_btns if b.callback_data == "btn_ping"), None))

        # 3. Test bilingual help_body contains /quote documentation
        help_en = t("help_body", "en")
        help_ar = t("help_body", "ar")
        self.assertIn("/quote", help_en)
        self.assertIn("/sim", help_en)
        self.assertIn("/quote", help_ar)
        self.assertIn("/sim", help_ar)

    def test_89_multi_word_token_query_resilience(self):
        """Test v3.65.0 multi-word token query resilience across /price, /audit, /quote, and /track."""
        import asyncio
        from unittest.mock import patch, MagicMock, AsyncMock
        from telegram_bot import price_command, audit_command, quote_command, track_command

        test_uid = 99881189
        dummy_match = {"mint": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263", "symbol": "POPCAT"}

        # 1. Test price_command joins multi-word args: /price pepe coin
        p_update = MagicMock()
        p_update.effective_user.id = test_uid
        p_update.message.reply_text = AsyncMock(return_value=AsyncMock())
        p_ctx = MagicMock()
        p_ctx.args = ["pepe", "coin"]
        with patch("telegram_bot.search_solana_token", return_value=dummy_match) as mock_search, \
             patch("telegram_bot.render_price_card", new_callable=AsyncMock) as mock_rpc:
            asyncio.run(price_command(p_update, p_ctx))
            mock_search.assert_called_with("pepe coin")

        # 2. Test audit_command joins multi-word args: /audit ai 16z
        a_update = MagicMock()
        a_update.effective_user.id = test_uid
        a_update.message.reply_text = AsyncMock(return_value=AsyncMock())
        a_ctx = MagicMock()
        a_ctx.args = ["ai", "16z"]
        with patch("telegram_bot.search_solana_token", return_value=dummy_match) as mock_search, \
             patch("telegram_bot.scan_token_security", return_value={"mint": dummy_match["mint"], "symbol": "AI16Z", "rug_score": 1, "risks": []}):
            asyncio.run(audit_command(a_update, a_ctx))
            mock_search.assert_called_with("ai 16z")

        # 3. Test quote_command with multi-word token and amount first: /quote 0.5 pop cat
        q_update = MagicMock()
        q_update.effective_user.id = test_uid
        q_update.message.reply_text = AsyncMock(return_value=AsyncMock())
        q_ctx1 = MagicMock()
        q_ctx1.args = ["0.5", "pop", "cat"]
        with patch("telegram_bot.search_solana_token", return_value=dummy_match) as mock_search, \
             patch("telegram_bot.render_quote_card", new_callable=AsyncMock) as mock_rq:
            asyncio.run(quote_command(q_update, q_ctx1))
            mock_search.assert_called_with("pop cat")
            self.assertEqual(mock_rq.call_args[0][4], 0.5)

        # 4. Test quote_command with multi-word token and amount last: /quote pop cat 0.5
        q_ctx2 = MagicMock()
        q_ctx2.args = ["pop", "cat", "0.5"]
        with patch("telegram_bot.search_solana_token", return_value=dummy_match) as mock_search, \
             patch("telegram_bot.render_quote_card", new_callable=AsyncMock) as mock_rq:
            asyncio.run(quote_command(q_update, q_ctx2))
            mock_search.assert_called_with("pop cat")
            self.assertEqual(mock_rq.call_args[0][4], 0.5)

        # 5. Test track_command joins multi-word args: /track doge 2.0
        t_update = MagicMock()
        t_update.effective_user.id = test_uid
        t_update.message.reply_text = AsyncMock()
        t_ctx = MagicMock()
        t_ctx.args = ["doge", "2.0"]
        with patch("telegram_bot.search_solana_token", return_value=dummy_match) as mock_search, \
             patch("telegram_bot.add_to_watchlist") as mock_add, \
             patch("telegram_bot.scan_token_security", return_value={"price_usd": 0.05, "symbol": "DOGE2"}):
            asyncio.run(track_command(t_update, t_ctx))
            mock_search.assert_called_with("doge 2.0")
            self.assertTrue(mock_add.called)

    def test_90_pnl_success_rate_metric_and_watchlist_button(self):
        """Test v3.66.0 render_pnl_card execution success rate metric and watchlist button integration."""
        import asyncio
        from unittest.mock import patch, MagicMock, AsyncMock
        from telegram_bot import render_pnl_card

        test_uid = 99881190
        mock_user = MagicMock()
        mock_user.username = "alpha_trader"
        mock_user.first_name = "Alpha"

        # 1. Test English render_pnl_card with custom stats (87.5% success rate)
        mock_target_en = AsyncMock()
        custom_stats = {
            "total_trades": 8,
            "confirmed_trades": 7,
            "success_rate_pct": 87.5,
            "total_volume_sol": 12.345,
            "total_fees_sol": 0.12345,
            "recent_trades": []
        }
        with patch("telegram_bot.get_user_trade_stats", return_value=custom_stats):
            asyncio.run(render_pnl_card(mock_target_en, mock_user, test_uid, "en", is_edit=False))
            self.assertTrue(mock_target_en.reply_text.called)
            msg_en = mock_target_en.reply_text.call_args[0][0]
            kb_en = mock_target_en.reply_text.call_args[1]["reply_markup"]
            cbs_en = [b.callback_data for row in kb_en.inline_keyboard for b in row if b.callback_data]

            self.assertIn("Execution Success Rate", msg_en)
            self.assertIn("87.5%", msg_en)
            self.assertIn("btn_watchlist", cbs_en)
            self.assertIn("btn_positions", cbs_en)
            self.assertIn("btn_trending", cbs_en)

        # 2. Test Arabic render_pnl_card with default stats (100.0% success rate)
        mock_target_ar = AsyncMock()
        default_stats = {
            "total_trades": 0,
            "confirmed_trades": 0,
            "success_rate_pct": 100.0,
            "total_volume_sol": 0.0,
            "total_fees_sol": 0.0,
            "recent_trades": []
        }
        with patch("telegram_bot.get_user_trade_stats", return_value=default_stats):
            asyncio.run(render_pnl_card(mock_target_ar, mock_user, test_uid, "ar", is_edit=False))
            self.assertTrue(mock_target_ar.reply_text.called)
            msg_ar = mock_target_ar.reply_text.call_args[0][0]
            kb_ar = mock_target_ar.reply_text.call_args[1]["reply_markup"]
            cbs_ar = [b.callback_data for row in kb_ar.inline_keyboard for b in row if b.callback_data]

            self.assertIn("معدل نجاح التنفيذ", msg_ar)
            self.assertIn("100.0%", msg_ar)
            self.assertIn("btn_watchlist", cbs_ar)

    def test_91_csv_export_callback_and_command_parity(self):
        """Test v3.67.0 CSV export callback parity across /pnl and /history, and dedicated /csv slash command."""
        import asyncio
        from unittest.mock import patch, MagicMock, AsyncMock
        from telegram_bot import csv_command, callback_router, build_application
        from telegram.ext import CommandHandler

        test_uid = 99881191

        # 1. Test dedicated /csv slash command calls send_trades_csv_export
        mock_update = MagicMock()
        mock_update.effective_user.id = test_uid
        mock_update.message = AsyncMock()
        mock_context = MagicMock()

        with patch("telegram_bot.send_trades_csv_export", new_callable=AsyncMock) as mock_send:
            asyncio.run(csv_command(mock_update, mock_context))
            self.assertTrue(mock_send.called)
            self.assertEqual(mock_send.call_args[0][1], test_uid)

        # 2. Test callback_router routing with btn_history_csv (from PnL card)
        mock_query_pnl = MagicMock()
        mock_query_pnl.from_user.id = test_uid
        mock_query_pnl.data = "btn_history_csv"
        mock_query_pnl.answer = AsyncMock()
        mock_update_pnl = MagicMock(callback_query=mock_query_pnl)

        with patch("telegram_bot.send_trades_csv_export", new_callable=AsyncMock) as mock_send_pnl:
            asyncio.run(callback_router(mock_update_pnl, mock_context))
            self.assertTrue(mock_query_pnl.answer.called)
            self.assertTrue(mock_send_pnl.called)
            self.assertEqual(mock_send_pnl.call_args[0][1], test_uid)

        # 3. Test callback_router routing with btn_export_trades_csv (from History card)
        mock_query_hist = MagicMock()
        mock_query_hist.from_user.id = test_uid
        mock_query_hist.data = "btn_export_trades_csv"
        mock_query_hist.answer = AsyncMock()
        mock_update_hist = MagicMock(callback_query=mock_query_hist)

        with patch("telegram_bot.send_trades_csv_export", new_callable=AsyncMock) as mock_send_hist:
            asyncio.run(callback_router(mock_update_hist, mock_context))
            self.assertTrue(mock_query_hist.answer.called)
            self.assertTrue(mock_send_hist.called)
            self.assertEqual(mock_send_hist.call_args[0][1], test_uid)

        # 4. Verify /csv and /tradescsv are registered commands in build_application
        app = build_application(MOCK_TEST_BOT_TOKEN)
        command_handlers = [h for h in app.handlers[0] if isinstance(h, CommandHandler)]
        registered_commands = set()
        for h in command_handlers:
            registered_commands.update(h.commands)

        self.assertIn("csv", registered_commands)
        self.assertIn("tradescsv", registered_commands)

    def test_92_multi_word_buy_sell_and_untrack_resilience(self):
        """Test v3.68.0 multi-word token query and argument resilience across /buy, /sell, and /untrack."""
        import asyncio
        from unittest.mock import patch, MagicMock, AsyncMock
        from telegram_bot import buy_command, sell_command, untrack_command

        test_uid = 99881192
        dummy_match = {"mint": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263", "symbol": "POPCAT"}

        # 1. Test buy_command with amount first: /buy 0.2 pepe coin
        b_update1 = MagicMock()
        b_update1.effective_user.id = test_uid
        b_update1.message.reply_text = AsyncMock(return_value=AsyncMock())
        b_ctx1 = MagicMock()
        b_ctx1.args = ["0.2", "pepe", "coin"]

        with patch("telegram_bot.search_solana_token", return_value=dummy_match) as mock_b_search, \
             patch("telegram_bot.execute_buy_swap", return_value=(True, "sig_b1", 1000.0)):
            asyncio.run(buy_command(b_update1, b_ctx1))
            mock_b_search.assert_called_with("pepe coin")

        # 2. Test buy_command with amount last: /buy pepe coin 0.5
        b_update2 = MagicMock()
        b_update2.effective_user.id = test_uid
        b_update2.message.reply_text = AsyncMock(return_value=AsyncMock())
        b_ctx2 = MagicMock()
        b_ctx2.args = ["pepe", "coin", "0.5"]

        with patch("telegram_bot.search_solana_token", return_value=dummy_match) as mock_b_search2, \
             patch("telegram_bot.execute_buy_swap", return_value=(True, "sig_b2", 1000.0)):
            asyncio.run(buy_command(b_update2, b_ctx2))
            mock_b_search2.assert_called_with("pepe coin")

        # 3. Test sell_command with percentage first: /sell 50 pepe coin
        s_update1 = MagicMock()
        s_update1.effective_user.id = test_uid
        s_update1.message.reply_text = AsyncMock(return_value=AsyncMock())
        s_ctx1 = MagicMock()
        s_ctx1.args = ["50", "pepe", "coin"]

        with patch("telegram_bot.search_solana_token", return_value=dummy_match) as mock_s_search1, \
             patch("telegram_bot.get_user_keypair", return_value=None), \
             patch("telegram_bot.execute_sell_swap", return_value=(True, "sig_s1", 0.15)) as mock_sell_exec:
            asyncio.run(sell_command(s_update1, s_ctx1))
            mock_s_search1.assert_called_with("pepe coin")
            self.assertEqual(mock_sell_exec.call_args[0][2], 50)

        # 4. Test sell_command with percentage last: /sell pepe coin all
        s_update2 = MagicMock()
        s_update2.effective_user.id = test_uid
        s_update2.message.reply_text = AsyncMock(return_value=AsyncMock())
        s_ctx2 = MagicMock()
        s_ctx2.args = ["pepe", "coin", "all"]

        with patch("telegram_bot.search_solana_token", return_value=dummy_match) as mock_s_search2, \
             patch("telegram_bot.get_user_keypair", return_value=None), \
             patch("telegram_bot.execute_sell_swap", return_value=(True, "sig_s2", 0.30)) as mock_sell_exec2:
            asyncio.run(sell_command(s_update2, s_ctx2))
            mock_s_search2.assert_called_with("pepe coin")
            self.assertEqual(mock_sell_exec2.call_args[0][2], 100)

        # 5. Test untrack_command with multi-word token: /untrack doge 2.0
        u_update = MagicMock()
        u_update.effective_user.id = test_uid
        u_update.message.reply_text = AsyncMock()
        u_ctx = MagicMock()
        u_ctx.args = ["doge", "2.0"]

        with patch("telegram_bot.search_solana_token", return_value=dummy_match) as mock_u_search, \
             patch("telegram_bot.get_user_watchlist", return_value=[]), \
             patch("telegram_bot.remove_from_watchlist", return_value=True) as mock_u_rem:
            asyncio.run(untrack_command(u_update, u_ctx))
            mock_u_search.assert_called_with("doge 2.0")
            mock_u_rem.assert_called_with(test_uid, dummy_match["mint"])

    def test_93_dexscreener_null_safety_and_chat_multiword_search(self):
        """Test v3.69.0 DexScreener null-field safety and handle_text_message multi-word token query routing."""
        import asyncio
        from unittest.mock import patch, MagicMock, AsyncMock
        from rugcheck_scanner import search_solana_token, scan_token_security
        from telegram_bot import handle_text_message

        test_uid = 99881193

        # 1. Test search_solana_token resilience against null fields
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "pairs": [
                {
                    "chainId": "solana",
                    "baseToken": {"address": "So11111111111111111111111111111111111111112", "symbol": "TEST", "name": "Test Token"},
                    "liquidity": None,  # Often None on newly launched pools
                    "volume": None,     # Often None on low-volume pools
                    "priceUsd": "0.001"
                }
            ]
        }
        with patch("rugcheck_scanner._SESSION.get", return_value=mock_resp) as mock_get:
            result = search_solana_token("test token")
            self.assertIsNotNone(result)
            self.assertEqual(result["mint"], "So11111111111111111111111111111111111111112")
            self.assertEqual(result["liquidity_usd"], 0.0)
            self.assertEqual(result["volume_24h"], 0.0)
            self.assertEqual(mock_get.call_args[1]["params"], {"q": "test token"})

        # 2. Test scan_token_security resilience against null liquidity in DexScreener
        mock_dex_resp = MagicMock()
        mock_dex_resp.status_code = 200
        mock_dex_resp.json.return_value = {
            "pairs": [
                {
                    "chainId": "solana",
                    "baseToken": {"symbol": "TEST", "name": "Test Token"},
                    "liquidity": None,
                    "volume": None,
                    "priceChange": None
                }
            ]
        }
        mock_rug_resp = MagicMock()
        mock_rug_resp.status_code = 200
        mock_rug_resp.json.return_value = {"score": 50, "risks": []}

        with patch("rugcheck_scanner._SESSION.get", side_effect=[mock_dex_resp, mock_rug_resp]):
            scan = scan_token_security("So11111111111111111111111111111111111111112")
            self.assertEqual(scan["liquidity_usd"], 0.0)
            self.assertEqual(scan["volume_24h"], 0.0)

        # 3. Test handle_text_message resolves multi-word token (e.g. "pepe coin")
        mock_update = MagicMock()
        mock_update.effective_user.id = test_uid
        mock_msg = MagicMock()
        mock_msg.text = "pepe coin"
        mock_msg.reply_text = AsyncMock()
        mock_update.message = mock_msg
        mock_context = MagicMock()
        mock_context.user_data = {}

        dummy_match = {"mint": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263", "symbol": "POPCAT"}
        dummy_scan = {"symbol": "PEPE", "name": "Pepe Coin", "price_usd": 0.01, "mcap": 1000000, "liquidity_usd": 50000, "price_change_24h": 5.0, "status": "SAFE", "rug_score": 10, "risks": []}

        with patch("telegram_bot.search_solana_token", return_value=dummy_match) as mock_search, \
             patch("telegram_bot.scan_token_security", return_value=dummy_scan):
            asyncio.run(handle_text_message(mock_update, mock_context))
            mock_search.assert_called_with("pepe coin")
            self.assertTrue(mock_msg.reply_text.called)

    def test_94_trending_and_batch_prices_null_safety(self):
        """Test v3.70.0 DexScreener null safety in trending engine, batch prices, and quote card rendering."""
        import asyncio
        from unittest.mock import patch, MagicMock, AsyncMock
        from trending_engine import get_trending_tokens, get_batch_token_prices
        from telegram_bot import render_quote_card

        test_uid = 99881194

        import trending_engine
        trending_engine._TRENDING_CACHE["timestamp"] = 0
        trending_engine._TRENDING_CACHE["data"] = []

        # 1. Test get_trending_tokens with null fields in DexScreener pairs
        mock_resp_boosts = MagicMock()
        mock_resp_boosts.status_code = 200
        mock_resp_boosts.json.return_value = [
            {"chainId": "solana", "tokenAddress": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"}
        ]

        mock_resp_pairs = MagicMock()
        mock_resp_pairs.status_code = 200
        mock_resp_pairs.json.return_value = {
            "pairs": [
                {
                    "chainId": "solana",
                    "baseToken": {"address": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263", "symbol": "BONK", "name": "Bonk"},
                    "liquidity": None,
                    "volume": None,
                    "priceChange": None,
                    "priceUsd": "0.00003"
                }
            ]
        }

        with patch("trending_engine._SESSION.get", side_effect=[mock_resp_boosts, mock_resp_pairs]):
            trending = get_trending_tokens(limit=1)
            self.assertEqual(len(trending), 1)
            self.assertEqual(trending[0]["symbol"], "BONK")
            self.assertEqual(trending[0]["liquidity"], 0.0)
            self.assertEqual(trending[0]["volume_24h"], 0.0)

        # 2. Test get_batch_token_prices with null fields
        mock_resp_batch = MagicMock()
        mock_resp_batch.status_code = 200
        mock_resp_batch.json.return_value = {
            "pairs": [
                {
                    "baseToken": {"address": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263", "symbol": "BONK", "name": "Bonk"},
                    "liquidity": None,
                    "priceChange": None,
                    "priceUsd": "0.00003"
                }
            ]
        }

        with patch("trending_engine._SESSION.get", return_value=mock_resp_batch):
            prices = get_batch_token_prices(["DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"])
            self.assertIn("DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263", prices)
            self.assertEqual(prices["DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"]["liquidity"], 0.0)
            self.assertEqual(prices["DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"]["change_24h"], 0.0)

        # 3. Test render_quote_card with null platformFee and null swapInfo
        mock_target = AsyncMock()
        mock_quote_null = {
            "inAmount": "100000000",
            "outAmount": "5000000000",
            "otherAmountThreshold": "4950000000",
            "priceImpactPct": "0.01",
            "routePlan": [
                {"swapInfo": None}
            ],
            "platformFee": None
        }

        with patch("telegram_bot.get_user_settings", return_value={"slippage_bps": 100}), \
             patch("telegram_bot.get_jupiter_quote", return_value=mock_quote_null), \
             patch("telegram_bot.scan_token_security", return_value={"symbol": "BONK", "price_usd": 0.00003, "mint": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"}):
            asyncio.run(render_quote_card(mock_target, test_uid, "en", "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263", 0.1, is_edit=False))
            self.assertTrue(mock_target.reply_text.called)

    def test_95_start_deep_link_token_and_compound_referral(self):
        """Test v3.71.0 /start token deep-links, compound referral+token, and /snipe alias."""
        import asyncio
        from unittest.mock import patch, MagicMock, AsyncMock
        from telegram_bot import start_command, build_application
        from telegram.ext import CommandHandler
        from wallet_manager import get_referral_stats

        test_mint = "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"
        fake_scan = {
            "mint": test_mint,
            "symbol": "BONK",
            "name": "Bonk",
            "price_usd": 0.00003,
            "mcap": 2000000000,
            "liquidity_usd": 15000000,
            "price_change_24h": 12.5,
            "price_change_1h": 2.1,
            "status": "SAFE",
            "rug_score": 0,
            "risks": []
        }

        # 1. Test /start token_<mint>
        mock_update = MagicMock()
        mock_update.effective_user.id = 99881195
        mock_update.effective_user.username = "trader_deep"
        mock_update.effective_user.first_name = "Trader"
        mock_update.effective_user.language_code = "en"
        mock_update.message.reply_text = AsyncMock()

        mock_context = MagicMock()
        mock_context.args = [f"token_{test_mint}"]

        with patch("telegram_bot.scan_token_security", return_value=fake_scan):
            asyncio.run(start_command(mock_update, mock_context))
            self.assertTrue(mock_update.message.reply_text.called)
            sent_text = mock_update.message.reply_text.call_args[0][0]
            self.assertIn("$BONK", sent_text)
            self.assertIn("DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263", sent_text)
            kb = mock_update.message.reply_text.call_args[1]["reply_markup"]
            all_cbs = [b.callback_data for row in kb.inline_keyboard for b in row if b.callback_data]
            self.assertIn(f"buy_{test_mint}_0.05", all_cbs)
            self.assertIn(f"buy_{test_mint}_0.1", all_cbs)

        # 2. Test compound /start ref_<id>_token_<mint>
        mock_update2 = MagicMock()
        ref_uid = 99881196
        mock_update2.effective_user.id = ref_uid
        mock_update2.effective_user.username = "trader_ref"
        mock_update2.effective_user.first_name = "ReferredTrader"
        mock_update2.effective_user.language_code = "en"
        mock_update2.message.reply_text = AsyncMock()

        from wallet_manager import get_referral_stats, get_or_create_wallet

        referrer_id = 77112233
        get_or_create_wallet(referrer_id, "referrer_boss")
        mock_context2 = MagicMock()
        mock_context2.args = [f"ref_{referrer_id}_token_{test_mint}"]
        mock_context2.bot.send_message = AsyncMock()

        with patch("telegram_bot.scan_token_security", return_value=fake_scan):
            asyncio.run(start_command(mock_update2, mock_context2))
            self.assertTrue(mock_update2.message.reply_text.called)
            sent_text2 = mock_update2.message.reply_text.call_args[0][0]
            self.assertIn("$BONK", sent_text2)
            # Verify referral was attributed
            ref_stats = get_referral_stats(referrer_id)
            self.assertGreaterEqual(ref_stats["total_referrals"], 1)

        # 3. Test /snipe and /token command handler registration
        app = build_application(MOCK_TEST_BOT_TOKEN)
        command_handlers = [h for h in app.handlers[0] if isinstance(h, CommandHandler)]
        registered_commands = set()
        for h in command_handlers:
            registered_commands.update(h.commands)
        self.assertIn("snipe", registered_commands)
        self.assertIn("token", registered_commands)

    def test_96_deposit_qr_buffer_cache_and_insufficient_balance_keyboard(self):
        """Test v3.74.0 deposit QR buffer in-memory caching and high-converting deposit funnel."""
        import asyncio
        from unittest.mock import AsyncMock, MagicMock, patch
        from wallet_manager import generate_deposit_qr_buffer, _DEPOSIT_QR_CACHE, get_or_create_wallet
        from telegram_bot import callback_router

        test_pubkey = "7kz1mcQcaZhYzFUHBFHH6s5tGrDHc7gNhN5WAUyXyq5r"
        _DEPOSIT_QR_CACHE.clear()

        # 1. Test QR buffer generation and caching
        buf1 = generate_deposit_qr_buffer(test_pubkey)
        bytes1 = buf1.getvalue()
        self.assertTrue(bytes1.startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertIn(test_pubkey, _DEPOSIT_QR_CACHE)

        buf2 = generate_deposit_qr_buffer(test_pubkey)
        bytes2 = buf2.getvalue()
        self.assertEqual(bytes1, bytes2)

        # 2. Test insufficient balance deposit routing keyboard
        test_uid = 99881197
        get_or_create_wallet(test_uid, "low_sol_trader")
        test_mint = "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"

        mock_update = MagicMock()
        mock_query = MagicMock()
        mock_query.from_user.id = test_uid
        mock_query.from_user.username = "low_sol_trader"
        mock_query.data = f"buy_{test_mint}_0.5"
        mock_query.answer = AsyncMock()
        mock_query.edit_message_text = AsyncMock()
        mock_update.callback_query = mock_query

        mock_context = MagicMock()
        mock_context.bot.username = "PopcornSniperBot"

        with patch("telegram_bot.get_sol_balance", return_value=0.0):
            asyncio.run(callback_router(mock_update, mock_context))
            self.assertTrue(mock_query.edit_message_text.called)
            sent_text = mock_query.edit_message_text.call_args[0][0]
            markup = mock_query.edit_message_text.call_args[1]["reply_markup"]
            self.assertIn("Insufficient SOL balance", sent_text)
            
            button_callbacks = [btn.callback_data for row in markup.inline_keyboard for btn in row]
            self.assertIn("btn_show_qr", button_callbacks)
            self.assertIn(f"buy_{test_mint}_0.5", button_callbacks)
            self.assertIn("btn_refresh", button_callbacks)

        # 3. Test btn_show_qr navigation keyboard includes btn_refresh
        mock_query.data = "btn_show_qr"
        mock_query.message.reply_photo = AsyncMock()
        asyncio.run(callback_router(mock_update, mock_context))
        self.assertTrue(mock_query.message.reply_photo.called)
        qr_markup = mock_query.message.reply_photo.call_args[1]["reply_markup"]
        qr_callbacks = [btn.callback_data for row in qr_markup.inline_keyboard for btn in row]
        self.assertIn("btn_wallet", qr_callbacks)
        self.assertIn("btn_refresh", qr_callbacks)

    def test_97_token_card_deposit_button_and_new_user_deep_link_onboarding(self):
        """Test v3.75.0 token card 1-tap deposit button and new user deep link onboarding header."""
        import asyncio
        from unittest.mock import AsyncMock, MagicMock, patch
        from telegram_bot import get_token_card_keyboard, start_command

        test_mint = "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"
        test_uid = 99881198

        # 1. Test get_token_card_keyboard embeds direct btn_show_qr
        kb_en = get_token_card_keyboard(test_mint, user_lang="en", user_id=test_uid, symbol="BONK")
        all_cbs = [btn.callback_data for row in kb_en.inline_keyboard for btn in row if btn.callback_data]
        self.assertIn("btn_show_qr", all_cbs)
        self.assertIn("btn_refresh", all_cbs)

        # 2. Test start_command with token_ deep link on brand new user prepends onboarding wallet info
        import random
        import sqlite3
        from config import DB_PATH
        new_uid = random.randint(900_000_000, 999_999_999)
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("DELETE FROM users WHERE user_id = ?", (new_uid,))
            conn.commit()

        mock_update = MagicMock()
        mock_update.effective_user.id = new_uid
        mock_update.effective_user.username = "alpha_newbie"
        mock_update.effective_user.first_name = "Alpha"
        mock_update.effective_user.language_code = "en"
        mock_update.message.reply_text = AsyncMock()

        mock_context = MagicMock()
        mock_context.args = [f"token_{test_mint}"]

        fake_scan = {
            "mint": test_mint,
            "symbol": "BONK",
            "name": "Bonk",
            "price_usd": 0.000025,
            "rug_score": 10,
            "status": "SAFE",
            "risks": []
        }

        with patch("telegram_bot.scan_token_security", return_value=fake_scan):
            asyncio.run(start_command(mock_update, mock_context))
            self.assertTrue(mock_update.message.reply_text.called)
            sent_text = mock_update.message.reply_text.call_args[0][0]
            markup = mock_update.message.reply_text.call_args[1]["reply_markup"]
            self.assertIn("Welcome to Popcorn Sniper", sent_text)
            self.assertIn("BONK", sent_text)
            deep_cbs = [btn.callback_data for row in markup.inline_keyboard for btn in row if btn.callback_data]
            self.assertIn("btn_show_qr", deep_cbs)

    def test_98_pump_fun_venue_and_direct_card_button(self):
        """Test v3.76.0 Pump.fun venue detection, dynamic link button, and bonding curve routing."""
        from rugcheck_scanner import format_token_card
        from telegram_bot import get_token_card_keyboard

        pump_mint = "61V8vBaqAGMpgDQi4Jcgoc1vSEKqTY4WbRC26EkDpump"
        standard_mint = "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"

        # 1. Test format_token_card identifies Pump.fun venue
        pump_scan = {
            "mint": pump_mint,
            "symbol": "PIPPIN",
            "name": "Pippin",
            "price_usd": 0.05,
            "status": "SAFE",
            "rug_score": 15
        }
        card_en = format_token_card(pump_scan, lang="en")
        self.assertIn("Pump.fun", card_en)

        # 2. Test get_token_card_keyboard embeds direct Pump.fun link button
        kb_pump = get_token_card_keyboard(pump_mint, "en", 99881177, "PIPPIN")
        pump_btns = [b for row in kb_pump.inline_keyboard for b in row if b.url]
        pump_url_btn = next((b for b in pump_btns if "pump.fun" in b.url), None)
        self.assertIsNotNone(pump_url_btn, "Pump.fun button must be present for pump tokens")
        self.assertEqual(pump_url_btn.url, f"https://pump.fun/coin/{pump_mint}")

        # 3. Test non-pump tokens do not embed Pump.fun link
        kb_std = get_token_card_keyboard(standard_mint, "en", 99881177, "BONK")
        std_btns = [b for row in kb_std.inline_keyboard for b in row if b.url]
        std_pump_btn = next((b for b in std_btns if "pump.fun" in b.url), None)
        self.assertIsNone(std_pump_btn, "Pump.fun button should not be present for non-pump tokens")


if __name__ == "__main__":
    unittest.main()






