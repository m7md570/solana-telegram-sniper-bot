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
from typing import Optional, Dict, Any, List, Tuple

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
    add_to_watchlist,
    remove_from_watchlist,
    get_user_watchlist,
    toggle_price_alerts,
    get_price_alerts_status,
    set_price_alerts_status,
    get_all_active_watchlist_subscriptions,
    update_watchlist_price_and_alert
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
    execute_sell_swap,
    calculate_optimal_slippage
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
            InlineKeyboardButton(t("btn_snipe_guide", lang), callback_data="btn_snipe_guide")
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
    """Builds interactive inline keyboard for audited token card with custom buy, watchlist tracking, and viral share."""
    sell_prefix = "بيع" if user_lang == "ar" else "Sell"
    track_btn_label = "⭐ " + t("btn_track", user_lang)
    custom_buy_label = "✏️ " + t("btn_custom_buy", user_lang)
    custom_sell_label = t("btn_custom_sell", user_lang)

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
            InlineKeyboardButton(track_btn_label, callback_data=f"track_{mint}"),
            InlineKeyboardButton(share_btn_label, url=tg_share_link),
            InlineKeyboardButton(t("btn_dexscreener", user_lang), url=f"https://dexscreener.com/solana/{mint}")
        ],
        [
            InlineKeyboardButton(t("btn_rugcheck", user_lang), url=f"https://rugcheck.xyz/tokens/{mint}"),
            InlineKeyboardButton(t("btn_back", user_lang), callback_data="btn_refresh")
        ]
    ])


