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
import re
import urllib.parse
from typing import Optional, Dict, Any, List, Tuple

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    BotCommand,
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
    USDC_MINT,
    PRIMARY_RPC,
    BOT_VERSION
)
from wallet_manager import (
    get_or_create_wallet,
    get_sol_balance,
    get_user_keypair,
    export_private_key_b58,
    get_user_settings,
    update_user_slippage,
    update_user_priority_fee,
    update_user_tp,
    update_user_sl,
    get_token_accounts,
    withdraw_sol,
    record_referral,
    get_referral_stats,
    get_auto_buy_settings,
    toggle_auto_buy,
    set_auto_buy_status,
    set_auto_buy_amount,
    get_user_language,
    set_user_language,
    get_user_trade_stats,
    get_all_user_trades,
    generate_trades_csv_bytes,
    add_to_watchlist,
    remove_from_watchlist,
    clear_user_watchlist,
    get_user_watchlist,
    is_token_in_watchlist,
    toggle_price_alerts,
    get_price_alerts_status,
    set_price_alerts_status,
    get_user_alert_settings,
    update_user_alert_threshold,
    get_all_active_watchlist_subscriptions,
    update_watchlist_price_and_alert,
    generate_deposit_qr_buffer,
    reset_user_settings_to_defaults,
    get_user_default_buy_amount,
    update_user_default_buy_amount
)
from rugcheck_scanner import (
    scan_token_security,
    format_token_card,
    extract_token_mint,
    search_solana_token
)
from jupiter_engine import (
    get_jupiter_quote,
    build_and_sign_swap_tx,
    broadcast_transaction,
    record_trade_db,
    execute_buy_swap,
    execute_sell_swap,
    calculate_optimal_slippage,
    get_network_gas_fees
)

from trending_engine import (
    get_trending_tokens,
    format_trending_list,
    get_top_gainers,
    format_gainers_list,
    get_batch_token_prices
)
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
            InlineKeyboardButton(t("btn_snipe_guide", lang), callback_data="btn_snipe_guide"),
            InlineKeyboardButton(t("btn_tour", lang), callback_data="btn_tour")
        ],
        [
            InlineKeyboardButton(t("btn_show_qr", lang), callback_data="btn_show_qr"),
            InlineKeyboardButton(t("btn_gas_radar", lang), callback_data="btn_gas_fees")
        ],
        [
            InlineKeyboardButton(t("btn_trending", lang), callback_data="btn_trending"),
            InlineKeyboardButton(t("btn_surge", lang), callback_data="btn_surge")
        ],

        [
            InlineKeyboardButton(t("btn_watchlist", lang), callback_data="btn_watchlist"),
            InlineKeyboardButton(t("btn_positions", lang), callback_data="btn_positions")
        ],
        [
            InlineKeyboardButton(t("btn_history", lang), callback_data="btn_history"),
            InlineKeyboardButton(t("btn_pnl", lang), callback_data="btn_pnl")
        ],
        [
            InlineKeyboardButton(t("btn_wallet", lang), callback_data="btn_wallet"),
            InlineKeyboardButton(t("btn_referral", lang), callback_data="btn_referral")
        ],
        [
            InlineKeyboardButton(f"{t('btn_autobuy', lang)} ({auto_badge})", callback_data="btn_autobuy_settings"),
            InlineKeyboardButton(t("btn_settings", lang), callback_data="btn_settings")
        ],
        [
            InlineKeyboardButton("🛰️ " + ("Status" if lang == "en" else "حالة الشبكة"), callback_data="btn_status"),
            InlineKeyboardButton("💰 " + ("Fees" if lang == "en" else "الرسوم"), callback_data="btn_fee_info")
        ],
        [
            InlineKeyboardButton(lang_toggle_btn, callback_data="btn_toggle_lang")
        ],
        [
            InlineKeyboardButton(t("btn_withdraw", lang), callback_data="btn_withdraw_guide"),
            InlineKeyboardButton(t("btn_ping", lang), callback_data="btn_ping")
        ],
        [
            InlineKeyboardButton(t("btn_refresh", lang), callback_data="btn_refresh")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_token_card_keyboard(mint: str, user_lang: str, user_id: int = 0, symbol: str = "TOKEN") -> InlineKeyboardMarkup:
    """Builds interactive inline keyboard for audited token card with custom buy, watchlist tracking, X share, and live refresh."""
    sell_prefix = "بيع" if user_lang == "ar" else "Sell"
    custom_buy_label = "✏️ " + t("btn_custom_buy", user_lang)
    custom_sell_label = t("btn_custom_sell", user_lang)

    # Dynamic watchlist tracking state
    is_tracked = is_token_in_watchlist(user_id, mint) if user_id else False
    if is_tracked:
        track_btn_label = "⭐ " + ("Untrack" if user_lang == "en" else "إزالة من المتابعة")
        track_cb = f"untrack_{mint}"
    else:
        track_btn_label = "⭐ " + t("btn_track", user_lang)
        track_cb = f"track_{mint}"

    # Pre-generate viral sharing link with user's referral parameter
    ref_param = f"?start=ref_{user_id}" if user_id else ""
    share_bot_url = f"https://t.me/PopcornSniperBot{ref_param}"
    share_msg = (
        f"🔥 Check out ${symbol} on @PopcornSniperBot! Audited with RugCheck & 1-click sub-400ms sniper."
        if user_lang == "en" else
        f"🔥 تفحص عملة ${symbol} على بوت @PopcornSniperBot! فحص أمان فوري وقنص سريع بنقرة واحدة."
    )
    import urllib.parse
    tg_share_link = f"https://t.me/share/url?url={share_bot_url}&text={urllib.parse.quote(share_msg)}"
    share_btn_label = "📤 " + ("Share Signal" if user_lang == "en" else "مشاركة التوصية")

    x_intent_text = (
        f"Sniping ${symbol} on Solana with @PopcornSniperBot! 🍿⚡\n\n"
        f"Contract: {mint}\n\n"
        f"Trade now: {share_bot_url}"
    )
    x_share_link = f"https://twitter.com/intent/tweet?text={urllib.parse.quote(x_intent_text)}"
    refresh_quote_label = "🔄 Refresh Quote" if user_lang == "en" else "🔄 تحديث السعر والتدقيق"

    links_row = [
        InlineKeyboardButton(t("btn_dexscreener", user_lang), url=f"https://dexscreener.com/solana/{mint}"),
        InlineKeyboardButton(t("btn_rugcheck", user_lang), url=f"https://rugcheck.xyz/tokens/{mint}")
    ]
    if mint.lower().endswith("pump"):
        links_row.append(InlineKeyboardButton("💊 Pump.fun", url=f"https://pump.fun/coin/{mint}"))

    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🟢 0.05 SOL", callback_data=f"buy_{mint}_0.05"),
            InlineKeyboardButton("🟢 0.1 SOL", callback_data=f"buy_{mint}_0.1"),
            InlineKeyboardButton("🟢 0.25 SOL", callback_data=f"buy_{mint}_0.25")
        ],
        [
            InlineKeyboardButton("🟢 0.5 SOL", callback_data=f"buy_{mint}_0.5"),
            InlineKeyboardButton("🟢 1.0 SOL", callback_data=f"buy_{mint}_1.0"),
            InlineKeyboardButton(custom_buy_label, callback_data=f"custom_buy_{mint}")
        ],
        [
            InlineKeyboardButton(f"🔴 {sell_prefix} 25%", callback_data=f"sell_{mint}_25"),
            InlineKeyboardButton(f"🔴 {sell_prefix} 50%", callback_data=f"sell_{mint}_50"),
            InlineKeyboardButton(f"🔴 {sell_prefix} 100%", callback_data=f"sell_{mint}_100"),
            InlineKeyboardButton(custom_sell_label, callback_data=f"custom_sell_{mint}")
        ],
        [
            InlineKeyboardButton(track_btn_label, callback_data=track_cb),
            InlineKeyboardButton(share_btn_label, url=tg_share_link),
            InlineKeyboardButton("📢 Share on X", url=x_share_link)
        ],
        links_row,
        [
            InlineKeyboardButton("💵 Price Radar", callback_data=f"price_{mint}"),
            InlineKeyboardButton("💱 " + ("Sim Quote" if user_lang == "en" else "محاكاة الصفقة"), callback_data=f"quote_{mint}"),
            InlineKeyboardButton(refresh_quote_label, callback_data=f"inspect_{mint}")
        ],
        [
            InlineKeyboardButton("📲 " + ("Deposit" if user_lang == "en" else "إيداع"), callback_data="btn_show_qr"),
            InlineKeyboardButton(t("btn_back", user_lang), callback_data="btn_refresh")
        ]
    ])


def build_settings_card(user_id: int, user_lang: str) -> Tuple[str, InlineKeyboardMarkup]:
    """Constructs the unified trading settings interface with dynamic checkmarks, slippage, gas, and volatility alert toggles."""
    settings = get_user_settings(user_id)
    current_bps = settings.get("slippage_bps", 100)
    current_slip = current_bps / 100.0
    gas_lamports = settings.get("priority_fee", 50000)
    gas_sol = gas_lamports / 1e9
    current_tp = settings.get("default_tp_pct", 50)
    current_sl = settings.get("default_sl_pct", 25)
    alerts_on, alert_th = get_user_alert_settings(user_id)
    now_str = get_current_time_str()

    tier_label = (
        t("gas_tier_normal", user_lang) if gas_lamports <= 100000 else
        (t("gas_tier_turbo", user_lang) if gas_lamports <= 500000 else t("gas_tier_ultra", user_lang))
    )

    current_buy_amt = settings.get("default_buy_amount", 0.1)

    title = t("settings_title", user_lang)
    body = t("settings_body", user_lang, slippage=current_slip)
    if user_lang == "en":
        extra_info = (
            f"\n\n⚡ <b>Priority Gas:</b> <code>{gas_sol:.5f} SOL</code> ({tier_label})\n"
            f"🎯 <b>Auto Take-Profit:</b> <code>+{current_tp}%</code>\n"
            f"🛑 <b>Auto Stop-Loss:</b> <code>-{current_sl}%</code>\n"
            f"💰 <b>Default Quick-Buy:</b> <code>{current_buy_amt:.2f} SOL</code>\n"
            f"🔔 <b>Price Movement Alerts:</b> <code>{'ENABLED' if alerts_on else 'DISABLED'} (±{alert_th:.0f}%)</code>\n\n"
            f"Select parameters or speed tiers below:"
        )
        alerts_btn_text = f"🔔 Alerts: ON (±{alert_th:.0f}%)" if alerts_on else "🔕 Alerts: OFF"
        reset_label = "🔄 Reset Defaults"
        autobuy_label = "🎯 Auto-Buy Radar"
        presets_label = f"🎯 Quick-Buy ({current_buy_amt:.2f} SOL)"
    else:
        extra_info = (
            f"\n\n⚡ <b>أولوية الغاز:</b> <code>{gas_sol:.5f} SOL</code> ({tier_label})\n"
            f"🎯 <b>جني الأرباح التلقائي:</b> <code>+{current_tp}%</code>\n"
            f"🛑 <b>وقف الخسارة التلقائي:</b> <code>-{current_sl}%</code>\n"
            f"💰 <b>مبلغ القنص السريع الافتراضي:</b> <code>{current_buy_amt:.2f} SOL</code>\n"
            f"🔔 <b>تنبيهات تقلبات الأسعار:</b> <code>{'مفعلة' if alerts_on else 'معطلة'} (±{alert_th:.0f}%)</code>\n\n"
            f"اختر الإعدادات المناسبة لاستراتيجيتك أدناه:"
        )
        alerts_btn_text = f"🔔 التنبيهات: مفعلة (±{alert_th:.0f}%)" if alerts_on else "🔕 التنبيهات: معطلة"
        reset_label = "🔄 استعادة الافتراضيات"
        autobuy_label = "🎯 رادار القنص التلقائي"
        presets_label = f"🎯 مبالغ القنص ({current_buy_amt:.2f} SOL)"

    text = f"{title}\n━━━━━━━━━━━━━━━━━━━\n{body}{extra_info}\n🕒 <code>{now_str}</code>"

    # Slippage row with active checkmark
    slip_btns = [
        InlineKeyboardButton(f"{'✅ ' if current_bps == 50 else ''}0.5%", callback_data="slip_50"),
        InlineKeyboardButton(f"{'✅ ' if current_bps == 100 else ''}1.0%", callback_data="slip_100"),
        InlineKeyboardButton(f"{'✅ ' if current_bps == 200 else ''}2.0%", callback_data="slip_200"),
        InlineKeyboardButton(f"{'✅ ' if current_bps == 500 else ''}5.0%", callback_data="slip_500")
    ]

    # Priority fee row with active checkmark
    gas_btns = [
        InlineKeyboardButton(f"{'✅ ' if gas_lamports == 50000 else ''}⚡ Normal", callback_data="gas_50000"),
        InlineKeyboardButton(f"{'✅ ' if gas_lamports == 250000 else ''}🚀 Turbo", callback_data="gas_250000"),
        InlineKeyboardButton(f"{'✅ ' if gas_lamports == 1000000 else ''}🏎️ Ultra", callback_data="gas_1000000")
    ]

    # Take-Profit row with active checkmark
    tp_btns = [
        InlineKeyboardButton(f"{'✅ ' if current_tp == 25 else ''}🎯 +25%", callback_data="tp_25"),
        InlineKeyboardButton(f"{'✅ ' if current_tp == 50 else ''}🎯 +50%", callback_data="tp_50"),
        InlineKeyboardButton(f"{'✅ ' if current_tp == 100 else ''}🎯 +100%", callback_data="tp_100")
    ]

    # Stop-Loss row with active checkmark
    sl_btns = [
        InlineKeyboardButton(f"{'✅ ' if current_sl == 15 else ''}🛑 -15%", callback_data="sl_15"),
        InlineKeyboardButton(f"{'✅ ' if current_sl == 25 else ''}🛑 -25%", callback_data="sl_25"),
        InlineKeyboardButton(f"{'✅ ' if current_sl == 50 else ''}🛑 -50%", callback_data="sl_50")
    ]

    kb = [
        slip_btns,
        gas_btns,
        tp_btns,
        sl_btns,
        [
            InlineKeyboardButton(alerts_btn_text, callback_data="toggle_alerts"),
            InlineKeyboardButton(autobuy_label, callback_data="btn_autobuy")
        ],
        [
            InlineKeyboardButton(presets_label, callback_data="btn_presets"),
            InlineKeyboardButton(reset_label, callback_data="btn_reset_defaults")
        ],
        [
            InlineKeyboardButton(t("btn_gas_radar", user_lang), callback_data="btn_gas_fees"),
            InlineKeyboardButton(t("btn_lang_toggle", user_lang), callback_data="btn_toggle_lang")
        ],
        [
            InlineKeyboardButton("❓ Help" if user_lang == "en" else "❓ المساعدة", callback_data="btn_help"),
            InlineKeyboardButton(t("btn_back", user_lang), callback_data="btn_refresh")
        ]
    ]

    return text, InlineKeyboardMarkup(kb)



def build_welcome_text(user, pubkey: str, balance: float, now_str: str, lang: str = "en") -> str:
    """Constructs the executive dashboard card in user's preferred language."""
    if getattr(user, "username", None) and user.username.strip():
        display_user = f"@{html.escape(user.username.strip())}"
    elif getattr(user, "first_name", None) and user.first_name.strip() and user.first_name.strip() != ".":
        display_user = html.escape(user.first_name.strip())
    else:
        display_user = "Trader" if lang == "en" else "المتداول"

    if balance > 0.0001:
        bal_status = " 🟢 " + ("(Ready to snipe!)" if lang == "en" else "(جاهز للقنص الفوري!)")
    else:
        bal_status = " 💡 " + ("(Tap [📲 Deposit QR] below to start)" if lang == "en" else "(اضغط [📲 رمز QR للإيداع] للبدء)")

    return (
        f"{t('welcome_title', lang)}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{t('trader', lang)}: <b>{display_user}</b>\n"
        f"{t('wallet_dedicated', lang)}:\n"
        f"<code>{pubkey}</code>\n\n"
        f"{t('current_balance', lang)}: <code>{balance:.4f} SOL</code>{bal_status}\n"
        f"{t('platform_fee', lang)}\n"
        f"{t('updated_at', lang)}: <code>{now_str}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{t('how_to_start_title', lang)}\n"
        f"{t('how_to_start_steps', lang)}\n"
    )



async def safe_edit_text(query, text: str, reply_markup=None):
    """Safely edits message text while preventing 'Message is not modified' errors."""
    try:
        if isinstance(getattr(query, "data", None), str) and hasattr(query, "edit_message_text"):
            await query.edit_message_text(text, parse_mode="HTML", reply_markup=reply_markup, disable_web_page_preview=True)
        elif hasattr(query, "edit_text"):
            await query.edit_text(text, parse_mode="HTML", reply_markup=reply_markup, disable_web_page_preview=True)
        elif hasattr(query, "edit_message_text"):
            await query.edit_message_text(text, parse_mode="HTML", reply_markup=reply_markup, disable_web_page_preview=True)
    except BadRequest as e:
        if "Message is not modified" in str(e):
            if hasattr(query, "answer"):
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

    target_token_mint = None

    # Process Referral Code & Deep-Link Parameters
    if context.args:
        raw_arg = context.args[0].strip()

        # 1. Compound referral + token: e.g. ref_12345_token_MINT or ref_12345_MINT
        ref_match = re.match(r"^ref_(\d+)(?:_(?:token_|buy_|snipe_)?([1-9A-HJ-NP-Za-km-z]{32,44}))?$", raw_arg)
        if ref_match:
            try:
                referrer_id = int(ref_match.group(1))
                if is_new and record_referral(user_id, referrer_id):
                    logger.info(f"User {user_id} referred by {referrer_id}")
                    try:
                        ref_lang = get_user_language(referrer_id)
                        ref_username = f"@{username}" if username else f"User {user_id}"
                        if ref_lang == "ar":
                            ref_msg = (
                                "🎉 <b>إحالة جديدة انضمت بنجاح!</b>\n"
                                "━━━━━━━━━━━━━━━━━━━━━━\n"
                                f"👤 انضم المتداول <b>{html.escape(ref_username)}</b> عبر رابط إحالتك.\n"
                                "💰 ستحصل تلقائياً على <b>25%</b> من جميع عمولات التداول التي ينفذها مدى الحياة!\n"
                                "━━━━━━━━━━━━━━━━━━━━━━\n"
                                "📊 تفقد أرباحك عبر الأمر /referral"
                            )
                        else:
                            ref_msg = (
                                "🎉 <b>New Referral Joined!</b>\n"
                                "━━━━━━━━━━━━━━━━━━━━━━\n"
                                f"👤 Trader <b>{html.escape(ref_username)}</b> joined via your referral link.\n"
                                "💰 You will automatically earn <b>25%</b> of all their trading fees for life!\n"
                                "━━━━━━━━━━━━━━━━━━━━━━\n"
                                "📊 Track earnings anytime via /referral"
                            )
                        await context.bot.send_message(
                            chat_id=referrer_id,
                            text=ref_msg,
                            parse_mode="HTML"
                        )
                    except Exception as ref_err:
                        logger.warning(f"Failed to send referral notification to {referrer_id}: {ref_err}")
            except Exception as e:
                logger.warning(f"Referral parsing error: {e}")

            if ref_match.group(2):
                target_token_mint = ref_match.group(2)

        # 2. Token deep-link prefix: token_<mint>, buy_<mint>, snipe_<mint>
        elif any(raw_arg.startswith(pfx) for pfx in ("token_", "buy_", "snipe_")):
            potential = raw_arg.split("_", 1)[1]
            extracted = extract_token_mint(potential)
            if extracted:
                target_token_mint = extracted
            else:
                matched = search_solana_token(potential)
                if matched:
                    target_token_mint = matched["mint"]

        # 3. Direct token CA (32-44 base58 characters)
        elif extract_token_mint(raw_arg):
            target_token_mint = extract_token_mint(raw_arg)

    # If deep-link points to a specific token, immediately open audited token card with 1-click buy buttons
    if target_token_mint:
        scan = scan_token_security(target_token_mint)
        card_text = format_token_card(scan, lang=user_lang)
        if is_new:
            welcome_header = (
                f"👋 <b>Welcome to Popcorn Sniper!</b>\n"
                f"Your dedicated non-custodial wallet has been created:\n"
                f"<code>{pubkey}</code>\n"
                f"━━━━━━━━━━━━━━━━━━━\n\n"
            ) if user_lang == "en" else (
                f"👋 <b>مرحباً بك في بوت Popcorn للقنص!</b>\n"
                f"تم إنشاء محفظتك المخصصة غير الاحتجازية بنجاح:\n"
                f"<code>{pubkey}</code>\n"
                f"━━━━━━━━━━━━━━━━━━━\n\n"
            )
            card_text = welcome_header + card_text
        kb = get_token_card_keyboard(target_token_mint, user_lang, user_id=user_id, symbol=scan.get("symbol", "TOKEN"))
        await update.message.reply_text(
            card_text,
            parse_mode="HTML",
            reply_markup=kb,
            disable_web_page_preview=True
        )
        return

    balance = get_sol_balance(pubkey)
    now_str = get_current_time_str()
    welcome_text = build_welcome_text(user, pubkey, balance, now_str, user_lang)

    await update.message.reply_text(
        welcome_text,
        parse_mode="HTML",
        reply_markup=get_main_menu_keyboard(user_id, user_lang),
        disable_web_page_preview=True
    )


async def render_trending_radar(target, user_id: int, user_lang: str, is_edit: bool = False):
    """Renders real-time DexScreener trending radar with 1-click snipe, price radar, and swap simulation shortcuts."""
    tokens = get_trending_tokens(limit=5)
    text = format_trending_list(tokens, lang=user_lang)

    keyboard = []
    for tkn in tokens:
        sym = html.escape(tkn["symbol"])
        mint = tkn["mint"]
        c24 = tkn.get("change_24h", 0.0)
        snipe_lbl = f"🚀 ${sym} ({c24:+.1f}%)"
        keyboard.append([
            InlineKeyboardButton(snipe_lbl, callback_data=f"inspect_{mint}"),
            InlineKeyboardButton("💵 Price", callback_data=f"price_{mint}"),
            InlineKeyboardButton("💱 Quote", callback_data=f"quote_{mint}")
        ])
    refresh_btn_text = "🔄 " + ("Refresh Trending" if user_lang == "en" else "تحديث القائمة")
    surge_btn_text = "🚀 " + ("Top Gainers" if user_lang == "en" else "الأعلى صعوداً")
    keyboard.append([
        InlineKeyboardButton(refresh_btn_text, callback_data="btn_trending"),
        InlineKeyboardButton(surge_btn_text, callback_data="btn_surge")
    ])
    keyboard.append([
        InlineKeyboardButton(t("btn_back", user_lang), callback_data="btn_refresh")
    ])

    markup = InlineKeyboardMarkup(keyboard)
    if is_edit:
        await safe_edit_text(target, text, reply_markup=markup)
    else:
        if hasattr(target, "edit_text"):
            await target.edit_text(text, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True)
        elif hasattr(target, "reply_text"):
            await target.reply_text(text, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True)
        elif hasattr(target, "message") and hasattr(target.message, "reply_text"):
            await target.message.reply_text(text, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True)


