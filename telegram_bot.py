# -*- coding: utf-8 -*-
"""
Solana Telegram Sniper & Trading Bot — Enterprise Master Interface (v3.0)
High-velocity decentralized trading bot on Solana with:
- Sub-400ms Jupiter V6 swap routing & 1.0% developer fee distribution
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
    set_auto_buy_amount
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

# Logging configuration
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger("SolanaSniperBot")


def get_current_time_str() -> str:
    """Returns local formatted time string for UI freshness."""
    return datetime.datetime.now().strftime("%I:%M:%S %p")


def get_main_menu_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """Builds the main dashboard keyboard."""
    auto_enabled, auto_amt = get_auto_buy_settings(user_id)
    auto_badge = "⚡ مفعل" if auto_enabled else "⚪ معطل"

    keyboard = [
        [
            InlineKeyboardButton("⚡ قنص فوري (أرسل العقد أو الرابط)", callback_data="btn_snipe_guide")
        ],
        [
            InlineKeyboardButton("🔥 تريند سولانا اللحظي", callback_data="btn_trending"),
            InlineKeyboardButton("💳 المحفظة والإيداع", callback_data="btn_wallet")
        ],
        [
            InlineKeyboardButton("🤝 نظام الإحالات والأرباح", callback_data="btn_referral"),
            InlineKeyboardButton("📊 صفقاتي المفتوحة", callback_data="btn_positions")
        ],
        [
            InlineKeyboardButton(f"🎯 الشراء التلقائي ({auto_badge})", callback_data="btn_autobuy_settings"),
            InlineKeyboardButton("⚙️ إعدادات الانزلاق", callback_data="btn_settings")
        ],
        [
            InlineKeyboardButton("💸 سحب SOL للخارج", callback_data="btn_withdraw_guide"),
            InlineKeyboardButton("🔄 تحديث الرصيد", callback_data="btn_refresh")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


async def safe_edit_text(query, text: str, reply_markup=None):
    """Safely edits message text while preventing 'Message is not modified' errors."""
    try:
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=reply_markup, disable_web_page_preview=True)
    except BadRequest as e:
        if "Message is not modified" in str(e):
            await query.answer("✅ الرصيد محدّث لأحدث قيمة!", show_alert=False)
        else:
            logger.warning(f"BadRequest in safe_edit_text: {e}")
    except Exception as e:
        logger.error(f"Error in safe_edit_text: {e}")


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /start command with optional referral attribution."""
    user = update.effective_user
    user_id = user.id
    username = user.username or user.first_name or "المتداول"

    pubkey, is_new = get_or_create_wallet(user_id, username)

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

    welcome_text = (
        f"⚡ <b>مرحباً بك في بوت قنص وتداول سولانا فائق السرعة!</b> 🎯\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>المتداول</b>: @{html.escape(username)}\n"
        f"💳 <b>محفظتك المخصصة (اضغط للنسخ)</b>:\n"
        f"<code>{pubkey}</code>\n\n"
        f"💰 <b>الرصيد الحالي</b>: <code>{balance:.4f} SOL</code>\n"
        f"🛡️ <b>رسوم المنصة المعتمدة</b>: <code>1.0%</code> (مقتطعة آلياً عبر Jupiter)\n"
        f"🕒 <b>وقت التحديث</b>: <code>{now_str}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💡 <b>كيف تبدأ التداول فورياً؟</b>\n"
        f"1. انسخ عنوان محفظتك أعلاه وقم بإيداع أي رصيد SOL من Phantom أو أي منصة.\n"
        f"2. الصق أي رابط أو عنوان عقد (CA) هنا مباشرة.\n"
        f"3. سيقوم البوت بفحص أمان العملة (RugCheck) وإظهار أزرار الشراء بنقرة واحدة!\n"
    )

    await update.message.reply_text(
        welcome_text,
        parse_mode="HTML",
        reply_markup=get_main_menu_keyboard(user_id),
        disable_web_page_preview=True
    )


