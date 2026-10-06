# -*- coding: utf-8 -*-
"""
Solana Telegram Sniper & Trading Bot — Enterprise Master Interface (v3.1)
High-velocity decentralized trading bot on Solana with:
- Sub-400ms Jupiter V6 swap routing & 1.0% developer fee distribution
- Full Dual-Language Internationalization (English default 🇬🇧 / Arabic 🇸🇦)
- Real-time DexScreener Trending tokens radar (/trending)
- Viral 25% Affiliate & Referral system (/referral)
- Auto-Snipe mode (Instant 1-click buys on CA paste)
- Live RugCheck & DexScreener audit cards with HTML rendering
- Non-custodial AES-256 local wallet encryption & native /withdraw support
"""

import os
import sys

# Force UTF-8 encoding on Windows console
if sys.stdout is not None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
if sys.stderr is not None:
    try:
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import asyncio
import logging
import datetime
import html
from typing import Optional, Dict, Any, List

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.error import BadRequest, TelegramError
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from config import (
    TELEGRAM_BOT_TOKEN,
    DEVELOPER_WALLET,
    PLATFORM_FEE_BPS,
    WSOL_MINT,
    USDC_MINT
)
from wallet_manager import (
    get_or_create_wallet,
    get_sol_balance,
    get_user_keypair,
    export_private_key_b58,
    get_user_settings,
    update_user_slippage,
    get_token_accounts,
    withdraw_sol,
    record_referral,
    get_referral_stats,
    get_auto_buy_settings,
    toggle_auto_buy,
    set_auto_buy_amount,
    get_user_language,
    set_user_language
)
from rugcheck_scanner import scan_token_security, format_token_card, extract_token_mint
from jupiter_engine import (
    get_jupiter_quote,
    build_and_sign_swap_tx,
    broadcast_transaction,
    record_trade_db,
    execute_sell_swap
)
from trending_engine import get_trending_tokens, format_trending_list
from i18n import t

# Logging configuration
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger("SolanaSniperBot")


def get_current_time_str() -> str:
    """Returns local formatted time string for UI freshness."""
    return datetime.datetime.now().strftime("%I:%M:%S %p")


def get_main_menu_keyboard(user_id: int, lang: str = "en") -> InlineKeyboardMarkup:
    """Builds the main dashboard keyboard with bilingual support."""
    auto_enabled, auto_amt = get_auto_buy_settings(user_id)
    auto_badge = t("enabled", lang) if auto_enabled else t("disabled", lang)
    lang_toggle_btn = t("btn_lang_toggle", lang)

    keyboard = [
        [
            InlineKeyboardButton(t("btn_snipe_guide", lang), callback_data="btn_snipe_guide")
        ],
        [
            InlineKeyboardButton(t("btn_trending", lang), callback_data="btn_trending"),
            InlineKeyboardButton(t("btn_wallet", lang), callback_data="btn_wallet")
        ],
        [
            InlineKeyboardButton(t("btn_referral", lang), callback_data="btn_referral"),
            InlineKeyboardButton(t("btn_positions", lang), callback_data="btn_positions")
        ],
        [
            InlineKeyboardButton(f"{t('btn_autobuy', lang)} ({auto_badge})", callback_data="btn_autobuy_settings"),
            InlineKeyboardButton(t("btn_settings", lang), callback_data="btn_settings")
        ],
        [
            InlineKeyboardButton(lang_toggle_btn, callback_data="btn_toggle_lang")
        ],
        [
            InlineKeyboardButton(t("btn_withdraw", lang), callback_data="btn_withdraw_guide"),
            InlineKeyboardButton(t("btn_refresh", lang), callback_data="btn_refresh")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def build_welcome_text(user, pubkey: str, balance: float, now_str: str, lang: str = "en") -> str:
    """Constructs the executive dashboard card in user's preferred language."""
    username = user.username or user.first_name or ("Trader" if lang == "en" else "المتداول")
    return (
        f"{t('welcome_title', lang)}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{t('trader', lang)}: @{html.escape(username)}\n"
        f"{t('wallet_dedicated', lang)}:\n"
        f"<code>{pubkey}</code>\n\n"
        f"{t('current_balance', lang)}: <code>{balance:.4f} SOL</code>\n"
        f"{t('platform_fee', lang)}\n"
        f"{t('updated_at', lang)}: <code>{now_str}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{t('how_to_start_title', lang)}\n"
        f"{t('how_to_start_steps', lang)}\n"
    )


async def safe_edit_text(query, text: str, reply_markup=None):
    """Safely edits message text while preventing 'Message is not modified' errors."""
    try:
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=reply_markup, disable_web_page_preview=True)
    except BadRequest as e:
        if "Message is not modified" in str(e):
            await query.answer("✅ Up to date!", show_alert=False)
        else:
            logger.warning(f"BadRequest in safe_edit_text: {e}")
    except Exception as e:
        logger.error(f"Error in safe_edit_text: {e}")


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /start command with auto-language detection and referral attribution."""
    user = update.effective_user
    user_id = user.id
    username = user.username or user.first_name or "Trader"

    # Auto-detect language if new user (English default for global traders, Arabic if Telegram UI is Arabic)
    tg_lang = (user.language_code or "").lower()
    initial_lang = "ar" if tg_lang.startswith("ar") else "en"

    pubkey, is_new = get_or_create_wallet(user_id, username, initial_language=initial_lang)
    user_lang = get_user_language(user_id)

    # Process Referral Code
    if context.args and is_new:
        ref_arg = context.args[0]
        if ref_arg.startswith("ref_"):
            try:
                referrer_id = int(ref_arg.replace("ref_", ""))
                if record_referral(user_id, referrer_id):
                    logger.info(f"User {user_id} referred by {referrer_id}")
            except Exception as e:
                logger.warning(f"Referral parsing error: {e}")

    balance = get_sol_balance(pubkey)
    now_str = get_current_time_str()
    welcome_text = build_welcome_text(user, pubkey, balance, now_str, user_lang)

    await update.message.reply_text(
        welcome_text,
        parse_mode="HTML",
        reply_markup=get_main_menu_keyboard(user_id, user_lang),
        disable_web_page_preview=True
    )


async def trending_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /trending command."""
    user_id = update.effective_user.id
    user_lang = get_user_language(user_id)
    wait_text = "🔥 <b>جاري جلب أكثر عملات سولانا رواجاً من DexScreener...</b>" if user_lang == "ar" else "🔥 <b>Fetching top trending Solana tokens from DexScreener...</b>"
    status_msg = await update.message.reply_text(wait_text, parse_mode="HTML")

    tokens = get_trending_tokens(limit=5)
    text = format_trending_list(tokens, lang=user_lang)

    keyboard = []
    for tkn in tokens:
        sym = html.escape(tkn["symbol"])
        mint = tkn["mint"]
        btn_label = f"🚀 قنص ${sym} ({tkn['change_24h']:+.1f}%)" if user_lang == "ar" else f"🚀 Snipe ${sym} ({tkn['change_24h']:+.1f}%)"
        keyboard.append([
            InlineKeyboardButton(btn_label, callback_data=f"inspect_{mint}")
        ])
    keyboard.append([InlineKeyboardButton(t("btn_back", user_lang), callback_data="btn_refresh")])

    await status_msg.edit_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard), disable_web_page_preview=True)