async def trending_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /trending command."""
    user_id = update.effective_user.id
    user_lang = get_user_language(user_id)
    wait_text = "🔥 <b>جاري جلب أكثر عملات سولانا رواجاً من DexScreener...</b>" if user_lang == "ar" else "🔥 <b>Fetching top trending Solana tokens from DexScreener...</b>"
    status_msg = await update.message.reply_text(wait_text, parse_mode="HTML")
    await render_trending_radar(status_msg, user_id, user_lang, is_edit=False)


async def surge_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /surge, /gainers, and /pump command."""
    user_id = update.effective_user.id
    user_lang = get_user_language(user_id)
    await render_surge_radar(update.message, user_id, user_lang, is_edit=False)


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
    share_btn_text = "📤 Share on Telegram" if user_lang == "en" else "📤 مشاركة عبر تيليجرام"

    x_intent_text = (
        f"Trade Solana memecoins with sub-400ms execution on Popcorn Sniper Bot! 🍿⚡\n\n"
        f"Built-in RugCheck auditor, auto-buy, and non-custodial wallets.\n\n"
        f"Start trading: {ref_link}"
    )
    x_share_url = f"https://twitter.com/intent/tweet?text={urllib.parse.quote(x_intent_text)}"

    refresh_label = "🔄 تحديث الإحصائيات" if user_lang == "ar" else "🔄 Refresh Stats"

    kb = [
        [
            InlineKeyboardButton(share_btn_text, url=f"https://t.me/share/url?url={urllib.parse.quote(ref_link)}&text={urllib.parse.quote(share_text)}"),
            InlineKeyboardButton("📢 Share on X", url=x_share_url)
        ],
        [
            InlineKeyboardButton(refresh_label, callback_data="btn_referral"),
            InlineKeyboardButton(t("btn_back", user_lang), callback_data="btn_refresh")
        ]
    ]
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True)


async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Detects pasted token contract addresses, custom buy amounts, or platform URLs."""
    user_id = update.effective_user.id
    user_lang = get_user_language(user_id)
    text = update.message.text.strip()

    # 1. Check if user is replying with custom buy amount
    custom_buy_mint = context.user_data.get("awaiting_custom_buy")
    if custom_buy_mint:
        try:
            custom_amt = float(text)
            if custom_amt > 0:
                context.user_data.pop("awaiting_custom_buy", None)
                pubkey, _ = get_or_create_wallet(user_id)
                bal = get_sol_balance(pubkey)
                if bal < (custom_amt + 0.005):
                    err_text = (
                        f"❌ <b>Insufficient SOL balance!</b>\n"
                        f"Required: <code>{custom_amt} SOL</code> (+ gas fees)\n"
                        f"Available: <code>{bal:.4f} SOL</code>\n\n"
                        f"Deposit SOL to your trading wallet:\n<code>{pubkey}</code>"
                    ) if user_lang == "en" else (
                        f"❌ <b>رصيد SOL غير كافٍ!</b>\n"
                        f"المطلوب: <code>{custom_amt} SOL</code> (+ رسوم الغاز)\n"
                        f"الرصيد المتاح: <code>{bal:.4f} SOL</code>\n\n"
                        f"يرجى إيداع SOL في محفظتك:\n<code>{pubkey}</code>"
                    )
                    await update.message.reply_text(err_text, parse_mode="HTML")
                    return

                prep_text = "⚡ <b>Routing best swap via Jupiter V6...</b>" if user_lang == "en" else "⚡ <b>جاري تحضير مسار الشراء عبر Jupiter...</b>"
                status_msg = await update.message.reply_text(prep_text, parse_mode="HTML")

                success, sig_or_err, out_amount, fee_sol = execute_buy_swap(user_id, custom_buy_mint, custom_amt, user_lang)

                if success:
                    if user_lang == "en":
                        success_text = (
                            f"🎉 <b>Custom Buy Swap Executed Successfully!</b> 🟢\n"
                            f"━━━━━━━━━━━━━━━━━━━\n"
                            f"💸 Amount: <code>{custom_amt} SOL</code>\n"
                            f"🛡️ Platform Fee (1%): <code>{fee_sol:.6f} SOL</code>\n\n"
                            f"🔗 <a href='https://solscan.io/tx/{sig_or_err}'>View Transaction on Solscan</a>"
                        )
                    else:
                        success_text = (
                            f"🎉 <b>تم تنفيذ صفقة الشراء المخصصة بنجاح!</b> 🟢\n"
                            f"━━━━━━━━━━━━━━━━━━━\n"
                            f"💸 القيمة: <code>{custom_amt} SOL</code>\n"
                            f"🛡️ عمولة المنصة (1%): <code>{fee_sol:.6f} SOL</code>\n\n"
                            f"🔗 <a href='https://solscan.io/tx/{sig_or_err}'>عرض المعاملة على Solscan</a>"
                        )
                    await status_msg.edit_text(success_text, parse_mode="HTML", disable_web_page_preview=True)
                    return
                else:
                    await status_msg.edit_text(f"❌ <b>Transaction failed</b>: <code>{html.escape(sig_or_err)}</code>", parse_mode="HTML")
                    return
        except ValueError:
            pass  # Not a numeric reply, proceed to normal analysis

    # 2. Check if user is replying with custom sell percentage
    custom_sell_mint = context.user_data.get("awaiting_custom_sell")
    if custom_sell_mint:
        try:
            clean_pct = text.strip().rstrip("%").lower()
            if clean_pct in ("all", "max"):
                pct_val = 100
            else:
                pct_val = int(clean_pct)

            if 1 <= pct_val <= 100:
                context.user_data.pop("awaiting_custom_sell", None)
                prep_sell = f"⚡ <b>Executing {pct_val}% Sell Swap via Jupiter...</b>" if user_lang == "en" else f"⚡ <b>جاري تنفيذ بيع {pct_val}% من العملة عبر Jupiter...</b>"
                status_msg = await update.message.reply_text(prep_sell, parse_mode="HTML")
                success, sig_or_err, sol_received = execute_sell_swap(user_id, custom_sell_mint, pct_val, lang=user_lang)
                if success:
                    if user_lang == "en":
                        succ_text = (
                            f"🎉 <b>Custom Sell Swap Executed Successfully!</b> 🔴\n"
                            f"━━━━━━━━━━━━━━━━━━━\n"
                            f"💰 Received: <code>{sol_received:.4f} SOL</code> in wallet\n\n"
                            f"🔗 <a href='https://solscan.io/tx/{sig_or_err}'>View Transaction on Solscan</a>"
                        )
                    else:
                        succ_text = (
                            f"🎉 <b>تم تنفيذ صفقة البيع المخصصة بنجاح!</b> 🔴\n"
                            f"━━━━━━━━━━━━━━━━━━━\n"
                            f"💰 تم استلام: <code>{sol_received:.4f} SOL</code> في محفظتك\n\n"
                            f"🔗 <a href='https://solscan.io/tx/{sig_or_err}'>عرض المعاملة على Solscan</a>"
                        )
                    await status_msg.edit_text(succ_text, parse_mode="HTML", disable_web_page_preview=True)
                    return
                else:
                    await status_msg.edit_text(f"❌ <b>Sell failed</b>: <code>{html.escape(sig_or_err)}</code>", parse_mode="HTML")
                    return
        except ValueError:
            pass

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
                success, sig_or_err, out_amount, fee_sol = execute_buy_swap(user_id, mint, auto_amt, user_lang)
                if success:
                    if user_lang == "ar":
                        success_text = (
                            f"🎯 <b>تم القنص التلقائي (Auto-Buy) بنجاح!</b> 🟢\n"
                            f"━━━━━━━━━━━━━━━━━━━\n"
                            f"💸 القيمة: <code>{auto_amt} SOL</code>\n"
                            f"🪙 العملة: <b>${html.escape(scan['symbol'])}</b>\n"
                            f"🛡️ عمولة المنصة (1%): <code>{fee_sol:.6f} SOL</code>\n\n"
                            f"🔗 <a href='https://solscan.io/tx/{sig_or_err}'>عرض المعاملة على Solscan</a>"
                        )
                    else:
                        success_text = (
                            f"🎯 <b>Auto-Buy Swap Executed Successfully!</b> 🟢\n"
                            f"━━━━━━━━━━━━━━━━━━━\n"
                            f"💸 Amount: <code>{auto_amt} SOL</code>\n"
                            f"🪙 Token: <b>${html.escape(scan['symbol'])}</b>\n"
                            f"🛡️ Platform Fee (1%): <code>{fee_sol:.6f} SOL</code>\n\n"
                            f"🔗 <a href='https://solscan.io/tx/{sig_or_err}'>View Transaction on Solscan</a>"
                        )
                    await status_msg.edit_text(success_text, parse_mode="HTML", disable_web_page_preview=True)
                    return
                else:
                    err_msg = f"❌ <b>Auto-Buy failed:</b> <code>{html.escape(sig_or_err)}</code>" if user_lang == "en" else f"❌ <b>فشل القنص التلقائي:</b> <code>{html.escape(sig_or_err)}</code>"
                    await status_msg.edit_text(err_msg, parse_mode="HTML")
                    return

        await status_msg.edit_text(card_text, parse_mode="HTML", reply_markup=get_token_card_keyboard(mint, user_lang, user_id=user_id, symbol=scan.get("symbol", "TOKEN")), disable_web_page_preview=True)
    else:
        # Check if user sent a token ticker or name (e.g. BONK, $POPCAT, WIF, pepe coin, ai 16z)
        clean_text = text.strip().lstrip("$")
        if 1 <= len(clean_text) <= 40 and "\n" not in clean_text and "\r" not in clean_text and not clean_text.startswith("/"):
            matched_token = search_solana_token(clean_text)
            if matched_token:
                found_mint = matched_token["mint"]
                scan = scan_token_security(found_mint)
                card_text = format_token_card(scan, lang=user_lang)
                await update.message.reply_text(card_text, parse_mode="HTML", reply_markup=get_token_card_keyboard(found_mint, user_lang, user_id=user_id, symbol=scan.get("symbol", "TOKEN")), disable_web_page_preview=True)
                return

        hint_text = (
            "ℹ️ <b>Send any Solana Contract Address (CA), token ticker (e.g. <code>BONK</code>), or DexScreener / Pump.fun link to start sniping.</b>\n\n"
            "Example: <code>DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263</code> (BONK)"
        ) if user_lang == "en" else (
            "ℹ️ <b>أرسل عنوان العقد الذكي (CA) أو رمز العملة (مثل <code>BONK</code>) أو رابطها من DexScreener أو Pump.fun لبدء القنص.</b>\n\n"
            "مثال: <code>DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263</code> (BONK)"
        )
        await update.message.reply_text(hint_text, parse_mode="HTML")


async def render_watchlist(target, user_id: int, user_lang: str, is_edit: bool = False):
    """Renders the user's personal watchlist with real-time prices and 1-click buy buttons."""
    watchlist = get_user_watchlist(user_id)
    now_str = get_current_time_str()
    if not watchlist:
        empty_text = (
            f"{t('watchlist_title', user_lang)}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"{t('watchlist_empty', user_lang)}\n\n"
            f"🕒 <code>{now_str}</code>"
        )
        trending_btn = "🔥 Explore Trending" if user_lang == "en" else "🔥 استكشاف العملات الرائجة"
        alerts_btn = "🔔 Alert Radar" if user_lang == "en" else "🔔 رادار التنبيهات"
        kb = [
            [
                InlineKeyboardButton(trending_btn, callback_data="btn_trending"),
                InlineKeyboardButton(alerts_btn, callback_data="btn_alerts")
            ],
            [InlineKeyboardButton(t("btn_back", user_lang), callback_data="btn_refresh")]
        ]
        if is_edit:
            await safe_edit_text(target, empty_text, reply_markup=InlineKeyboardMarkup(kb))
        else:
            await target.reply_text(empty_text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb))
        return

    text_lines = [
        f"{t('watchlist_title', user_lang)}",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━"
    ]
    kb = []
    active_items = watchlist[:8]
    mints_to_fetch = [item["mint"] for item in active_items]
    batch_prices = get_batch_token_prices(mints_to_fetch)

    for item in active_items:
        sym = html.escape(item["symbol"])
        mint = item["mint"]
        b_info = batch_prices.get(mint, {})
        p = float(b_info.get("price_usd") or item.get("last_price") or item.get("initial_price") or 0.0)
        c24 = float(b_info.get("change_24h") or 0.0)
        emoji = "📈" if c24 >= 0 else "📉"
        text_lines.append(f"• <b>${sym}</b>: <code>${p:.6f}</code> {emoji} <code>{c24:+.1f}%</code>")
        text_lines.append(f"  📋 <code>{mint}</code>\n")
        kb.append([
            InlineKeyboardButton(f"🚀 Snipe ${sym}", callback_data=f"inspect_{mint}"),
            InlineKeyboardButton("💵 Price", callback_data=f"price_{mint}"),
            InlineKeyboardButton("💱 Quote", callback_data=f"quote_{mint}"),
            InlineKeyboardButton("🗑️ Untrack", callback_data=f"untrack_{mint}")
        ])

    if active_items:
        avg_change = sum(float(batch_prices.get(item["mint"], {}).get("change_24h") or 0.0) for item in active_items) / len(active_items)
        avg_emoji = "📈" if avg_change >= 0 else "📉"
        pulse_label = "24h Avg Pulse" if user_lang == "en" else "متوسط النبض 24 ساعة"
        text_lines.append(f"📊 <b>{pulse_label}</b>: {avg_emoji} <code>{avg_change:+.2f}%</code>\n")

    tip_text = (
        "💡 <b>Commands:</b> <code>/track [CA]</code> • <code>/untrack [CA]</code> • <code>/untrack all</code>\n"
        if user_lang == "en" else
        "💡 <b>الأوامر المتاحة:</b> <code>/track [العقد]</code> • <code>/untrack [العقد]</code> • <code>/untrack all</code>\n"
    )
    text_lines.append(tip_text)
    text_lines.append(f"🕒 <code>{now_str}</code>")
    refresh_btn_text = "🔄 " + ("Refresh Prices" if user_lang == "en" else "تحديث الأسعار")
    alerts_btn_text = "🔔 " + ("Alert Radar" if user_lang == "en" else "رادار التنبيهات")
    clear_btn_text = "🗑️ " + ("Clear All" if user_lang == "en" else "مسح الكل")
    kb.append([
        InlineKeyboardButton(refresh_btn_text, callback_data="btn_watchlist"),
        InlineKeyboardButton(clear_btn_text, callback_data="btn_clear_watchlist")
    ])
    kb.append([
        InlineKeyboardButton(alerts_btn_text, callback_data="btn_alerts"),
        InlineKeyboardButton(t("btn_back", user_lang), callback_data="btn_refresh")
    ])

    full_text = "\n".join(text_lines)
    if is_edit:
        await safe_edit_text(target, full_text, reply_markup=InlineKeyboardMarkup(kb))
    else:
        await target.reply_text(full_text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb))


async def render_price_card(target, user_id: int, user_lang: str, mint: str, is_edit: bool = False, bot_username: str = "PopcornSniperBot"):
    """Renders real-time token price & liquidity radar with 1-click quick-buy, dynamic watchlist tracking, X viral sharing, and live refresh."""
    scan = scan_token_security(mint)
    sym = html.escape(scan.get("symbol", "TOKEN"))
    name = html.escape(scan.get("name", "Unknown Token"))
    p_usd = scan.get("price_usd", 0.0)
    c24 = scan.get("price_change_24h", 0.0)
    liq = scan.get("liquidity_usd", 0.0)
    mcap = scan.get("mcap", 0.0)
    vol24 = scan.get("volume_24h", 0.0)
    now_str = get_current_time_str()
    emoji = "📈" if c24 >= 0 else "📉"

    title = t("price_card_title", user_lang)
    settings = get_user_settings(user_id)
    default_buy_amt = settings.get("default_buy_amount", 0.1)

    if user_lang == "ar":
        card = (
            f"{title} ⚡\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"🪙 <b>{name}</b> (<code>${sym}</code>)\n"
            f"💵 <b>السعر اللحظي:</b> <code>${p_usd:.8f}</code> {emoji} <code>{c24:+.2f}%</code>\n"
            f"💎 <b>القيمة السوقية:</b> <code>${mcap:,.0f}</code>\n"
            f"💧 <b>السيولة المتاحة:</b> <code>${liq:,.0f}</code>\n"
            f"📊 <b>حجم تداول 24 ساعة:</b> <code>${vol24:,.0f}</code>\n"
            f"📋 <b>العقد:</b> <code>{mint}</code>\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"🕒 <code>{now_str}</code>"
        )
        quick_buy_label = f"🟢 شراء سريع ({default_buy_amt:.2f} SOL)"
        snipe_label = f"🚀 فحص وتداول ${sym}"
        refresh_label = "🔄 تحديث السعر"
    else:
        card = (
            f"{title} ⚡\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"🪙 <b>{name}</b> (<code>${sym}</code>)\n"
            f"💵 <b>Current Price:</b> <code>${p_usd:.8f}</code> {emoji} <code>{c24:+.2f}%</code>\n"
            f"💎 <b>Market Cap:</b> <code>${mcap:,.0f}</code>\n"
            f"💧 <b>Liquidity:</b> <code>${liq:,.0f}</code>\n"
            f"📊 <b>24h Volume:</b> <code>${vol24:,.0f}</code>\n"
            f"📋 <b>CA:</b> <code>{mint}</code>\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"🕒 <code>{now_str}</code>"
        )
        quick_buy_label = f"🟢 Quick Buy ({default_buy_amt:.2f} SOL)"
        snipe_label = f"🚀 Inspect & Snipe ${sym}"
        refresh_label = "🔄 Refresh Price"

    is_tracked = is_token_in_watchlist(user_id, mint) if user_id else False
    if is_tracked:
        track_label = "⭐ " + ("Untrack" if user_lang == "en" else "إزالة من المتابعة")
        track_cb = f"untrack_{mint}"
    else:
        track_label = "⭐ " + t("btn_track", user_lang)
        track_cb = f"track_{mint}"

    ref_param = f"?start=ref_{user_id}" if user_id else ""
    share_bot_url = f"https://t.me/{bot_username}{ref_param}"
    x_intent_text = (
        f"Checking ${sym} on @{bot_username}! 🍿⚡\n"
        f"Price: ${p_usd:.8f} ({c24:+.1f}%)\n"
        f"Contract: {mint}\n\n"
        f"Trade now: {share_bot_url}"
    )
    import urllib.parse
    x_share_link = f"https://twitter.com/intent/tweet?text={urllib.parse.quote(x_intent_text)}"

    quote_sim_label = "💱 " + ("Sim Quote" if user_lang == "en" else "محاكاة الصفقة")
    kb = [
        [
            InlineKeyboardButton(quick_buy_label, callback_data=f"buy_{mint}_{default_buy_amt}"),
            InlineKeyboardButton(quote_sim_label, callback_data=f"quote_{mint}_{default_buy_amt}")
        ],
        [
            InlineKeyboardButton(snipe_label, callback_data=f"inspect_{mint}"),
            InlineKeyboardButton(track_label, callback_data=track_cb)
        ],
        [
            InlineKeyboardButton("📊 DexScreener", url=f"https://dexscreener.com/solana/{mint}"),
            InlineKeyboardButton("🛡️ RugCheck", url=f"https://rugcheck.xyz/tokens/{mint}")
        ],
        [
            InlineKeyboardButton("📢 Share on X", url=x_share_link),
            InlineKeyboardButton(refresh_label, callback_data=f"price_{mint}")
        ],
        [InlineKeyboardButton(t("btn_back", user_lang), callback_data="btn_refresh")]
    ]
    markup = InlineKeyboardMarkup(kb)
    if is_edit:
        await safe_edit_text(target, card, reply_markup=markup)
    else:
        if hasattr(target, "reply_text"):
            await target.reply_text(card, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True)
        elif hasattr(target, "message") and hasattr(target.message, "reply_text"):
            await target.message.reply_text(card, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True)


def get_token_decimals(mint: str) -> int:
    """Queries mint decimals via Solana RPC getTokenSupply with resilient fallback."""
    import urllib.request
    import json
    try:
        data = json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getTokenSupply",
            "params": [mint]
        }).encode("utf-8")
        req = urllib.request.Request(
            PRIMARY_RPC,
            data=data,
            headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}
        )
        with urllib.request.urlopen(req, timeout=5) as res:
            parsed = json.loads(res.read().decode("utf-8"))
            val = parsed.get("result", {}).get("value", {})
            dec = val.get("decimals")
            if dec is not None:
                return int(dec)
    except Exception:
        pass
    return 6