def build_settings_card(user_id: int, user_lang: str) -> Tuple[str, InlineKeyboardMarkup]:
    """Constructs the unified trading settings interface with slippage, gas, and volatility alert toggles."""
    settings = get_user_settings(user_id)
    current_slip = settings["slippage_bps"] / 100.0
    gas_lamports = settings.get("priority_fee", 50000)
    gas_sol = gas_lamports / 1e9
    current_tp = settings.get("default_tp_pct", 50)
    current_sl = settings.get("default_sl_pct", 25)
    alerts_on = get_price_alerts_status(user_id)
    now_str = get_current_time_str()

    tier_label = (
        t("gas_tier_normal", user_lang) if gas_lamports <= 100000 else
        (t("gas_tier_turbo", user_lang) if gas_lamports <= 500000 else t("gas_tier_ultra", user_lang))
    )

    title = t("settings_title", user_lang)
    body = t("settings_body", user_lang, slippage=current_slip)
    if user_lang == "en":
        extra_info = (
            f"\n\n⚡ <b>Priority Gas:</b> <code>{gas_sol:.5f} SOL</code> ({tier_label})\n"
            f"🎯 <b>Auto Take-Profit:</b> <code>+{current_tp}%</code>\n"
            f"🛑 <b>Auto Stop-Loss:</b> <code>-{current_sl}%</code>\n"
            f"🔔 <b>Price Movement Alerts:</b> <code>{'ENABLED' if alerts_on else 'DISABLED'}</code>\n\n"
            f"Select parameters or speed tiers below:"
        )
        alerts_btn_text = "🔔 Alerts: ON (±10%)" if alerts_on else "🔕 Alerts: OFF"
    else:
        extra_info = (
            f"\n\n⚡ <b>أولوية الغاز:</b> <code>{gas_sol:.5f} SOL</code> ({tier_label})\n"
            f"🎯 <b>جني الأرباح التلقائي:</b> <code>+{current_tp}%</code>\n"
            f"🛑 <b>وقف الخسارة التلقائي:</b> <code>-{current_sl}%</code>\n"
            f"🔔 <b>تنبيهات تقلبات الأسعار:</b> <code>{'مفعلة' if alerts_on else 'معطلة'}</code>\n\n"
            f"اختر الإعدادات المناسبة لاستراتيجيتك أدناه:"
        )
        alerts_btn_text = "🔔 التنبيهات: مفعلة (±10%)" if alerts_on else "🔕 التنبيهات: معطلة"
    text = f"{title}\n━━━━━━━━━━━━━━━━━━━\n{body}{extra_info}\n🕒 <code>{now_str}</code>"

    kb = [
        [
            InlineKeyboardButton("0.5%", callback_data="slip_50"),
            InlineKeyboardButton("1.0%", callback_data="slip_100"),
            InlineKeyboardButton("2.0%", callback_data="slip_200"),
            InlineKeyboardButton("5.0%", callback_data="slip_500")
        ],
        [
            InlineKeyboardButton("⚡ Normal (50k)", callback_data="gas_50000"),
            InlineKeyboardButton("🚀 Turbo (250k)", callback_data="gas_250000"),
            InlineKeyboardButton("🏎️ Ultra (1M)", callback_data="gas_1000000")
        ],
        [
            InlineKeyboardButton("🎯 TP +25%", callback_data="tp_25"),
            InlineKeyboardButton("🎯 TP +50%", callback_data="tp_50"),
            InlineKeyboardButton("🎯 TP +100%", callback_data="tp_100")
        ],
        [
            InlineKeyboardButton("🛑 SL -15%", callback_data="sl_15"),
            InlineKeyboardButton("🛑 SL -25%", callback_data="sl_25"),
            InlineKeyboardButton("🛑 SL -50%", callback_data="sl_50")
        ],
        [
            InlineKeyboardButton(alerts_btn_text, callback_data="toggle_alerts")
        ],
        [
            InlineKeyboardButton(t("btn_lang_toggle", user_lang), callback_data="btn_toggle_lang")
        ],
        [InlineKeyboardButton(t("btn_back", user_lang), callback_data="btn_refresh")]
    ]
    return text, InlineKeyboardMarkup(kb)



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
        if hasattr(query, "edit_message_text"):
            await query.edit_message_text(text, parse_mode="HTML", reply_markup=reply_markup, disable_web_page_preview=True)
        elif hasattr(query, "edit_text"):
            await query.edit_text(text, parse_mode="HTML", reply_markup=reply_markup, disable_web_page_preview=True)
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
    share_btn_text = "📤 Share Link with Friends" if user_lang == "en" else "📤 مشاركة الرابط مع الأصدقاء"

    kb = [
        [InlineKeyboardButton(share_btn_text, url=f"https://t.me/share/url?url={ref_link}&text={share_text}")],
        [InlineKeyboardButton(t("btn_back", user_lang), callback_data="btn_refresh")]
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

                settings = get_user_settings(user_id)
                slippage = settings["slippage_bps"]
                amount_lamports = int(custom_amt * 1_000_000_000)

                quote = get_jupiter_quote(WSOL_MINT, custom_buy_mint, amount_lamports, slippage, with_fee=True)
                if not quote:
                    fail_text = "❌ <b>No liquidity route discovered on Jupiter right now.</b>" if user_lang == "en" else "❌ <b>تعذر إيجاد مسار سيولة في Jupiter حالياً.</b>"
                    await status_msg.edit_text(fail_text, parse_mode="HTML")
                    return

                keypair = get_user_keypair(user_id)
                tx_bytes = build_and_sign_swap_tx(quote, keypair, settings["priority_fee"])
                if not tx_bytes:
                    sign_err = "❌ <b>Failed to build and sign transaction offline.</b>" if user_lang == "en" else "❌ <b>فشل في بناء وتوقيع المعاملة.</b>"
                    await status_msg.edit_text(sign_err, parse_mode="HTML")
                    return

                bcast_text = "🚀 <b>Broadcasting to Solana cluster & confirming on-chain...</b>" if user_lang == "en" else "🚀 <b>جاري إرسال المعاملة إلى شبكة سولانا وتأكيد التنفيذ...</b>"
                await status_msg.edit_text(bcast_text, parse_mode="HTML")
                success, sig_or_err = broadcast_transaction(tx_bytes)

                if success:
                    out_amount = float(quote.get("outAmount", 0))
                    fee_lamports = float(quote.get("platformFee", {}).get("amount", 0))
                    record_trade_db(user_id, WSOL_MINT, custom_buy_mint, custom_amt, out_amount, fee_lamports/1e9, sig_or_err, "CONFIRMED")
                    if user_lang == "en":
                        success_text = (
                            f"🎉 <b>Custom Buy Swap Executed Successfully!</b> 🟢\n"
                            f"━━━━━━━━━━━━━━━━━━━\n"
                            f"💸 Amount: <code>{custom_amt} SOL</code>\n"
                            f"🛡️ Platform Fee (1%): <code>{fee_lamports/1e9:.6f} SOL</code>\n\n"
                            f"🔗 <a href='https://solscan.io/tx/{sig_or_err}'>View Transaction on Solscan</a>"
                        )
                    else:
                        success_text = (
                            f"🎉 <b>تم تنفيذ صفقة الشراء المخصصة بنجاح!</b> 🟢\n"
                            f"━━━━━━━━━━━━━━━━━━━\n"
                            f"💸 القيمة: <code>{custom_amt} SOL</code>\n"
                            f"🛡️ عمولة المنصة (1%): <code>{fee_lamports/1e9:.6f} SOL</code>\n\n"
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

        await status_msg.edit_text(card_text, parse_mode="HTML", reply_markup=get_token_card_keyboard(mint, user_lang, user_id=user_id, symbol=scan.get("symbol", "TOKEN")), disable_web_page_preview=True)
    else:
        # Check if user sent a token ticker or name (e.g. BONK, $POPCAT, WIF)
        clean_text = text.strip().lstrip("$")
        if 1 <= len(clean_text) <= 20 and not any(c in clean_text for c in " \t\n\r/"):
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
            "ℹ️ <b>أرسل عنوان العقد الذكي (CA) أو رمز العملة (مثل <code>BONK</code>) أو رابطها من DexScreener لبدء القنص.</b>\n\n"
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
        kb = [[InlineKeyboardButton(t("btn_back", user_lang), callback_data="btn_refresh")]]
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
            InlineKeyboardButton("🗑️ Untrack", callback_data=f"untrack_{mint}")
        ])
    text_lines.append(f"🕒 <code>{now_str}</code>")
    refresh_btn_text = "🔄 " + ("Refresh Prices" if user_lang == "en" else "تحديث الأسعار")
    kb.append([
        InlineKeyboardButton(refresh_btn_text, callback_data="btn_watchlist"),
        InlineKeyboardButton(t("btn_back", user_lang), callback_data="btn_refresh")
    ])

    full_text = "\n".join(text_lines)
    if is_edit:
        await safe_edit_text(target, full_text, reply_markup=InlineKeyboardMarkup(kb))
    else:
        await target.reply_text(full_text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb))


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
    kb = [
        [
            InlineKeyboardButton(refresh_btn_text, callback_data="btn_history"),
            InlineKeyboardButton(t("btn_back", user_lang), callback_data="btn_refresh")
        ]
    ]
    full_text = "\n".join(text_lines)
    if is_edit:
        await safe_edit_text(target, full_text, reply_markup=InlineKeyboardMarkup(kb))
    else:
        await target.reply_text(full_text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True)


