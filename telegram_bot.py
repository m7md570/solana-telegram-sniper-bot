# -*- coding: utf-8 -*-
"""
Solana Telegram Sniper & Trading Bot — Production Telegram Interface (v2.0)
High-velocity interactive trading bot with robust HTML formatting, error-resilient callbacks,
live RugCheck token auditing, 1-click buy/sell, withdrawal support, and on-chain fee distribution.
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
from typing import Optional, Dict, Any

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
    withdraw_sol
)
from rugcheck_scanner import scan_token_security, format_token_card, extract_token_mint
from jupiter_engine import (
    get_jupiter_quote,
    build_and_sign_swap_tx,
    broadcast_transaction,
    record_trade_db,
    execute_sell_swap
)

# Logging configuration
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger("SolanaSniperBot")


def get_current_time_str() -> str:
    """Returns local formatted time string for UI freshness."""
    return datetime.datetime.now().strftime("%I:%M:%S %p")


def get_main_menu_keyboard() -> InlineKeyboardMarkup:
    """Builds the main dashboard keyboard."""
    keyboard = [
        [
            InlineKeyboardButton("⚡ قنص فوري (أرسل العقد أو الرابط)", callback_data="btn_snipe_guide")
        ],
        [
            InlineKeyboardButton("💳 المحفظة والإيداع", callback_data="btn_wallet"),
            InlineKeyboardButton("💸 سحب SOL للخارج", callback_data="btn_withdraw_guide")
        ],
        [
            InlineKeyboardButton("📊 صفقاتي المفتوحة", callback_data="btn_positions"),
            InlineKeyboardButton("⚙️ إعدادات الانزلاق (Slippage)", callback_data="btn_settings")
        ],
        [
            InlineKeyboardButton("🔄 تحديث الرصيد لحظياً", callback_data="btn_refresh")
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
    """Handler for /start command."""
    user = update.effective_user
    user_id = user.id
    username = user.username or user.first_name or "المتداول"

    pubkey, is_new = get_or_create_wallet(user_id, username)
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
        f"3. سيقوم البوت بفحص أمان العملة (RugCheck) وإظهار أزرار الشراء الفوري بنقرة واحدة!\n"
    )

    await update.message.reply_text(
        welcome_text,
        parse_mode="HTML",
        reply_markup=get_main_menu_keyboard(),
        disable_web_page_preview=True
    )


async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Detects pasted token contract addresses or platform URLs and renders token card."""
    text = update.message.text.strip()
    mint = extract_token_mint(text)

    if mint:
        status_msg = await update.message.reply_text(
            "🔍 <b>جاري فحص العقد الذكي وتدقيق الأمان (RugCheck + DexScreener)...</b>",
            parse_mode="HTML"
        )

        scan = scan_token_security(mint)
        card_text = format_token_card(scan)

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
        await safe_edit_text(query, text, reply_markup=get_main_menu_keyboard())

    elif data == "btn_wallet":
        pubkey, _ = get_or_create_wallet(user_id)
        balance = get_sol_balance(pubkey)
        text = (
            f"💳 <b>إدارة المحفظة والإيداع</b> 🏦\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"📍 <b>عنوان إيداع SOL (اضغط للنسخ)</b>:\n<code>{pubkey}</code>\n\n"
            f"💰 <b>الرصيد المتاح</b>: <code>{balance:.4f} SOL</code>\n"
            f"🕒 وقت الفحص: <code>{now_str}</code>\n\n"
            f"🔗 <a href='https://solscan.io/account/{pubkey}'>عرض المحفظة على Solscan</a>\n\n"
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
        await safe_edit_text(query, f"✅ <b>تم ضبط نسبة الانزلاق إلى {new_bps/100.0}% بنجاح!</b>\n🕒 <code>{now_str}</code>", reply_markup=get_main_menu_keyboard())

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
                reply_markup=get_main_menu_keyboard()
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
    text = (
        f"💳 <b>إدارة المحفظة والإيداع</b> 🏦\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"📍 <b>عنوان إيداع SOL (اضغط للنسخ)</b>:\n<code>{pubkey}</code>\n\n"
        f"💰 <b>الرصيد المتاح</b>: <code>{balance:.4f} SOL</code>\n"
        f"🕒 وقت الفحص: <code>{now_str}</code>\n"
    )
    kb = [
        [InlineKeyboardButton("💸 سحب SOL للخارج", callback_data="btn_withdraw_guide")],
        [InlineKeyboardButton("🔑 إظهار المفتاح الخاص", callback_data="btn_export_key")],
        [InlineKeyboardButton("🔄 تحديث الرصيد", callback_data="btn_wallet")]
    ]
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb))


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
        "• <code>/start</code> - فتح لوحة التحكم وتوليد المحفظة.\n"
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

    print("🚀 جاري إطلاق بوت التيليجرام لقنص وتداول سولانا v2.0...")
    app = build_application(token)
    app.run_polling()