async def referral_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /referral command."""
    user_id = update.effective_user.id
    user_lang = get_user_language(user_id)
    bot_username = context.bot.username or "PopcornSniperBot"
    ref_link = f"https://t.me/{bot_username}?start=ref_{user_id}"

    stats = get_referral_stats(user_id)
    title = t("referral_card_title", user_lang)
    body = t("referral_card_body", user_lang, ref_link=ref_link, total_ref=stats["total_referrals"], earnings=stats["earnings_sol"])
    text = f"{title}\n━━━━━━━━━━━━━━━━━━━━━━━━━━\n{body}"

    share_text = "⚡ Fastest Solana Sniper & Trading Bot on Jupiter V6!" if user_lang == "en" else "⚡ أقوى بوت قنص وتداول على سولانا مع فحص RugCheck!"
    share_btn_text = "📤 Share Link with Friends" if user_lang == "en" else "📤 مشاركة الرابط مع الأصدقاء"

    kb = [
        [InlineKeyboardButton(share_btn_text, url=f"https://t.me/share/url?url={ref_link}&text={share_text}")],
        [InlineKeyboardButton(t("btn_back", user_lang), callback_data="btn_refresh")]
    ]
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True)


async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Detects pasted token contract addresses or platform URLs and renders token card."""
    user_id = update.effective_user.id
    user_lang = get_user_language(user_id)
    text = update.message.text.strip()
    mint = extract_token_mint(text)

    if mint:
        wait_text = "🔍 <b>جاري فحص العقد الذكي وتدقيق الأمان (RugCheck + DexScreener)...</b>" if user_lang == "ar" else "🔍 <b>Auditing token security via RugCheck & DexScreener...</b>"
        status_msg = await update.message.reply_text(wait_text, parse_mode="HTML")

        scan = scan_token_security(mint)
        card_text = format_token_card(scan, lang=user_lang)

        # Check if Auto-Buy is active
        auto_enabled, auto_amt = get_auto_buy_settings(user_id)
        if auto_enabled and scan["status"] == "SAFE":
            pubkey, _ = get_or_create_wallet(user_id)
            bal = get_sol_balance(pubkey)
            if bal >= (auto_amt + 0.005):
                auto_msg = f"⚡ <b>تم رصد العقد! جاري تنفيذ القنص التلقائي بمبلغ {auto_amt} SOL...</b>" if user_lang == "ar" else f"⚡ <b>Safe token detected! Executing instant auto-snipe for {auto_amt} SOL...</b>"
                await status_msg.edit_text(auto_msg, parse_mode="HTML")
                settings = get_user_settings(user_id)
                quote = get_jupiter_quote(WSOL_MINT, mint, int(auto_amt * 1e9), settings["slippage_bps"], with_fee=True)
                if quote:
                    keypair = get_user_keypair(user_id)
                    tx_bytes = build_and_sign_swap_tx(quote, keypair, settings["priority_fee"])
                    if tx_bytes:
                        success, sig_or_err = broadcast_transaction(tx_bytes)
                        if success:
                            out_amount = float(quote.get("outAmount", 0))
                            fee_lamports = float(quote.get("platformFee", {}).get("amount", 0))
                            record_trade_db(user_id, WSOL_MINT, mint, auto_amt, out_amount, fee_lamports/1e9, sig_or_err, "CONFIRMED")
                            if user_lang == "ar":
                                success_text = (
                                    f"🎯 <b>تم القنص التلقائي (Auto-Buy) بنجاح!</b> 🟢\n"
                                    f"━━━━━━━━━━━━━━━━━━━\n"
                                    f"💸 القيمة: <code>{auto_amt} SOL</code>\n"
                                    f"🪙 العملة: <b>${html.escape(scan['symbol'])}</b>\n\n"
                                    f"🔗 <a href='https://solscan.io/tx/{sig_or_err}'>عرض المعاملة على Solscan</a>"
                                )
                            else:
                                success_text = (
                                    f"🎯 <b>Auto-Buy Swap Executed Successfully!</b> 🟢\n"
                                    f"━━━━━━━━━━━━━━━━━━━\n"
                                    f"💸 Amount: <code>{auto_amt} SOL</code>\n"
                                    f"🪙 Token: <b>${html.escape(scan['symbol'])}</b>\n\n"
                                    f"🔗 <a href='https://solscan.io/tx/{sig_or_err}'>View Transaction on Solscan</a>"
                                )
                            await status_msg.edit_text(success_text, parse_mode="HTML", disable_web_page_preview=True)
                            return

        # Inline action keyboard
        sell_prefix = "بيع" if user_lang == "ar" else "Sell"
        keyboard = [
            [
                InlineKeyboardButton("🟢 0.05 SOL", callback_data=f"buy_{mint}_0.05"),
                InlineKeyboardButton("🟢 0.1 SOL", callback_data=f"buy_{mint}_0.1"),
                InlineKeyboardButton("🟢 0.25 SOL", callback_data=f"buy_{mint}_0.25")
            ],
            [
                InlineKeyboardButton("🟢 0.5 SOL", callback_data=f"buy_{mint}_0.5"),
                InlineKeyboardButton("🟢 1.0 SOL", callback_data=f"buy_{mint}_1.0"),
                InlineKeyboardButton("🟢 2.0 SOL", callback_data=f"buy_{mint}_2.0")
            ],
            [
                InlineKeyboardButton(f"🔴 {sell_prefix} 25%", callback_data=f"sell_{mint}_25"),
                InlineKeyboardButton(f"🔴 {sell_prefix} 50%", callback_data=f"sell_{mint}_50"),
                InlineKeyboardButton(f"🔴 {sell_prefix} 100%", callback_data=f"sell_{mint}_100")
            ],
            [
                InlineKeyboardButton(t("btn_dexscreener", user_lang), url=f"https://dexscreener.com/solana/{mint}"),
                InlineKeyboardButton(t("btn_rugcheck", user_lang), url=f"https://rugcheck.xyz/tokens/{mint}")
            ],
            [
                InlineKeyboardButton(t("btn_back", user_lang), callback_data="btn_refresh")
            ]
        ]

        await status_msg.edit_text(card_text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard), disable_web_page_preview=True)
    else:
        hint_text = (
            "ℹ️ <b>Send any Solana Contract Address (CA) or DexScreener / Pump.fun link to start sniping.</b>\n\n"
            "Example: <code>DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263</code> (BONK)"
        ) if user_lang == "en" else (
            "ℹ️ <b>أرسل عنوان العقد الذكي (CA) أو رابط العملة من DexScreener / Pump.fun لبدء القنص.</b>\n\n"
            "مثال: <code>DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263</code> (BONK)"
        )
        await update.message.reply_text(hint_text, parse_mode="HTML")