async def render_surge_radar(target, user_id: int, user_lang: str, is_edit: bool = False):
    """Renders the top explosive gainers on Solana with 1-click snipe buttons."""
    tokens = get_top_gainers(limit=5)
    text = format_gainers_list(tokens, lang=user_lang)
    keyboard = []
    for tkn in tokens:
        sym = html.escape(tkn["symbol"])
        mint = tkn["mint"]
        btn_label = f"🚀 قنص ${sym} ({tkn['change_1h']:+.1f}%)" if user_lang == "ar" else f"🚀 Snipe ${sym} ({tkn['change_1h']:+.1f}%)"
        keyboard.append([
            InlineKeyboardButton(btn_label, callback_data=f"inspect_{mint}")
        ])
    refresh_label = "🔄 " + ("Refresh Gainers" if user_lang == "en" else "تحديث القائمة")
    keyboard.append([
        InlineKeyboardButton(refresh_label, callback_data="btn_surge"),
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
        kb = [[InlineKeyboardButton(t("btn_back", user_lang), callback_data="btn_refresh")]]
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
            InlineKeyboardButton(f"🔍 Inspect ${sym_escaped}", callback_data=f"inspect_{mint}"),
            InlineKeyboardButton("📈 DexScreener", url=f"https://dexscreener.com/solana/{mint}")
        ])

    sol_price_usd = batch_prices.get("So11111111111111111111111111111111111111112", {}).get("price_usd", 150.0)
    total_sol_equiv = (total_usd / sol_price_usd) if sol_price_usd > 0 else 0.0

    if user_lang == "ar":
        text_lines.append(f"💼 <b>إجمالي القيمة التقديرية</b>: <code>${total_usd:,.2f}</code> (<code>~{total_sol_equiv:.4f} SOL</code>)")
        refresh_label = "🔄 تحديث الصفقات"
    else:
        text_lines.append(f"💼 <b>Total Estimated Value</b>: <code>${total_usd:,.2f}</code> (<code>~{total_sol_equiv:.4f} SOL</code>)")
        refresh_label = "🔄 Refresh Portfolio"

    text_lines.append(f"🕒 <code>{now_str}</code>")

    kb.append([
        InlineKeyboardButton(t("btn_panic_confirm", user_lang), callback_data="btn_panic_confirm")
    ])
    kb.append([
        InlineKeyboardButton(refresh_label, callback_data="btn_positions"),
        InlineKeyboardButton(t("btn_back", user_lang), callback_data="btn_refresh")
    ])

    full_text = "\n".join(text_lines)
    if is_edit:
        await safe_edit_text(target, full_text, reply_markup=InlineKeyboardMarkup(kb))
    else:
        await target.reply_text(full_text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True)


def benchmark_network_latency() -> Dict[str, Any]:
    """Measures live round-trip latency to Solana Primary RPC and Jupiter V6 API."""
    import time
    from config import PRIMARY_RPC, JUPITER_QUOTE_API, WSOL_MINT, USDC_MINT
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

    return {
        "rpc_ms": rpc_ms,
        "rpc_ok": rpc_ok,
        "jup_ms": jup_ms,
        "jup_ok": jup_ok
    }