async def render_quote_card(target, user_id: int, user_lang: str, mint: str, amount_sol: float, is_edit: bool = False):
    """Renders real-time Jupiter V6 swap simulation card with route plan, slippage calculation, and 1-click execution."""
    scan = scan_token_security(mint)
    sym = html.escape(scan.get("symbol", "TOKEN"))
    name = html.escape(scan.get("name", "Unknown Token"))
    settings = get_user_settings(user_id)
    slippage_bps = settings.get("slippage_bps", 100)
    slip_pct = slippage_bps / 100.0
    gas_lamports = settings.get("priority_fee", 50000)
    gas_sol = gas_lamports / 1e9
    now_str = get_current_time_str()

    amount_lamports = int(amount_sol * 1_000_000_000)
    quote = get_jupiter_quote(
        input_mint=WSOL_MINT,
        output_mint=mint,
        amount_lamports=amount_lamports,
        slippage_bps=slippage_bps,
        with_fee=True
    )

    if not quote:
        err_text = (
            f"❌ <b>No Liquidity Route Found!</b>\n\n"
            f"Could not find a valid Jupiter V6 routing path for <code>{amount_sol} SOL</code> into <b>${sym}</b>."
        ) if user_lang == "en" else (
            f"❌ <b>تعذر العثور على مسار سيولة!</b>\n\n"
            f"لم يتم العثور على مسار صالح في Jupiter V6 لمبلغ <code>{amount_sol} SOL</code> مقابل عملة <b>${sym}</b>."
        )
        kb = [[InlineKeyboardButton(t("btn_back", user_lang), callback_data="btn_refresh")]]
        markup = InlineKeyboardMarkup(kb)
        if is_edit:
            await safe_edit_text(target, err_text, reply_markup=markup)
        else:
            if hasattr(target, "reply_text"):
                await target.reply_text(err_text, parse_mode="HTML", reply_markup=markup)
            elif hasattr(target, "message") and hasattr(target.message, "reply_text"):
                await target.message.reply_text(err_text, parse_mode="HTML", reply_markup=markup)
        return

    # Extract quote metrics
    raw_out = float(quote.get("outAmount", 0))
    raw_min = float(quote.get("otherAmountThreshold", 0))
    decimals = get_token_decimals(mint)
    divisor = 10 ** decimals
    out_tokens = raw_out / divisor
    min_tokens = raw_min / divisor
    price_impact_pct = float(quote.get("priceImpactPct") or 0.0)

    # Route AMM summary
    route_plan = quote.get("routePlan") or []
    routes = [(step.get("swapInfo") or {}).get("label", "DEX") for step in route_plan if isinstance(step, dict)]
    route_str = " ➔ ".join(routes) if routes else "Jupiter V6 Aggregator"

    # Platform fee calculation
    fee_lamports = float((quote.get("platformFee") or {}).get("amount", 0) or 0)
    fee_sol = fee_lamports / 1e9

    if user_lang == "ar":
        card = (
            f"🎯 <b>محاكاة صفقة الشراء الذكية (Jupiter V6 Quote)</b> ⚡\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"🪙 <b>العملة:</b> <b>{name}</b> (<code>${sym}</code>)\n"
            f"💸 <b>المبلغ المدفوع:</b> <code>{amount_sol:.4f} SOL</code>\n"
            f"💎 <b>الكمية المتوقعة:</b> <code>{out_tokens:,.2f} ${sym}</code>\n"
            f"🛑 <b>الحد الأدنى المضمون:</b> <code>{min_tokens:,.2f} ${sym}</code> ({slip_pct:.1f}% انزلاق)\n"
            f"📉 <b>تأثير السعر (Price Impact):</b> <code>{price_impact_pct:.2f}%</code>\n"
            f"🛣️ <b>مسار السيولة:</b> <code>{route_str}</code>\n"
            f"🛡️ <b>عمولة المنصة (1.0%):</b> <code>{fee_sol:.5f} SOL</code> (مشمولة)\n"
            f"⚡ <b>رسوم الأولوية:</b> <code>{gas_sol:.5f} SOL</code>\n"
            f"📋 <b>العقد:</b> <code>{mint}</code>\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"🕒 <code>{now_str}</code>"
        )
        exec_label = f"🟢 تنفيذ الشراء ({amount_sol:.2f} SOL)"
        refresh_label = "🔄 تحديث المحاكاة"
    else:
        card = (
            f"🎯 <b>Jupiter V6 Swap Simulation Quote</b> ⚡\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"🪙 <b>Token:</b> <b>{name}</b> (<code>${sym}</code>)\n"
            f"💸 <b>Input Amount:</b> <code>{amount_sol:.4f} SOL</code>\n"
            f"💎 <b>Estimated Output:</b> <code>~{out_tokens:,.2f} ${sym}</code>\n"
            f"🛑 <b>Guaranteed Minimum:</b> <code>~{min_tokens:,.2f} ${sym}</code> ({slip_pct:.1f}% Slippage)\n"
            f"📉 <b>Price Impact:</b> <code>{price_impact_pct:.2f}%</code>\n"
            f"🛣️ <b>Route Path:</b> <code>{route_str}</code>\n"
            f"🛡️ <b>Dev Fee (1.0%):</b> <code>{fee_sol:.5f} SOL</code> (Included)\n"
            f"⚡ <b>Priority Gas:</b> <code>{gas_sol:.5f} SOL</code>\n"
            f"📋 <b>CA:</b> <code>{mint}</code>\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"🕒 <code>{now_str}</code>"
        )
        exec_label = f"🟢 Execute Swap ({amount_sol:.2f} SOL)"
        refresh_label = "🔄 Refresh Simulation"

    is_tracked = is_token_in_watchlist(user_id, mint) if user_id else False
    if is_tracked:
        track_label = "⭐ " + ("Untrack" if user_lang == "en" else "إزالة من المتابعة")
        track_cb = f"untrack_{mint}"
    else:
        track_label = "⭐ " + t("btn_track", user_lang)
        track_cb = f"track_{mint}"

    # Interactive quick swap size tiers (e.g. 0.05, 0.1, 0.5, 1.0 SOL)
    amt_row = []
    for tier in [0.05, 0.1, 0.5, 1.0]:
        is_sel = abs(amount_sol - tier) < 0.001
        tier_lbl = f"🟢 {tier} SOL" if is_sel else f"{tier} SOL"
        amt_row.append(InlineKeyboardButton(tier_lbl, callback_data=f"quote_{mint}_{tier}"))

    kb = [
        amt_row,
        [
            InlineKeyboardButton(exec_label, callback_data=f"buy_{mint}_{amount_sol}"),
            InlineKeyboardButton("💵 Price Radar", callback_data=f"price_{mint}")
        ],
        [
            InlineKeyboardButton(track_label, callback_data=track_cb),
            InlineKeyboardButton("🛡️ RugCheck", callback_data=f"inspect_{mint}"),
            InlineKeyboardButton("📊 Dex", url=f"https://dexscreener.com/solana/{mint}")
        ],
        [
            InlineKeyboardButton(refresh_label, callback_data=f"quote_{mint}_{amount_sol}"),
            InlineKeyboardButton(t("btn_back", user_lang), callback_data="btn_refresh")
        ]
    ]
    markup = InlineKeyboardMarkup(kb)
    if is_edit:
        await safe_edit_text(target, card, reply_markup=markup)
    else:
        if hasattr(target, "reply_text"):
            await target.reply_text(card, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True)
        elif hasattr(target, "message") and hasattr(target.message, "reply_text"):
            await target.message.reply_text(card, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True)


async def render_trade_history(target, user_id: int, user_lang: str, is_edit: bool = False):
    """Renders recent executed trades with Solscan transaction links."""
    stats = get_user_trade_stats(user_id)
    recent = stats.get("recent_trades", [])
    now_str = get_current_time_str()
    title = t("trades_history_title", user_lang)

    if not recent:
        empty_text = (
            f"{title}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"{t('trades_no_history', user_lang)}\n\n"
            f"🕒 <code>{now_str}</code>"
        )
        kb = [[InlineKeyboardButton(t("btn_back", user_lang), callback_data="btn_refresh")]]
        if is_edit:
            await safe_edit_text(target, empty_text, reply_markup=InlineKeyboardMarkup(kb))
        else:
            await target.reply_text(empty_text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb))
        return

    text_lines = [
        title,
        "━━━━━━━━━━━━━━━━━━━━━━━━━━"
    ]
    for tr in recent[:8]:
        in_m = tr["input_mint"]
        out_m = tr["output_mint"]
        amt_in = tr["amount_in"]
        amt_out = tr["amount_out"]
        fee = tr.get("platform_fee_sol", 0.0) or 0.0
        sig = tr.get("tx_signature", "")
        status = tr.get("status", "CONFIRMED")
        dt = (tr.get("created_at") or "")[:19]

        is_buy = (in_m == WSOL_MINT)
        if is_buy:
            mint_short = f"{out_m[:4]}...{out_m[-4:]}"
            action_label = f"🟢 <b>BUY</b> <code>{amt_out:,.1f}</code> ({mint_short})"
            cost_label = f"💰 <code>{amt_in:.4f} SOL</code> (Fee: <code>{fee:.5f} SOL</code>)"
        else:
            mint_short = f"{in_m[:4]}...{in_m[-4:]}"
            action_label = f"🔴 <b>SELL</b> <code>{amt_in:,.1f}</code> ({mint_short})"
            cost_label = f"💰 Recv: <code>{amt_out:.4f} SOL</code> (Fee: <code>{fee:.5f} SOL</code>)"

        sig_link = f"<a href='https://solscan.io/tx/{sig}'>Solscan ↗</a>" if sig else "<code>Pending</code>"
        text_lines.append(f"{action_label}\n{cost_label} | {sig_link}\n🕒 <i>{dt}</i>\n")

    text_lines.append(f"🕒 <code>{now_str}</code>")
    refresh_btn_text = "🔄 " + ("Refresh History" if user_lang == "en" else "تحديث السجل")
    export_btn_text = t("btn_export_trades", user_lang)
    kb = [
        [
            InlineKeyboardButton(refresh_btn_text, callback_data="btn_history"),
            InlineKeyboardButton(export_btn_text, callback_data="btn_export_trades_csv")
        ],
        [InlineKeyboardButton(t("btn_back", user_lang), callback_data="btn_refresh")]
    ]
    full_text = "\n".join(text_lines)
    if is_edit:
        await safe_edit_text(target, full_text, reply_markup=InlineKeyboardMarkup(kb))
    else:
        await target.reply_text(full_text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True)


async def send_trades_csv_export(target, user_id: int, user_lang: str):
    """Generates and uploads an RFC 4180 CSV document of user's complete trade history."""
    import io
    from datetime import datetime, timezone
    trades = get_all_user_trades(user_id)
    if not trades:
        empty_msg = t("trades_csv_empty", user_lang)
        if hasattr(target, "reply_text"):
            await target.reply_text(empty_msg, parse_mode="HTML")
        elif hasattr(target, "message") and hasattr(target.message, "reply_text"):
            await target.message.reply_text(empty_msg, parse_mode="HTML")
        return

    csv_data = generate_trades_csv_bytes(user_id)
    bio = io.BytesIO(csv_data)
    now_str = get_current_time_str()
    timestamp_suffix = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    bio.name = f"popcorn_trades_{user_id}_{timestamp_suffix}.csv"

    caption = t("trades_csv_caption", user_lang, count=len(trades), time=now_str)
    if hasattr(target, "reply_document"):
        await target.reply_document(
            document=bio,
            filename=bio.name,
            caption=caption,
            parse_mode="HTML"
        )
    elif hasattr(target, "message") and hasattr(target.message, "reply_document"):
        await target.message.reply_document(
            document=bio,
            filename=bio.name,
            caption=caption,
            parse_mode="HTML"
        )


async def render_surge_radar(target, user_id: int, user_lang: str, is_edit: bool = False):
    """Renders the top explosive gainers on Solana with 1-click snipe buttons."""
    tokens = get_top_gainers(limit=5)
    text = format_gainers_list(tokens, lang=user_lang)
    keyboard = []
    if tokens:
        for tkn in tokens:
            sym = html.escape(tkn["symbol"])
            mint = tkn["mint"]
            c1 = tkn.get("change_1h", 0.0)
            snipe_label = f"🚀 ${sym} ({c1:+.1f}%)"
            keyboard.append([
                InlineKeyboardButton(snipe_label, callback_data=f"inspect_{mint}"),
                InlineKeyboardButton("💵 Price", callback_data=f"price_{mint}"),
                InlineKeyboardButton("💱 Quote", callback_data=f"quote_{mint}")
            ])
    else:
        trending_btn = "🔥 " + ("Explore Trending" if user_lang == "en" else "استكشاف العملات الرائجة")
        keyboard.append([
            InlineKeyboardButton(trending_btn, callback_data="btn_trending")
        ])
    refresh_label = "🔄 " + ("Refresh Gainers" if user_lang == "en" else "تحديث القائمة")
    trending_label = "🔥 " + ("Trending" if user_lang == "en" else "الرائجة")
    keyboard.append([
        InlineKeyboardButton(refresh_label, callback_data="btn_surge"),
        InlineKeyboardButton(trending_label, callback_data="btn_trending")
    ])
    keyboard.append([
        InlineKeyboardButton(t("btn_back", user_lang), callback_data="btn_refresh")
    ])
    if is_edit:
        await safe_edit_text(target, text, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await target.reply_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard), disable_web_page_preview=True)


async def render_positions(target, user_id: int, user_lang: str, is_edit: bool = False):
    """Renders the executive interactive portfolio card with real-time valuations and 1-click Sell buttons."""
    pubkey, _ = get_or_create_wallet(user_id)
    tokens = get_token_accounts(pubkey)
    now_str = get_current_time_str()
    title = t("positions_title", user_lang)

    if not tokens:
        empty_text = (
            f"{title}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"{t('no_positions', user_lang)}\n\n"
            f"🕒 <code>{now_str}</code>"
        )
        trending_btn = "🔥 Explore Trending" if user_lang == "en" else "🔥 استكشاف العملات الرائجة"
        deposit_btn = "💳 Deposit SOL" if user_lang == "en" else "💳 إيداع SOL"
        refresh_btn = "🔄 Refresh" if user_lang == "en" else "🔄 تحديث"
        kb = [
            [
                InlineKeyboardButton(trending_btn, callback_data="btn_trending"),
                InlineKeyboardButton(deposit_btn, callback_data="btn_show_qr")
            ],
            [
                InlineKeyboardButton(refresh_btn, callback_data="btn_positions"),
                InlineKeyboardButton(t("btn_back", user_lang), callback_data="btn_refresh")
            ]
        ]
        if is_edit:
            await safe_edit_text(target, empty_text, reply_markup=InlineKeyboardMarkup(kb))
        else:
            await target.reply_text(empty_text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb))
        return

    mints = [tkn["mint"] for tkn in tokens]
    batch_prices = get_batch_token_prices(mints)

    total_usd = 0.0
    text_lines = [
        f"{title} ⚡",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━"
    ]
    kb = []

    for tkn in tokens[:6]:
        mint = tkn["mint"]
        amt = tkn["amount"]
        price_info = batch_prices.get(mint, {})
        sym = price_info.get("symbol") or f"{mint[:4]}..{mint[-4:]}"
        sym_escaped = html.escape(sym)
        price = price_info.get("price_usd", 0.0)
        c24 = price_info.get("change_24h", 0.0)
        val_usd = amt * price
        total_usd += val_usd
        emoji = "📈" if c24 >= 0 else "📉"

        text_lines.append(f"• <b>${sym_escaped}</b>: <code>{amt:,.2f}</code>")
        if price > 0:
            text_lines.append(f"  💵 <code>${val_usd:,.2f}</code> (<code>${price:.6f}</code>) {emoji} <code>{c24:+.1f}%</code>")
        text_lines.append(f"  📋 <code>{mint}</code>\n")

        kb.append([
            InlineKeyboardButton(f"🔴 Sell 50% ${sym_escaped}", callback_data=f"sell_{mint}_50"),
            InlineKeyboardButton(f"🚨 Sell 100% ${sym_escaped}", callback_data=f"sell_{mint}_100")
        ])
        kb.append([
            InlineKeyboardButton("💱 Quote", callback_data=f"quote_{mint}"),
            InlineKeyboardButton("💵 Price", callback_data=f"price_{mint}"),
            InlineKeyboardButton(f"🔍 Inspect", callback_data=f"inspect_{mint}"),
            InlineKeyboardButton("📈 Dex", url=f"https://dexscreener.com/solana/{mint}")
        ])

    sol_price_usd = (batch_prices.get("So11111111111111111111111111111111111111112") or {}).get("price_usd", 150.0)
    total_sol_equiv = (total_usd / sol_price_usd) if sol_price_usd > 0 else 0.0

    if user_lang == "ar":
        text_lines.append(f"💼 <b>إجمالي القيمة التقديرية</b>: <code>${total_usd:,.2f}</code> (<code>~{total_sol_equiv:.4f} SOL</code>)")
        refresh_label = "🔄 تحديث الصفقات"
    else:
        text_lines.append(f"💼 <b>Total Estimated Value</b>: <code>${total_usd:,.2f}</code> (<code>~{total_sol_equiv:.4f} SOL</code>)")
        refresh_label = "🔄 Refresh Portfolio"

    tip_text = (
        "💡 <b>Commands:</b> <code>/sell [TOKEN] [PERCENT]</code> • <code>/panic</code> • <code>/pnl</code>\n"
        if user_lang == "en" else
        "💡 <b>الأوامر المتاحة:</b> <code>/sell [العملة] [النسبة]</code> • <code>/panic</code> • <code>/pnl</code>\n"
    )
    text_lines.append(tip_text)
    text_lines.append(f"🕒 <code>{now_str}</code>")

    pnl_btn = "📊 " + ("Trading PnL" if user_lang == "en" else "تقرير الأرباح")
    kb.append([
        InlineKeyboardButton(t("btn_panic_confirm", user_lang), callback_data="btn_panic_confirm")
    ])
    kb.append([
        InlineKeyboardButton(refresh_label, callback_data="btn_positions"),
        InlineKeyboardButton(pnl_btn, callback_data="btn_pnl")
    ])
    kb.append([
        InlineKeyboardButton(t("btn_back", user_lang), callback_data="btn_refresh")
    ])

    full_text = "\n".join(text_lines)
    if is_edit:
        await safe_edit_text(target, full_text, reply_markup=InlineKeyboardMarkup(kb))
    else:
        await target.reply_text(full_text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True)


def benchmark_network_latency() -> Dict[str, Any]:
    """Measures live round-trip latency to Solana Primary RPC, Jupiter V6, RugCheck, and DexScreener APIs."""
    import time
    from config import PRIMARY_RPC, JUPITER_QUOTE_API, WSOL_MINT, USDC_MINT, RUGCHECK_API, DEXSCREENER_API
    from jupiter_engine import _SESSION

    rpc_ms = 999.0
    rpc_ok = False
    try:
        t0 = time.time()
        r = _SESSION.post(PRIMARY_RPC, json={"jsonrpc": "2.0", "id": 1, "method": "getHealth"}, timeout=5)
        rpc_ms = (time.time() - t0) * 1000.0
        rpc_ok = (r.status_code == 200)
    except Exception:
        rpc_ok = False

    jup_ms = 999.0
    jup_ok = False
    try:
        t1 = time.time()
        url = f"{JUPITER_QUOTE_API}?inputMint={WSOL_MINT}&outputMint={USDC_MINT}&amount=10000000"
        r2 = _SESSION.get(url, timeout=5)
        jup_ms = (time.time() - t1) * 1000.0
        jup_ok = (r2.status_code == 200)
    except Exception:
        jup_ok = False

    rug_ms = 999.0
    rug_ok = False
    try:
        t2 = time.time()
        r3 = _SESSION.get(f"{RUGCHECK_API}/{WSOL_MINT}/report", timeout=5)
        rug_ms = (time.time() - t2) * 1000.0
        rug_ok = (r3.status_code == 200)
    except Exception:
        rug_ok = False

    dex_ms = 999.0
    dex_ok = False
    try:
        t3 = time.time()
        r4 = _SESSION.get(f"{DEXSCREENER_API}/{WSOL_MINT}", timeout=5)
        dex_ms = (time.time() - t3) * 1000.0
        dex_ok = (r4.status_code == 200)
    except Exception:
        dex_ok = False

    return {
        "rpc_ms": rpc_ms,
        "rpc_ok": rpc_ok,
        "jup_ms": jup_ms,
        "jup_ok": jup_ok,
        "rug_ms": rug_ms,
        "rug_ok": rug_ok,
        "dex_ms": dex_ms,
        "dex_ok": dex_ok
    }


async def render_network_ping(target, user_id: int, user_lang: str, is_edit: bool = False):
    """Renders real-time Solana cluster latency and Jupiter routing benchmark card."""
    bench = benchmark_network_latency()
    now_str = get_current_time_str()

    rpc_ms = bench["rpc_ms"]
    jup_ms = bench["jup_ms"]
    rug_ms = bench.get("rug_ms", 999.0)
    dex_ms = bench.get("dex_ms", 999.0)

    if user_lang == "ar":
        rpc_status = "🟢 سرعة فائقة" if rpc_ms < 1000 else "🟡 معتدل"
        jup_status = "🟢 استجابة فورية" if jup_ms < 2000 else "🟡 معتدل"
        rug_status = "🟢 استجابة فورية" if rug_ms < 2000 else "🟡 معتدل"
        dex_status = "🟢 استجابة فورية" if dex_ms < 2000 else "🟡 معتدل"
    else:
        rpc_status = "🟢 Ultra-Fast" if rpc_ms < 1000 else "🟡 Normal"
        jup_status = "🟢 Sub-Second" if jup_ms < 2000 else "🟡 Normal"
        rug_status = "🟢 Sub-Second" if rug_ms < 2000 else "🟡 Normal"
        dex_status = "🟢 Sub-Second" if dex_ms < 2000 else "🟡 Normal"

    title = t("ping_title", user_lang)
    body = t("ping_body", user_lang,
             rpc_ms=rpc_ms, rpc_status=rpc_status,
             jup_ms=jup_ms, jup_status=jup_status,
             rug_ms=rug_ms, rug_status=rug_status,
             dex_ms=dex_ms, dex_status=dex_status)
    retest_label = "🔄 فحص السرعة مجدداً" if user_lang == "ar" else "🔄 Re-test Latency"

    kb = [
        [InlineKeyboardButton(retest_label, callback_data="btn_ping")],
        [InlineKeyboardButton(t("btn_back", user_lang), callback_data="btn_refresh")]
    ]
    card_text = f"{title}\n{body}\n🕒 <code>{now_str}</code>"

    if is_edit:
        await safe_edit_text(target, card_text, reply_markup=InlineKeyboardMarkup(kb))
    else:
        await target.reply_text(card_text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb))


def get_cluster_telemetry() -> Dict[str, Any]:
    """Retrieves live Solana cluster metrics: current slot, RPC health/latency, and trader stats."""
    import time
    from config import PRIMARY_RPC, DEVELOPER_WALLET, PLATFORM_FEE_BPS
    from jupiter_engine import _SESSION
    import wallet_manager

    slot = None
    rpc_ms = 999.0
    rpc_ok = False
    try:
        t0 = time.time()
        r = _SESSION.post(PRIMARY_RPC, json={"jsonrpc": "2.0", "id": 1, "method": "getSlot"}, timeout=6)
        rpc_ms = round((time.time() - t0) * 1000.0, 1)
        if r.status_code == 200:
            data = r.json()
            slot = data.get("result")
            rpc_ok = True
    except Exception:
        rpc_ok = False

    trader_count = 0
    try:
        conn = wallet_manager.get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM users")
        row = cur.fetchone()
        trader_count = row[0] if row else 0
        conn.close()
    except Exception:
        trader_count = 5

    return {
        "bot_version": BOT_VERSION,
        "cluster": "Solana Mainnet-Beta",
        "slot": slot,
        "rpc_ms": rpc_ms,
        "rpc_ok": rpc_ok,
        "trader_count": trader_count,
        "developer_wallet": DEVELOPER_WALLET,
        "fee_pct": PLATFORM_FEE_BPS / 100.0,
    }


async def render_status_card(target, user_id: int, user_lang: str, is_edit: bool = False):
    """Renders comprehensive Solana cluster health and bot platform telemetry card."""
    telem = get_cluster_telemetry()
    now_str = get_current_time_str()
    slot_str = f"#{telem['slot']:,}" if telem['slot'] else "Syncing..."
    status_icon = "🟢 Healthy" if telem['rpc_ok'] and telem['rpc_ms'] < 1000 else ("🟡 Moderate" if telem['rpc_ok'] else "🔴 Degraded")
    dev_wallet_short = f"{telem['developer_wallet'][:6]}...{telem['developer_wallet'][-4:]}"

    if user_lang == "ar":
        card = (
            "🛰️ <b>حالة الشبكة والمنظومة (Solana Cluster & Bot Telemetry)</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🤖 <b>إصدار البوت:</b> <code>{telem['bot_version']} (Enterprise)</code>\n"
            f"🌐 <b>الشبكة:</b> <code>{telem['cluster']}</code>\n"
            f"⚡ <b>حالة العقدة (RPC):</b> {status_icon} (<code>{telem['rpc_ms']} ms</code>)\n"
            f"📦 <b>البلوك الحالي (Slot):</b> <code>{slot_str}</code>\n"
            f"👥 <b>المتداولين المسجلين:</b> <code>{telem['trader_count']} مستخدم</code>\n"
            f"💎 <b>عمولة التداول:</b> <code>{telem['fee_pct']:.1f}%</code> (Jupiter V6 Dev Routing)\n"
            f"🛡️ <b>محفظة المطورين:</b> <code>{dev_wallet_short}</code>\n\n"
            "✨ <i>جميع العمليات غير احتجازية ومؤمنة محلياً بتشفير AES-256.</i>\n\n"
            f"🕒 <code>{now_str}</code>"
        )
        refresh_label = "🔄 تحديث الحالة"
        fees_label = "💰 تفاصيل الرسوم"
        release_label = f"📦 الإصدار {telem['bot_version']}"
        tour_label = "🚀 الجولة السريعة"
    else:
        card = (
            "🛰️ <b>Cluster Status & Bot Telemetry</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🤖 <b>Bot Version:</b> <code>{telem['bot_version']} (Enterprise)</code>\n"
            f"🌐 <b>Network:</b> <code>{telem['cluster']}</code>\n"
            f"⚡ <b>RPC Health:</b> {status_icon} (<code>{telem['rpc_ms']} ms</code>)\n"
            f"📦 <b>Current Slot:</b> <code>{slot_str}</code>\n"
            f"👥 <b>Registered Traders:</b> <code>{telem['trader_count']} users</code>\n"
            f"💎 <b>Platform Swap Fee:</b> <code>{telem['fee_pct']:.1f}%</code> (Jupiter V6 Dev Routing)\n"
            f"🛡️ <b>Payout Settlement:</b> <code>{dev_wallet_short}</code>\n\n"
            "✨ <i>All operations are non-custodial and locally AES-256 encrypted.</i>\n\n"
            f"🕒 <code>{now_str}</code>"
        )
        refresh_label = "🔄 Refresh Status"
        fees_label = "💰 Fee Schedule"
        release_label = f"📦 Release {telem['bot_version']}"
        tour_label = "🚀 Quick Tour"

    release_url = f"https://github.com/m7md570/solana-telegram-sniper-bot/releases/tag/{telem['bot_version']}"

    kb = [
        [
            InlineKeyboardButton(refresh_label, callback_data="btn_status"),
            InlineKeyboardButton(fees_label, callback_data="btn_fee_info")
        ],
        [
            InlineKeyboardButton(release_label, url=release_url),
            InlineKeyboardButton(tour_label, callback_data="btn_tour")
        ],
        [
            InlineKeyboardButton(t("btn_back", user_lang), callback_data="btn_refresh")
        ]
    ]

    if is_edit:
        await safe_edit_text(target, card, reply_markup=InlineKeyboardMarkup(kb))
    else:
        await target.reply_text(card, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True)