async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles all inline button clicks with bilingual localization."""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    user_lang = get_user_language(user_id)
    data = query.data
    now_str = get_current_time_str()

    if data == "btn_toggle_lang":
        new_lang = "ar" if user_lang == "en" else "en"
        set_user_language(user_id, new_lang)
        user_lang = new_lang
        toast = t("lang_switched_toast", user_lang)
        await query.answer(toast, show_alert=False)

        pubkey, _ = get_or_create_wallet(user_id)
        balance = get_sol_balance(pubkey)
        welcome_text = build_welcome_text(query.from_user, pubkey, balance, now_str, user_lang)
        await safe_edit_text(query, welcome_text, reply_markup=get_main_menu_keyboard(user_id, user_lang))

    elif data == "btn_refresh":
        pubkey, _ = get_or_create_wallet(user_id)
        balance = get_sol_balance(pubkey)
        welcome_text = build_welcome_text(query.from_user, pubkey, balance, now_str, user_lang)
        await safe_edit_text(query, welcome_text, reply_markup=get_main_menu_keyboard(user_id, user_lang))

    elif data == "btn_trending":
        await query.message.reply_chat_action("typing")
        tokens = get_trending_tokens(limit=5)
        text = format_trending_list(tokens, lang=user_lang)
        keyboard = []
        for tkn in tokens:
            sym = html.escape(tkn["symbol"])
            mint = tkn["mint"]
            btn_label = f"🚀 قنص ${sym} ({tkn['change_24h']:+.1f}%)" if user_lang == "ar" else f"🚀 Snipe ${sym} ({tkn['change_24h']:+.1f}%)"
            keyboard.append([
                InlineKeyboardButton(btn_label, callback_data=f"inspect_{mint}")
            ])
        keyboard.append([InlineKeyboardButton(t("btn_back", user_lang), callback_data="btn_refresh")])
        await safe_edit_text(query, text, reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("inspect_"):
        mint = data.split("_")[1]
        await query.message.reply_chat_action("typing")
        scan = scan_token_security(mint)
        card_text = format_token_card(scan, lang=user_lang)
        sell_prefix = "بيع" if user_lang == "ar" else "Sell"
        keyboard = [
            [
                InlineKeyboardButton("🟢 0.1 SOL", callback_data=f"buy_{mint}_0.1"),
                InlineKeyboardButton("🟢 0.5 SOL", callback_data=f"buy_{mint}_0.5"),
                InlineKeyboardButton("🟢 1.0 SOL", callback_data=f"buy_{mint}_1.0")
            ],
            [
                InlineKeyboardButton(f"🔴 {sell_prefix} 50%", callback_data=f"sell_{mint}_50"),
                InlineKeyboardButton(f"🔴 {sell_prefix} 100%", callback_data=f"sell_{mint}_100")
            ],
            [
                InlineKeyboardButton(t("btn_dexscreener", user_lang), url=f"https://dexscreener.com/solana/{mint}"),
                InlineKeyboardButton(t("btn_rugcheck", user_lang), url=f"https://rugcheck.xyz/tokens/{mint}")
            ],
            [InlineKeyboardButton(t("btn_back", user_lang), callback_data="btn_trending")]
        ]
        await safe_edit_text(query, card_text, reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "btn_referral":
        bot_username = context.bot.username or "PopcornSniperBot"
        ref_link = f"https://t.me/{bot_username}?start=ref_{user_id}"
        stats = get_referral_stats(user_id)
        title = t("referral_card_title", user_lang)
        body = t("referral_card_body", user_lang, ref_link=ref_link, total_ref=stats["total_referrals"], earnings=stats["earnings_sol"])
        text = f"{title}\n━━━━━━━━━━━━━━━━━━━━━━━━━━\n{body}"

        share_text = "⚡ Fastest Solana Sniper & Trading Bot on Jupiter V6!" if user_lang == "en" else "⚡ أقوى بوت قنص وتداول على سولانا مع فحص RugCheck!"
        share_btn_text = "📤 Share Link with Friends" if user_lang == "en" else "📤 مشاركة الرابط مع الأصدقاء"

        kb = [
            [InlineKeyboardButton(share_btn_text, url=f"https://t.me/share/url?url={ref_link}&text={share_text}")],
            [InlineKeyboardButton(t("btn_back", user_lang), callback_data="btn_refresh")]
        ]
        await safe_edit_text(query, text, reply_markup=InlineKeyboardMarkup(kb))

    elif data == "btn_autobuy_settings":
        auto_enabled, auto_amt = get_auto_buy_settings(user_id)
        status_label = t("enabled", user_lang) if auto_enabled else t("disabled", user_lang)
        title = t("autobuy_title", user_lang)
        body = t("autobuy_body", user_lang, status=status_label, amount=auto_amt)
        text = f"{title}\n━━━━━━━━━━━━━━━━━━━\n{body}"

        toggle_label = ("🔴 Disable Auto-Buy" if auto_enabled else "🟢 Enable Auto-Buy") if user_lang == "en" else ("🔴 تعطيل القنص التلقائي" if auto_enabled else "🟢 تفعيل القنص التلقائي")
        kb = [
            [InlineKeyboardButton(toggle_label, callback_data="btn_toggle_autobuy")],
            [
                InlineKeyboardButton("0.05 SOL", callback_data="set_auto_0.05"),
                InlineKeyboardButton("0.1 SOL", callback_data="set_auto_0.1"),
                InlineKeyboardButton("0.25 SOL", callback_data="set_auto_0.25"),
                InlineKeyboardButton("0.5 SOL", callback_data="set_auto_0.5")
            ],
            [InlineKeyboardButton(t("btn_back", user_lang), callback_data="btn_refresh")]
        ]
        await safe_edit_text(query, text, reply_markup=InlineKeyboardMarkup(kb))

    elif data == "btn_toggle_autobuy":
        new_state = toggle_auto_buy(user_id)
        state_str = ("🟢 Auto-Buy Enabled!" if new_state else "🔴 Auto-Buy Disabled!") if user_lang == "en" else ("🟢 تم تفعيل القنص التلقائي!" if new_state else "🔴 تم تعطيل القنص التلقائي!")
        await query.answer(state_str, show_alert=True)
        # Refresh autobuy menu
        auto_enabled, auto_amt = get_auto_buy_settings(user_id)
        status_label = t("enabled", user_lang) if auto_enabled else t("disabled", user_lang)
        title = t("autobuy_title", user_lang)
        body = t("autobuy_body", user_lang, status=status_label, amount=auto_amt)
        text = f"{title}\n━━━━━━━━━━━━━━━━━━━\n{body}"
        toggle_label = ("🔴 Disable Auto-Buy" if auto_enabled else "🟢 Enable Auto-Buy") if user_lang == "en" else ("🔴 تعطيل القنص التلقائي" if auto_enabled else "🟢 تفعيل القنص التلقائي")
        kb = [
            [InlineKeyboardButton(toggle_label, callback_data="btn_toggle_autobuy")],
            [InlineKeyboardButton(t("btn_back", user_lang), callback_data="btn_refresh")]
        ]
        await safe_edit_text(query, text, reply_markup=InlineKeyboardMarkup(kb))

    elif data.startswith("set_auto_"):
        amt = float(data.split("_")[2])
        set_auto_buy_amount(user_id, amt)
        ack = f"✅ Auto-buy amount set to {amt} SOL!" if user_lang == "en" else f"✅ تم ضبط مبلغ الشراء التلقائي إلى {amt} SOL!"
        await query.answer(ack, show_alert=True)
        await safe_edit_text(query, f"✅ <b>{ack}</b>", reply_markup=get_main_menu_keyboard(user_id, user_lang))

    elif data == "btn_wallet":
        pubkey, _ = get_or_create_wallet(user_id)
        balance = get_sol_balance(pubkey)
        qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=250x250&data=solana:{pubkey}"
        if user_lang == "ar":
            text = (
                f"💳 <b>إدارة المحفظة والإيداع</b> 🏦\n"
                f"━━━━━━━━━━━━━━━━━━━\n"
                f"📍 <b>عنوان إيداع SOL (اضغط للنسخ)</b>:\n<code>{pubkey}</code>\n\n"
                f"💰 <b>الرصيد المتاح</b>: <code>{balance:.4f} SOL</code>\n"
                f"🕒 وقت الفحص: <code>{now_str}</code>\n\n"
                f"🔗 <a href='https://solscan.io/account/{pubkey}'>عرض المحفظة على Solscan</a>\n"
                f"📷 <a href='{qr_url}'>عرض رمز QR للإيداع السريع عبر الكاميرا</a>\n\n"
                f"⚠️ <i>مفتاحك الخاص مشفر محلياً بنظام AES-256 لحمايتك الكاملة.</i>\n"
            )
            kb = [
                [InlineKeyboardButton("💸 سحب SOL إلى محفظتك الخارجية", callback_data="btn_withdraw_guide")],
                [InlineKeyboardButton("🔑 إظهار المفتاح الخاص (Private Key)", callback_data="btn_export_key")],
                [InlineKeyboardButton("🔙 العودة للرئيسية", callback_data="btn_refresh")]
            ]
        else:
            text = (
                f"💳 <b>Solana Trading Wallet & Deposit</b> 🏦\n"
                f"━━━━━━━━━━━━━━━━━━━\n"
                f"📍 <b>SOL Deposit Address (Tap to copy)</b>:\n<code>{pubkey}</code>\n\n"
                f"💰 <b>Available Balance</b>: <code>{balance:.4f} SOL</code>\n"
                f"🕒 Checked: <code>{now_str}</code>\n\n"
                f"🔗 <a href='https://solscan.io/account/{pubkey}'>View Account on Solscan</a>\n"
                f"📷 <a href='{qr_url}'>Instant QR Code Deposit</a>\n\n"
                f"⚠️ <i>Your private key is encrypted locally with AES-256 for non-custodial ownership.</i>\n"
            )
            kb = [
                [InlineKeyboardButton("💸 Withdraw SOL to External Wallet", callback_data="btn_withdraw_guide")],
                [InlineKeyboardButton("🔑 Export Private Key", callback_data="btn_export_key")],
                [InlineKeyboardButton(t("btn_back", user_lang), callback_data="btn_refresh")]
            ]
        await safe_edit_text(query, text, reply_markup=InlineKeyboardMarkup(kb))

    elif data == "btn_withdraw_guide":
        pubkey, _ = get_or_create_wallet(user_id)
        bal = get_sol_balance(pubkey)
        title = t("withdraw_title", user_lang)
        body = t("withdraw_body", user_lang, balance=bal)
        text = f"{title}\n━━━━━━━━━━━━━━━━━━━\n{body}"
        kb = [[InlineKeyboardButton(t("btn_back", user_lang), callback_data="btn_wallet")]]
        await safe_edit_text(query, text, reply_markup=InlineKeyboardMarkup(kb))

    elif data == "btn_export_key":
        p_key = export_private_key_b58(user_id)
        if user_lang == "ar":
            text = (
                f"🚨 <b>تحذير أمني شديد</b>: لا تشارك هذا المفتاح مع أي شخص أبداً!\n\n"
                f"🔑 <b>المفتاح الخاص (Base58)</b>:\n"
                f"<code>{p_key}</code>\n\n"
                f"يمكنك نسخه واستيراده في محفظة Phantom أو Solflare في أي وقت."
            )
        else:
            text = (
                f"🚨 <b>STRICT SECURITY WARNING</b>: Never share this key with anyone!\n\n"
                f"🔑 <b>Private Key (Base58)</b>:\n"
                f"<code>{p_key}</code>\n\n"
                f"You can copy and import this into Phantom or Solflare wallet anytime."
            )
        kb = [[InlineKeyboardButton(t("btn_back", user_lang), callback_data="btn_wallet")]]
        await safe_edit_text(query, text, reply_markup=InlineKeyboardMarkup(kb))

    elif data == "btn_positions":
        pubkey, _ = get_or_create_wallet(user_id)
        tokens = get_token_accounts(pubkey)
        if not tokens:
            text = f"{t('positions_title', user_lang)}\n━━━━━━━━━━━━━━━━━━━\n{t('no_positions', user_lang)}\n🕒 <code>{now_str}</code>"
        else:
            header = "الرموز المفتوحة في محفظتك" if user_lang == "ar" else "Open Token Holdings in Wallet"
            text = f"📊 <b>{header}</b>:\n━━━━━━━━━━━━━━━━━━━\n"
            for tkn in tokens:
                text += f"• <code>{tkn['mint'][:6]}...{tkn['mint'][-4:]}</code>: <b>{tkn['amount']:,.2f}</b>\n"
            text += f"\n🕒 <code>{now_str}</code>"
        kb = [[InlineKeyboardButton(t("btn_back", user_lang), callback_data="btn_refresh")]]
        await safe_edit_text(query, text, reply_markup=InlineKeyboardMarkup(kb))

    elif data == "btn_settings":
        settings = get_user_settings(user_id)
        current_slip = settings["slippage_bps"] / 100.0
        title = t("settings_title", user_lang)
        body = t("settings_body", user_lang, slippage=current_slip)
        text = f"{title}\n━━━━━━━━━━━━━━━━━━━\n{body}\n🕒 <code>{now_str}</code>"
        kb = [
            [
                InlineKeyboardButton("0.5%", callback_data="slip_50"),
                InlineKeyboardButton("1.0%", callback_data="slip_100"),
                InlineKeyboardButton("2.0%", callback_data="slip_200"),
                InlineKeyboardButton("5.0%", callback_data="slip_500")
            ],
            [
                InlineKeyboardButton(t("btn_lang_toggle", user_lang), callback_data="btn_toggle_lang")
            ],
            [InlineKeyboardButton(t("btn_back", user_lang), callback_data="btn_refresh")]
        ]
        await safe_edit_text(query, text, reply_markup=InlineKeyboardMarkup(kb))

    elif data.startswith("slip_"):
        new_bps = int(data.split("_")[1])
        update_user_slippage(user_id, new_bps)
        ack = f"Slippage tolerance set to {new_bps/100.0}%" if user_lang == "en" else f"تم ضبط نسبة الانزلاق إلى {new_bps/100.0}%"
        await safe_edit_text(query, f"✅ <b>{ack}</b>\n🕒 <code>{now_str}</code>", reply_markup=get_main_menu_keyboard(user_id, user_lang))

    elif data == "btn_snipe_guide":
        title = t("snipe_guide_title", user_lang)
        body = t("snipe_guide_body", user_lang)
        text = f"{title}\n━━━━━━━━━━━━━━━━━━━\n{body}"
        kb = [[InlineKeyboardButton(t("btn_back", user_lang), callback_data="btn_refresh")]]
        await safe_edit_text(query, text, reply_markup=InlineKeyboardMarkup(kb))

    elif data.startswith("buy_"):
        parts = data.split("_")
        mint = parts[1]
        amount_sol = float(parts[2])

        pubkey, _ = get_or_create_wallet(user_id)
        bal = get_sol_balance(pubkey)

        if bal < (amount_sol + 0.005):  # Gas buffer
            err_text = (
                f"❌ <b>Insufficient SOL balance!</b>\n"
                f"Required: <code>{amount_sol} SOL</code> (+ gas fees)\n"
                f"Available: <code>{bal:.4f} SOL</code>\n\n"
                f"Deposit SOL to your trading wallet:\n<code>{pubkey}</code>"
            ) if user_lang == "en" else (
                f"❌ <b>رصيد SOL غير كافٍ!</b>\n"
                f"المطلوب: <code>{amount_sol} SOL</code> (+ رسوم الغاز)\n"
                f"الرصيد المتاح: <code>{bal:.4f} SOL</code>\n\n"
                f"يرجى إيداع SOL في محفظتك:\n<code>{pubkey}</code>"
            )
            await safe_edit_text(query, err_text, reply_markup=get_main_menu_keyboard(user_id, user_lang))
            return

        prep_text = "⚡ <b>Routing best swap via Jupiter V6...</b>" if user_lang == "en" else "⚡ <b>جاري تحضير مسار الشراء عبر Jupiter...</b>"
        status_msg = await query.message.reply_text(prep_text, parse_mode="HTML")

        settings = get_user_settings(user_id)
        slippage = settings["slippage_bps"]
        amount_lamports = int(amount_sol * 1_000_000_000)

        # 1. Fetch Quote
        quote = get_jupiter_quote(WSOL_MINT, mint, amount_lamports, slippage, with_fee=True)
        if not quote:
            fail_text = "❌ <b>No liquidity route discovered on Jupiter right now.</b>" if user_lang == "en" else "❌ <b>تعذر إيجاد مسار سيولة في Jupiter حالياً.</b>"
            await status_msg.edit_text(fail_text, parse_mode="HTML")
            return

        # 2. Build & Sign
        keypair = get_user_keypair(user_id)
        tx_bytes = build_and_sign_swap_tx(quote, keypair, settings["priority_fee"])
        if not tx_bytes:
            sign_err = "❌ <b>Failed to build and sign transaction offline.</b>" if user_lang == "en" else "❌ <b>فشل في بناء وتوقيع المعاملة.</b>"
            await status_msg.edit_text(sign_err, parse_mode="HTML")
            return

        # 3. Broadcast
        bcast_text = "🚀 <b>Broadcasting to Solana cluster & confirming on-chain...</b>" if user_lang == "en" else "🚀 <b>جاري إرسال المعاملة إلى شبكة سولانا وتأكيد التنفيذ...</b>"
        await status_msg.edit_text(bcast_text, parse_mode="HTML")
        success, sig_or_err = broadcast_transaction(tx_bytes)

        if success:
            out_amount = float(quote.get("outAmount", 0))
            fee_lamports = float(quote.get("platformFee", {}).get("amount", 0))
            record_trade_db(user_id, WSOL_MINT, mint, amount_sol, out_amount, fee_lamports/1e9, sig_or_err, "CONFIRMED")
            if user_lang == "en":
                success_text = (
                    f"🎉 <b>Buy Swap Executed Successfully!</b> 🟢\n"
                    f"━━━━━━━━━━━━━━━━━━━\n"
                    f"💸 Amount: <code>{amount_sol} SOL</code>\n"
                    f"🛡️ Platform Fee (1%): <code>{fee_lamports/1e9:.6f} SOL</code>\n\n"
                    f"🔗 <a href='https://solscan.io/tx/{sig_or_err}'>View Transaction on Solscan</a>"
                )
            else:
                success_text = (
                    f"🎉 <b>تم تنفيذ صفقة الشراء بنجاح!</b> 🟢\n"
                    f"━━━━━━━━━━━━━━━━━━━\n"
                    f"💸 القيمة: <code>{amount_sol} SOL</code>\n"
                    f"🛡️ عمولة المنصة (1%): <code>{fee_lamports/1e9:.6f} SOL</code>\n\n"
                    f"🔗 <a href='https://solscan.io/tx/{sig_or_err}'>عرض المعاملة على Solscan</a>"
                )
            await status_msg.edit_text(success_text, parse_mode="HTML", disable_web_page_preview=True)
        else:
            await status_msg.edit_text(f"❌ <b>Transaction failed</b>: <code>{html.escape(sig_or_err)}</code>", parse_mode="HTML")

    elif data.startswith("sell_"):
        parts = data.split("_")
        mint = parts[1]
        pct = int(parts[2])

        prep_sell = f"⚡ <b>Executing {pct}% Sell Swap via Jupiter...</b>" if user_lang == "en" else f"⚡ <b>جاري تنفيذ بيع {pct}% من العملة عبر Jupiter...</b>"
        status_msg = await query.message.reply_text(prep_sell, parse_mode="HTML")

        success, sig_or_err, sol_received = execute_sell_swap(user_id, mint, pct)
        if success:
            if user_lang == "en":
                text = (
                    f"🎉 <b>Sell Swap Executed Successfully!</b> 🔴\n"
                    f"━━━━━━━━━━━━━━━━━━━\n"
                    f"💰 Received: <code>{sol_received:.4f} SOL</code> in wallet\n\n"
                    f"🔗 <a href='https://solscan.io/tx/{sig_or_err}'>View Transaction on Solscan</a>"
                )
            else:
                text = (
                    f"🎉 <b>تم تنفيذ صفقة البيع بنجاح!</b> 🔴\n"
                    f"━━━━━━━━━━━━━━━━━━━\n"
                    f"💰 تم استلام: <code>{sol_received:.4f} SOL</code> في محفظتك\n\n"
                    f"🔗 <a href='https://solscan.io/tx/{sig_or_err}'>عرض المعاملة على Solscan</a>"
                )
            await status_msg.edit_text(text, parse_mode="HTML", disable_web_page_preview=True)
        else:
            await status_msg.edit_text(f"❌ <b>Sell failed</b>: <code>{html.escape(sig_or_err)}</code>", parse_mode="HTML")


async def withdraw_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /withdraw command."""
    user_id = update.effective_user.id
    user_lang = get_user_language(user_id)
    args = context.args

    if len(args) < 2:
        help_text = (
            "ℹ️ <b>Withdrawal Syntax</b>:\n"
            "<code>/withdraw [DESTINATION_ADDRESS] [AMOUNT_SOL]</code>\n\n"
            "<b>Example:</b>\n"
            "<code>/withdraw 7kz1mcQcaZhYzFUHBFHH6s5tGrDHc7gNhN5WAUyXyq5r 0.05</code>"
        ) if user_lang == "en" else (
            "ℹ️ <b>صيغة السحب</b>:\n"
            "<code>/withdraw [عنوان_محفظتك] [المبلغ_SOL]</code>\n\n"
            "<b>مثال:</b>\n"
            "<code>/withdraw 7kz1mcQcaZhYzFUHBFHH6s5tGrDHc7gNhN5WAUyXyq5r 0.05</code>"
        )
        await update.message.reply_text(help_text, parse_mode="HTML")
        return

    dest_address = args[0].strip()
    try:
        amount_sol = float(args[1].strip())
    except ValueError:
        invalid_num = "❌ Invalid amount entered. Please specify a valid number like 0.1" if user_lang == "en" else "❌ المبلغ المدخل غير صحيح، يرجى كتابة رقم صالح مثل 0.1"
        await update.message.reply_text(invalid_num, parse_mode="HTML")
        return

    wait_tx = "⚡ <b>Preparing and broadcasting withdrawal transaction on Solana...</b>" if user_lang == "en" else "⚡ <b>جاري تحضير وتوقيع معاملة السحب على شبكة سولانا...</b>"
    status_msg = await update.message.reply_text(wait_tx, parse_mode="HTML")
    success, sig_or_err = withdraw_sol(user_id, dest_address, amount_sol)

    if success:
        if user_lang == "en":
            text = (
                f"🎉 <b>Successfully Withdrawn {amount_sol} SOL!</b> 💸\n"
                f"━━━━━━━━━━━━━━━━━━━\n"
                f"📍 Recipient Address: <code>{dest_address}</code>\n\n"
                f"🔗 <a href='https://solscan.io/tx/{sig_or_err}'>View Transaction on Solscan</a>"
            )
        else:
            text = (
                f"🎉 <b>تم سحب {amount_sol} SOL بنجاح!</b> 💸\n"
                f"━━━━━━━━━━━━━━━━━━━\n"
                f"📍 المحفظة المستلمة: <code>{dest_address}</code>\n\n"
                f"🔗 <a href='https://solscan.io/tx/{sig_or_err}'>عرض المعاملة على Solscan</a>"
            )
        await status_msg.edit_text(text, parse_mode="HTML", disable_web_page_preview=True)
    else:
        await status_msg.edit_text(f"❌ <b>Withdrawal failed</b>: <code>{html.escape(sig_or_err)}</code>", parse_mode="HTML")