async def render_network_ping(target, user_id: int, user_lang: str, is_edit: bool = False):
    """Renders real-time Solana cluster latency and Jupiter routing benchmark card."""
    bench = benchmark_network_latency()
    now_str = get_current_time_str()

    rpc_ms = bench["rpc_ms"]
    jup_ms = bench["jup_ms"]

    if user_lang == "ar":
        rpc_status = "🟢 سرعة فائقة" if rpc_ms < 1000 else "🟡 معتدل"
        jup_status = "🟢 استجابة فورية" if jup_ms < 2000 else "🟡 معتدل"
    else:
        rpc_status = "🟢 Ultra-Fast" if rpc_ms < 1000 else "🟡 Normal"
        jup_status = "🟢 Sub-Second" if jup_ms < 2000 else "🟡 Normal"

    title = t("ping_title", user_lang)
    body = t("ping_body", user_lang, rpc_ms=rpc_ms, rpc_status=rpc_status, jup_ms=jup_ms, jup_status=jup_status)
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
        await safe_edit_text(target, empty_text, reply_markup=InlineKeyboardMarkup(kb))
        return

    progress_msg = (
        "🚨 <b>جاري تنفيذ تصفية الطوارئ الشاملة لجميع الصفقات...</b>\n<i>يرجى الانتظار حتى اكتمال بيع كافة العملات عبر Jupiter.</i>"
        if user_lang == "ar" else
        "🚨 <b>Executing Emergency Panic Liquidation across all open positions...</b>\n<i>Please hold while all tokens are swapped back into SOL via Jupiter.</i>"
    )
    await safe_edit_text(target, progress_msg)

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
    await safe_edit_text(target, full_text, reply_markup=InlineKeyboardMarkup(kb))


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
        tokens = get_token_accounts(pubkey)
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
                [InlineKeyboardButton("📊 عرض الصفقات المفتوحة", callback_data="btn_positions")],
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
                f"📊 <b>Open Token Holdings</b>: <code>{len(tokens)} positions</code>\n"
                f"🕒 Checked: <code>{now_str}</code>\n\n"
                f"🔗 <a href='https://solscan.io/account/{pubkey}'>View Account on Solscan</a>\n"
                f"📷 <a href='{qr_url}'>Instant QR Code Deposit</a>\n\n"
                f"⚠️ <i>Your private key is encrypted locally with AES-256 for non-custodial ownership.</i>\n"
            )
            kb = [
                [InlineKeyboardButton("📊 View Open Positions", callback_data="btn_positions")],
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
        await render_positions(query, user_id, user_lang, is_edit=True)

    elif data == "btn_panic_confirm":
        await render_panic_confirm(query, user_id, user_lang, is_edit=True)

    elif data == "btn_panic_execute":
        await execute_panic_sell_all(query, user_id, user_lang)

    elif data == "toggle_autobuy":
        new_state = toggle_auto_buy(user_id)
        _, current_amt = get_auto_buy_settings(user_id)
        state_str = ("ENABLED 🟢" if new_state else "DISABLED ⚪") if user_lang == "en" else ("مفعل 🟢" if new_state else "معطل ⚪")
        ack = t("autobuy_updated", user_lang, status=state_str, amt=current_amt)
        await query.answer(ack, show_alert=False)
        title = t("autobuy_status_title", user_lang)
        body = t("autobuy_status_body", user_lang, status=state_str, amt=current_amt)
        toggle_label = ("🔕 Disable Auto-Buy" if new_state else "🔔 Enable Auto-Buy") if user_lang == "en" else ("🔕 تعطيل الشراء التلقائي" if new_state else "🔔 تفعيل الشراء التلقائي")
        kb = [
            [InlineKeyboardButton(toggle_label, callback_data="toggle_autobuy")],
            [
                InlineKeyboardButton("0.05 SOL", callback_data="set_auto_amt_0.05"),
                InlineKeyboardButton("0.1 SOL", callback_data="set_auto_amt_0.1"),
                InlineKeyboardButton("0.5 SOL", callback_data="set_auto_amt_0.5")
            ],
            [InlineKeyboardButton(t("btn_back", user_lang), callback_data="btn_refresh")]
        ]
        await safe_edit_text(query, f"{title}\n━━━━━━━━━━━━━━━━━━━\n{body}", reply_markup=InlineKeyboardMarkup(kb))

    elif data.startswith("set_auto_amt_"):
        new_amt = float(data.replace("set_auto_amt_", ""))
        set_auto_buy_amount(user_id, new_amt)
        set_auto_buy_status(user_id, True)
        state_str = "ENABLED 🟢" if user_lang == "en" else "مفعل 🟢"
        ack = t("autobuy_updated", user_lang, status=state_str, amt=new_amt)
        await query.answer(ack, show_alert=False)
        title = t("autobuy_status_title", user_lang)
        body = t("autobuy_status_body", user_lang, status=state_str, amt=new_amt)
        toggle_label = "🔕 Disable Auto-Buy" if user_lang == "en" else "🔕 تعطيل الشراء التلقائي"
        kb = [
            [InlineKeyboardButton(toggle_label, callback_data="toggle_autobuy")],
            [
                InlineKeyboardButton("0.05 SOL", callback_data="set_auto_amt_0.05"),
                InlineKeyboardButton("0.1 SOL", callback_data="set_auto_amt_0.1"),
                InlineKeyboardButton("0.5 SOL", callback_data="set_auto_amt_0.5")
            ],
            [InlineKeyboardButton(t("btn_back", user_lang), callback_data="btn_refresh")]
        ]
        await safe_edit_text(query, f"{title}\n━━━━━━━━━━━━━━━━━━━\n{body}", reply_markup=InlineKeyboardMarkup(kb))

    elif data == "btn_watchlist":
        await render_watchlist(query, user_id, user_lang, is_edit=True)

    elif data == "btn_history":
        await render_trade_history(query, user_id, user_lang, is_edit=True)

    elif data == "btn_ping":
        await query.message.reply_chat_action("typing")
        await render_network_ping(query, user_id, user_lang, is_edit=True)

    elif data.startswith("track_"):
        mint = data.replace("track_", "", 1)
        scan = scan_token_security(mint)
        sym = scan.get("symbol", "TOKEN")
        current_price = float(scan.get("price_usd") or 0.0)
        add_to_watchlist(user_id, mint, sym, current_price=current_price)
        await query.answer(t("watchlist_added", user_lang), show_alert=False)

    elif data.startswith("untrack_"):
        mint = data.replace("untrack_", "", 1)
        remove_from_watchlist(user_id, mint)
        await query.answer(t("watchlist_removed", user_lang), show_alert=False)
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
        stats = get_user_trade_stats(user_id)
        username = user.username or user.first_name or ("Trader" if user_lang == "en" else "المتداول")
        pnl_body_text = t(
            "pnl_body",
            user_lang,
            username=html.escape(username),
            total_trades=stats["total_trades"],
            total_vol=stats["total_volume_sol"]
        )
        text = f"{t('pnl_title', user_lang)}\n{pnl_body_text}\n🕒 <code>{now_str}</code>"
        kb = [
            [
                InlineKeyboardButton(t("btn_history", user_lang), callback_data="btn_history"),
                InlineKeyboardButton(t("btn_positions", user_lang), callback_data="btn_positions")
            ],
            [
                InlineKeyboardButton(t("btn_trending", user_lang), callback_data="btn_trending"),
                InlineKeyboardButton(t("btn_back", user_lang), callback_data="btn_refresh")
            ]
        ]
        await safe_edit_text(query, text, reply_markup=InlineKeyboardMarkup(kb))

    elif data == "btn_settings":
        text, kb = build_settings_card(user_id, user_lang)
        await safe_edit_text(query, text, reply_markup=kb)

    elif data.startswith("slip_"):
        new_bps = int(data.split("_")[1])
        update_user_slippage(user_id, new_bps)
        ack = f"Slippage tolerance set to {new_bps/100.0}%" if user_lang == "en" else f"تم ضبط نسبة الانزلاق إلى {new_bps/100.0}%"
        await query.answer(ack, show_alert=False)
        text, kb = build_settings_card(user_id, user_lang)
        await safe_edit_text(query, text, reply_markup=kb)

    elif data.startswith("gas_"):
        new_lamports = int(data.split("_")[1])
        update_user_priority_fee(user_id, new_lamports)
        ack = f"Priority fee set to {new_lamports/1e9:.5f} SOL" if user_lang == "en" else f"تم ضبط رسوم أولوية الغاز إلى {new_lamports/1e9:.5f} SOL"
        await query.answer(ack, show_alert=False)
        text, kb = build_settings_card(user_id, user_lang)
        await safe_edit_text(query, text, reply_markup=kb)

    elif data.startswith("tp_"):
        new_tp = int(data.split("_")[1])
        update_user_tp(user_id, new_tp)
        ack = t("tp_updated", user_lang, pct=new_tp)
        await query.answer(ack, show_alert=False)
        text, kb = build_settings_card(user_id, user_lang)
        await safe_edit_text(query, text, reply_markup=kb)

    elif data.startswith("sl_"):
        new_sl = int(data.split("_")[1])
        update_user_sl(user_id, new_sl)
        ack = t("sl_updated", user_lang, pct=new_sl)
        await query.answer(ack, show_alert=False)
        text, kb = build_settings_card(user_id, user_lang)
        await safe_edit_text(query, text, reply_markup=kb)

    elif data == "toggle_alerts":
        new_state = toggle_price_alerts(user_id)
        state_str = ("ENABLED" if new_state else "DISABLED") if user_lang == "en" else ("مفعلة" if new_state else "معطلة")
        ack = t("alerts_toggled", user_lang, status=state_str)
        await query.answer(ack, show_alert=False)
        text, kb = build_settings_card(user_id, user_lang)
        await safe_edit_text(query, text, reply_markup=kb)

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
        help_text = (
            "ℹ️ <b>Withdrawal Syntax</b>:\n"
            "<code>/withdraw [DESTINATION_ADDRESS] [AMOUNT_SOL|all]</code>\n\n"
            "<b>Examples:</b>\n"
            "<code>/withdraw 7kz1mcQcaZhYzFUHBFHH6s5tGrDHc7gNhN5WAUyXyq5r 0.05</code>\n"
            "<code>/withdraw 7kz1mcQcaZhYzFUHBFHH6s5tGrDHc7gNhN5WAUyXyq5r all</code> (Withdraw full balance)"
        ) if user_lang == "en" else (
            "ℹ️ <b>صيغة السحب</b>:\n"
            "<code>/withdraw [عنوان_محفظتك] [المبلغ_SOL|all]</code>\n\n"
            "<b>أمثلة:</b>\n"
            "<code>/withdraw 7kz1mcQcaZhYzFUHBFHH6s5tGrDHc7gNhN5WAUyXyq5r 0.05</code>\n"
            "<code>/withdraw 7kz1mcQcaZhYzFUHBFHH6s5tGrDHc7gNhN5WAUyXyq5r all</code> (سحب كامل الرصيد المتاح)"
        )
        await update.message.reply_text(help_text, parse_mode="HTML")
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


async def wallet_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /wallet command with open token holdings preview."""
    user_id = update.effective_user.id
    user_lang = get_user_language(user_id)
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
            [InlineKeyboardButton("📊 عرض الصفقات المفتوحة", callback_data="btn_positions")],
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
            f"📊 <b>Open Token Holdings</b>: <code>{len(tokens)} positions</code>\n"
            f"🕒 Checked: <code>{now_str}</code>\n\n"
            f"🔗 <a href='https://solscan.io/account/{pubkey}'>View Account on Solscan</a>\n"
            f"📷 <a href='{qr_url}'>Instant QR Code Deposit</a>\n\n"
            f"⚠️ <i>Your private key is locally encrypted with AES-256 for non-custodial ownership.</i>\n"
        )
        kb = [
            [InlineKeyboardButton("📊 View Open Positions", callback_data="btn_positions")],
            [InlineKeyboardButton("💸 Withdraw SOL to External Wallet", callback_data="btn_withdraw_guide")],
            [InlineKeyboardButton("🔑 Export Private Key", callback_data="btn_export_key")],
            [InlineKeyboardButton("🔄 Refresh Balance", callback_data="btn_wallet")]
        ]
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True)


async def positions_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /positions command."""
    user_id = update.effective_user.id
    user_lang = get_user_language(user_id)
    await render_positions(update.message, user_id, user_lang, is_edit=False)


async def panic_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /panic and /sellall command."""
    user_id = update.effective_user.id
    user_lang = get_user_language(user_id)
    await render_panic_confirm(update.message, user_id, user_lang, is_edit=False)


async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /settings command."""
    user_id = update.effective_user.id
    user_lang = get_user_language(user_id)
    text, kb = build_settings_card(user_id, user_lang)
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=kb)