async def render_fees_card(target, user_id: int, user_lang: str, is_edit: bool = False):
    """Renders transparent fee schedule card for traders."""
    now_str = get_current_time_str()
    from config import PLATFORM_FEE_BPS
    fee_pct = PLATFORM_FEE_BPS / 100.0

    if user_lang == "ar":
        card = (
            "💰 <b>جدول الرسوم والعمولات الشفافة (Fee Schedule)</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🟢 <b>عمولة التداول (Swaps):</b> <code>{fee_pct:.1f}%</code> فقط عند تنفيذ صفقات الشراء والبيع عبر Jupiter V6.\n"
            "🟢 <b>الإيداع:</b> <code>0.00 SOL مجاناً</code> (المحفظة لا تقتطع أي رسوم إيداع).\n"
            "🟢 <b>السحب:</b> <code>0.00 SOL مجاناً</code> (تدفع فقط رسوم شبكة سولانا الاعتيادية ~0.000005 SOL).\n"
            "🟢 <b>نظام الإحالة:</b> اربح <code>25%</code> من رسوم التداول لأي صديق تدعوه عبر رابطك (/referral).\n"
            "🟢 <b>رسوم الأولوية (Priority Gas):</b> قابلة للتخصيص (/gas) لتسريع الصفقات أثناء ازدحام الشبكة.\n\n"
            "💡 <i>شفافية مطلقة: لا توجد أي رسوم خفية أو اشتراكات شهرية.</i>\n\n"
            f"🕒 <code>{now_str}</code>"
        )
        status_label = "🛰️ حالة الشبكة"
        settings_label = "⚙️ إعدادات الغاز"
        referral_label = "🎁 برنامج الإحالة"
    else:
        card = (
            "💰 <b>Transparent Fee Schedule & Payouts</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🟢 <b>Platform Swap Fee:</b> <code>{fee_pct:.1f}%</code> charged only upon executed Jupiter V6 buy/sell swaps.\n"
            "🟢 <b>Deposits:</b> <code>0.00 SOL Free</code> (zero platform deposit fee).\n"
            "🟢 <b>Withdrawals:</b> <code>0.00 SOL Free</code> (you only pay standard Solana network gas ~0.000005 SOL).\n"
            "🟢 <b>Affiliate Rewards:</b> Earn <code>25%</code> lifetime kickback on trading fees from invited peers (/referral).\n"
            "🟢 <b>Priority Gas:</b> Configurable (/gas) to front-run network congestion during high-volatility launches.\n\n"
            "💡 <i>100% non-custodial: No hidden fees, no subscriptions, no locked liquidity.</i>\n\n"
            f"🕒 <code>{now_str}</code>"
        )
        status_label = "🛰️ Cluster Status"
        settings_label = "⚙️ Gas Settings"
        referral_label = "🎁 Referral Rewards"

    kb = [
        [
            InlineKeyboardButton(status_label, callback_data="btn_status"),
            InlineKeyboardButton(settings_label, callback_data="btn_gas_fees")
        ],
        [
            InlineKeyboardButton(referral_label, callback_data="btn_referral"),
            InlineKeyboardButton(t("btn_back", user_lang), callback_data="btn_refresh")
        ]
    ]

    if is_edit:
        await safe_edit_text(target, card, reply_markup=InlineKeyboardMarkup(kb))
    else:
        await target.reply_text(card, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True)


async def render_gas_card(target, user_id: int, user_lang: str, is_edit: bool = False):
    """Renders real-time Solana on-chain priority fee congestion radar with user's active gas tier."""
    gas_data = get_network_gas_fees()
    badge = gas_data["congestion_badge_ar"] if user_lang == "ar" else gas_data["congestion_badge_en"]
    card_title = t("gas_card_title", user_lang)
    card_body = t(
        "gas_card_body",
        user_lang,
        congestion_badge=badge,
        median_fee=gas_data["median_micro_lamports"],
        median_sol=gas_data["median_sol"],
        p95_fee=gas_data["p95_micro_lamports"],
        p95_sol=gas_data["p95_sol"],
        rec_normal=gas_data["recommended_normal"],
        rec_turbo=gas_data["recommended_turbo"],
        rec_ultra=gas_data["recommended_ultra"],
    )
    settings = get_user_settings(user_id)
    user_lamports = settings.get("priority_fee", 50000)
    user_sol = user_lamports / 1e9

    if user_lang == "ar":
        tier_name = "عادي" if user_lamports <= 100000 else ("تيربو" if user_lamports <= 500000 else "فائق")
        user_info = f"\n\n🎯 <b>رسوم الأولوية النشطة لديك:</b> <code>{user_sol:.5f} SOL</code> ({tier_name})"
        normal_btn = f"⚡ عادي (50k) {'✅' if user_lamports == 50000 else ''}".strip()
        turbo_btn = f"🚀 تيربو (250k) {'✅' if user_lamports == 250000 else ''}".strip()
        ultra_btn = f"🏎️ فائق (1M) {'✅' if user_lamports == 1000000 else ''}".strip()
        settings_label = "⚙️ الإعدادات"
    else:
        tier_name = "Normal" if user_lamports <= 100000 else ("Turbo" if user_lamports <= 500000 else "Ultra")
        user_info = f"\n\n🎯 <b>Your Active Priority Fee:</b> <code>{user_sol:.5f} SOL</code> ({tier_name})"
        normal_btn = f"⚡ Normal (50k) {'✅' if user_lamports == 50000 else ''}".strip()
        turbo_btn = f"🚀 Turbo (250k) {'✅' if user_lamports == 250000 else ''}".strip()
        ultra_btn = f"🏎️ Ultra (1M) {'✅' if user_lamports == 1000000 else ''}".strip()
        settings_label = "⚙️ Settings"

    text = f"{card_title}\n{card_body}{user_info}"
    kb = [
        [
            InlineKeyboardButton(normal_btn, callback_data="gas_50000"),
            InlineKeyboardButton(turbo_btn, callback_data="gas_250000"),
            InlineKeyboardButton(ultra_btn, callback_data="gas_1000000")
        ],
        [
            InlineKeyboardButton(t("btn_refresh", user_lang), callback_data="btn_gas_fees"),
            InlineKeyboardButton(settings_label, callback_data="btn_settings")
        ],
        [
            InlineKeyboardButton(t("btn_back", user_lang), callback_data="btn_refresh")
        ]
    ]
    markup = InlineKeyboardMarkup(kb)
    if is_edit:
        await safe_edit_text(target, text, reply_markup=markup)
    else:
        await target.reply_text(text, parse_mode="HTML", reply_markup=markup)


async def render_slippage_card(target, user_id: int, user_lang: str, is_edit: bool = False):
    """Renders interactive slippage tolerance configuration card with active checkmarks."""
    settings = get_user_settings(user_id)
    current_bps = settings.get("slippage_bps", 100)
    current_pct = current_bps / 100.0
    now_str = get_current_time_str()

    s50 = f"0.5% {'✅' if current_bps == 50 else ''}".strip()
    s100 = f"1.0% {'✅' if current_bps == 100 else ''}".strip()
    s200 = f"2.0% {'✅' if current_bps == 200 else ''}".strip()
    s500 = f"5.0% {'✅' if current_bps == 500 else ''}".strip()

    if user_lang == "ar":
        title = "🎯 <b>إعدادات نسبة الانزلاق السعري (Slippage Tolerance)</b>"
        body = (
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"• <b>النسبة النشطة حالياً:</b> <code>{current_pct:.2f}%</code> (<code>{current_bps} BPS</code>)\n\n"
            f"{t('slippage_syntax_help', user_lang)}\n\n"
            f"🕒 <code>{now_str}</code>"
        )
        refresh_label = "🔄 تحديث"
        settings_label = "⚙️ الإعدادات"
    else:
        title = "🎯 <b>Slippage Tolerance Configuration</b>"
        body = (
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"• <b>Active Slippage:</b> <code>{current_pct:.2f}%</code> (<code>{current_bps} BPS</code>)\n\n"
            f"{t('slippage_syntax_help', user_lang)}\n\n"
            f"🕒 <code>{now_str}</code>"
        )
        refresh_label = "🔄 Refresh"
        settings_label = "⚙️ Settings"

    text = f"{title}\n{body}"
    kb = [
        [
            InlineKeyboardButton(s50, callback_data="slip_50"),
            InlineKeyboardButton(s100, callback_data="slip_100"),
            InlineKeyboardButton(s200, callback_data="slip_200"),
            InlineKeyboardButton(s500, callback_data="slip_500")
        ],
        [
            InlineKeyboardButton(refresh_label, callback_data="btn_slippage"),
            InlineKeyboardButton(settings_label, callback_data="btn_settings")
        ],
        [
            InlineKeyboardButton(t("btn_back", user_lang), callback_data="btn_refresh")
        ]
    ]
    markup = InlineKeyboardMarkup(kb)
    if is_edit:
        await safe_edit_text(target, text, reply_markup=markup)
    else:
        await target.reply_text(text, parse_mode="HTML", reply_markup=markup)


async def render_tp_card(target, user_id: int, user_lang: str, is_edit: bool = False):
    """Renders interactive Take-Profit target configuration card with active checkmarks."""
    settings = get_user_settings(user_id)
    current_tp = settings.get("default_tp_pct", 50)
    now_str = get_current_time_str()

    tp25 = f"+25% {'✅' if current_tp == 25 else ''}".strip()
    tp50 = f"+50% {'✅' if current_tp == 50 else ''}".strip()
    tp100 = f"+100% {'✅' if current_tp == 100 else ''}".strip()
    tp200 = f"+200% {'✅' if current_tp == 200 else ''}".strip()

    if user_lang == "ar":
        title = "🎯 <b>إعدادات جني الأرباح التلقائي (Auto Take-Profit)</b>"
        body = (
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"• <b>الهدف النشط حالياً:</b> <code>+{current_tp}%</code>\n\n"
            f"{t('tp_syntax_help', user_lang)}\n\n"
            f"🕒 <code>{now_str}</code>"
        )
        refresh_label = "🔄 تحديث"
        settings_label = "⚙️ الإعدادات"
    else:
        title = "🎯 <b>Auto Take-Profit Configuration</b>"
        body = (
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"• <b>Active Target:</b> <code>+{current_tp}%</code>\n\n"
            f"{t('tp_syntax_help', user_lang)}\n\n"
            f"🕒 <code>{now_str}</code>"
        )
        refresh_label = "🔄 Refresh"
        settings_label = "⚙️ Settings"

    text = f"{title}\n{body}"
    kb = [
        [
            InlineKeyboardButton(tp25, callback_data="tp_25"),
            InlineKeyboardButton(tp50, callback_data="tp_50"),
            InlineKeyboardButton(tp100, callback_data="tp_100"),
            InlineKeyboardButton(tp200, callback_data="tp_200")
        ],
        [
            InlineKeyboardButton(refresh_label, callback_data="btn_tp"),
            InlineKeyboardButton(settings_label, callback_data="btn_settings")
        ],
        [
            InlineKeyboardButton(t("btn_back", user_lang), callback_data="btn_refresh")
        ]
    ]
    markup = InlineKeyboardMarkup(kb)
    if is_edit:
        await safe_edit_text(target, text, reply_markup=markup)
    else:
        await target.reply_text(text, parse_mode="HTML", reply_markup=markup)


async def render_sl_card(target, user_id: int, user_lang: str, is_edit: bool = False):
    """Renders interactive Stop-Loss protection configuration card with active checkmarks."""
    settings = get_user_settings(user_id)
    current_sl = settings.get("default_sl_pct", 25)
    now_str = get_current_time_str()

    sl15 = f"-15% {'✅' if current_sl == 15 else ''}".strip()
    sl25 = f"-25% {'✅' if current_sl == 25 else ''}".strip()
    sl50 = f"-50% {'✅' if current_sl == 50 else ''}".strip()
    sl75 = f"-75% {'✅' if current_sl == 75 else ''}".strip()

    if user_lang == "ar":
        title = "🛑 <b>إعدادات وقف الخسارة التلقائي (Auto Stop-Loss)</b>"
        body = (
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"• <b>الحد النشط حالياً:</b> <code>-{current_sl}%</code>\n\n"
            f"{t('sl_syntax_help', user_lang)}\n\n"
            f"🕒 <code>{now_str}</code>"
        )
        refresh_label = "🔄 تحديث"
        settings_label = "⚙️ الإعدادات"
    else:
        title = "🛑 <b>Auto Stop-Loss Configuration</b>"
        body = (
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"• <b>Active Limit:</b> <code>-{current_sl}%</code>\n\n"
            f"{t('sl_syntax_help', user_lang)}\n\n"
            f"🕒 <code>{now_str}</code>"
        )
        refresh_label = "🔄 Refresh"
        settings_label = "⚙️ Settings"

    text = f"{title}\n{body}"
    kb = [
        [
            InlineKeyboardButton(sl15, callback_data="sl_15"),
            InlineKeyboardButton(sl25, callback_data="sl_25"),
            InlineKeyboardButton(sl50, callback_data="sl_50"),
            InlineKeyboardButton(sl75, callback_data="sl_75")
        ],
        [
            InlineKeyboardButton(refresh_label, callback_data="btn_sl"),
            InlineKeyboardButton(settings_label, callback_data="btn_settings")
        ],
        [
            InlineKeyboardButton(t("btn_back", user_lang), callback_data="btn_refresh")
        ]
    ]
    markup = InlineKeyboardMarkup(kb)
    if is_edit:
        await safe_edit_text(target, text, reply_markup=markup)
    else:
        await target.reply_text(text, parse_mode="HTML", reply_markup=markup)


async def render_autobuy_card(target, user_id: int, user_lang: str, is_edit: bool = False):
    """Renders interactive Auto-Buy sniper configuration card with active checkmarks and amount tiers."""
    enabled, amt = get_auto_buy_settings(user_id)
    status_str = ("ENABLED 🟢" if enabled else "DISABLED ⚪") if user_lang == "en" else ("مفعل 🟢" if enabled else "معطل ⚪")
    title = t("autobuy_status_title", user_lang)
    body = t("autobuy_status_body", user_lang, status=status_str, amt=amt)
    toggle_label = ("🔕 Disable Auto-Buy" if enabled else "🔔 Enable Auto-Buy") if user_lang == "en" else ("🔕 تعطيل الشراء التلقائي" if enabled else "🔔 تفعيل الشراء التلقائي")

    b005 = f"0.05 SOL {'✅' if enabled and abs(amt - 0.05) < 0.001 else ''}".strip()
    b01 = f"0.1 SOL {'✅' if enabled and abs(amt - 0.1) < 0.001 else ''}".strip()
    b05 = f"0.5 SOL {'✅' if enabled and abs(amt - 0.5) < 0.001 else ''}".strip()
    b10 = f"1.0 SOL {'✅' if enabled and abs(amt - 1.0) < 0.001 else ''}".strip()

    refresh_label = "🔄 Refresh" if user_lang == "en" else "🔄 تحديث"
    settings_label = "⚙️ Settings" if user_lang == "en" else "⚙️ الإعدادات"

    text = f"{title}\n━━━━━━━━━━━━━━━━━━━\n{body}"
    kb = [
        [InlineKeyboardButton(toggle_label, callback_data="toggle_autobuy")],
        [
            InlineKeyboardButton(b005, callback_data="set_auto_amt_0.05"),
            InlineKeyboardButton(b01, callback_data="set_auto_amt_0.1"),
            InlineKeyboardButton(b05, callback_data="set_auto_amt_0.5"),
            InlineKeyboardButton(b10, callback_data="set_auto_amt_1.0")
        ],
        [
            InlineKeyboardButton(refresh_label, callback_data="btn_autobuy"),
            InlineKeyboardButton(settings_label, callback_data="btn_settings")
        ],
        [InlineKeyboardButton(t("btn_back", user_lang), callback_data="btn_refresh")]
    ]
    markup = InlineKeyboardMarkup(kb)
    if is_edit:
        await safe_edit_text(target, text, reply_markup=markup)
    else:
        await target.reply_text(text, parse_mode="HTML", reply_markup=markup)


async def render_alerts_card(target, user_id: int, user_lang: str, is_edit: bool = False):
    """Renders interactive Price & Volatility Alert configuration radar with active checkmarks and threshold tiers."""
    enabled, threshold = get_user_alert_settings(user_id)
    now_str = get_current_time_str()

    status_str = ("ENABLED 🟢" if enabled else "DISABLED ⚪") if user_lang == "en" else ("مفعلة 🟢" if enabled else "معطلة ⚪")
    toggle_label = ("🔕 Disable Alerts" if enabled else "🔔 Enable Alerts") if user_lang == "en" else ("🔕 تعطيل التنبيهات" if enabled else "🔔 تفعيل التنبيهات")

    p05 = f"±5% {'✅' if enabled and abs(threshold - 5.0) < 0.1 else ''}".strip()
    p10 = f"±10% {'✅' if enabled and abs(threshold - 10.0) < 0.1 else ''}".strip()
    p20 = f"±20% {'✅' if enabled and abs(threshold - 20.0) < 0.1 else ''}".strip()
    p50 = f"±50% {'✅' if enabled and abs(threshold - 50.0) < 0.1 else ''}".strip()

    if user_lang == "ar":
        title = "🔔 <b>رادار تنبيهات حركة الأسعار والتقلبات (Price Volatility Radar)</b>"
        body = (
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"• <b>حالة التنبيهات:</b> <code>{status_str}</code>\n"
            f"• <b>حد التذبذب النشط:</b> <code>±{threshold:.1f}%</code>\n\n"
            f"يراقب البوت أسعار عملات قائمة متابعتك ويرسل إشعارات فورية مع أزرار قنص بنقرة واحدة عند رصد أي صعود أو هبوط حاد.\n\n"
            f"🕒 <code>{now_str}</code>"
        )
        refresh_label = "🔄 تحديث"
        settings_label = "⚙️ الإعدادات"
        watchlist_label = "📋 قائمة المتابعة"
    else:
        title = "🔔 <b>Price Movement & Volatility Alert Radar</b>"
        body = (
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"• <b>Alert Status:</b> <code>{status_str}</code>\n"
            f"• <b>Active Swing Threshold:</b> <code>±{threshold:.1f}%</code>\n\n"
            f"Monitors real-time price movements for tokens in your watchlist, dispatching instant 1-click snipe alert cards whenever prices shift beyond your threshold.\n\n"
            f"🕒 <code>{now_str}</code>"
        )
        refresh_label = "🔄 Refresh"
        settings_label = "⚙️ Settings"
        watchlist_label = "📋 Watchlist"

    text = f"{title}\n{body}"
    kb = [
        [InlineKeyboardButton(toggle_label, callback_data="toggle_alerts")],
        [
            InlineKeyboardButton(p05, callback_data="alert_pct_5"),
            InlineKeyboardButton(p10, callback_data="alert_pct_10"),
            InlineKeyboardButton(p20, callback_data="alert_pct_20"),
            InlineKeyboardButton(p50, callback_data="alert_pct_50")
        ],
        [
            InlineKeyboardButton(refresh_label, callback_data="btn_alerts"),
            InlineKeyboardButton(watchlist_label, callback_data="btn_watchlist")
        ],
        [
            InlineKeyboardButton(settings_label, callback_data="btn_settings"),
            InlineKeyboardButton(t("btn_back", user_lang), callback_data="btn_refresh")
        ]
    ]
    markup = InlineKeyboardMarkup(kb)
    if is_edit:
        await safe_edit_text(target, text, reply_markup=markup)
    else:
        await target.reply_text(text, parse_mode="HTML", reply_markup=markup)


async def render_withdraw_card(target, user_id: int, user_lang: str, is_edit: bool = False):
    """Renders interactive withdrawal radar with balance telemetry, gas reserve, and syntax examples."""
    pubkey, _ = get_or_create_wallet(user_id)
    balance = get_sol_balance(pubkey)
    now_str = get_current_time_str()
    gas_reserve = 0.005
    max_withdrawable = max(0.0, balance - gas_reserve)

    if user_lang == "ar":
        title = "💸 <b>رادار سحب رصيد SOL الفوري</b> 🏦"
        body = (
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📍 <b>عنوان محفظة البوت:</b>\n<code>{pubkey}</code>\n\n"
            f"💰 <b>إجمالي الرصيد المتاح:</b> <code>{balance:.4f} SOL</code>\n"
            f"🛡️ <b>احتياطي رسوم الغاز (محجوز):</b> <code>{gas_reserve:.3f} SOL</code>\n"
            f"💎 <b>الحد الأقصى القابل للسحب:</b> <code>{max_withdrawable:.4f} SOL</code>\n\n"
            "💡 <b>صيغة أمر السحب:</b>\n"
            "<code>/withdraw [عنوان_المحفظة_المستلمة] [المبلغ|all]</code>\n\n"
            "<b>أمثلة سريعة:</b>\n"
            "• <code>/withdraw 7kz1mcQcaZhYzFUHBFHH6s5tGrDHc7gNhN5WAUyXyq5r 0.05</code>\n"
            "• <code>/withdraw 7kz1mcQcaZhYzFUHBFHH6s5tGrDHc7gNhN5WAUyXyq5r all</code>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🕒 <code>{now_str}</code>"
        )
        refresh_label = "🔄 تحديث الرصيد"
        deposit_label = "📲 رمز QR للإيداع"
        wallet_label = "💳 المحفظة"
    else:
        title = "💸 <b>Fast SOL Withdrawal Radar</b> 🏦"
        body = (
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📍 <b>Bot Wallet Address:</b>\n<code>{pubkey}</code>\n\n"
            f"💰 <b>Total Balance:</b> <code>{balance:.4f} SOL</code>\n"
            f"🛡️ <b>Gas Reserve (Auto-Kept):</b> <code>{gas_reserve:.3f} SOL</code>\n"
            f"💎 <b>Max Withdrawable:</b> <code>{max_withdrawable:.4f} SOL</code>\n\n"
            "💡 <b>Command Syntax:</b>\n"
            "<code>/withdraw [DEST_ADDRESS] [AMOUNT|all]</code>\n\n"
            "<b>Quick Examples:</b>\n"
            "• <code>/withdraw 7kz1mcQcaZhYzFUHBFHH6s5tGrDHc7gNhN5WAUyXyq5r 0.05</code>\n"
            "• <code>/withdraw 7kz1mcQcaZhYzFUHBFHH6s5tGrDHc7gNhN5WAUyXyq5r all</code>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🕒 <code>{now_str}</code>"
        )
        refresh_label = "🔄 Refresh Balance"
        deposit_label = "📲 Instant QR Deposit"
        wallet_label = "💳 Wallet"

    text = f"{title}\n{body}"
    if balance < 0.005:
        action_btn = InlineKeyboardButton(deposit_label, callback_data="btn_qr")
    else:
        action_btn = InlineKeyboardButton(refresh_label, callback_data="btn_withdraw_guide")

    kb = [
        [
            action_btn,
            InlineKeyboardButton(wallet_label, callback_data="btn_wallet")
        ],
        [
            InlineKeyboardButton(deposit_label, callback_data="btn_show_qr"),
            InlineKeyboardButton(refresh_label, callback_data="btn_withdraw")
        ],
        [InlineKeyboardButton(t("btn_back", user_lang), callback_data="btn_refresh")]
    ]

    markup = InlineKeyboardMarkup(kb)
    if is_edit:
        await safe_edit_text(target, text, reply_markup=markup)
    else:
        await target.reply_text(text, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True)