async def wallet_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /wallet command."""
    user_id = update.effective_user.id
    user_lang = get_user_language(user_id)
    pubkey, _ = get_or_create_wallet(user_id)
    balance = get_sol_balance(pubkey)
    now_str = get_current_time_str()
    qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=250x250&data=solana:{pubkey}"

    if user_lang == "ar":
        text = (
            f"💳 <b>إدارة المحفظة والإيداع</b> 🏦\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"📍 <b>عنوان إيداع SOL (اضغط للنسخ)</b>:\n<code>{pubkey}</code>\n\n"
            f"💰 <b>الرصيد المتاح</b>: <code>{balance:.4f} SOL</code>\n"
            f"🕒 وقت الفحص: <code>{now_str}</code>\n\n"
            f"🔗 <a href='https://solscan.io/account/{pubkey}'>عرض المحفظة على Solscan</a>\n"
            f"📷 <a href='{qr_url}'>عرض رمز QR للإيداع السريع عبر الكاميرا</a>\n\n"
            f"⚠️ <i>مفتاحك الخاص مشفر محلياً بنظام AES-256 لحمايتك الكاملة.</i>\n"
        )
        kb = [
            [InlineKeyboardButton("💸 سحب SOL للخارج", callback_data="btn_withdraw_guide")],
            [InlineKeyboardButton("🔑 إظهار المفتاح الخاص", callback_data="btn_export_key")],
            [InlineKeyboardButton("🔄 تحديث الرصيد", callback_data="btn_wallet")]
        ]
    else:
        text = (
            f"💳 <b>Solana Trading Wallet & Deposit</b> 🏦\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"📍 <b>SOL Deposit Address (Tap to copy)</b>:\n<code>{pubkey}</code>\n\n"
            f"💰 <b>Available Balance</b>: <code>{balance:.4f} SOL</code>\n"
            f"🕒 Checked: <code>{now_str}</code>\n\n"
            f"🔗 <a href='https://solscan.io/account/{pubkey}'>View Account on Solscan</a>\n"
            f"📷 <a href='{qr_url}'>Instant QR Code Deposit</a>\n\n"
            f"⚠️ <i>Your private key is locally encrypted with AES-256 for non-custodial ownership.</i>\n"
        )
        kb = [
            [InlineKeyboardButton("💸 Withdraw SOL to External Wallet", callback_data="btn_withdraw_guide")],
            [InlineKeyboardButton("🔑 Export Private Key", callback_data="btn_export_key")],
            [InlineKeyboardButton("🔄 Refresh Balance", callback_data="btn_wallet")]
        ]
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True)


async def positions_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /positions command."""
    user_id = update.effective_user.id
    user_lang = get_user_language(user_id)
    pubkey, _ = get_or_create_wallet(user_id)
    tokens = get_token_accounts(pubkey)
    now_str = get_current_time_str()

    if not tokens:
        text = f"{t('positions_title', user_lang)}\n━━━━━━━━━━━━━━━━━━━\n{t('no_positions', user_lang)}\n🕒 <code>{now_str}</code>"
    else:
        header = "الرموز المفتوحة في محفظتك" if user_lang == "ar" else "Open Token Holdings in Wallet"
        text = f"📊 <b>{header}</b>:\n━━━━━━━━━━━━━━━━━━━\n"
        for tkn in tokens:
            text += f"• <code>{tkn['mint'][:6]}...{tkn['mint'][-4:]}</code>: <b>{tkn['amount']:,.2f}</b>\n"
        text += f"\n🕒 <code>{now_str}</code>"
    await update.message.reply_text(text, parse_mode="HTML")