async def gas_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /gas and /priority command."""
    user_id = update.effective_user.id
    user_lang = get_user_language(user_id)
    text, kb = build_settings_card(user_id, user_lang)
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=kb)


async def slippage_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /slippage and /slip command: /slippage [PERCENT]"""
    user_id = update.effective_user.id
    user_lang = get_user_language(user_id)
    args = context.args

    if not args:
        settings = get_user_settings(user_id)
        current_pct = settings["slippage_bps"] / 100.0
        current_bps = settings["slippage_bps"]
        info_text = (
            f"🎯 <b>Current Slippage Tolerance:</b> <code>{current_pct:.2f}%</code> (<code>{current_bps} BPS</code>)\n\n"
            f"{t('slippage_syntax_help', user_lang)}"
        ) if user_lang == "en" else (
            f"🎯 <b>نسبة الانزلاق المحددة حالياً:</b> <code>{current_pct:.2f}%</code> (<code>{current_bps} BPS</code>)\n\n"
            f"{t('slippage_syntax_help', user_lang)}"
        )
        kb = [
            [
                InlineKeyboardButton("0.5%", callback_data="slip_50"),
                InlineKeyboardButton("1.0%", callback_data="slip_100"),
                InlineKeyboardButton("2.0%", callback_data="slip_200"),
                InlineKeyboardButton("5.0%", callback_data="slip_500")
            ],
            [InlineKeyboardButton(t("btn_back", user_lang), callback_data="btn_settings")]
        ]
        await update.message.reply_text(info_text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb))
        return

    try:
        val = float(args[0].strip().rstrip("%"))
        if val < 0.1 or val > 50.0:
            await update.message.reply_text(t("slippage_invalid", user_lang), parse_mode="HTML")
            return
        bps = int(val * 100)
        update_user_slippage(user_id, bps)
        msg = t("slippage_updated", user_lang, pct=val, bps=bps)
        await update.message.reply_text(msg, parse_mode="HTML")
    except ValueError:
        await update.message.reply_text(t("slippage_syntax_help", user_lang), parse_mode="HTML")