async def render_presets_card(target, user_id: int, user_lang: str, is_edit: bool = False):
    """Renders interactive quick-snipe buy amount presets card with dynamic checkmarks."""
    current_amt = get_user_default_buy_amount(user_id)
    now_str = get_current_time_str()

    p005 = f"0.05 SOL {'✅' if abs(current_amt - 0.05) < 0.001 else ''}".strip()
    p010 = f"0.10 SOL {'✅' if abs(current_amt - 0.10) < 0.001 else ''}".strip()
    p025 = f"0.25 SOL {'✅' if abs(current_amt - 0.25) < 0.001 else ''}".strip()
    p050 = f"0.50 SOL {'✅' if abs(current_amt - 0.50) < 0.001 else ''}".strip()
    p100 = f"1.00 SOL {'✅' if abs(current_amt - 1.00) < 0.001 else ''}".strip()
    p200 = f"2.00 SOL {'✅' if abs(current_amt - 2.00) < 0.001 else ''}".strip()

    if user_lang == "ar":
        title = "🎯 <b>إعدادات مبالغ القنص السريع الافتراضية (Quick Buy Presets)</b>"
        body = (
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"• <b>مبلغ القنص النشط حالياً:</b> <code>{current_amt:.2f} SOL</code>\n\n"
            f"اختر حجم الصفقة السريعة المفضل لديك بنقرة واحدة لتسهيل قنص وتداول العملات اللحظي.\n\n"
            f"💡 <b>صيغة الأمر المباشر:</b> <code>/presets [المبلغ_SOL]</code>\n"
            f"مثال: <code>/presets 0.25</code>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🕒 <code>{now_str}</code>"
        )
        refresh_label = "🔄 تحديث"
        settings_label = "⚙️ الإعدادات"
        autobuy_label = "🎯 رادار القنص التلقائي"
    else:
        title = "🎯 <b>Quick-Snipe Buy Presets Radar</b>"
        body = (
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"• <b>Active Quick-Buy Size:</b> <code>{current_amt:.2f} SOL</code>\n\n"
            f"Select your default 1-click execution size for lightning-fast token entries:\n\n"
            f"💡 <b>Direct Command:</b> <code>/presets [AMOUNT_SOL]</code>\n"
            f"Example: <code>/presets 0.25</code>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🕒 <code>{now_str}</code>"
        )
        refresh_label = "🔄 Refresh"
        settings_label = "⚙️ Settings"
        autobuy_label = "🎯 Auto-Buy Radar"

    text = f"{title}\n{body}"
    kb = [
        [
            InlineKeyboardButton(p005, callback_data="preset_buy_0.05"),
            InlineKeyboardButton(p010, callback_data="preset_buy_0.10"),
            InlineKeyboardButton(p025, callback_data="preset_buy_0.25")
        ],
        [
            InlineKeyboardButton(p050, callback_data="preset_buy_0.50"),
            InlineKeyboardButton(p100, callback_data="preset_buy_1.00"),
            InlineKeyboardButton(p200, callback_data="preset_buy_2.00")
        ],
        [
            InlineKeyboardButton(autobuy_label, callback_data="btn_autobuy"),
            InlineKeyboardButton(settings_label, callback_data="btn_settings")
        ],
        [
            InlineKeyboardButton(refresh_label, callback_data="btn_presets"),
            InlineKeyboardButton(t("btn_back", user_lang), callback_data="btn_refresh")
        ]
    ]

    markup = InlineKeyboardMarkup(kb)
    if is_edit:
        await safe_edit_text(target, text, reply_markup=markup)
    else:
        await target.reply_text(text, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True)


async def render_pnl_card(target, user, user_id: int, user_lang: str, is_edit: bool = False, bot_username: str = "PopcornSniperBot"):
    """Renders comprehensive user trading performance, PnL metrics, viral share buttons, and export actions."""
    stats = get_user_trade_stats(user_id)
    username = (user.username or user.first_name or ("Trader" if user_lang == "en" else "المتداول")) if user else ("Trader" if user_lang == "en" else "المتداول")
    now_str = get_current_time_str()

    pnl_body_text = t(
        "pnl_body",
        user_lang,
        username=html.escape(username),
        total_trades=stats["total_trades"],
        success_rate=stats.get("success_rate_pct", 100.0),
        total_vol=stats["total_volume_sol"],
        total_fees=stats.get("total_fees_sol", 0.0)
    )

    ref_link = f"https://t.me/{bot_username}?start=ref_{user_id}"
    tweet_msg = f"Sniping Solana memecoins with sub-400ms speed on @PopcornSniperBot! Traded {stats['total_volume_sol']:.3f} SOL. Start sniping: {ref_link}"
    share_url = f"https://twitter.com/intent/tweet?text={urllib.parse.quote(tweet_msg)}"
    tg_share_text = f"🚀 I'm sniping Solana memecoins with sub-400ms execution on @{bot_username}! Traded {stats['total_volume_sol']:.3f} SOL. Start sniping: {ref_link}"
    tg_share_url = f"https://t.me/share/url?url={urllib.parse.quote(ref_link)}&text={urllib.parse.quote(tg_share_text)}"

    text = f"{t('pnl_title', user_lang)}\n{pnl_body_text}\n🕒 <code>{now_str}</code>"
    share_btn_text = "📢 " + ("Share PnL on X / Twitter" if user_lang == "en" else "مشاركة الأرباح على X")
    tg_share_btn_text = "👥 " + ("Share on Telegram" if user_lang == "en" else "مشاركة على تيليجرام")
    refresh_pnl_label = "🔄 تحديث الأرباح" if user_lang == "ar" else "🔄 Refresh PnL"
    csv_label = "📥 Export CSV" if user_lang == "en" else "📥 تصدير السجل CSV"

    kb = [
        [
            InlineKeyboardButton(share_btn_text, url=share_url),
            InlineKeyboardButton(tg_share_btn_text, url=tg_share_url)
        ],
        [
            InlineKeyboardButton(t("btn_history", user_lang), callback_data="btn_history"),
            InlineKeyboardButton(csv_label, callback_data="btn_history_csv")
        ],
        [
            InlineKeyboardButton(t("btn_positions", user_lang), callback_data="btn_positions"),
            InlineKeyboardButton(t("btn_watchlist", user_lang), callback_data="btn_watchlist"),
            InlineKeyboardButton(t("btn_trending", user_lang), callback_data="btn_trending")
        ],
        [
            InlineKeyboardButton(refresh_pnl_label, callback_data="btn_pnl"),
            InlineKeyboardButton(t("btn_back", user_lang), callback_data="btn_refresh")
        ]
    ]

    markup = InlineKeyboardMarkup(kb)
    if is_edit:
        await safe_edit_text(target, text, reply_markup=markup)
    else:
        await target.reply_text(text, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True)


async def render_panic_confirm(target, user_id: int, user_lang: str, is_edit: bool = False):
    """Renders the emergency panic sell-all confirmation warning card."""
    pubkey, _ = get_or_create_wallet(user_id)
    tokens = get_token_accounts(pubkey)
    now_str = get_current_time_str()

    if not tokens:
        empty_text = (
            f"{t('panic_confirm_title', user_lang)}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"{t('panic_no_positions', user_lang)}\n\n"
            f"🕒 <code>{now_str}</code>"
        )
        kb = [[InlineKeyboardButton(t("btn_back", user_lang), callback_data="btn_positions")]]
        if is_edit:
            await safe_edit_text(target, empty_text, reply_markup=InlineKeyboardMarkup(kb))
        else:
            await target.reply_text(empty_text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb))
        return

    title = t("panic_confirm_title", user_lang)
    body = t("panic_confirm_body", user_lang, count=len(tokens))
    full_text = f"{title}\n{body}\n\n🕒 <code>{now_str}</code>"

    back_label = "⬅️ إلغاء والعودة" if user_lang == "ar" else "⬅️ Cancel & Back"
    kb = [
        [InlineKeyboardButton(t("btn_panic_execute", user_lang), callback_data="btn_panic_execute")],
        [InlineKeyboardButton(back_label, callback_data="btn_positions")]
    ]
    if is_edit:
        await safe_edit_text(target, full_text, reply_markup=InlineKeyboardMarkup(kb))
    else:
        await target.reply_text(full_text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb))


async def execute_panic_sell_all(target, user_id: int, user_lang: str):
    """Executes 100% market liquidation of all open SPL token holdings."""
    pubkey, _ = get_or_create_wallet(user_id)
    tokens = get_token_accounts(pubkey)
    now_str = get_current_time_str()

    if not tokens:
        empty_text = (
            f"{t('panic_confirm_title', user_lang)}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"{t('panic_no_positions', user_lang)}\n\n"
            f"🕒 <code>{now_str}</code>"
        )
        kb = [[InlineKeyboardButton(t("btn_back", user_lang), callback_data="btn_positions")]]
        if hasattr(target, "edit_message_text") or hasattr(target, "edit_text"):
            await safe_edit_text(target, empty_text, reply_markup=InlineKeyboardMarkup(kb))
        else:
            await target.reply_text(empty_text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb))
        return

    progress_msg = (
        "🚨 <b>جاري تنفيذ تصفية الطوارئ الشاملة لجميع الصفقات...</b>\n<i>يرجى الانتظار حتى اكتمال بيع كافة العملات عبر Jupiter.</i>"
        if user_lang == "ar" else
        "🚨 <b>Executing Emergency Panic Liquidation across all open positions...</b>\n<i>Please hold while all tokens are swapped back into SOL via Jupiter.</i>"
    )
    if hasattr(target, "edit_message_text") or hasattr(target, "edit_text"):
        await safe_edit_text(target, progress_msg)
        status_handle = target
    else:
        status_handle = await target.reply_text(progress_msg, parse_mode="HTML")

    success_cnt = 0
    total_reclaimed_sol = 0.0

    for tkn in tokens:
        mint = tkn["mint"]
        success, sig_or_err, sol_recv = execute_sell_swap(user_id, mint, 100, lang=user_lang)
        if success:
            success_cnt += 1
            total_reclaimed_sol += (sol_recv or 0.0)

    title = t("panic_success_title", user_lang)
    body = t(
        "panic_success_body",
        user_lang,
        success_cnt=success_cnt,
        total_cnt=len(tokens),
        total_sol=total_reclaimed_sol
    )
    full_text = f"{title}\n{body}\n🕒 <code>{now_str}</code>"
    kb = [
        [InlineKeyboardButton(t("btn_positions", user_lang), callback_data="btn_positions")],
        [InlineKeyboardButton(t("btn_back", user_lang), callback_data="btn_refresh")]
    ]
    await safe_edit_text(status_handle, full_text, reply_markup=InlineKeyboardMarkup(kb))


async def render_help_card(target, user_id: int, user_lang: str, is_edit: bool = False):
    """Renders comprehensive interactive user manual and command directory."""
    title = t("help_title", user_lang)
    body = t("help_body", user_lang)
    text = f"{title}\n{body}"
    kb = [
        [
            InlineKeyboardButton("🚀 Dashboard" if user_lang == "en" else "🚀 الرئيسية", callback_data="btn_refresh"),
            InlineKeyboardButton("💳 Wallet" if user_lang == "en" else "💳 المحفظة", callback_data="btn_wallet"),
            InlineKeyboardButton("🔥 Trending" if user_lang == "en" else "🔥 الرائج", callback_data="btn_trending")
        ],
        [
            InlineKeyboardButton("⚙️ Settings" if user_lang == "en" else "⚙️ الإعدادات", callback_data="btn_settings"),
            InlineKeyboardButton("🤝 Referral" if user_lang == "en" else "🤝 الإحالات", callback_data="btn_referral"),
            InlineKeyboardButton("📊 Status" if user_lang == "en" else "📊 الحالة", callback_data="btn_status")
        ],
        [
            InlineKeyboardButton("ℹ️ Version" if user_lang == "en" else "ℹ️ الإصدار", callback_data="btn_version"),
            InlineKeyboardButton("⚡ Latency Radar" if user_lang == "en" else "⚡ سرعة الشبكة", callback_data="btn_ping")
        ],
        [
            InlineKeyboardButton("🚀 Quick Tour" if user_lang == "en" else "🚀 الجولة السريعة", callback_data="btn_tour"),
            InlineKeyboardButton(t("btn_back", user_lang), callback_data="btn_refresh")
        ]
    ]
    markup = InlineKeyboardMarkup(kb)
    if is_edit:
        await safe_edit_text(target, text, reply_markup=markup)
    else:
        await target.reply_text(text, parse_mode="HTML", reply_markup=markup)