async def trending_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /trending command."""
    status_msg = await update.message.reply_text("🔥 <b>جاري جلب أكثر عملات سولانا رواجاً وزخماً من DexScreener...</b>", parse_mode="HTML")
    tokens = get_trending_tokens(limit=5)
    text = format_trending_list(tokens)

    keyboard = []
    for t in tokens:
        sym = html.escape(t["symbol"])
        mint = t["mint"]
        keyboard.append([
            InlineKeyboardButton(f"🚀 قنص ${sym} ({t['change_24h']:+.1f}%)", callback_data=f"inspect_{mint}")
        ])
    keyboard.append([InlineKeyboardButton("🔙 العودة للرئيسية", callback_data="btn_refresh")])

    await status_msg.edit_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard), disable_web_page_preview=True)


async def referral_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /referral command."""
    user_id = update.effective_user.id
    bot_username = context.bot.username or "PopcornSniperBot"
    ref_link = f"https://t.me/{bot_username}?start=ref_{user_id}"

    stats = get_referral_stats(user_id)
    text = (
        f"🤝 <b>برنامج الإحالات والأرباح السلبية (25% Rev-Share)</b> 💰\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🔗 <b>رابط الإحالة الخاص بك (اضغط للنسخ)</b>:\n"
        f"<code>{ref_link}</code>\n\n"
        f"📊 <b>إحصائياتك</b>:\n"
        f"• عدد المتداولين المسجلين عبرك: <b>{stats['total_referrals']}</b> متداول\n"
        f"• إجمالي أرباحك من العمولات: <b>{stats['earnings_sol']:.4f} SOL</b>\n\n"
        f"💡 <b>كيف يعمل البرنامج؟</b>\n"
        f"شارك رابطك في قنوات تداول الكريبتو وتويتر ومجموعات ألفا. مع كل صفقة تداول ينفذها أي شخص يسجل عبرك، تحصل على <b>25% من رسوم البوت</b> تودع مباشرة في رصيدك مدى الحياة!\n"
    )
    kb = [
        [InlineKeyboardButton("📤 مشاركة الرابط مع الأصدقاء", url=f"https://t.me/share/url?url={ref_link}&text=⚡ أقوى بوت قنص وتداول على سولانا مع فحص RugCheck!")],
        [InlineKeyboardButton("🔙 العودة للرئيسية", callback_data="btn_refresh")]
    ]
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True)