async def autobuy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /autobuy and /auto command: /autobuy [AMOUNT|on|off]"""
    user_id = update.effective_user.id
    user_lang = get_user_language(user_id)
    args = context.args

    if args:
        sub = args[0].strip().lower()
        if sub in ("off", "disable", "stop", "0"):
            set_auto_buy_status(user_id, False)
            _, current_amt = get_auto_buy_settings(user_id)
            status_label = "DISABLED ⚪" if user_lang == "en" else "معطل ⚪"
            await update.message.reply_text(t("autobuy_updated", user_lang, status=status_label, amt=current_amt), parse_mode="HTML")
            return
        elif sub in ("on", "enable", "start", "1"):
            set_auto_buy_status(user_id, True)
            _, current_amt = get_auto_buy_settings(user_id)
            status_label = "ENABLED 🟢" if user_lang == "en" else "مفعل 🟢"
            await update.message.reply_text(t("autobuy_updated", user_lang, status=status_label, amt=current_amt), parse_mode="HTML")
            return
        else:
            try:
                amt = float(sub)
                if amt < 0.005 or amt > 50.0:
                    err = "❌ Please specify an amount between 0.005 and 50 SOL." if user_lang == "en" else "❌ يرجى تحديد مبلغ بين 0.005 و 50 SOL."
                    await update.message.reply_text(err, parse_mode="HTML")
                    return
                set_auto_buy_amount(user_id, amt)
                set_auto_buy_status(user_id, True)
                status_label = "ENABLED 🟢" if user_lang == "en" else "مفعل 🟢"
                await update.message.reply_text(t("autobuy_updated", user_lang, status=status_label, amt=amt), parse_mode="HTML")
                return
            except ValueError:
                pass

    enabled, amt = get_auto_buy_settings(user_id)
    status_str = ("ENABLED 🟢" if enabled else "DISABLED ⚪") if user_lang == "en" else ("مفعل 🟢" if enabled else "معطل ⚪")
    title = t("autobuy_status_title", user_lang)
    body = t("autobuy_status_body", user_lang, status=status_str, amt=amt)
    toggle_label = ("🔕 Disable Auto-Buy" if enabled else "🔔 Enable Auto-Buy") if user_lang == "en" else ("🔕 تعطيل الشراء التلقائي" if enabled else "🔔 تفعيل الشراء التلقائي")
    kb = [
        [InlineKeyboardButton(toggle_label, callback_data="toggle_autobuy")],
        [
            InlineKeyboardButton("0.05 SOL", callback_data="set_auto_amt_0.05"),
            InlineKeyboardButton("0.1 SOL", callback_data="set_auto_amt_0.1"),
            InlineKeyboardButton("0.5 SOL", callback_data="set_auto_amt_0.5")
        ],
        [InlineKeyboardButton(t("btn_back", user_lang), callback_data="btn_refresh")]
    ]
    await update.message.reply_text(f"{title}\n━━━━━━━━━━━━━━━━━━━\n{body}", parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb))


async def price_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /price and /chart command: /price [CA_OR_TICKER]"""
    user_id = update.effective_user.id
    user_lang = get_user_language(user_id)
    args = context.args

    if not args:
        await update.message.reply_text(t("price_syntax_help", user_lang), parse_mode="HTML")
        return

    query = args[0].strip()
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

    scan = scan_token_security(mint)
    sym = html.escape(scan.get("symbol", "TOKEN"))
    name = html.escape(scan.get("name", "Unknown Token"))
    p_usd = scan.get("price_usd", 0.0)
    c24 = scan.get("price_change_24h", 0.0)
    liq = scan.get("liquidity_usd", 0.0)
    mcap = scan.get("mcap", 0.0)
    now_str = get_current_time_str()
    emoji = "📈" if c24 >= 0 else "📉"

    title = t("price_card_title", user_lang)
    if user_lang == "ar":
        card = (
            f"{title} ⚡\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"🪙 <b>{name}</b> (<code>${sym}</code>)\n"
            f"💵 <b>السعر اللحظي:</b> <code>${p_usd:.8f}</code> {emoji} <code>{c24:+.2f}%</code>\n"
            f"💎 <b>القيمة السوقية:</b> <code>${mcap:,.0f}</code>\n"
            f"💧 <b>السيولة المتاحة:</b> <code>${liq:,.0f}</code>\n"
            f"📋 <b>العقد:</b> <code>{mint}</code>\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"🕒 <code>{now_str}</code>"
        )
    else:
        card = (
            f"{title} ⚡\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"🪙 <b>{name}</b> (<code>${sym}</code>)\n"
            f"💵 <b>Current Price:</b> <code>${p_usd:.8f}</code> {emoji} <code>{c24:+.2f}%</code>\n"
            f"💎 <b>Market Cap:</b> <code>${mcap:,.0f}</code>\n"
            f"💧 <b>Liquidity:</b> <code>${liq:,.0f}</code>\n"
            f"📋 <b>CA:</b> <code>{mint}</code>\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"🕒 <code>{now_str}</code>"
        )

    kb = [
        [
            InlineKeyboardButton(f"🚀 Snipe ${sym}", callback_data=f"inspect_{mint}"),
            InlineKeyboardButton("📊 Chart", url=f"https://dexscreener.com/solana/{mint}")
        ],
        [InlineKeyboardButton(t("btn_back", user_lang), callback_data="btn_refresh")]
    ]
    await status_msg.edit_text(card, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True)