async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles all inline button clicks with bilingual localization."""
    query = update.callback_query
    await query.answer()

    user = query.from_user
    user_id = user.id
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
        await render_trending_radar(query, user_id, user_lang, is_edit=True)

    elif data == "btn_surge":
        await query.message.reply_chat_action("typing")
        await render_surge_radar(query, user_id, user_lang, is_edit=True)

    elif data.startswith("inspect_"):
        mint = data.split("_")[1]
        await query.message.reply_chat_action("typing")
        scan = scan_token_security(mint)
        card_text = format_token_card(scan, lang=user_lang)
        await safe_edit_text(query, card_text, reply_markup=get_token_card_keyboard(mint, user_lang, user_id=user_id, symbol=scan.get("symbol", "TOKEN")))

    elif data == "btn_referral":
        bot_username = context.bot.username or "PopcornSniperBot"
        ref_link = f"https://t.me/{bot_username}?start=ref_{user_id}"
        stats = get_referral_stats(user_id)
        title = t("referral_card_title", user_lang)
        body = t("referral_card_body", user_lang, ref_link=ref_link, total_ref=stats["total_referrals"], earnings=stats["earnings_sol"])
        text = f"{title}\n━━━━━━━━━━━━━━━━━━━━━━━━━━\n{body}"

        share_text = "⚡ Fastest Solana Sniper & Trading Bot on Jupiter V6!" if user_lang == "en" else "⚡ أقوى بوت قنص وتداول على سولانا مع فحص RugCheck!"
        share_btn_text = "📤 Share on Telegram" if user_lang == "en" else "📤 مشاركة عبر تيليجرام"
        refresh_label = "🔄 تحديث الإحصائيات" if user_lang == "ar" else "🔄 Refresh Stats"

        x_intent_text = (
            f"Trade Solana memecoins with sub-400ms execution on Popcorn Sniper Bot! 🍿⚡\n\n"
            f"Built-in RugCheck auditor, auto-buy, and non-custodial wallets.\n\n"
            f"Start trading: {ref_link}"
        )
        x_share_url = f"https://twitter.com/intent/tweet?text={urllib.parse.quote(x_intent_text)}"

        kb = [
            [
                InlineKeyboardButton(share_btn_text, url=f"https://t.me/share/url?url={urllib.parse.quote(ref_link)}&text={urllib.parse.quote(share_text)}"),
                InlineKeyboardButton("📢 Share on X", url=x_share_url)
            ],
            [
                InlineKeyboardButton(refresh_label, callback_data="btn_referral"),
                InlineKeyboardButton(t("btn_back", user_lang), callback_data="btn_refresh")
            ]
        ]
        await safe_edit_text(query, text, reply_markup=InlineKeyboardMarkup(kb))

    elif data in ("btn_autobuy", "btn_autobuy_settings"):
        await render_autobuy_card(query, user_id, user_lang, is_edit=True)

    elif data in ("btn_toggle_autobuy", "toggle_autobuy"):
        new_state = toggle_auto_buy(user_id)
        _, current_amt = get_auto_buy_settings(user_id)
        state_str = ("ENABLED 🟢" if new_state else "DISABLED ⚪") if user_lang == "en" else ("مفعل 🟢" if new_state else "معطل ⚪")
        ack = t("autobuy_updated", user_lang, status=state_str, amt=current_amt)
        await query.answer(ack, show_alert=False)
        await render_autobuy_card(query, user_id, user_lang, is_edit=True)

    elif data.startswith("set_auto_amt_") or data.startswith("set_auto_"):
        if data.startswith("set_auto_amt_"):
            new_amt = float(data.replace("set_auto_amt_", ""))
        else:
            new_amt = float(data.replace("set_auto_", ""))
        set_auto_buy_amount(user_id, new_amt)
        set_auto_buy_status(user_id, True)
        state_str = "ENABLED 🟢" if user_lang == "en" else "مفعل 🟢"
        ack = t("autobuy_updated", user_lang, status=state_str, amt=new_amt)
        await query.answer(ack, show_alert=False)
        await render_autobuy_card(query, user_id, user_lang, is_edit=True)

    elif data == "btn_wallet":
        await render_wallet_card(query, user_id, user_lang, is_edit=True)

    elif data == "btn_show_qr":
        pubkey, _ = get_or_create_wallet(user_id)
        bal = get_sol_balance(pubkey)
        qr_buf = generate_deposit_qr_buffer(pubkey)
        caption = (
            f"{t('qr_card_title', user_lang)}\n"
            f"{t('qr_card_body', user_lang, pubkey=pubkey, balance=bal)}"
        )
        kb = [
            [InlineKeyboardButton(t("btn_wallet", user_lang), callback_data="btn_wallet")],
            [InlineKeyboardButton(t("btn_back", user_lang), callback_data="btn_refresh")]
        ]
        await query.message.reply_photo(photo=qr_buf, caption=caption, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb))

    elif data == "btn_gas_fees":
        await render_gas_card(query, user_id, user_lang, is_edit=True)

    elif data in ("btn_withdraw", "btn_withdraw_guide"):
        await render_withdraw_card(query, user_id, user_lang, is_edit=True)

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
        await render_positions(query, user_id, user_lang, is_edit=True)

    elif data == "btn_panic_confirm":
        await render_panic_confirm(query, user_id, user_lang, is_edit=True)

    elif data == "btn_panic_execute":
        await execute_panic_sell_all(query, user_id, user_lang)

    elif data == "btn_watchlist":
        await render_watchlist(query, user_id, user_lang, is_edit=True)

    elif data == "btn_history":
        await render_trade_history(query, user_id, user_lang, is_edit=True)

    elif data in ("btn_export_trades_csv", "btn_history_csv"):
        await query.answer()
        await send_trades_csv_export(query, user_id, user_lang)

    elif data == "btn_ping":
        await query.message.reply_chat_action("typing")
        await render_network_ping(query, user_id, user_lang, is_edit=True)

    elif data.startswith("price_"):
        mint = data.replace("price_", "", 1)
        await query.message.reply_chat_action("typing")
        bot_user = (context.bot.username if context and context.bot else None) or "PopcornSniperBot"
        await render_price_card(query, user_id, user_lang, mint, is_edit=True, bot_username=bot_user)

    elif data.startswith("quote_"):
        parts = data.split("_")
        mint = parts[1]
        amt = float(parts[2]) if len(parts) > 2 else 0.1
        await query.message.reply_chat_action("typing")
        await render_quote_card(query, user_id, user_lang, mint, amt, is_edit=True)

    elif data.startswith("track_"):
        mint = data.replace("track_", "", 1)
        scan = scan_token_security(mint)
        sym = scan.get("symbol", "TOKEN")
        current_price = float(scan.get("price_usd") or 0.0)
        add_to_watchlist(user_id, mint, sym, current_price=current_price)
        await query.answer(t("watchlist_added", user_lang), show_alert=False)
        msg_text = (query.message.text or "") if query.message else ""
        if "Radar" in msg_text or "رادار" in msg_text or "Price" in msg_text:
            bot_user = (context.bot.username if context and context.bot else None) or "PopcornSniperBot"
            await render_price_card(query, user_id, user_lang, mint, is_edit=True, bot_username=bot_user)
        elif "Simulation" in msg_text or "محاكاة" in msg_text:
            amt = get_user_settings(user_id).get("default_buy_amount", 0.1)
            await render_quote_card(query, user_id, user_lang, mint, amt, is_edit=True)
        elif "RugCheck" in msg_text or "Audit" in msg_text or "تدقيق" in msg_text or "أمان" in msg_text:
            await query.edit_message_reply_markup(reply_markup=get_token_card_keyboard(mint, user_lang, user_id=user_id, symbol=sym))

    elif data.startswith("untrack_"):
        mint = data.replace("untrack_", "", 1)
        remove_from_watchlist(user_id, mint)
        await query.answer(t("watchlist_removed", user_lang), show_alert=False)
        msg_text = (query.message.text or "") if query.message else ""
        if "Radar" in msg_text or "رادار" in msg_text or "Price" in msg_text:
            bot_user = (context.bot.username if context and context.bot else None) or "PopcornSniperBot"
            await render_price_card(query, user_id, user_lang, mint, is_edit=True, bot_username=bot_user)
        elif "Simulation" in msg_text or "محاكاة" in msg_text:
            amt = get_user_settings(user_id).get("default_buy_amount", 0.1)
            await render_quote_card(query, user_id, user_lang, mint, amt, is_edit=True)
        elif "RugCheck" in msg_text or "Audit" in msg_text or "تدقيق" in msg_text or "أمان" in msg_text:
            scan = scan_token_security(mint)
            sym = scan.get("symbol", "TOKEN")
            await query.edit_message_reply_markup(reply_markup=get_token_card_keyboard(mint, user_lang, user_id=user_id, symbol=sym))
        else:
            await render_watchlist(query, user_id, user_lang, is_edit=True)

    elif data == "btn_clear_watchlist":
        cleared_count = clear_user_watchlist(user_id)
        ack = f"Cleared {cleared_count} tokens from watchlist! 🗑️" if user_lang == "en" else f"تم مسح {cleared_count} عملات من قائمة المتابعة! 🗑️"
        await query.answer(ack, show_alert=False)
        await render_watchlist(query, user_id, user_lang, is_edit=True)

    elif data.startswith("custom_buy_"):
        mint = data.replace("custom_buy_", "", 1)
        context.user_data["awaiting_custom_buy"] = mint
        scan = scan_token_security(mint)
        sym = scan.get("symbol", "TOKEN")
        prompt_text = t("custom_buy_prompt", user_lang, symbol=html.escape(sym))
        await query.message.reply_text(prompt_text, parse_mode="HTML")

    elif data.startswith("custom_sell_"):
        mint = data.replace("custom_sell_", "", 1)
        context.user_data["awaiting_custom_sell"] = mint
        scan = scan_token_security(mint)
        sym = scan.get("symbol", "TOKEN")
        prompt_text = t("custom_sell_prompt", user_lang, symbol=html.escape(sym))
        await query.message.reply_text(prompt_text, parse_mode="HTML")

    elif data == "btn_pnl":
        bot_uname = (context.bot.username if context and context.bot and context.bot.username else "PopcornSniperBot")
        await render_pnl_card(query, user, user_id, user_lang, is_edit=True, bot_username=bot_uname)

    elif data == "btn_settings":
        text, kb = build_settings_card(user_id, user_lang)
        await safe_edit_text(query, text, reply_markup=kb)

    elif data == "btn_reset_defaults":
        reset_user_settings_to_defaults(user_id)
        ack = "Settings restored to defaults! 🔄" if user_lang == "en" else "تمت استعادة الإعدادات الافتراضية! 🔄"
        await query.answer(ack, show_alert=False)
        text, kb = build_settings_card(user_id, user_lang)
        await safe_edit_text(query, text, reply_markup=kb)

    elif data == "btn_presets":
        await render_presets_card(query, user_id, user_lang, is_edit=True)

    elif data.startswith("preset_buy_"):
        new_amt = float(data.split("_")[2])
        update_user_default_buy_amount(user_id, new_amt)
        ack = f"Default quick-buy size set to {new_amt:.2f} SOL" if user_lang == "en" else f"تم ضبط مبلغ القنص السريع إلى {new_amt:.2f} SOL"
        await query.answer(ack, show_alert=False)
        await render_presets_card(query, user_id, user_lang, is_edit=True)

    elif data == "btn_help":
        await render_help_card(query, user_id, user_lang, is_edit=True)

    elif data == "btn_version":
        await render_version_card(query, user_id, user_lang, is_edit=True)

    elif data == "btn_slippage":
        await render_slippage_card(query, user_id, user_lang, is_edit=True)

    elif data.startswith("slip_"):
        new_bps = int(data.split("_")[1])
        update_user_slippage(user_id, new_bps)
        ack = f"Slippage tolerance set to {new_bps/100.0}%" if user_lang == "en" else f"تم ضبط نسبة الانزلاق إلى {new_bps/100.0}%"
        await query.answer(ack, show_alert=False)
        msg_text = (query.message.text or "") if query.message else ""
        if "Slippage" in msg_text or "الانزلاق" in msg_text:
            await render_slippage_card(query, user_id, user_lang, is_edit=True)
        else:
            text, kb = build_settings_card(user_id, user_lang)
            await safe_edit_text(query, text, reply_markup=kb)

    elif data.startswith("gas_"):
        new_lamports = int(data.split("_")[1])
        update_user_priority_fee(user_id, new_lamports)
        ack = f"Priority fee set to {new_lamports/1e9:.5f} SOL" if user_lang == "en" else f"تم ضبط رسوم أولوية الغاز إلى {new_lamports/1e9:.5f} SOL"
        await query.answer(ack, show_alert=False)
        msg_text = (query.message.text or "") if query.message else ""
        if "Priority Fee" in msg_text or "أولوية الغاز" in msg_text or "Solana Priority" in msg_text:
            await render_gas_card(query, user_id, user_lang, is_edit=True)
        else:
            text, kb = build_settings_card(user_id, user_lang)
            await safe_edit_text(query, text, reply_markup=kb)

    elif data == "btn_tp":
        await render_tp_card(query, user_id, user_lang, is_edit=True)

    elif data == "btn_sl":
        await render_sl_card(query, user_id, user_lang, is_edit=True)

    elif data.startswith("tp_"):
        new_tp = int(data.split("_")[1])
        update_user_tp(user_id, new_tp)
        ack = t("tp_updated", user_lang, pct=new_tp)
        await query.answer(ack, show_alert=False)
        msg_text = (query.message.text or "") if query.message else ""
        if "Take-Profit" in msg_text or "الأرباح" in msg_text:
            await render_tp_card(query, user_id, user_lang, is_edit=True)
        else:
            text, kb = build_settings_card(user_id, user_lang)
            await safe_edit_text(query, text, reply_markup=kb)

    elif data.startswith("sl_"):
        new_sl = int(data.split("_")[1])
        update_user_sl(user_id, new_sl)
        ack = t("sl_updated", user_lang, pct=new_sl)
        await query.answer(ack, show_alert=False)
        msg_text = (query.message.text or "") if query.message else ""
        if "Stop-Loss" in msg_text or "الخسارة" in msg_text:
            await render_sl_card(query, user_id, user_lang, is_edit=True)
        else:
            text, kb = build_settings_card(user_id, user_lang)
            await safe_edit_text(query, text, reply_markup=kb)

    elif data == "toggle_alerts":
        new_state = toggle_price_alerts(user_id)
        state_str = ("ENABLED" if new_state else "DISABLED") if user_lang == "en" else ("مفعلة" if new_state else "معطلة")
        ack = t("alerts_toggled", user_lang, status=state_str)
        await query.answer(ack, show_alert=False)
        msg_text = (query.message.text or "") if query.message else ""
        if "Volatility" in msg_text or "التقلبات" in msg_text or "Alerts" in msg_text:
            await render_alerts_card(query, user_id, user_lang, is_edit=True)
        else:
            text, kb = build_settings_card(user_id, user_lang)
            await safe_edit_text(query, text, reply_markup=kb)

    elif data == "btn_alerts":
        await render_alerts_card(query, user_id, user_lang, is_edit=True)

    elif data.startswith("alert_pct_"):
        new_pct = float(data.split("_")[2])
        update_user_alert_threshold(user_id, new_pct)
        set_price_alerts_status(user_id, True)
        ack = f"Price alert threshold set to ±{new_pct:.0f}%" if user_lang == "en" else f"تم ضبط حد التنبيه إلى ±{new_pct:.0f}%"
        await query.answer(ack, show_alert=False)
        msg_text = (query.message.text or "") if query.message else ""
        if "Volatility" in msg_text or "التقلبات" in msg_text:
            await render_alerts_card(query, user_id, user_lang, is_edit=True)
        else:
            text, kb = build_settings_card(user_id, user_lang)
            await safe_edit_text(query, text, reply_markup=kb)

    elif data == "btn_snipe_guide":
        title = t("snipe_guide_title", user_lang)
        body = t("snipe_guide_body", user_lang)
        text = f"{title}\n━━━━━━━━━━━━━━━━━━━\n{body}"
        kb = [
            [InlineKeyboardButton(t("btn_show_qr", user_lang), callback_data="btn_show_qr")],
            [InlineKeyboardButton(t("btn_back", user_lang), callback_data="btn_refresh")]
        ]
        await safe_edit_text(query, text, reply_markup=InlineKeyboardMarkup(kb))

    elif data == "btn_tour":
        if user_lang == "ar":
            tour_text = (
                "🚀 <b>جولة سريعة: كيف تقتنص وتربح عبر البوت في 3 خطوات!</b> ⚡\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "1️⃣ <b>الخطوة الأولى - الإيداع السريع:</b>\n"
                "استخدم الأمر <code>/qr</code> أو <code>/wallet</code> وانسخ عنوان محفظتك المخصصة أو امسح الرمز عبر تطبيق Phantom أو منصتك المفضلة لإيداع رصيد من SOL.\n\n"
                "2️⃣ <b>الخطوة الثانية - القنص الفوري:</b>\n"
                "بمجرد رؤيتك لأي عملة جديدة على X أو DexScreener أو Pump.fun، انسخ عنوان العقد (CA) والصقه هنا مباشرة في المحادثة. سيقوم البوت بفحص أمان العملة تلقائياً عبر RugCheck وتوفير أزرار شراء بنقرة واحدة فائقة السرعة.\n\n"
                "3️⃣ <b>الخطوة الثالثة - جني الأرباح والتأمين:</b>\n"
                "استعرض صفقاتك المفتوحة فورياً عبر <code>/positions</code> أو اضبط أهداف الربح التلقائية عبر <code>/tp 50</code> ووقف الخسارة عبر <code>/sl 25</code>.\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "💡 <i>المحفظة غير احتجازية ومفتاحك الخاص مشفر بالكامل بـ AES-256!</i>"
            )
            tour_kb = [
                [InlineKeyboardButton("📲 إيداع الآن (QR)", callback_data="btn_show_qr")],
                [InlineKeyboardButton("🔥 تريند سولانا اللحظي", callback_data="btn_trending")],
                [InlineKeyboardButton("🔙 العودة للرئيسية", callback_data="btn_refresh")]
            ]
        else:
            tour_text = (
                "🚀 <b>Quick Tour: How to Snipe & Profit in 3 Simple Steps!</b> ⚡\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "1️⃣ <b>Step 1 — Instant Deposit:</b>\n"
                "Type <code>/qr</code> or <code>/wallet</code> to copy your dedicated deposit address or scan the QR code from Phantom / Solflare to fund your balance with SOL.\n\n"
                "2️⃣ <b>Step 2 — 1-Click Fast Sniping:</b>\n"
                "Whenever you spot an alpha token on X, DexScreener, or Pump.fun, paste the Contract Address (CA) directly into this chat. The bot audits honeypot safety via RugCheck and provides instant sub-400ms buy buttons.\n\n"
                "3️⃣ <b>Step 3 — Take Profit & Secure Capital:</b>\n"
                "View live token holdings with <code>/positions</code> or configure automatic Take-Profit (<code>/tp 50</code>) and Stop-Loss (<code>/sl 25</code>).\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "💡 <i>Non-custodial security: Your keys remain strictly encrypted with AES-256!</i>"
            )
            tour_kb = [
                [InlineKeyboardButton("📲 Deposit Now (QR)", callback_data="btn_show_qr")],
                [InlineKeyboardButton("🔥 Solana Trending Radar", callback_data="btn_trending")],
                [InlineKeyboardButton("🔙 Back to Dashboard", callback_data="btn_refresh")]
            ]
        await safe_edit_text(query, tour_text, reply_markup=InlineKeyboardMarkup(tour_kb))

    elif data == "btn_status":
        await query.message.reply_chat_action("typing")
        await render_status_card(query, user_id, user_lang, is_edit=True)

    elif data == "btn_fee_info":
        await query.message.reply_chat_action("typing")
        await render_fees_card(query, user_id, user_lang, is_edit=True)

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
            deposit_btn_text = "📲 Deposit SOL (QR Code)" if user_lang == "en" else "📲 إيداع فوري (رمز QR)"
            retry_btn_text = f"🔄 Retry Buy ({amount_sol} SOL)" if user_lang == "en" else f"🔄 إعادة محاولة الشراء ({amount_sol} SOL)"
            inspect_btn_text = "🔍 Back to Token" if user_lang == "en" else "🔍 العودة لبيانات العملة"
            kb = [
                [InlineKeyboardButton(deposit_btn_text, callback_data="btn_show_qr")],
                [InlineKeyboardButton(retry_btn_text, callback_data=f"buy_{mint}_{amount_sol}")],
                [
                    InlineKeyboardButton(inspect_btn_text, callback_data=f"inspect_{mint}"),
                    InlineKeyboardButton(t("btn_back", user_lang), callback_data="btn_refresh")
                ]
            ]
            await safe_edit_text(query, err_text, reply_markup=InlineKeyboardMarkup(kb))
            return

        prep_text = "⚡ <b>Routing best swap via Jupiter V6...</b>" if user_lang == "en" else "⚡ <b>جاري تحضير مسار الشراء عبر Jupiter...</b>"
        status_msg = await query.message.reply_text(prep_text, parse_mode="HTML")

        success, sig_or_err, out_amount, fee_sol = execute_buy_swap(user_id, mint, amount_sol, user_lang)

        if success:
            if user_lang == "en":
                success_text = (
                    f"🎉 <b>Buy Swap Executed Successfully!</b> 🟢\n"
                    f"━━━━━━━━━━━━━━━━━━━\n"
                    f"💸 Amount: <code>{amount_sol} SOL</code>\n"
                    f"🛡️ Platform Fee (1%): <code>{fee_sol:.6f} SOL</code>\n\n"
                    f"🔗 <a href='https://solscan.io/tx/{sig_or_err}'>View Transaction on Solscan</a>"
                )
            else:
                success_text = (
                    f"🎉 <b>تم تنفيذ صفقة الشراء بنجاح!</b> 🟢\n"
                    f"━━━━━━━━━━━━━━━━━━━\n"
                    f"💸 القيمة: <code>{amount_sol} SOL</code>\n"
                    f"🛡️ عمولة المنصة (1%): <code>{fee_sol:.6f} SOL</code>\n\n"
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

        success, sig_or_err, sol_received = execute_sell_swap(user_id, mint, pct, lang=user_lang)
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
        await render_withdraw_card(update.message, user_id, user_lang, is_edit=False)
        return

    raw1 = args[0].strip()
    raw2 = args[1].strip()

    # Smart detect which arg is the destination address vs amount
    if len(raw1) >= 32 and not raw1.replace(".", "").isdigit() and raw1.lower() not in ("all", "max"):
        dest_address = raw1
        amt_str = raw2
    elif len(raw2) >= 32 and not raw2.replace(".", "").isdigit() and raw2.lower() not in ("all", "max"):
        dest_address = raw2
        amt_str = raw1
    else:
        dest_address = raw1
        amt_str = raw2

    pubkey, _ = get_or_create_wallet(user_id)
    current_bal = get_sol_balance(pubkey)

    if amt_str.lower() in ("all", "max", "100%"):
        # Reserve buffer 0.0008 SOL for rent & signature fees
        amount_sol = max(0.0, current_bal - 0.0008)
        if amount_sol <= 0.0001:
            err = "❌ الرصيد المتاح غير كافٍ لتغطية رسوم المعاملة (الحد الأدنى 0.001 SOL)." if user_lang == "ar" else "❌ Balance too low to cover Solana transaction fees (minimum 0.001 SOL)."
            await update.message.reply_text(err, parse_mode="HTML")
            return
    else:
        try:
            amount_sol = float(amt_str.rstrip("%"))
            if amount_sol <= 0:
                raise ValueError()
        except ValueError:
            invalid_num = "❌ Invalid amount entered. Please specify a valid number (e.g. <code>0.1</code>) or <code>all</code>." if user_lang == "en" else "❌ المبلغ المدخل غير صحيح، يرجى كتابة رقم صالح (مثل <code>0.1</code>) أو كلمة <code>all</code>."
            await update.message.reply_text(invalid_num, parse_mode="HTML")
            return

    wait_tx = "⚡ <b>Preparing and broadcasting withdrawal transaction on Solana...</b>" if user_lang == "en" else "⚡ <b>جاري تحضير وتوقيع معاملة السحب على شبكة سولانا...</b>"
    status_msg = await update.message.reply_text(wait_tx, parse_mode="HTML")
    success, sig_or_err = withdraw_sol(user_id, dest_address, amount_sol, lang=user_lang)

    if success:
        if user_lang == "en":
            text = (
                f"🎉 <b>Successfully Withdrawn {amount_sol:.4f} SOL!</b> 💸\n"
                f"━━━━━━━━━━━━━━━━━━━\n"
                f"📍 Recipient Address: <code>{dest_address}</code>\n\n"
                f"🔗 <a href='https://solscan.io/tx/{sig_or_err}'>View Transaction on Solscan</a>"
            )
        else:
            text = (
                f"🎉 <b>تم سحب {amount_sol:.4f} SOL بنجاح!</b> 💸\n"
                f"━━━━━━━━━━━━━━━━━━━\n"
                f"📍 المحفظة المستلمة: <code>{dest_address}</code>\n\n"
                f"🔗 <a href='https://solscan.io/tx/{sig_or_err}'>عرض المعاملة على Solscan</a>"
            )
        await status_msg.edit_text(text, parse_mode="HTML", disable_web_page_preview=True)
    else:
        await status_msg.edit_text(f"❌ <b>Withdrawal failed</b>: <code>{html.escape(sig_or_err)}</code>", parse_mode="HTML")


async def render_wallet_card(target, user_id: int, user_lang: str, is_edit: bool = False):
    """Renders the comprehensive non-custodial Solana wallet cockpit and deposit interface."""
    pubkey, _ = get_or_create_wallet(user_id)
    balance = get_sol_balance(pubkey)
    tokens = get_token_accounts(pubkey)
    now_str = get_current_time_str()
    qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=250x250&data=solana:{pubkey}"

    if user_lang == "ar":
        text = (
            f"💳 <b>إدارة المحفظة والإيداع</b> 🏦\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"📍 <b>عنوان إيداع SOL (اضغط للنسخ)</b>:\n<code>{pubkey}</code>\n\n"
            f"💰 <b>الرصيد المتاح</b>: <code>{balance:.4f} SOL</code>\n"
            f"📊 <b>العملات المفتوحة</b>: <code>{len(tokens)} صفقات</code>\n"
            f"🕒 وقت الفحص: <code>{now_str}</code>\n\n"
            f"🔗 <a href='https://solscan.io/account/{pubkey}'>عرض المحفظة على Solscan</a>\n"
            f"📷 <a href='{qr_url}'>عرض رمز QR للإيداع السريع عبر الكاميرا</a>\n\n"
            f"⚠️ <i>مفتاحك الخاص مشفر محلياً بنظام AES-256 لحمايتك الكاملة.</i>\n"
        )
        kb = [
            [InlineKeyboardButton("📲 إظهار رمز QR للإيداع", callback_data="btn_show_qr")],
            [InlineKeyboardButton("📊 عرض الصفقات المفتوحة", callback_data="btn_positions")],
            [InlineKeyboardButton("💸 سحب SOL للخارج", callback_data="btn_withdraw_guide")],
            [InlineKeyboardButton("🔑 إظهار المفتاح الخاص", callback_data="btn_export_key")],
            [
                InlineKeyboardButton("🔄 تحديث الرصيد", callback_data="btn_wallet"),
                InlineKeyboardButton("🔙 العودة للرئيسية", callback_data="btn_refresh")
            ]
        ]
    else:
        text = (
            f"💳 <b>Solana Trading Wallet & Deposit</b> 🏦\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"📍 <b>SOL Deposit Address (Tap to copy)</b>:\n<code>{pubkey}</code>\n\n"
            f"💰 <b>Available Balance</b>: <code>{balance:.4f} SOL</code>\n"
            f"📊 <b>Open Token Holdings</b>: <code>{len(tokens)} positions</code>\n"
            f"🕒 Checked: <code>{now_str}</code>\n\n"
            f"🔗 <a href='https://solscan.io/account/{pubkey}'>View Account on Solscan</a>\n"
            f"📷 <a href='{qr_url}'>Instant QR Code Deposit</a>\n\n"
            f"⚠️ <i>Your private key is locally encrypted with AES-256 for non-custodial ownership.</i>\n"
        )
        kb = [
            [InlineKeyboardButton("📲 Instant Deposit QR", callback_data="btn_show_qr")],
            [InlineKeyboardButton("📊 View Open Positions", callback_data="btn_positions")],
            [InlineKeyboardButton("💸 Withdraw SOL to External Wallet", callback_data="btn_withdraw_guide")],
            [InlineKeyboardButton("🔑 Export Private Key", callback_data="btn_export_key")],
            [
                InlineKeyboardButton("🔄 Refresh Balance", callback_data="btn_wallet"),
                InlineKeyboardButton(t("btn_back", user_lang), callback_data="btn_refresh")
            ]
        ]
    markup = InlineKeyboardMarkup(kb)
    if is_edit:
        await safe_edit_text(target, text, reply_markup=markup)
    else:
        if hasattr(target, "reply_text"):
            await target.reply_text(text, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True)
        elif hasattr(target, "message") and hasattr(target.message, "reply_text"):
            await target.message.reply_text(text, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True)


async def wallet_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /wallet command with open token holdings preview."""
    user_id = update.effective_user.id
    user_lang = get_user_language(user_id)
    await render_wallet_card(update.message, user_id, user_lang, is_edit=False)


async def qr_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /qr and /deposit command: generates and sends native Solana deposit QR code."""
    user_id = update.effective_user.id
    user_lang = get_user_language(user_id)
    pubkey, _ = get_or_create_wallet(user_id)
    balance = get_sol_balance(pubkey)
    buf = generate_deposit_qr_buffer(pubkey)
    caption = (
        f"{t('qr_card_title', user_lang)}\n"
        f"{t('qr_card_body', user_lang, pubkey=pubkey, balance=balance)}"
    )
    kb = [
        [InlineKeyboardButton(t("btn_wallet", user_lang), callback_data="btn_wallet")],
        [InlineKeyboardButton(t("btn_back", user_lang), callback_data="btn_refresh")]
    ]
    await update.message.reply_photo(photo=buf, caption=caption, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb))


async def export_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /export and /backup command: Exports the user's private key with strict security warning."""
    user = update.effective_user
    user_id = user.id
    user_lang = get_user_language(user_id)
    p_key = export_private_key_b58(user_id)
    if user_lang == "ar":
        text = (
            f"🚨 <b>تحذير أمني شديد</b>: لا تشارك هذا المفتاح مع أي شخص أو في أي محادثة أبداً!\n\n"
            f"🔑 <b>المفتاح الخاص (Base58)</b>:\n"
            f"<code>{p_key}</code>\n\n"
            f"💡 يمكنك نسخه واستيراده في محفظة Phantom أو Solflare للوصول المباشر إلى أموالك دون وسيط."
        )
    else:
        text = (
            f"🚨 <b>STRICT SECURITY WARNING</b>: Never share this private key with anyone or in any group chat!\n\n"
            f"🔑 <b>Private Key (Base58)</b>:\n"
            f"<code>{p_key}</code>\n\n"
            f"💡 You can copy and import this into Phantom or Solflare wallet anytime to access your funds non-custodially."
        )
    kb = [[InlineKeyboardButton(t("btn_back", user_lang), callback_data="btn_wallet")]]
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb))


async def gas_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /gas command: queries Solana on-chain priority fees and displays live congestion radar."""
    user_id = update.effective_user.id
    user_lang = get_user_language(user_id)
    if context.args:
        raw_arg = context.args[0].lower().strip()
        new_lamports = None
        if raw_arg in ("normal", "عادي"):
            new_lamports = 50_000
        elif raw_arg in ("turbo", "تيربو"):
            new_lamports = 250_000
        elif raw_arg in ("ultra", "فائق"):
            new_lamports = 1_000_000
        else:
            try:
                val = float(raw_arg)
                new_lamports = int(val * 1e9) if val < 1.0 else int(val)
            except ValueError:
                pass
        if new_lamports and 1_000 <= new_lamports <= 50_000_000:
            update_user_priority_fee(user_id, new_lamports)
    await render_gas_card(update.message, user_id, user_lang, is_edit=False)



async def positions_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /positions command."""
    user_id = update.effective_user.id
    user_lang = get_user_language(user_id)
    await render_positions(update.message, user_id, user_lang, is_edit=False)


async def panic_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /panic and /sellall command: /panic [now|confirm]"""
    user_id = update.effective_user.id
    user_lang = get_user_language(user_id)
    args = context.args

    if args and args[0].lower().strip() in ("now", "confirm", "instant", "force"):
        await execute_panic_sell_all(update.message, user_id, user_lang)
        return

    await render_panic_confirm(update.message, user_id, user_lang, is_edit=False)


async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /settings command."""
    user_id = update.effective_user.id
    user_lang = get_user_language(user_id)
    text, kb = build_settings_card(user_id, user_lang)
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=kb)