async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Detects pasted token contract addresses or platform URLs and renders token card."""
    user_id = update.effective_user.id
    text = update.message.text.strip()
    mint = extract_token_mint(text)

    if mint:
        status_msg = await update.message.reply_text(
            "🔍 <b>جاري فحص العقد الذكي وتدقيق الأمان (RugCheck + DexScreener)...</b>",
            parse_mode="HTML"
        )

        scan = scan_token_security(mint)
        card_text = format_token_card(scan)

        # Check if Auto-Buy is active
        auto_enabled, auto_amt = get_auto_buy_settings(user_id)
        if auto_enabled and scan["status"] == "SAFE":
            pubkey, _ = get_or_create_wallet(user_id)
            bal = get_sol_balance(pubkey)
            if bal >= (auto_amt + 0.005):
                await status_msg.edit_text(f"⚡ <b>تم رصد العقد! جاري تنفيذ القنص التلقائي الفوري بمبلغ {auto_amt} SOL...</b>", parse_mode="HTML")
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
                            success_text = (
                                f"🎯 <b>تم القنص التلقائي (Auto-Buy) بنجاح!</b> 🟢\n"
                                f"━━━━━━━━━━━━━━━━━━━\n"
                                f"💸 القيمة: <code>{auto_amt} SOL</code>\n"
                                f"🪙 العملة: <b>${html.escape(scan['symbol'])}</b>\n\n"
                                f"🔗 <a href='https://solscan.io/tx/{sig_or_err}'>عرض المعاملة على Solscan</a>"
                            )
                            await status_msg.edit_text(success_text, parse_mode="HTML", disable_web_page_preview=True)
                            return

        # Inline action keyboard
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
                InlineKeyboardButton("🔴 بيع 25%", callback_data=f"sell_{mint}_25"),
                InlineKeyboardButton("🔴 بيع 50%", callback_data=f"sell_{mint}_50"),
                InlineKeyboardButton("🔴 بيع 100%", callback_data=f"sell_{mint}_100")
            ],
            [
                InlineKeyboardButton("📊 شارت DexScreener", url=f"https://dexscreener.com/solana/{mint}"),
                InlineKeyboardButton("🛡️ تقرير RugCheck", url=f"https://rugcheck.xyz/tokens/{mint}")
            ],
            [
                InlineKeyboardButton("🔙 العودة للرئيسية", callback_data="btn_refresh")
            ]
        ]

        await status_msg.edit_text(card_text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard), disable_web_page_preview=True)
    else:
        await update.message.reply_text(
            "ℹ️ <b>أرسل عنوان العقد الذكي (CA) أو رابط العملة من DexScreener / Pump.fun لبدء القنص.</b>\n\n"
            "مثال: <code>DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263</code> (BONK)",
            parse_mode="HTML"
        )


async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles all inline button clicks."""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    data = query.data
    now_str = get_current_time_str()

    if data == "btn_refresh":
        pubkey, _ = get_or_create_wallet(user_id)
        balance = get_sol_balance(pubkey)
        text = (
            f"🔄 <b>تم تحديث الرصيد لحظياً!</b>\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"💳 المحفظة: <code>{pubkey}</code>\n"
            f"💰 الرصيد المتاح: <code>{balance:.4f} SOL</code>\n"
            f"🕒 آخر تحديث: <code>{now_str}</code>\n"
        )
        await safe_edit_text(query, text, reply_markup=get_main_menu_keyboard(user_id))

    elif data == "btn_trending":
        await query.message.reply_chat_action("typing")
        tokens = get_trending_tokens(limit=5)
        text = format_trending_list(tokens)
        keyboard = []
        for t in tokens:
            sym = html.escape(t["symbol"])
            mint = t["mint"]
            keyboard.append([
                InlineKeyboardButton(f"🚀 قنص ${sym} ({t['change_24h']:+.1f}%)", callback_data=f"inspect_{mint}")
            ])
        keyboard.append([InlineKeyboardButton("🔙 العودة للرئيسية", callback_data="btn_refresh")])
        await safe_edit_text(query, text, reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("inspect_"):
        mint = data.split("_")[1]
        await query.message.reply_chat_action("typing")
        scan = scan_token_security(mint)
        card_text = format_token_card(scan)
        keyboard = [
            [
                InlineKeyboardButton("🟢 0.1 SOL", callback_data=f"buy_{mint}_0.1"),
                InlineKeyboardButton("🟢 0.5 SOL", callback_data=f"buy_{mint}_0.5"),
                InlineKeyboardButton("🟢 1.0 SOL", callback_data=f"buy_{mint}_1.0")
            ],
            [
                InlineKeyboardButton("🔴 بيع 50%", callback_data=f"sell_{mint}_50"),
                InlineKeyboardButton("🔴 بيع 100%", callback_data=f"sell_{mint}_100")
            ],
            [
                InlineKeyboardButton("📊 DexScreener", url=f"https://dexscreener.com/solana/{mint}"),
                InlineKeyboardButton("🛡️ RugCheck", url=f"https://rugcheck.xyz/tokens/{mint}")
            ],
            [InlineKeyboardButton("🔙 رجوع لقائمة التريند", callback_data="btn_trending")]
        ]
        await safe_edit_text(query, card_text, reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "btn_referral":
        bot_username = context.bot.username or "PopcornSniperBot"
        ref_link = f"https://t.me/{bot_username}?start=ref_{user_id}"
        stats = get_referral_stats(user_id)
        text = (
            f"🤝 <b>برنامج الإحالات والأرباح السلبية (25% Rev-Share)</b> 💰\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🔗 <b>رابط الإحالة الخاص بك (اضغط للنسخ)</b>:\n"
            f"<code>{ref_link}</code>\n\n"
            f"📊 <b>إحصائياتك</b>:\n"
            f"• عدد المتداولين المسجلين عبرك: <b>{stats['total_referrals']}</b> متداول\n"
            f"• إجمالي أرباحك: <b>{stats['earnings_sol']:.4f} SOL</b>\n\n"
            f"💡 شارك رابطك واربح 25% من رسوم كل صفقة تداول ينفذها أصدقاؤك مدى الحياة!\n"
        )
        kb = [
            [InlineKeyboardButton("📤 إرسال ومشاركة الرابط", url=f"https://t.me/share/url?url={ref_link}&text=⚡ أقوى بوت تداول وقنص على سولانا مع فحص RugCheck!")],
            [InlineKeyboardButton("🔙 العودة للرئيسية", callback_data="btn_refresh")]
        ]
        await safe_edit_text(query, text, reply_markup=InlineKeyboardMarkup(kb))

    elif data == "btn_autobuy_settings":
        auto_enabled, auto_amt = get_auto_buy_settings(user_id)
        status_label = "🟢 مفعل حالياً" if auto_enabled else "🔴 معطل حالياً"
        text = (
            f"🎯 <b>إعدادات القنص والشراء التلقائي (Auto-Snipe)</b> ⚡\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"• الحالة: <b>{status_label}</b>\n"
            f"• مبلغ الشراء الافتراضي: <code>{auto_amt} SOL</code>\n\n"
            f"💡 <i>عند التفعيل: بمجرد إرسال أي عقد عملة آمن (RugCheck Score &lt; 400)، يقوم البوت بشرائها فوراً دون انتظار الضغط على الأزرار!</i>\n"
        )
        toggle_label = "🔴 تعطيل القنص التلقائي" if auto_enabled else "🟢 تفعيل القنص التلقائي"
        kb = [
            [InlineKeyboardButton(toggle_label, callback_data="btn_toggle_autobuy")],
            [
                InlineKeyboardButton("0.05 SOL", callback_data="set_auto_0.05"),
                InlineKeyboardButton("0.1 SOL", callback_data="set_auto_0.1"),
                InlineKeyboardButton("0.25 SOL", callback_data="set_auto_0.25"),
                InlineKeyboardButton("0.5 SOL", callback_data="set_auto_0.5")
            ],
            [InlineKeyboardButton("🔙 رجوع", callback_data="btn_refresh")]
        ]
        await safe_edit_text(query, text, reply_markup=InlineKeyboardMarkup(kb))

    elif data == "btn_toggle_autobuy":
        new_state = toggle_auto_buy(user_id)
        state_str = "🟢 تم تفعيل القنص التلقائي!" if new_state else "🔴 تم تعطيل القنص التلقائي!"
        await query.answer(state_str, show_alert=True)
        # Refresh autobuy menu
        auto_enabled, auto_amt = get_auto_buy_settings(user_id)
        status_label = "🟢 مفعل حالياً" if auto_enabled else "🔴 معطل حالياً"
        text = (
            f"🎯 <b>إعدادات القنص والشراء التلقائي (Auto-Snipe)</b> ⚡\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"• الحالة: <b>{status_label}</b>\n"
            f"• مبلغ الشراء الافتراضي: <code>{auto_amt} SOL</code>\n"
        )
        toggle_label = "🔴 تعطيل القنص التلقائي" if auto_enabled else "🟢 تفعيل القنص التلقائي"
        kb = [
            [InlineKeyboardButton(toggle_label, callback_data="btn_toggle_autobuy")],
            [InlineKeyboardButton("🔙 رجوع", callback_data="btn_refresh")]
        ]
        await safe_edit_text(query, text, reply_markup=InlineKeyboardMarkup(kb))

    elif data.startswith("set_auto_"):
        amt = float(data.split("_")[2])
        set_auto_buy_amount(user_id, amt)
        await query.answer(f"✅ تم ضبط مبلغ الشراء التلقائي إلى {amt} SOL!", show_alert=True)
        await safe_edit_text(query, f"✅ <b>تم حفظ مبلغ الشراء التلقائي: {amt} SOL</b>", reply_markup=get_main_menu_keyboard(user_id))

    elif data == "btn_wallet":
        pubkey, _ = get_or_create_wallet(user_id)
        balance = get_sol_balance(pubkey)
        qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=250x250&data=solana:{pubkey}"
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
        await safe_edit_text(query, text, reply_markup=InlineKeyboardMarkup(kb))

    elif data == "btn_withdraw_guide":
        pubkey, _ = get_or_create_wallet(user_id)
        bal = get_sol_balance(pubkey)
        text = (
            f"💸 <b>سحب رصيد SOL إلى محفظتك الخارجية</b> 🚀\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"💰 رصيدك المتاح للسحب: <code>{bal:.4f} SOL</code>\n\n"
            f"لسحب أي مبلغ لمحفظتك في Phantom أو منصة التداول، أرسل الأمر بالصيغة:\n"
            f"<code>/withdraw [العنوان] [المبلغ]</code>\n\n"
            f"<b>مثال:</b>\n"
            f"<code>/withdraw 7kz1mcQcaZhYzFUHBFHH6s5tGrDHc7gNhN5WAUyXyq5r 0.1</code>\n"
        )
        kb = [[InlineKeyboardButton("🔙 رجوع", callback_data="btn_wallet")]]
        await safe_edit_text(query, text, reply_markup=InlineKeyboardMarkup(kb))

    elif data == "btn_export_key":
        p_key = export_private_key_b58(user_id)
        text = (
            f"🚨 <b>تحذير أمني شديد</b>: لا تشارك هذا المفتاح مع أي شخص أبداً!\n\n"
            f"🔑 <b>المفتاح الخاص (Base58)</b>:\n"
            f"<code>{p_key}</code>\n\n"
            f"يمكنك نسخه واستيراده في محفظة Phantom أو Solflare في أي وقت."
        )
        kb = [[InlineKeyboardButton("🔙 رجوع وإخفاء المفتاح", callback_data="btn_wallet")]]
        await safe_edit_text(query, text, reply_markup=InlineKeyboardMarkup(kb))

    elif data == "btn_positions":
        pubkey, _ = get_or_create_wallet(user_id)
        tokens = get_token_accounts(pubkey)
        if not tokens:
            text = f"📊 <b>لا توجد رموز مشتراة حالياً في محفظتك.</b>\n🕒 التحديث: <code>{now_str}</code>"
        else:
            text = f"📊 <b>الرموز المفتوحة في محفظتك</b>:\n━━━━━━━━━━━━━━━━━━━\n"
            for t in tokens:
                text += f"• <code>{t['mint'][:6]}...{t['mint'][-4:]}</code>: <b>{t['amount']:,.2f}</b> رمز\n"
            text += f"\n🕒 التحديث: <code>{now_str}</code>"
        kb = [[InlineKeyboardButton("🔙 رجوع", callback_data="btn_refresh")]]
        await safe_edit_text(query, text, reply_markup=InlineKeyboardMarkup(kb))

    elif data == "btn_settings":
        settings = get_user_settings(user_id)
        current_slip = settings["slippage_bps"] / 100.0
        text = (
            f"⚙️ <b>إعدادات التداول والانزلاق (Slippage)</b>\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"🎯 الانزلاق الحالي: <code>{current_slip}%</code>\n"
            f"🕒 التحديث: <code>{now_str}</code>\n\n"
            f"اختر نسبة الانزلاق المناسبة لقنص العملات السريعة:"
        )
        kb = [
            [
                InlineKeyboardButton("0.5%", callback_data="slip_50"),
                InlineKeyboardButton("1.0%", callback_data="slip_100"),
                InlineKeyboardButton("2.0%", callback_data="slip_200"),
                InlineKeyboardButton("5.0%", callback_data="slip_500")
            ],
            [InlineKeyboardButton("🔙 رجوع", callback_data="btn_refresh")]
        ]
        await safe_edit_text(query, text, reply_markup=InlineKeyboardMarkup(kb))

    elif data.startswith("slip_"):
        new_bps = int(data.split("_")[1])
        update_user_slippage(user_id, new_bps)
        await safe_edit_text(query, f"✅ <b>تم ضبط نسبة الانزلاق إلى {new_bps/100.0}% بنجاح!</b>\n🕒 <code>{now_str}</code>", reply_markup=get_main_menu_keyboard(user_id))

    elif data == "btn_snipe_guide":
        text = (
            "🎯 <b>دليل القنص والشراء الفوري</b> ⚡\n"
            "━━━━━━━━━━━━━━━━━━━\n"
            "1. افتح أي منصة تداول (DexScreener, Pump.fun, Photon, X).\n"
            "2. انسخ عنوان العقد الذكي للعملة (CA) أو رابط الصفحة بالكامل.\n"
            "3. الصق العنوان هنا في المحادثة مباشرة.\n"
            "4. سيقوم البوت فوراً بفحص الأمان (RugCheck) وإظهار أزرار الشراء الفوري بنقرة واحدة!\n"
        )
        kb = [[InlineKeyboardButton("🔙 رجوع", callback_data="btn_refresh")]]
        await safe_edit_text(query, text, reply_markup=InlineKeyboardMarkup(kb))

    elif data.startswith("buy_"):
        parts = data.split("_")
        mint = parts[1]
        amount_sol = float(parts[2])

        pubkey, _ = get_or_create_wallet(user_id)
        bal = get_sol_balance(pubkey)

        if bal < (amount_sol + 0.005):  # Gas buffer
            await safe_edit_text(
                query,
                f"❌ <b>رصيد SOL غير كافٍ!</b>\n"
                f"المطلوب: <code>{amount_sol} SOL</code> (+ رسوم الغاز)\n"
                f"الرصيد المتاح: <code>{bal:.4f} SOL</code>\n\n"
                f"يرجى إيداع SOL في محفظتك:\n<code>{pubkey}</code>",
                reply_markup=get_main_menu_keyboard(user_id)
            )
            return

        status_msg = await query.message.reply_text("⚡ <b>جاري تحضير مسار الشراء وحساب العمولة عبر Jupiter...</b>", parse_mode="HTML")

        settings = get_user_settings(user_id)
        slippage = settings["slippage_bps"]
        amount_lamports = int(amount_sol * 1_000_000_000)

        # 1. Fetch Quote
        quote = get_jupiter_quote(WSOL_MINT, mint, amount_lamports, slippage, with_fee=True)
        if not quote:
            await status_msg.edit_text("❌ <b>تعذر إيجاد مسار سيولة أو زوج تداول في Jupiter حالياً.</b>", parse_mode="HTML")
            return

        # 2. Build & Sign
        keypair = get_user_keypair(user_id)
        tx_bytes = build_and_sign_swap_tx(quote, keypair, settings["priority_fee"])
        if not tx_bytes:
            await status_msg.edit_text("❌ <b>فشل في بناء وتوقيع المعاملة الذكية.</b>", parse_mode="HTML")
            return

        # 3. Broadcast
        await status_msg.edit_text("🚀 <b>جاري إرسال المعاملة إلى شبكة سولانا وتأكيد التنفيذ...</b>", parse_mode="HTML")
        success, sig_or_err = broadcast_transaction(tx_bytes)

        if success:
            out_amount = float(quote.get("outAmount", 0))
            fee_lamports = float(quote.get("platformFee", {}).get("amount", 0))
            record_trade_db(user_id, WSOL_MINT, mint, amount_sol, out_amount, fee_lamports/1e9, sig_or_err, "CONFIRMED")
            success_text = (
                f"🎉 <b>تم تنفيذ صفقة الشراء بنجاح!</b> 🟢\n"
                f"━━━━━━━━━━━━━━━━━━━\n"
                f"💸 القيمة: <code>{amount_sol} SOL</code>\n"
                f"🛡️ عمولة المطور (1%): <code>{fee_lamports/1e9:.6f} SOL</code>\n\n"
                f"🔗 <a href='https://solscan.io/tx/{sig_or_err}'>عرض المعاملة على Solscan</a>"
            )
            await status_msg.edit_text(success_text, parse_mode="HTML", disable_web_page_preview=True)
        else:
            await status_msg.edit_text(f"❌ <b>فشل في إرسال المعاملة</b>: <code>{html.escape(sig_or_err)}</code>", parse_mode="HTML")

    elif data.startswith("sell_"):
        parts = data.split("_")
        mint = parts[1]
        pct = int(parts[2])

        status_msg = await query.message.reply_text(
            f"⚡ <b>جاري تنفيذ بيع {pct}% من العملة عبر Jupiter Swap...</b>",
            parse_mode="HTML"
        )

        success, sig_or_err, sol_received = execute_sell_swap(user_id, mint, pct)
        if success:
            text = (
                f"🎉 <b>تم تنفيذ صفقة البيع بنجاح!</b> 🔴\n"
                f"━━━━━━━━━━━━━━━━━━━\n"
                f"💰 تم استلام: <code>{sol_received:.4f} SOL</code> في محفظتك\n\n"
                f"🔗 <a href='https://solscan.io/tx/{sig_or_err}'>عرض المعاملة على Solscan</a>"
            )
            await status_msg.edit_text(text, parse_mode="HTML", disable_web_page_preview=True)
        else:
            await status_msg.edit_text(f"❌ <b>فشل في البيع</b>: <code>{html.escape(sig_or_err)}</code>", parse_mode="HTML")


async def withdraw_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /withdraw command."""
    user_id = update.effective_user.id
    args = context.args

    if len(args) < 2:
        await update.message.reply_text(
            "ℹ️ <b>صيغة السحب</b>:\n"
            "<code>/withdraw [عنوان_محفظتك] [المبلغ_SOL]</code>\n\n"
            "<b>مثال:</b>\n"
            "<code>/withdraw 7kz1mcQcaZhYzFUHBFHH6s5tGrDHc7gNhN5WAUyXyq5r 0.05</code>",
            parse_mode="HTML"
        )
        return

    dest_address = args[0].strip()
    try:
        amount_sol = float(args[1].strip())
    except ValueError:
        await update.message.reply_text("❌ المبلغ المدخل غير صحيح، يرجى كتابة رقم صالح مثل 0.1", parse_mode="HTML")
        return

    status_msg = await update.message.reply_text("⚡ <b>جاري تحضير وتوقيع معاملة السحب على شبكة سولانا...</b>", parse_mode="HTML")
    success, sig_or_err = withdraw_sol(user_id, dest_address, amount_sol)

    if success:
        text = (
            f"🎉 <b>تم سحب {amount_sol} SOL بنجاح!</b> 💸\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"📍 المحفظة المستلمة: <code>{dest_address}</code>\n\n"
            f"🔗 <a href='https://solscan.io/tx/{sig_or_err}'>عرض المعاملة على Solscan</a>"
        )
        await status_msg.edit_text(text, parse_mode="HTML", disable_web_page_preview=True)
    else:
        await status_msg.edit_text(f"❌ <b>فشل السحب</b>: <code>{html.escape(sig_or_err)}</code>", parse_mode="HTML")


async def wallet_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /wallet command."""
    user_id = update.effective_user.id
    pubkey, _ = get_or_create_wallet(user_id)
    balance = get_sol_balance(pubkey)
    now_str = get_current_time_str()
    qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=250x250&data=solana:{pubkey}"
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
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True)


async def positions_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /positions command."""
    user_id = update.effective_user.id
    pubkey, _ = get_or_create_wallet(user_id)
    tokens = get_token_accounts(pubkey)
    now_str = get_current_time_str()
    if not tokens:
        text = f"📊 <b>لا توجد رموز مشتراة حالياً في محفظتك.</b>\n🕒 <code>{now_str}</code>"
    else:
        text = f"📊 <b>الرموز المفتوحة في محفظتك</b>:\n━━━━━━━━━━━━━━━━━━━\n"
        for t in tokens:
            text += f"• <code>{t['mint'][:6]}...{t['mint'][-4:]}</code>: <b>{t['amount']:,.2f}</b> رمز\n"
        text += f"\n🕒 <code>{now_str}</code>"
    await update.message.reply_text(text, parse_mode="HTML")


async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /settings command."""
    user_id = update.effective_user.id
    settings = get_user_settings(user_id)
    current_slip = settings["slippage_bps"] / 100.0
    now_str = get_current_time_str()
    text = (
        f"⚙️ <b>إعدادات التداول والانزلاق (Slippage)</b>\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"🎯 الانزلاق الحالي: <code>{current_slip}%</code>\n"
        f"🕒 التحديث: <code>{now_str}</code>\n\n"
        f"اختر نسبة الانزلاق المناسبة:"
    )
    kb = [
        [
            InlineKeyboardButton("0.5%", callback_data="slip_50"),
            InlineKeyboardButton("1.0%", callback_data="slip_100"),
            InlineKeyboardButton("2.0%", callback_data="slip_200"),
            InlineKeyboardButton("5.0%", callback_data="slip_500")
        ]
    ]
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb))


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /help command."""
    text = (
        "❓ <b>دليل استخدام بوت قنص وتداول سولانا</b> ⚡\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "• <code>/start</code> - فتح لوحة التحكم الرئيسية.\n"
        "• <code>/trending</code> - عرض أكثر عملات سولانا رواجاً وزخماً.\n"
        "• <code>/referral</code> - رابط الإحالة ومكافآت دعوة الأصدقاء (25%).\n"
        "• <code>/wallet</code> - عرض المحفظة والإيداع وتصدير المفاتيح.\n"
        "• <code>/withdraw [العنوان] [المبلغ]</code> - سحب رصيد SOL إلى محفظتك الخارجية.\n"
        "• <code>/positions</code> - عرض صفقاتك والعملات المفتوحة.\n"
        "• <code>/settings</code> - ضبط نسبة الانزلاق (Slippage).\n\n"
        "💡 <b>للقنص الفوري</b>: الصق عنوان أي عملة أو رابط DexScreener هنا مباشرة!"
    )
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
        print("⚠️ يرجى تزويد TELEGRAM_BOT_TOKEN لتشغيل البوت على الشبكة.")
        print("💡 يمكنك تشغيل وضع الاختبار التلقائي عبر: py test_bot.py")
        sys.exit(0)

    print("🚀 جاري إطلاق بوت التيليجرام لقنص وتداول سولانا v3.0 (Enterprise Master)...")
    app = build_application(token)
    app.run_polling()