async def tp_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /tp command: /tp [PERCENT]"""
    user_id = update.effective_user.id
    user_lang = get_user_language(user_id)
    args = context.args
    if not args:
        await update.message.reply_text(t("tp_syntax_help", user_lang), parse_mode="HTML")
        return
    try:
        val = int(args[0].strip().rstrip("%"))
        if val < 5 or val > 1000:
            err = "❌ Please specify between 5% and 1000%." if user_lang == "en" else "❌ يرجى تحديد نسبة بين 5% و 1000%."
            await update.message.reply_text(err, parse_mode="HTML")
            return
        update_user_tp(user_id, val)
        await update.message.reply_text(t("tp_updated", user_lang, pct=val), parse_mode="HTML")
    except ValueError:
        await update.message.reply_text(t("tp_syntax_help", user_lang), parse_mode="HTML")


async def sl_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /sl command: /sl [PERCENT]"""
    user_id = update.effective_user.id
    user_lang = get_user_language(user_id)
    args = context.args
    if not args:
        await update.message.reply_text(t("sl_syntax_help", user_lang), parse_mode="HTML")
        return
    try:
        val = int(args[0].strip().rstrip("%"))
        if val < 5 or val > 95:
            err = "❌ Please specify between 5% and 95%." if user_lang == "en" else "❌ يرجى تحديد نسبة بين 5% و 95%."
            await update.message.reply_text(err, parse_mode="HTML")
            return
        update_user_sl(user_id, val)
        await update.message.reply_text(t("sl_updated", user_lang, pct=val), parse_mode="HTML")
    except ValueError:
        await update.message.reply_text(t("sl_syntax_help", user_lang), parse_mode="HTML")


