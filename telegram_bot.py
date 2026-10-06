# -*- coding: utf-8 -*-
"""
Solana Telegram Sniper & Trading Bot — Telegram Interface
High-velocity interactive trading bot with inline keyboards, 1-click buy/sell,
RugCheck security integration, and on-chain developer fee routing.
"""

import os
import sys
import asyncio
import logging
from typing import Optional
import re

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
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
    get_token_accounts
)
from rugcheck_scanner import scan_token_security, format_token_card
from jupiter_engine import (
    get_jupiter_quote,
    build_and_sign_swap_tx,
    broadcast_transaction,
    record_trade_db
)

# Logging configuration
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger("SolanaSniperBot")

# Regex pattern for Solana Base58 addresses (32-44 characters)
SOLANA_ADDRESS_REGEX = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")


def get_main_menu_keyboard() -> InlineKeyboardMarkup:
    """Builds the main dashboard keyboard."""
    keyboard = [
        [
            InlineKeyboardButton("⚡ قنص فوري (أرسل العقد CA)", callback_data="btn_snipe_guide")
        ],
        [
            InlineKeyboardButton("💳 المحفظة والإيداع", callback_data="btn_wallet"),
            InlineKeyboardButton("📊 صفقاتي المفتوحة", callback_data="btn_positions")
        ],
        [
            InlineKeyboardButton("⚙️ إعدادات الانزلاق (Slippage)", callback_data="btn_settings"),
            InlineKeyboardButton("🔄 تحديث الرصيد", callback_data="btn_refresh")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /start command."""
    user = update.effective_user
    user_id = user.id
    username = user.username or user.first_name

    pubkey, is_new = get_or_create_wallet(user_id, username)
    balance = get_sol_balance(pubkey)

    welcome_text = (
        f"⚡ *مرحباً بك في بوت قنص وتداول سولانا فائق السرعة!* 🎯\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 *المتداول*: @{username}\n"
        f"💳 *محفظتك المخصصة*:\n"
        f"`{pubkey}`\n\n"
        f"💰 *الرصيد الحالي*: `{balance:.4f} SOL`\n"
        f"🛡️ *رسوم المنصة المعتمدة*: `1.0%` (مقتطعة آلياً عبر Jupiter)\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💡 *كيف تبدأ التداول فورياً؟*\n"
        f"1. انسخ عنوان محفظتك أعلاه وقم بإيداع أي مبلغ SOL.\n"
        f"2. الصق أي عنوان عملة (Contract Address) هنا مباشرة.\n"
        f"3. سيقوم البوت بفحص العملة (RugCheck) وإظهار أزرار الشراء الفوري بنقرة واحدة!\n"
    )

    await update.message.reply_text(
        welcome_text,
        parse_mode="Markdown",
        reply_markup=get_main_menu_keyboard()
    )


async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Detects pasted token contract addresses and renders the token card."""
    text = update.message.text.strip()

    # Check if text is a Solana Token Address
    if SOLANA_ADDRESS_REGEX.match(text):
        mint = text
        status_msg = await update.message.reply_text("🔍 *جاري فحص العقد الذكي وتدقيق الأمان (RugCheck + DexScreener)...*", parse_mode="Markdown")

        scan = scan_token_security(mint)
        card_text = format_token_card(scan)

        # Inline action keyboard
        keyboard = [
            [
                InlineKeyboardButton("🟢 شراء 0.1 SOL", callback_data=f"buy_{mint}_0.1"),
                InlineKeyboardButton("🟢 شراء 0.5 SOL", callback_data=f"buy_{mint}_0.5"),
                InlineKeyboardButton("🟢 شراء 1.0 SOL", callback_data=f"buy_{mint}_1.0")
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
                InlineKeyboardButton("🔙 العودة للقائمة الرئيسية", callback_data="btn_refresh")
            ]
        ]

        await status_msg.edit_text(card_text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text(
            "ℹ️ *أرسل عنوان العقد الذكي (Token CA) للعملة لبدء القنص والشراء الفوري.*\n"
            "مثال: `DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263` (BONK)",
            parse_mode="Markdown"
        )


async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles all inline button clicks."""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    data = query.data

    if data == "btn_refresh":
        pubkey, _ = get_or_create_wallet(user_id)
        balance = get_sol_balance(pubkey)
        text = (
            f"🔄 *تم تحديث البيانات لحظياً!*\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"💳 المحفظة: `{pubkey}`\n"
            f"💰 الرصيد: `{balance:.4f} SOL`\n"
        )
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=get_main_menu_keyboard())

    elif data == "btn_wallet":
        pubkey, _ = get_or_create_wallet(user_id)
        balance = get_sol_balance(pubkey)
        text = (
            f"💳 *إدارة المحفظة والإيداع* 🏦\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"📍 *عنوان إيداع SOL*:\n`{pubkey}`\n\n"
            f"💰 *الرصيد المتاح*: `{balance:.4f} SOL`\n\n"
            f"⚠️ *ملاحظة أمنية*: مفتاحك الخاص مشفر محلياً بنظام AES-256.\n"
        )
        kb = [
            [InlineKeyboardButton("🔑 إظهار المفتاح الخاص (Private Key)", callback_data="btn_export_key")],
            [InlineKeyboardButton("🔙 رجوع", callback_data="btn_refresh")]
        ]
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

    elif data == "btn_export_key":
        p_key = export_private_key_b58(user_id)
        text = (
            f"🚨 *تحذير أمني شديد*: لا تشارك هذا المفتاح مع أي شخص أبداً!\n\n"
            f"🔑 *المفتاح الخاص (Base58)*:\n"
            f"`{p_key}`\n\n"
            f"يمكنك نسخه واستيراده في محفظة Phantom أو Solflare."
        )
        kb = [[InlineKeyboardButton("🔙 رجوع ومسح الشاشة", callback_data="btn_refresh")]]
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

    elif data == "btn_positions":
        pubkey, _ = get_or_create_wallet(user_id)
        tokens = get_token_accounts(pubkey)
        if not tokens:
            text = "📊 *لا توجد صفقات أو عملات مشتراة حالياً في محفظتك.*"
        else:
            text = "📊 *العملات المفتوحة في محفظتك*:\n━━━━━━━━━━━━━━━━━━━\n"
            for t in tokens:
                text += f"• `{t['mint'][:6]}...{t['mint'][-4:]}`: `{t['amount']:,.2f}` رمز\n"
        kb = [[InlineKeyboardButton("🔙 رجوع", callback_data="btn_refresh")]]
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

    elif data == "btn_settings":
        settings = get_user_settings(user_id)
        current_slip = settings["slippage_bps"] / 100.0
        text = (
            f"⚙️ *إعدادات التداول والانزلاق (Slippage)*\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"🎯 الانزلاق الحالي: `{current_slip}%`\n\n"
            f"اختر نسبة الانزلاق المناسبة لقنص العملات:"
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
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

    elif data.startswith("slip_"):
        new_bps = int(data.split("_")[1])
        update_user_slippage(user_id, new_bps)
        await query.edit_message_text(f"✅ *تم ضبط نسبة الانزلاق إلى {new_bps/100.0}% بنجاح!*", parse_mode="Markdown", reply_markup=get_main_menu_keyboard())

    elif data.startswith("buy_"):
        parts = data.split("_")
        mint = parts[1]
        amount_sol = float(parts[2])

        pubkey, _ = get_or_create_wallet(user_id)
        bal = get_sol_balance(pubkey)

        if bal < (amount_sol + 0.005):  # Buffer for gas
            await query.edit_message_text(
                f"❌ *رصيد SOL غير كافٍ!*\n"
                f"المطلوب: `{amount_sol} SOL` (+ رسوم الشبكة)\n"
                f"الرصيد المتاح: `{bal:.4f} SOL`\n\n"
                f"يرجى إيداع SOL في محفظتك:\n`{pubkey}`",
                parse_mode="Markdown",
                reply_markup=get_main_menu_keyboard()
            )
            return

        status_msg = await query.message.reply_text("⚡ *جاري تحضير مسار الشراء وحساب العمولة عبر Jupiter...*", parse_mode="Markdown")

        settings = get_user_settings(user_id)
        slippage = settings["slippage_bps"]
        amount_lamports = int(amount_sol * 1_000_000_000)

        # 1. Fetch Quote
        quote = get_jupiter_quote(WSOL_MINT, mint, amount_lamports, slippage, with_fee=True)
        if not quote:
            await status_msg.edit_text("❌ *تعذر إيجاد مسار سيولة أو زوج تداول في Jupiter حالياً.*")
            return

        # 2. Build & Sign
        keypair = get_user_keypair(user_id)
        tx_bytes = build_and_sign_swap_tx(quote, keypair, settings["priority_fee"])
        if not tx_bytes:
            await status_msg.edit_text("❌ *فشل في بناء وتوقيع المعاملة الذكية.*")
            return

        # 3. Broadcast
        await status_msg.edit_text("🚀 *جاري إرسال المعاملة إلى شبكة سولانا وتأكيد التنفيذ...*", parse_mode="Markdown")
        success, sig_or_err = broadcast_transaction(tx_bytes)

        if success:
            out_amount = float(quote.get("outAmount", 0))
            fee_lamports = float(quote.get("platformFee", {}).get("amount", 0))
            record_trade_db(user_id, WSOL_MINT, mint, amount_sol, out_amount, fee_lamports/1e9, sig_or_err, "CONFIRMED")
            success_text = (
                f"🎉 *تم تنفيذ صفقة الشراء بنجاح!* 🟢\n"
                f"━━━━━━━━━━━━━━━━━━━\n"
                f"💸 القيمة: `{amount_sol} SOL`\n"
                f"🛡️ عمولة المطور (1%): `{fee_lamports/1e9:.6f} SOL`\n"
                f"🔗 [عرض المعاملة على Solscan](https://solscan.io/tx/{sig_or_err})\n"
            )
            await status_msg.edit_text(success_text, parse_mode="Markdown", disable_web_page_preview=True)
        else:
            await status_msg.edit_text(f"❌ *فشل في إرسال المعاملة*: `{sig_or_err}`", parse_mode="Markdown")

    elif data == "btn_snipe_guide":
        text = (
            "🎯 *دليل القنص والشراء الفوري* ⚡\n"
            "━━━━━━━━━━━━━━━━━━━\n"
            "1. افتح أي منصة (DexScreener, Pump.fun, Twitter, Photon).\n"
            "2. انسخ عنوان العقد الذكي للعملة (Contract Address).\n"
            "3. الصق العنوان هنا في هذه المحادثة مباشرة.\n"
            "4. سيقوم البوت فوراً بفحص أمان العملة (RugCheck) وإظهار أزرار الشراء الفوري بنقرة واحدة!\n"
        )
        kb = [[InlineKeyboardButton("🔙 رجوع", callback_data="btn_refresh")]]
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

    elif data.startswith("sell_"):
        parts = data.split("_")
        mint = parts[1]
        pct = int(parts[2])
        await query.message.reply_text(f"⚡ *جاري تحضير أمر بيع {pct}% من العملة...*", parse_mode="Markdown")


async def wallet_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /wallet command."""
    user_id = update.effective_user.id
    pubkey, _ = get_or_create_wallet(user_id)
    balance = get_sol_balance(pubkey)
    text = (
        f"💳 *إدارة المحفظة والإيداع* 🏦\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"📍 *عنوان إيداع SOL*:\n`{pubkey}`\n\n"
        f"💰 *الرصيد المتاح*: `{balance:.4f} SOL`\n"
    )
    kb = [
        [InlineKeyboardButton("🔑 إظهار المفتاح الخاص (Private Key)", callback_data="btn_export_key")],
        [InlineKeyboardButton("🔄 تحديث الرصيد", callback_data="btn_wallet")]
    ]
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))


async def positions_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /positions command."""
    user_id = update.effective_user.id
    pubkey, _ = get_or_create_wallet(user_id)
    tokens = get_token_accounts(pubkey)
    if not tokens:
        text = "📊 *لا توجد صفقات أو رموز مشتراة حالياً في محفظتك.*"
    else:
        text = "📊 *الرموز المفتوحة في محفظتك*:\n━━━━━━━━━━━━━━━━━━━\n"
        for t in tokens:
            text += f"• `{t['mint'][:6]}...{t['mint'][-4:]}`: `{t['amount']:,.2f}` رمز\n"
    await update.message.reply_text(text, parse_mode="Markdown")


async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /settings command."""
    user_id = update.effective_user.id
    settings = get_user_settings(user_id)
    current_slip = settings["slippage_bps"] / 100.0
    text = (
        f"⚙️ *إعدادات التداول والانزلاق (Slippage)*\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"🎯 الانزلاق الحالي: `{current_slip}%`\n\n"
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
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /help command."""
    text = (
        "❓ *دليل استخدام بوت قنص سولانا* ⚡\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "• `/start` - فتح لوحة التحكم الرئيسية.\n"
        "• `/wallet` - عرض عنوان المحفظة والإيداع وسحب المفاتيح.\n"
        "• `/positions` - عرض صفقاتك والعملات المشتراة.\n"
        "• `/settings` - ضبط نسبة الانزلاق وسرعة المعاملة.\n\n"
        "💡 *للقنص الفوري*: انسخ عنوان أي عملة والصقه هنا مباشرة!"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


def build_application(token: str) -> Application:
    """Builds the Telegram Application instance."""
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("wallet", wallet_command))
    app.add_handler(CommandHandler("positions", positions_command))
    app.add_handler(CommandHandler("settings", settings_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CallbackQueryHandler(callback_router))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    return app


if __name__ == "__main__":
    token = TELEGRAM_BOT_TOKEN or os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        print("⚠️ يرجى تزويد TELEGRAM_BOT_TOKEN لتشغيل البوت على الشبكة.")
        print("💡 يمكنك تشغيل وضع الاختبار التلقائي عبر: py test_bot.py")
        sys.exit(0)

    print("🚀 جاري إطلاق بوت التيليجرام لقنص سولانا...")
    app = build_application(token)
    app.run_polling()
