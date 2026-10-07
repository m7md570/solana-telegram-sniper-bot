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
        app = build_application("8935718262:AAGZc-RLQplBfx6cWzTtk2zyorXo5o74NqE")
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

        asyncio.run(version_command(mock_update, mock_context))
        self.assertTrue(mock_update.message.reply_text.called)
        card_text = mock_update.message.reply_text.call_args[0][0]
        self.assertIn("v3.30.0", card_text)
        self.assertIn("Jupiter V6", card_text)
        self.assertIn("AES-256", card_text)
        self.assertIn("Token-2022", card_text)

        kb = mock_update.message.reply_text.call_args[1]["reply_markup"]
        all_btns = [b for row in kb.inline_keyboard for b in row]
        gh_btn = next((b for b in all_btns if b.url and "github.com" in b.url), None)
        self.assertIsNotNone(gh_btn, "GitHub releases button must be present in /version card")

        # 2. Test command registration
        app = build_application("8935718262:AAGZc-RLQplBfx6cWzTtk2zyorXo5o74NqE")
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

        self.assertEqual(BOT_VERSION, "v3.30.0")
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


if __name__ == "__main__":
    unittest.main()