async def sell_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /sell command: /sell [CA_OR_TICKER] [PERCENT] or /sell [PERCENT] [CA_OR_TICKER]"""
    user = update.effective_user
    user_id = user.id
    user_lang = get_user_language(user_id)
    args = context.args

    if not args:
        await update.message.reply_text(t("sell_syntax_help", user_lang), parse_mode="HTML")
        return

    raw1 = args[0].strip()
    raw2 = args[1].strip() if len(args) >= 2 else None

    # Smart detect whether raw1 is the percentage/keyword or the token target
    clean1 = raw1.rstrip("%").lower()
    is_raw1_pct = False
    pct_from_1 = 100
    if clean1 in ("all", "max"):
        is_raw1_pct = True
        pct_from_1 = 100
    elif clean1.isdigit():
        val = int(clean1)
        if 1 <= val <= 100:
            is_raw1_pct = True
            pct_from_1 = val

    if is_raw1_pct and raw2:
        raw_target = raw2
        pct = pct_from_1
    else:
        raw_target = raw1
        pct = 100
        if raw2:
            clean2 = raw2.rstrip("%").lower()
            if clean2 in ("all", "max"):
                pct = 100
            else:
                try:
                    pct_val = int(clean2)
                    if 1 <= pct_val <= 100:
                        pct = pct_val
                    else:
                        await update.message.reply_text(t("sell_invalid_pct", user_lang), parse_mode="HTML")
                        return
                except ValueError:
                    await update.message.reply_text(t("sell_invalid_pct", user_lang), parse_mode="HTML")
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
    username = user.username or user.first_name or ("Trader" if user_lang == "en" else "المتداول")
    now_str = get_current_time_str()

    stats = get_user_trade_stats(user_id)
    pnl_body_text = t(
        "pnl_body",
        user_lang,
        username=html.escape(username),
        total_trades=stats["total_trades"],
        total_vol=stats["total_volume_sol"]
    )
    text = f"{t('pnl_title', user_lang)}\n{pnl_body_text}\n🕒 <code>{now_str}</code>"
    kb = [
        [
            InlineKeyboardButton(t("btn_history", user_lang), callback_data="btn_history"),
            InlineKeyboardButton(t("btn_positions", user_lang), callback_data="btn_positions")
        ],
        [
            InlineKeyboardButton(t("btn_trending", user_lang), callback_data="btn_trending"),
            InlineKeyboardButton(t("btn_back", user_lang), callback_data="btn_refresh")
        ]
    ]
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb))


async def ping_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /ping, /speed, and /network command."""
    user_id = update.effective_user.id
    user_lang = get_user_language(user_id)
    await render_network_ping(update.message, user_id, user_lang, is_edit=False)


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

    query = args[0].strip()
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
    """Handler for /history and /trades command."""
    user_id = update.effective_user.id
    user_lang = get_user_language(user_id)
    await render_trade_history(update.message, user_id, user_lang, is_edit=False)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /help command."""
    user_id = update.effective_user.id
    user_lang = get_user_language(user_id)
    title = t("help_title", user_lang)
    body = t("help_body", user_lang)
    text = f"{title}\n{body}"
    await update.message.reply_text(text, parse_mode="HTML")


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

    matched = search_solana_token(query)
    if not matched:
        await status_msg.edit_text(
            t("search_not_found", user_lang, query=html.escape(query)),
            parse_mode="HTML"
        )
        return

    mint = matched["mint"]
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
    raw = args[0].strip()
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
    await update.message.reply_text(ack, parse_mode="HTML")


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

    raw = args[0].strip()
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


async def alerts_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /alerts command: /alerts [on|off] or interactive toggle."""
    user_id = update.effective_user.id
    user_lang = get_user_language(user_id)
    args = context.args
    if args:
        sub = args[0].lower().strip()
        if sub in ("on", "enable", "1", "start"):
            set_price_alerts_status(user_id, True)
        elif sub in ("off", "disable", "0", "stop"):
            set_price_alerts_status(user_id, False)

    status = get_price_alerts_status(user_id)
    status_str = ("ENABLED 🟢" if status else "DISABLED ⚪") if user_lang == "en" else ("مفعلة 🟢" if status else "معطلة ⚪")
    title = t("alerts_status_title", user_lang)
    body = t("alerts_status_body", user_lang, status=status_str)
    btn_toggle = ("🔕 Turn OFF Alerts" if status else "🔔 Turn ON Alerts") if user_lang == "en" else ("🔕 تعطيل التنبيهات" if status else "🔔 تفعيل التنبيهات")
    kb = [
        [InlineKeyboardButton(btn_toggle, callback_data="toggle_alerts")],
        [InlineKeyboardButton(t("btn_back", user_lang), callback_data="btn_refresh")]
    ]
    await update.message.reply_text(f"{title}\n━━━━━━━━━━━━━━━━━━━\n{body}", parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb))


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

    raw1 = args[0].strip()
    raw2 = args[1].strip() if len(args) >= 2 else None

    # Check if raw1 is numeric amount: e.g. /buy 0.1 bonk
    is_raw1_amt = False
    try:
        val1 = float(raw1)
        if 0.001 <= val1 <= 100.0:
            is_raw1_amt = True
            amt_from_1 = val1
    except ValueError:
        is_raw1_amt = False

    if is_raw1_amt and raw2:
        raw_target = raw2
        amount_sol = amt_from_1
    else:
        raw_target = raw1
        if raw2:
            try:
                amount_sol = float(raw2)
                if amount_sol <= 0:
                    raise ValueError()
            except ValueError:
                err = "❌ Invalid SOL amount. Use e.g. 0.1" if user_lang == "en" else "❌ مبلغ SOL غير صحيح، يرجى كتابة رقم مثل 0.1"
                await update.message.reply_text(err, parse_mode="HTML")
                return
        else:
            _, auto_amt = get_auto_buy_settings(user_id)
            amount_sol = auto_amt if auto_amt > 0 else 0.1

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
        await update.message.reply_text(err_text, parse_mode="HTML")
        return

    prep_text = "⚡ <b>Routing best swap via Jupiter V6...</b>" if user_lang == "en" else "⚡ <b>جاري تحضير مسار الشراء عبر Jupiter...</b>"
    status_msg = await update.message.reply_text(prep_text, parse_mode="HTML")

    settings = get_user_settings(user_id)
    slippage = settings["slippage_bps"]
    amount_lamports = int(amount_sol * 1_000_000_000)

    quote = get_jupiter_quote(WSOL_MINT, mint, amount_lamports, slippage, with_fee=True)
    if not quote:
        fail_text = "❌ <b>No liquidity route discovered on Jupiter right now.</b>" if user_lang == "en" else "❌ <b>تعذر إيجاد مسار سيولة في Jupiter حالياً.</b>"
        await status_msg.edit_text(fail_text, parse_mode="HTML")
        return

    keypair = get_user_keypair(user_id)
    tx_bytes = build_and_sign_swap_tx(quote, keypair, settings["priority_fee"])
    if not tx_bytes:
        sign_err = "❌ <b>Failed to build and sign transaction offline.</b>" if user_lang == "en" else "❌ <b>فشل في بناء وتوقيع المعاملة.</b>"
        await status_msg.edit_text(sign_err, parse_mode="HTML")
        return

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
    except Exception as e:
        logger.warning(f"Could not sync bot descriptions: {e}")


def build_application(token: str) -> Application:
    """Builds the Telegram Application instance with all command and callback handlers."""
    app = Application.builder().token(token).post_init(bot_post_init).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("trending", trending_command))
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
    app.add_handler(CommandHandler("price", price_command))
    app.add_handler(CommandHandler("chart", price_command))
    app.add_handler(CommandHandler("tp", tp_command))
    app.add_handler(CommandHandler("sl", sl_command))
    app.add_handler(CommandHandler("alerts", alerts_command))
    app.add_handler(CommandHandler("alert", alerts_command))
    app.add_handler(CommandHandler("ping", ping_command))
    app.add_handler(CommandHandler("speed", ping_command))
    app.add_handler(CommandHandler("network", ping_command))
    app.add_handler(CommandHandler("audit", audit_command))
    app.add_handler(CommandHandler("check", audit_command))
    app.add_handler(CommandHandler("referral", referral_command))
    app.add_handler(CommandHandler("wallet", wallet_command))
    app.add_handler(CommandHandler("withdraw", withdraw_command))
    app.add_handler(CommandHandler("watchlist", watchlist_command))
    app.add_handler(CommandHandler("track", track_command))
    app.add_handler(CommandHandler("untrack", untrack_command))
    app.add_handler(CommandHandler("remove", untrack_command))
    app.add_handler(CommandHandler("positions", positions_command))
    app.add_handler(CommandHandler("panic", panic_command))
    app.add_handler(CommandHandler("sellall", panic_command))
    app.add_handler(CommandHandler("history", history_command))
    app.add_handler(CommandHandler("trades", history_command))
    app.add_handler(CommandHandler("settings", settings_command))
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

    print("🚀 Launching Popcorn Solana Sniper & Trading Bot v3.1 (Bilingual Master)...")
    app = build_application(token)
    app.run_polling()