async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /reset and /defaults command: Restores trading settings to recommended defaults."""
    user = update.effective_user
    user_id = user.id
    user_lang = get_user_language(user_id)
    reset_user_settings_to_defaults(user_id)
    now_str = get_current_time_str()

    if user_lang == "ar":
        text = (
            "⚙️ <b>تمت استعادة إعدادات التداول الافتراضية بنجاح!</b> 🔄\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "• 🎯 <b>الانزلاق السعري (Slippage):</b> <code>1.0%</code> (100 BPS)\n"
            "• ⛽ <b>أولوية الغاز (Priority Fee):</b> <code>عادي (0.00005 SOL)</code>\n"
            "• 🤖 <b>القنص التلقائي (Auto-Buy):</b> <code>معطل</code> (0.1 SOL)\n"
            "• 🎯 <b>هدف جني الأرباح (Take-Profit):</b> <code>+50%</code>\n"
            "• 🛑 <b>حد وقف الخسارة (Stop-Loss):</b> <code>-25%</code>\n\n"
            f"🕒 <code>{now_str}</code>"
        )
    else:
        text = (
            "⚙️ <b>Trading Settings Reset to Recommended Defaults!</b> 🔄\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "• 🎯 <b>Slippage Tolerance:</b> <code>1.0%</code> (100 BPS)\n"
            "• ⛽ <b>Priority Fee:</b> <code>Normal (0.00005 SOL)</code>\n"
            "• 🤖 <b>Auto-Buy Sniper:</b> <code>Disabled</code> (0.1 SOL)\n"
            "• 🎯 <b>Take-Profit Target:</b> <code>+50%</code>\n"
            "• 🛑 <b>Stop-Loss Limit:</b> <code>-25%</code>\n\n"
            f"🕒 <code>{now_str}</code>"
        )
    kb = [
        [
            InlineKeyboardButton(t("btn_settings", user_lang), callback_data="btn_settings"),
            InlineKeyboardButton(t("btn_back", user_lang), callback_data="btn_refresh")
        ]
    ]
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb))


async def tour_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /tour command: interactive step-by-step onboarding guide."""
    user_id = update.effective_user.id
    user_lang = get_user_language(user_id)
    if user_lang == "ar":
        text = (
            "🚀 <b>جولة سريعة: كيف تقتنص وتربح عبر البوت في 3 خطوات!</b> ⚡\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "1️⃣ <b>الخطوة الأولى - الإيداع السريع:</b>\n"
            "استخدم الأمر <code>/qr</code> أو <code>/wallet</code> وانسخ عنوان محفظتك المخصصة أو امسح الرمز عبر تطبيق Phantom أو منصتك المفضلة لإيداع رصيد من SOL.\n\n"
            "2️⃣ <b>الخطوة الثانية - القنص الفوري:</b>\n"
            "بمجرد رؤيتك لأي عملة جديدة على X أو DexScreener أو Pump.fun، انسخ عنوان العقد (CA) والصقه هنا مباشرة في المحادثة. سيقوم البوت بفحص أمان العملة تلقائياً عبر RugCheck وتوفير أزرار شراء بنقرة واحدة فائقة السرعة.\n\n"
            "3️⃣ <b>الخطوة الثالثة - جني الأرباح والتأمين:</b>\n"
            "استعرض صفقاتك المفتوحة فورياً عبر <code>/positions</code> أو اضبط أهداف الربح التلقائية عبر <code>/tp 50</code> ووقف الخسارة عبر <code>/sl 25</code>.\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "💡 <i>المحفظة غير احتجازية ومفتاحك الخاص مشفر بالكامل بـ AES-256!</i>"
        )
        kb = [
            [InlineKeyboardButton("📲 إيداع الآن (QR)", callback_data="btn_show_qr")],
            [InlineKeyboardButton("🔥 تريند سولانا اللحظي", callback_data="btn_trending")],
            [InlineKeyboardButton("🔙 العودة للرئيسية", callback_data="btn_refresh")]
        ]
    else:
        text = (
            "🚀 <b>Quick Tour: How to Snipe & Profit in 3 Simple Steps!</b> ⚡\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "1️⃣ <b>Step 1 — Instant Deposit:</b>\n"
            "Type <code>/qr</code> or <code>/wallet</code> to copy your dedicated deposit address or scan the QR code from Phantom / Solflare to fund your balance with SOL.\n\n"
            "2️⃣ <b>Step 2 — 1-Click Fast Sniping:</b>\n"
            "Whenever you spot an alpha token on X, DexScreener, or Pump.fun, paste the Contract Address (CA) directly into this chat. The bot audits honeypot safety via RugCheck and provides instant sub-400ms buy buttons.\n\n"
            "3️⃣ <b>Step 3 — Take Profit & Secure Capital:</b>\n"
            "View live token holdings with <code>/positions</code> or configure automatic Take-Profit (<code>/tp 50</code>) and Stop-Loss (<code>/sl 25</code>).\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "💡 <i>Non-custodial security: Your keys remain strictly encrypted with AES-256!</i>"
        )
        kb = [
            [InlineKeyboardButton("📲 Deposit Now (QR)", callback_data="btn_show_qr")],
            [InlineKeyboardButton("🔥 Solana Trending Radar", callback_data="btn_trending")],
            [InlineKeyboardButton("🔙 Back to Dashboard", callback_data="btn_refresh")]
        ]
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb))



async def slippage_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /slippage and /slip command: /slippage [PERCENT]"""
    user_id = update.effective_user.id
    user_lang = get_user_language(user_id)
    args = context.args

    if args:
        try:
            val = float(args[0].strip().rstrip("%"))
            if 0.1 <= val <= 50.0:
                bps = int(val * 100)
                update_user_slippage(user_id, bps)
            else:
                await update.message.reply_text(t("slippage_invalid", user_lang), parse_mode="HTML")
                return
        except ValueError:
            await update.message.reply_text(t("slippage_syntax_help", user_lang), parse_mode="HTML")
            return

    await render_slippage_card(update.message, user_id, user_lang, is_edit=False)


async def autobuy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /autobuy and /auto command: /autobuy [AMOUNT|on|off]"""
    user_id = update.effective_user.id
    user_lang = get_user_language(user_id)
    args = context.args

    if args:
        sub = args[0].strip().lower()
        if sub in ("off", "disable", "stop", "0"):
            set_auto_buy_status(user_id, False)
        elif sub in ("on", "enable", "start", "1"):
            set_auto_buy_status(user_id, True)
        else:
            try:
                amt = float(sub)
                if amt < 0.005 or amt > 50.0:
                    err = "❌ Please specify an amount between 0.005 and 50 SOL." if user_lang == "en" else "❌ يرجى تحديد مبلغ بين 0.005 و 50 SOL."
                    await update.message.reply_text(err, parse_mode="HTML")
                    return
                set_auto_buy_amount(user_id, amt)
                set_auto_buy_status(user_id, True)
            except ValueError:
                err = "❌ Usage: <code>/autobuy [0.05|0.1|0.5|1.0|on|off]</code>" if user_lang == "en" else "❌ طريقة الاستخدام: <code>/autobuy [0.05|0.1|0.5|1.0|on|off]</code>"
                await update.message.reply_text(err, parse_mode="HTML")
                return

    await render_autobuy_card(update.message, user_id, user_lang, is_edit=False)


async def presets_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /presets, /preset, /quickbuy command: /presets [AMOUNT_SOL]"""
    user_id = update.effective_user.id
    user_lang = get_user_language(user_id)
    args = context.args

    if args:
        try:
            amt = float(args[0].strip())
            if amt < 0.001 or amt > 100.0:
                err = "❌ Please specify an amount between 0.001 and 100 SOL." if user_lang == "en" else "❌ يرجى تحديد مبلغ بين 0.001 و 100 SOL."
                await update.message.reply_text(err, parse_mode="HTML")
                return
            update_user_default_buy_amount(user_id, amt)
            ack = f"✅ Default quick-buy size set to <code>{amt:.2f} SOL</code>" if user_lang == "en" else f"✅ تم ضبط مبلغ القنص السريع الافتراضي إلى <code>{amt:.2f} SOL</code>"
            await update.message.reply_text(ack, parse_mode="HTML")
        except ValueError:
            err = "❌ Usage: <code>/presets [AMOUNT_SOL]</code> (e.g. <code>/presets 0.25</code>)" if user_lang == "en" else "❌ الاستخدام: <code>/presets [المبلغ_SOL]</code> (مثال: <code>/presets 0.25</code>)"
            await update.message.reply_text(err, parse_mode="HTML")
            return

    await render_presets_card(update.message, user_id, user_lang, is_edit=False)


async def price_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /price, /chart, /p, and /c command: /price [CA_OR_TICKER]"""
    user_id = update.effective_user.id
    user_lang = get_user_language(user_id)
    args = context.args

    if not args:
        await update.message.reply_text(t("price_syntax_help", user_lang), parse_mode="HTML")
        return

    query = " ".join(args).strip()
    mint = extract_token_mint(query)
    if not mint:
        matched = search_solana_token(query)
        if matched:
            mint = matched["mint"]

    if not mint:
        err = t("search_not_found", user_lang, query=html.escape(query))
        await update.message.reply_text(err, parse_mode="HTML")
        return

    wait_text = "💵 <b>جاري فحص السعر والسيولة اللحظية...</b>" if user_lang == "ar" else "💵 <b>Fetching real-time price & liquidity quote...</b>"
    status_msg = await update.message.reply_text(wait_text, parse_mode="HTML")

    bot_user = (context.bot.username if context and context.bot else None) or "PopcornSniperBot"
    await render_price_card(status_msg, user_id, user_lang, mint, is_edit=True, bot_username=bot_user)


async def quote_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /quote, /sim, and /simulate commands: /quote [AMOUNT_SOL] [CA_OR_TICKER]"""
    user_id = update.effective_user.id
    user_lang = get_user_language(user_id)
    args = context.args

    if not args:
        help_text = (
            "ℹ️ <b>Jupiter V6 Swap Simulation Syntax:</b>\n"
            "<code>/quote [AMOUNT_SOL] [CA_OR_TICKER]</code>\n\n"
            "<b>Examples:</b>\n"
            "• <code>/quote 0.1 bonk</code>\n"
            "• <code>/quote 0.5 DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263</code>\n"
            "• <code>/quote popcat</code> (uses default quick-buy size)"
        ) if user_lang == "en" else (
            "ℹ️ <b>صيغة محاكاة صفقات Jupiter V6:</b>\n"
            "<code>/quote [المبلغ_SOL] [العقد_أو_الرمز]</code>\n\n"
            "<b>أمثلة سريعة:</b>\n"
            "• <code>/quote 0.1 bonk</code>\n"
            "• <code>/quote 0.5 DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263</code>\n"
            "• <code>/quote popcat</code> (يستخدم مبلغ القنص الافتراضي الخاص بك)"
        )
        await update.message.reply_text(help_text, parse_mode="HTML")
        return

    settings = get_user_settings(user_id)
    default_buy = settings.get("default_buy_amount", 0.1)

    # Resilient multi-word token and amount parsing
    amount_sol = None
    target_token = ""
    try:
        first_val = float(args[0].strip())
        if first_val > 0:
            amount_sol = first_val
            target_token = " ".join(args[1:]).strip()
    except ValueError:
        pass

    if amount_sol is None and len(args) > 1:
        try:
            last_val = float(args[-1].strip())
            if last_val > 0:
                amount_sol = last_val
                target_token = " ".join(args[:-1]).strip()
        except ValueError:
            pass

    if amount_sol is None:
        amount_sol = default_buy
        target_token = " ".join(args).strip()

    if not target_token:
        err = "❌ Please specify a token ticker or CA. Example: <code>/quote 0.1 bonk</code>" if user_lang == "en" else "❌ يرجى تحديد رمز أو عقد العملة. مثال: <code>/quote 0.1 bonk</code>"
        await update.message.reply_text(err, parse_mode="HTML")
        return

    mint = extract_token_mint(target_token)
    if not mint:
        matched = search_solana_token(target_token)
        if matched:
            mint = matched["mint"]

    if not mint:
        err = t("search_not_found", user_lang, query=html.escape(target_token))
        await update.message.reply_text(err, parse_mode="HTML")
        return

    wait_text = "⚡ <b>Simulating Jupiter V6 swap routing & price impact...</b>" if user_lang == "en" else "⚡ <b>جاري محاكاة مسار الصفقة وحساب السعر عبر Jupiter V6...</b>"
    status_msg = await update.message.reply_text(wait_text, parse_mode="HTML")
    await render_quote_card(status_msg, user_id, user_lang, mint, amount_sol, is_edit=True)


async def tp_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /tp command: /tp [PERCENT]"""
    user_id = update.effective_user.id
    user_lang = get_user_language(user_id)
    args = context.args
    if args:
        try:
            val = int(args[0].strip().rstrip("%"))
            if 5 <= val <= 1000:
                update_user_tp(user_id, val)
            else:
                err = "❌ Please specify between 5% and 1000%." if user_lang == "en" else "❌ يرجى تحديد نسبة بين 5% و 1000%."
                await update.message.reply_text(err, parse_mode="HTML")
                return
        except ValueError:
            await update.message.reply_text(t("tp_syntax_help", user_lang), parse_mode="HTML")
            return
    await render_tp_card(update.message, user_id, user_lang, is_edit=False)


async def sl_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /sl command: /sl [PERCENT]"""
    user_id = update.effective_user.id
    user_lang = get_user_language(user_id)
    args = context.args
    if args:
        try:
            val = int(args[0].strip().rstrip("%"))
            if 5 <= val <= 95:
                update_user_sl(user_id, val)
            else:
                err = "❌ Please specify between 5% and 95%." if user_lang == "en" else "❌ يرجى تحديد نسبة بين 5% و 95%."
                await update.message.reply_text(err, parse_mode="HTML")
                return
        except ValueError:
            await update.message.reply_text(t("sl_syntax_help", user_lang), parse_mode="HTML")
            return
    await render_sl_card(update.message, user_id, user_lang, is_edit=False)


async def sell_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /sell command: /sell [CA_OR_TICKER] [PERCENT] or /sell [PERCENT] [CA_OR_TICKER]"""
    user = update.effective_user
    user_id = user.id
    user_lang = get_user_language(user_id)
    args = context.args

    if not args:
        pubkey, _ = get_or_create_wallet(user_id)
        tokens = get_token_accounts(pubkey)
        if tokens:
            await render_positions(update.message, user_id, user_lang, is_edit=False)
            return
        await update.message.reply_text(t("sell_syntax_help", user_lang), parse_mode="HTML")
        return

    def parse_pct_val(val_str: str):
        clean = val_str.rstrip("%").lower().strip()
        if clean in ("all", "max"):
            return 100
        if clean.isdigit():
            val = int(clean)
            if 1 <= val <= 100:
                return val
        return None

    pct = None
    raw_target = ""

    # Check if first arg is percentage / all / max (e.g. /sell 50 pepe coin or /sell all bonk)
    p1 = parse_pct_val(args[0])
    if p1 is not None and len(args) > 1:
        pct = p1
        raw_target = " ".join(args[1:]).strip()

    # Check if last arg is percentage / all / max (e.g. /sell pepe coin 50 or /sell bonk all)
    if pct is None and len(args) > 1:
        p_last = parse_pct_val(args[-1])
        if p_last is not None:
            pct = p_last
            raw_target = " ".join(args[:-1]).strip()

    # Default to 100% sell if no percentage was specified: e.g. /sell pepe coin
    if pct is None:
        pct = 100
        raw_target = " ".join(args).strip()

    if not raw_target:
        await update.message.reply_text(t("sell_syntax_help", user_lang), parse_mode="HTML")
        return

    mint = extract_token_mint(raw_target)
    if not mint:
        # Check if user holds this token in wallet by symbol
        keypair = get_user_keypair(user_id)
        if keypair:
            try:
                tokens = get_token_accounts(str(keypair.pubkey()))
                clean_sym = raw_target.lower().lstrip("$")
                for t_acc in tokens:
                    if t_acc.get("symbol", "").lower() == clean_sym:
                        mint = t_acc["mint"]
                        break
            except Exception:
                pass

    if not mint:
        matched = search_solana_token(raw_target)
        if matched:
            mint = matched["mint"]
        else:
            err = f"❌ Could not resolve token: {html.escape(raw_target)}" if user_lang == "en" else f"❌ تعذر العثور على العملة: {html.escape(raw_target)}"
            await update.message.reply_text(err, parse_mode="HTML")
            return

    prep_sell = f"⚡ <b>Executing {pct}% Sell Swap via Jupiter...</b>" if user_lang == "en" else f"⚡ <b>جاري تنفيذ بيع {pct}% من العملة عبر Jupiter...</b>"
    status_msg = await update.message.reply_text(prep_sell, parse_mode="HTML")

    success, sig_or_err, sol_received = execute_sell_swap(user_id, mint, pct, lang=user_lang)
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


async def pnl_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /pnl command displaying user's trading performance card."""
    user = update.effective_user
    user_id = user.id
    user_lang = get_user_language(user_id)
    bot_uname = (context.bot.username if context and context.bot and context.bot.username else "PopcornSniperBot")
    await render_pnl_card(update.message, user, user_id, user_lang, is_edit=False, bot_username=bot_uname)


async def ping_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /ping, /speed, and /network command."""
    user_id = update.effective_user.id
    user_lang = get_user_language(user_id)
    await render_network_ping(update.message, user_id, user_lang, is_edit=False)


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /status, /cluster, and /info commands."""
    user_id = update.effective_user.id
    user_lang = get_user_language(user_id)
    await render_status_card(update.message, user_id, user_lang, is_edit=False)


async def fees_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /fees and /fee commands."""
    user_id = update.effective_user.id
    user_lang = get_user_language(user_id)
    await render_fees_card(update.message, user_id, user_lang, is_edit=False)


async def audit_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /audit and /check command: /audit [CA_OR_TICKER]"""
    user = update.effective_user
    user_id = user.id
    user_lang = get_user_language(user_id)
    args = context.args

    if not args:
        help_msg = t("audit_usage_help", user_lang)
        await update.message.reply_text(help_msg, parse_mode="HTML")
        return

    query = " ".join(args).strip()
    mint = extract_token_mint(query)
    if not mint:
        matched = search_solana_token(query)
        if matched:
            mint = matched["mint"]

    if not mint:
        err = t("search_not_found", user_lang, query=html.escape(query))
        await update.message.reply_text(err, parse_mode="HTML")
        return

    wait_text = "🔍 <b>جاري فحص وتدقيق أمان العقد الذكي...</b>" if user_lang == "ar" else "🔍 <b>Running full security audit on token...</b>"
    status_msg = await update.message.reply_text(wait_text, parse_mode="HTML")

    scan = scan_token_security(mint)
    card_text = format_token_card(scan, lang=user_lang)
    kb = get_token_card_keyboard(mint, user_lang, user_id=user_id, symbol=scan.get("symbol", "TOKEN"))
    await status_msg.edit_text(card_text, parse_mode="HTML", reply_markup=kb, disable_web_page_preview=True)


async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /history and /trades command: /history [csv|export]."""
    user_id = update.effective_user.id
    user_lang = get_user_language(user_id)
    if context.args and context.args[0].lower() in ["csv", "export", "file"]:
        await send_trades_csv_export(update.message, user_id, user_lang)
        return
    await render_trade_history(update.message, user_id, user_lang, is_edit=False)


async def csv_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Direct handler for /csv and /tradescsv: instantly exports user's trade history as CSV."""
    user_id = update.effective_user.id
    user_lang = get_user_language(user_id)
    await send_trades_csv_export(update.message, user_id, user_lang)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /help command with interactive quick-action navigation keyboard."""
    user_id = update.effective_user.id
    user_lang = get_user_language(user_id)
    await render_help_card(update.message, user_id, user_lang, is_edit=False)


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /cancel command to abort any pending custom input prompts."""
    user_id = update.effective_user.id
    user_lang = get_user_language(user_id)
    had_pending = (
        context.user_data.pop("awaiting_custom_buy", None) is not None or
        context.user_data.pop("awaiting_custom_sell", None) is not None
    )
    if had_pending:
        msg = "✅ <b>Input prompt cancelled.</b>" if user_lang == "en" else "✅ <b>تم إلغاء طلب الإدخال.</b>"
    else:
        msg = "ℹ️ <b>No active operation to cancel.</b>" if user_lang == "en" else "ℹ️ <b>لا توجد أي عملية معلقة لإلغائها.</b>"
    await update.message.reply_text(msg, parse_mode="HTML")


async def render_version_card(target, user_id: int, user_lang: str, is_edit: bool = False):
    """Renders architectural specs, release metadata, and navigation buttons."""
    if user_lang == "ar":
        card = (
            "🍿 <b>Popcorn Sniper Bot — معلومات الإصدار والبنية المعمارية</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🚀 <b>الإصدار الحالي:</b> <code>{BOT_VERSION} (Production)</code>\n"
            "⚡ <b>محرك التداول:</b> Jupiter V6 Routing Engine + Jito Anti-MEV Bundles\n"
            "🪙 <b>معايير التوكن:</b> SPL Standard + Token-2022 Extensions (دعم شامل)\n"
            "🛡️ <b>نظام الحماية:</b> فحص تلقائي مزدوج (RugCheck + DexScreener Analysis)\n"
            "🔐 <b>الأمان المالي:</b> محافظ محلية مشفرة بتقنية AES-256 (Non-Custodial)\n"
            "💎 <b>عمولة التداول:</b> 1.0% فقط على عمليات التداول عبر Jupiter\n"
            "🎁 <b>برنامج الإحالة:</b> 25% مشاركة أرباح مدى الحياة للمستخدمين\n"
            "⏱️ <b>زمن الاستجابة:</b> ما دون 400 ميلي ثانية (Sub-400ms High-Velocity)\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "🌐 <b>المستودع الرسمي:</b> github.com/m7md570/solana-telegram-sniper-bot"
        )
    else:
        card = (
            "🍿 <b>Popcorn Solana Sniper Bot — Architectural Specifications</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🚀 <b>Software Release:</b> <code>{BOT_VERSION} (Production)</code>\n"
            "⚡ <b>Routing Engine:</b> Jupiter V6 Aggregator + Jito Anti-MEV Sandwich Protection\n"
            "🪙 <b>Token Standards:</b> SPL Standard + Token-2022 Extensions (Universal)\n"
            "🛡️ <b>Security Engine:</b> Dual Real-Time Audit (RugCheck + DexScreener Integrity)\n"
            "🔐 <b>Key Management:</b> Non-Custodial Encrypted Local Storage (AES-256)\n"
            "💎 <b>Platform Fee:</b> 1.0% on executed Jupiter swaps (0% on deposits/withdrawals)\n"
            "🎁 <b>Affiliate Program:</b> 25% Lifetime Revenue Share (/referral)\n"
            "⏱️ <b>Execution Velocity:</b> Sub-400ms High-Frequency Architecture\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "🌐 <b>Official Repository:</b> github.com/m7md570/solana-telegram-sniper-bot"
        )

    latency_label = "⚡ سرعة الشبكة" if user_lang == "ar" else "⚡ Latency Radar"
    back_label = t("btn_back", user_lang)
    kb = [
        [
            InlineKeyboardButton("🚀 Launch Sniper", callback_data="btn_refresh"),
            InlineKeyboardButton("🎁 25% Referral", callback_data="btn_referral")
        ],
        [
            InlineKeyboardButton("📦 GitHub Releases", url="https://github.com/m7md570/solana-telegram-sniper-bot/releases"),
            InlineKeyboardButton(latency_label, callback_data="btn_ping")
        ],
        [
            InlineKeyboardButton(back_label, callback_data="btn_help")
        ]
    ]
    markup = InlineKeyboardMarkup(kb)
    if is_edit:
        await safe_edit_text(target, card, reply_markup=markup)
    else:
        await target.reply_text(card, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True)


async def version_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /version and /about command displaying architectural specs and release metadata."""
    user_id = update.effective_user.id
    user_lang = get_user_language(user_id)
    await render_version_card(update.message, user_id, user_lang, is_edit=False)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Global error handler to catch and log unexpected errors gracefully."""
    logger.error(f"Exception while handling an update: {context.error}")


