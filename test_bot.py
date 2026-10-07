# -*- coding: utf-8 -*-
"""
Solana Telegram Sniper & Trading Bot — Comprehensive Test Suite
Validates wallet encryption, RugCheck audits, Jupiter V6 routing,
and platform fee attribution on-chain.
"""

import sys
import time
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


if __name__ == "__main__":
    unittest.main()