async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /settings command."""
    user_id = update.effective_user.id
    user_lang = get_user_language(user_id)
    settings = get_user_settings(user_id)
    current_slip = settings["slippage_bps"] / 100.0
    now_str = get_current_time_str()

    title = t("settings_title", user_lang)
    body = t("settings_body", user_lang, slippage=current_slip)
    text = f"{title}\n━━━━━━━━━━━━━━━━━━━\n{body}\n🕒 <code>{now_str}</code>"

    kb = [
        [
            InlineKeyboardButton("0.5%", callback_data="slip_50"),
            InlineKeyboardButton("1.0%", callback_data="slip_100"),
            InlineKeyboardButton("2.0%", callback_data="slip_200"),
            InlineKeyboardButton("5.0%", callback_data="slip_500")
        ],
        [
            InlineKeyboardButton(t("btn_lang_toggle", user_lang), callback_data="btn_toggle_lang")
        ],
        [InlineKeyboardButton(t("btn_back", user_lang), callback_data="btn_refresh")]
    ]
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb))


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /help command."""
    user_id = update.effective_user.id
    user_lang = get_user_language(user_id)
    title = t("help_title", user_lang)
    body = t("help_body", user_lang)
    text = f"{title}\n{body}"
    await update.message.reply_text(text, parse_mode="HTML")


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Global error handler to catch and log unexpected errors gracefully."""
    logger.error(f"Exception while handling an update: {context.error}")


def build_application(token: str) -> Application:
    """Builds the Telegram Application instance with all command and callback handlers."""
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("trending", trending_command))
    app.add_handler(CommandHandler("referral", referral_command))
    app.add_handler(CommandHandler("wallet", wallet_command))
    app.add_handler(CommandHandler("withdraw", withdraw_command))
    app.add_handler(CommandHandler("positions", positions_command))
    app.add_handler(CommandHandler("settings", settings_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CallbackQueryHandler(callback_router))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    app.add_error_handler(error_handler)
    return app


if __name__ == "__main__":
    token = TELEGRAM_BOT_TOKEN or os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        print("⚠️ Please provide TELEGRAM_BOT_TOKEN in .env or environment.")
        print("💡 You can verify functionality via: py test_bot.py")
        sys.exit(0)

    print("🚀 Launching Popcorn Solana Sniper & Trading Bot v3.1 (Bilingual Master)...")
    app = build_application(token)
    app.run_polling()