async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /search and /find command to search any Solana token by ticker or name."""
    user = update.effective_user
    user_id = user.id
    user_lang = get_user_language(user_id)
    args = context.args

    if not args:
        help_msg = (
            "ℹ️ <b>Search Syntax</b>: <code>/search [TICKER_OR_NAME]</code>\n"
            "Example: <code>/search bonk</code> or <code>/search popcat</code>"
        ) if user_lang == "en" else (
            "ℹ️ <b>صيغة البحث</b>: <code>/search [الرمز أو الاسم]</code>\n"
            "مثال: <code>/search bonk</code> أو <code>/search popcat</code>"
        )
        await update.message.reply_text(help_msg, parse_mode="HTML")
        return

    query = " ".join(args).strip()
    status_msg = await update.message.reply_text(
        t("search_prompt", user_lang, query=html.escape(query)),
        parse_mode="HTML"
    )

    mint = extract_token_mint(query)
    if not mint:
        matched = search_solana_token(query)
        if matched:
            mint = matched["mint"]

    if not mint:
        not_found_kb = [
            [InlineKeyboardButton("🔥 Explore Trending" if user_lang == "en" else "🔥 استكشاف العملات الرائجة", callback_data="btn_trending")],
            [InlineKeyboardButton(t("btn_back", user_lang), callback_data="btn_refresh")]
        ]
        await status_msg.edit_text(
            t("search_not_found", user_lang, query=html.escape(query)),
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(not_found_kb)
        )
        return

    scan = scan_token_security(mint)
    card_text = format_token_card(scan, lang=user_lang)
    await status_msg.edit_text(card_text, parse_mode="HTML", reply_markup=get_token_card_keyboard(mint, user_lang, user_id=user_id, symbol=scan.get("symbol", "TOKEN")), disable_web_page_preview=True)


async def watchlist_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /watchlist command."""
    user_id = update.effective_user.id
    user_lang = get_user_language(user_id)
    await render_watchlist(update.message, user_id, user_lang, is_edit=False)


async def track_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /track command to add a token to user's watchlist."""
    user_id = update.effective_user.id
    user_lang = get_user_language(user_id)
    args = context.args
    if not args:
        hint = "ℹ️ <b>Usage</b>: <code>/track [CA_OR_TICKER]</code>\nExample: <code>/track bonk</code>" if user_lang == "en" else "ℹ️ <b>الاستخدام</b>: <code>/track [العقد_أو_الرمز]</code>\nمثال: <code>/track bonk</code>"
        await update.message.reply_text(hint, parse_mode="HTML")
        return
    raw = " ".join(args).strip()
    mint = extract_token_mint(raw)
    sym = "TOKEN"
    if not mint:
        matched = search_solana_token(raw)
        if matched:
            mint = matched["mint"]
            sym = matched.get("symbol", "TOKEN")
    if not mint:
        err = f"❌ Could not find token: {html.escape(raw)}" if user_lang == "en" else f"❌ تعذر العثور على العملة: {html.escape(raw)}"
        await update.message.reply_text(err, parse_mode="HTML")
        return
    scan = scan_token_security(mint)
    if sym == "TOKEN":
        sym = scan.get("symbol", "TOKEN")
    current_price = float(scan.get("price_usd") or 0.0)
    add_to_watchlist(user_id, mint, sym, current_price=current_price)
    ack = f"⭐ <b>Added ${html.escape(sym)} to your Watchlist!</b>" if user_lang == "en" else f"⭐ <b>تمت إضافة ${html.escape(sym)} إلى قائمة المتابعة!</b>"
    kb = [
        [
            InlineKeyboardButton("📊 View Watchlist" if user_lang == "en" else "📊 عرض قائمة المتابعة", callback_data="btn_watchlist"),
            InlineKeyboardButton(f"⚡ Snipe ${sym}", callback_data=f"inspect_{mint}")
        ],
        [InlineKeyboardButton(t("btn_back", user_lang), callback_data="btn_refresh")]
    ]
    await update.message.reply_text(ack, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb))


async def untrack_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /untrack and /remove command to remove a token from user's watchlist."""
    user_id = update.effective_user.id
    user_lang = get_user_language(user_id)
    args = context.args
    if not args:
        hint = (
            "ℹ️ <b>Usage</b>: <code>/untrack [CA_OR_TICKER]</code>\nExample: <code>/untrack bonk</code>"
        ) if user_lang == "en" else (
            "ℹ️ <b>الاستخدام</b>: <code>/untrack [العقد_أو_الرمز]</code>\nمثال: <code>/untrack bonk</code>"
        )
        await update.message.reply_text(hint, parse_mode="HTML")
        return

    raw = " ".join(args).strip()
    if raw.lower() in ("all", "clear", "purge", "reset"):
        cleared = clear_user_watchlist(user_id)
        ack = f"🗑️ <b>Cleared all {cleared} tokens from your Watchlist!</b>" if user_lang == "en" else f"🗑️ <b>تم مسح جميع العملات ({cleared}) من قائمة المتابعة بنجاح!</b>"
        await update.message.reply_text(ack, parse_mode="HTML")
        return

    mint = extract_token_mint(raw)
    sym = raw.upper().lstrip("$")

    # Match against user's active watchlist items first
    wl = get_user_watchlist(user_id)
    matched_mint = None
    matched_sym = sym
    for item in wl:
        if mint and item["mint"].lower() == mint.lower():
            matched_mint = item["mint"]
            matched_sym = item["symbol"]
            break
        if item["symbol"].upper() == sym:
            matched_mint = item["mint"]
            matched_sym = item["symbol"]
            break

    if not matched_mint:
        if not mint:
            matched = search_solana_token(raw)
            if matched:
                mint = matched["mint"]
                matched_sym = matched.get("symbol", sym)
        matched_mint = mint

    if not matched_mint:
        err = f"❌ Could not resolve token: {html.escape(raw)}" if user_lang == "en" else f"❌ تعذر التعرف على العملة: {html.escape(raw)}"
        await update.message.reply_text(err, parse_mode="HTML")
        return

    removed = remove_from_watchlist(user_id, matched_mint)
    if removed:
        ack = f"🗑️ <b>Removed ${html.escape(matched_sym)} from your Watchlist!</b>" if user_lang == "en" else f"🗑️ <b>تمت إزالة ${html.escape(matched_sym)} من قائمة المتابعة!</b>"
    else:
        ack = f"ℹ️ Token ${html.escape(matched_sym)} is not in your watchlist." if user_lang == "en" else f"ℹ️ العملة ${html.escape(matched_sym)} ليست موجودة في قائمة المتابعة."
    await update.message.reply_text(ack, parse_mode="HTML")


async def clear_watchlist_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /clearwatchlist and /purge command: purges all tracked tokens from user watchlist."""
    user_id = update.effective_user.id
    user_lang = get_user_language(user_id)
    cleared = clear_user_watchlist(user_id)
    ack = f"🗑️ <b>Cleared all {cleared} tokens from your Watchlist!</b>" if user_lang == "en" else f"🗑️ <b>تم مسح جميع العملات ({cleared}) من قائمة المتابعة بنجاح!</b>"
    await update.message.reply_text(ack, parse_mode="HTML")


async def alerts_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /alerts command: /alerts [5|10|20|50|on|off] or interactive radar."""
    user_id = update.effective_user.id
    user_lang = get_user_language(user_id)
    args = context.args
    if args:
        sub = args[0].lower().strip().lstrip("±").rstrip("%")
        if sub in ("on", "enable", "1", "start"):
            set_price_alerts_status(user_id, True)
        elif sub in ("off", "disable", "0", "stop"):
            set_price_alerts_status(user_id, False)
        else:
            try:
                val = float(sub)
                if 1.0 <= val <= 200.0:
                    update_user_alert_threshold(user_id, val)
                    set_price_alerts_status(user_id, True)
                else:
                    err = "❌ Threshold must be between 1% and 200%." if user_lang == "en" else "❌ يجب أن تكون النسبة بين 1% و 200%."
                    await update.message.reply_text(err, parse_mode="HTML")
                    return
            except ValueError:
                err = "❌ Usage: <code>/alerts [5|10|20|50|on|off]</code>" if user_lang == "en" else "❌ طريقة الاستخدام: <code>/alerts [5|10|20|50|on|off]</code>"
                await update.message.reply_text(err, parse_mode="HTML")
                return

    await render_alerts_card(update.message, user_id, user_lang, is_edit=False)


async def buy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /buy command: /buy [CA_OR_TICKER] [AMOUNT_SOL] or /buy [AMOUNT_SOL] [CA_OR_TICKER] or /buy [CA_OR_TICKER]"""
    user = update.effective_user
    user_id = user.id
    user_lang = get_user_language(user_id)
    args = context.args

    if not args:
        help_msg = (
            "ℹ️ <b>Instant Buy Syntax</b>:\n"
            "<code>/buy [CONTRACT_OR_TICKER] [AMOUNT_SOL]</code>\n\n"
            "<b>Example:</b>\n"
            "<code>/buy DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263 0.1</code>\n"
            "<code>/buy bonk 0.05</code> or <code>/buy 0.1 bonk</code>"
        ) if user_lang == "en" else (
            "ℹ️ <b>صيغة الشراء الفوري</b>:\n"
            "<code>/buy [عنوان العقد أو الرمز] [مبلغ SOL]</code>\n\n"
            "<b>مثال:</b>\n"
            "<code>/buy DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263 0.1</code>\n"
            "<code>/buy bonk 0.05</code> أو <code>/buy 0.1 bonk</code>"
        )
        await update.message.reply_text(help_msg, parse_mode="HTML")
        return

    amount_sol = None
    raw_target = ""

    # Check if first arg is numeric amount: e.g. /buy 0.1 pepe coin
    try:
        val1 = float(args[0].strip())
        if 0.001 <= val1 <= 100.0:
            amount_sol = val1
            raw_target = " ".join(args[1:]).strip()
    except ValueError:
        pass

    # Check if last arg is numeric amount: e.g. /buy pepe coin 0.1
    if amount_sol is None and len(args) > 1:
        try:
            val_last = float(args[-1].strip())
            if 0.001 <= val_last <= 100.0:
                amount_sol = val_last
                raw_target = " ".join(args[:-1]).strip()
        except ValueError:
            pass

    # Fallback: single or multi-word token query using default buy amount: e.g. /buy pepe coin
    if amount_sol is None:
        _, auto_amt = get_auto_buy_settings(user_id)
        amount_sol = auto_amt if auto_amt > 0 else 0.1
        raw_target = " ".join(args).strip()

    if not raw_target:
        await update.message.reply_text(help_msg, parse_mode="HTML")
        return

    mint = extract_token_mint(raw_target)
    if not mint:
        matched = search_solana_token(raw_target)
        if matched:
            mint = matched["mint"]
        else:
            err = f"❌ Could not resolve token: {html.escape(raw_target)}" if user_lang == "en" else f"❌ تعذر العثور على العملة: {html.escape(raw_target)}"
            await update.message.reply_text(err, parse_mode="HTML")
            return

    pubkey, _ = get_or_create_wallet(user_id)
    bal = get_sol_balance(pubkey)
    if bal < (amount_sol + 0.005):
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
        deposit_btn_text = "💳 Deposit QR" if user_lang == "en" else "💳 رمز الإيداع QR"
        refresh_btn_text = "🔄 Refresh" if user_lang == "en" else "🔄 تحديث"
        kb = [
            [
                InlineKeyboardButton(deposit_btn_text, callback_data="btn_qr"),
                InlineKeyboardButton(refresh_btn_text, callback_data="btn_refresh")
            ]
        ]
        await update.message.reply_text(err_text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb))
        return

    prep_text = "⚡ <b>Routing best swap via Jupiter V6...</b>" if user_lang == "en" else "⚡ <b>جاري تحضير مسار الشراء عبر Jupiter...</b>"
    status_msg = await update.message.reply_text(prep_text, parse_mode="HTML")

    success, sig_or_err, out_amount, fee_sol = execute_buy_swap(user_id, mint, amount_sol, user_lang)

    if success:
        if user_lang == "en":
            success_text = (
                f"🎉 <b>Buy Swap Executed Successfully!</b> 🟢\n"
                f"━━━━━━━━━━━━━━━━━━━\n"
                f"💸 Amount: <code>{amount_sol} SOL</code>\n"
                f"🛡️ Platform Fee (1%): <code>{fee_sol:.6f} SOL</code>\n\n"
                f"🔗 <a href='https://solscan.io/tx/{sig_or_err}'>View Transaction on Solscan</a>"
            )
        else:
            success_text = (
                f"🎉 <b>تم تنفيذ صفقة الشراء بنجاح!</b> 🟢\n"
                f"━━━━━━━━━━━━━━━━━━━\n"
                f"💸 القيمة: <code>{amount_sol} SOL</code>\n"
                f"🛡️ عمولة المنصة (1%): <code>{fee_sol:.6f} SOL</code>\n\n"
                f"🔗 <a href='https://solscan.io/tx/{sig_or_err}'>عرض المعاملة على Solscan</a>"
            )
        await status_msg.edit_text(success_text, parse_mode="HTML", disable_web_page_preview=True)
    else:
        await status_msg.edit_text(f"❌ <b>Transaction failed</b>: <code>{html.escape(sig_or_err)}</code>", parse_mode="HTML")


async def price_alert_worker(application: Application):
    """
    Autonomous Background Volatility & Price Alert Worker.
    Periodically checks prices of all tokens tracked in user watchlists.
    When a price swings >= threshold_pct, automatically dispatches
    a high-impact trading alert card with 1-click Snipe buttons.
    """
    logger.info("Autonomous Price Alert Worker started.")
    await asyncio.sleep(15)
    while True:
        try:
            subscriptions = get_all_active_watchlist_subscriptions()
            if subscriptions:
                mints = list({s["token_mint"] for s in subscriptions})
                price_data = get_batch_token_prices(mints)

                now_ts = time.time()
                for sub in subscriptions:
                    user_id = sub["user_id"]
                    mint = sub["token_mint"]
                    sym = sub["symbol"]
                    last_price = float(sub["last_price_usd"] or 0.0)
                    threshold = float(sub["alert_threshold_pct"] or 10.0)
                    last_alert = float(sub["last_alert_time"] or 0.0)
                    lang = sub["language"]

                    token_info = price_data.get(mint)
                    if not token_info or token_info.get("price_usd", 0.0) <= 0:
                        continue

                    current_price = token_info["price_usd"]
                    if last_price <= 0:
                        update_watchlist_price_and_alert(user_id, mint, current_price, record_alert=False)
                        continue

                    pct_change = ((current_price - last_price) / last_price) * 100.0

                    if abs(pct_change) >= threshold and (now_ts - last_alert) >= 600:
                        emoji = "🚀" if pct_change > 0 else "🔻"
                        now_str = get_current_time_str()

                        if lang == "ar":
                            card = (
                                f"🚨 <b>تنبيه حركة وتقلبات السعر!</b> {emoji}\n"
                                f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                                f"الرمز: <b>${html.escape(sym)}</b>\n"
                                f"الحركة: <b>{emoji} {pct_change:+.1f}%</b>\n"
                                f"السعر الحالي: <code>${current_price:.6f}</code>\n"
                                f"السعر السابق: <code>${last_price:.6f}</code>\n"
                                f"العقد: <code>{mint}</code>\n\n"
                                f"💡 <i>استغل فرصة التحرك واقنص فورياً عبر الأزرار أدناه:</i>\n"
                                f"🕒 <code>{now_str}</code>"
                            )
                        else:
                            card = (
                                f"🚨 <b>PRICE & VOLATILITY ALERT!</b> {emoji}\n"
                                f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                                f"Token: <b>${html.escape(sym)}</b>\n"
                                f"Movement: <b>{emoji} {pct_change:+.1f}%</b>\n"
                                f"Current Price: <code>${current_price:.6f}</code>\n"
                                f"Previous Price: <code>${last_price:.6f}</code>\n"
                                f"Mint: <code>{mint}</code>\n\n"
                                f"💡 <i>Take action now! 1-click snipe buttons below:</i>\n"
                                f"🕒 <code>{now_str}</code>"
                            )

                        kb = [
                            [
                                InlineKeyboardButton(f"🚀 Snipe ${html.escape(sym)}", callback_data=f"inspect_{mint}"),
                                InlineKeyboardButton("📈 DexScreener", url=f"https://dexscreener.com/solana/{mint}")
                            ],
                            [
                                InlineKeyboardButton("⚡ Buy 0.1 SOL", callback_data=f"buy_{mint}_0.1"),
                                InlineKeyboardButton("⚡ Buy 0.5 SOL", callback_data=f"buy_{mint}_0.5")
                            ]
                        ]

                        try:
                            await application.bot.send_message(
                                chat_id=user_id,
                                text=card,
                                parse_mode="HTML",
                                reply_markup=InlineKeyboardMarkup(kb),
                                disable_web_page_preview=True
                            )
                            update_watchlist_price_and_alert(user_id, mint, current_price, record_alert=True)
                        except Exception as send_err:
                            logger.warning(f"Could not dispatch price alert to user {user_id}: {send_err}")
                    else:
                        update_watchlist_price_and_alert(user_id, mint, current_price, record_alert=False)

        except Exception as e:
            logger.error(f"Error in price_alert_worker: {e}")

        await asyncio.sleep(60)


async def bot_post_init(app: Application):
    """Spawns background workers and ensures English default profile description for global link previews."""
    asyncio.create_task(price_alert_worker(app))
    try:
        desc_en = (
            "⚡ Ultra-fast Solana Sniper & Trading Bot powered by Jupiter V6 & RugCheck.\n\n"
            "🎯 Sub-400ms Swaps | 1-Click Buy/Sell | Built-in RugCheck Honeypot Scanner | Trending Radar | Non-Custodial Encrypted Wallets."
        )
        short_en = "⚡ Ultra-fast Solana Sniper & Trading Bot via Jupiter V6 & RugCheck. Sub-400ms 1-click swaps & auto-audit."
        await app.bot.set_my_description(desc_en, language_code="")
        await app.bot.set_my_short_description(short_en, language_code="")
        await app.bot.set_my_description(desc_en, language_code="ar")
        await app.bot.set_my_short_description(short_en, language_code="ar")

        commands = [
            BotCommand("start", "Launch Popcorn trading cockpit"),
            BotCommand("trending", "Top Solana trending memecoins radar"),
            BotCommand("surge", "Top 24h gainers & breakout tokens"),
            BotCommand("wallet", "View balance & deposit address"),
            BotCommand("buy", "Execute instant 1-click token buy"),
            BotCommand("sell", "Sell open token positions"),
            BotCommand("pnl", "Live trading performance & PnL card"),
            BotCommand("positions", "Track active token holdings"),
            BotCommand("watchlist", "Monitor target tokens"),
            BotCommand("alerts", "Price alert notifications"),
            BotCommand("referral", "25% revenue share affiliate link"),
            BotCommand("export", "Non-custodial private key export"),
            BotCommand("settings", "Customize slippage & gas fees"),
            BotCommand("about", "Bot version & architecture specs"),
            BotCommand("quote", "Jupiter V6 swap simulation & quote"),
            BotCommand("help", "All bot commands and guide")
        ]
        await app.bot.set_my_commands(commands)
    except Exception as e:
        logger.warning(f"Could not sync bot descriptions: {e}")


def build_application(token: str) -> Application:
    """Builds the Telegram Application instance with all command and callback handlers."""
    app = Application.builder().token(token).post_init(bot_post_init).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("tour", tour_command))
    app.add_handler(CommandHandler("guide", tour_command))
    app.add_handler(CommandHandler("trending", trending_command))
    app.add_handler(CommandHandler("tokens", trending_command))
    app.add_handler(CommandHandler("coins", trending_command))
    app.add_handler(CommandHandler("hot", trending_command))

    app.add_handler(CommandHandler("surge", surge_command))
    app.add_handler(CommandHandler("gainers", surge_command))
    app.add_handler(CommandHandler("pump", surge_command))
    app.add_handler(CommandHandler("search", search_command))
    app.add_handler(CommandHandler("find", search_command))
    app.add_handler(CommandHandler("buy", buy_command))
    app.add_handler(CommandHandler("sell", sell_command))
    app.add_handler(CommandHandler("pnl", pnl_command))
    app.add_handler(CommandHandler("gas", gas_command))
    app.add_handler(CommandHandler("priority", gas_command))
    app.add_handler(CommandHandler("slippage", slippage_command))
    app.add_handler(CommandHandler("slip", slippage_command))
    app.add_handler(CommandHandler("autobuy", autobuy_command))
    app.add_handler(CommandHandler("auto", autobuy_command))
    app.add_handler(CommandHandler("presets", presets_command))
    app.add_handler(CommandHandler("preset", presets_command))
    app.add_handler(CommandHandler("quickbuy", presets_command))
    app.add_handler(CommandHandler("price", price_command))
    app.add_handler(CommandHandler("chart", price_command))
    app.add_handler(CommandHandler("p", price_command))
    app.add_handler(CommandHandler("c", price_command))
    app.add_handler(CommandHandler("quote", quote_command))
    app.add_handler(CommandHandler("sim", quote_command))
    app.add_handler(CommandHandler("simulate", quote_command))
    app.add_handler(CommandHandler("tp", tp_command))
    app.add_handler(CommandHandler("sl", sl_command))
    app.add_handler(CommandHandler("alerts", alerts_command))
    app.add_handler(CommandHandler("alert", alerts_command))
    app.add_handler(CommandHandler("ping", ping_command))
    app.add_handler(CommandHandler("speed", ping_command))
    app.add_handler(CommandHandler("network", ping_command))
    app.add_handler(CommandHandler("audit", audit_command))
    app.add_handler(CommandHandler("check", audit_command))
    app.add_handler(CommandHandler("scan", audit_command))
    app.add_handler(CommandHandler("snipe", audit_command))
    app.add_handler(CommandHandler("token", audit_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("cluster", status_command))
    app.add_handler(CommandHandler("info", status_command))
    app.add_handler(CommandHandler("fees", fees_command))
    app.add_handler(CommandHandler("fee", fees_command))
    app.add_handler(CommandHandler("referral", referral_command))
    app.add_handler(CommandHandler("wallet", wallet_command))
    app.add_handler(CommandHandler("balance", wallet_command))
    app.add_handler(CommandHandler("bal", wallet_command))
    app.add_handler(CommandHandler("qr", qr_command))
    app.add_handler(CommandHandler("deposit", qr_command))
    app.add_handler(CommandHandler("withdraw", withdraw_command))
    app.add_handler(CommandHandler("export", export_command))
    app.add_handler(CommandHandler("backup", export_command))
    app.add_handler(CommandHandler("exportkey", export_command))

    app.add_handler(CommandHandler("watchlist", watchlist_command))
    app.add_handler(CommandHandler("track", track_command))
    app.add_handler(CommandHandler("untrack", untrack_command))
    app.add_handler(CommandHandler("remove", untrack_command))
    app.add_handler(CommandHandler("clearwatchlist", clear_watchlist_command))
    app.add_handler(CommandHandler("purge", clear_watchlist_command))
    app.add_handler(CommandHandler("positions", positions_command))
    app.add_handler(CommandHandler("portfolio", positions_command))
    app.add_handler(CommandHandler("holdings", positions_command))

    app.add_handler(CommandHandler("panic", panic_command))
    app.add_handler(CommandHandler("sellall", panic_command))
    app.add_handler(CommandHandler("history", history_command))
    app.add_handler(CommandHandler("trades", history_command))
    app.add_handler(CommandHandler("csv", csv_command))
    app.add_handler(CommandHandler("tradescsv", csv_command))
    app.add_handler(CommandHandler("settings", settings_command))
    app.add_handler(CommandHandler("reset", reset_command))
    app.add_handler(CommandHandler("defaults", reset_command))
    app.add_handler(CommandHandler("version", version_command))
    app.add_handler(CommandHandler("about", version_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("cancel", cancel_command))
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

    print(f"🚀 Launching Popcorn Solana Sniper & Trading Bot {BOT_VERSION} (Bilingual Master)...")
    app = build_application(token)
    app.run_polling(drop_pending_updates=True)
