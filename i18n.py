# -*- coding: utf-8 -*-
"""
Solana Telegram Sniper & Trading Bot — Internationalization (i18n) Engine
Supports seamless dual-language operation: English (default) and Arabic.
"""

from typing import Dict, Any, List
import html

MESSAGES = {
    "en": {
        "welcome_title": "⚡ <b>Welcome to Popcorn Solana Sniper & Trading Bot!</b> 🎯",
        "trader": "👤 <b>Trader</b>",
        "wallet_dedicated": "💳 <b>Your Dedicated Solana Wallet (Tap to copy)</b>",
        "current_balance": "💰 <b>Current Balance</b>",
        "platform_fee": "🛡️ <b>Platform Fee</b>: <code>1.0%</code> (Settled automatically via Jupiter)",
        "updated_at": "🕒 <b>Updated</b>",
        "how_to_start_title": "💡 <b>How to start trading?</b>",
        "how_to_start_steps": (
            "1. Copy your deposit wallet address above and send SOL from Phantom or any exchange.\n"
            "2. Paste any Solana Contract Address (CA) or DexScreener/Pump.fun link directly here.\n"
            "3. The bot will instantly audit the token (RugCheck) and provide 1-click buy buttons!"
        ),
        "btn_snipe_guide": "⚡ Instant Sniper (Send CA / Link)",
        "btn_trending": "🔥 Trending Radar",
        "btn_wallet": "💳 Wallet & Deposit",
        "btn_referral": "🤝 Referrals & Rewards (25%)",
        "btn_positions": "📊 Open Positions",
        "btn_autobuy": "🎯 Auto-Buy",
        "btn_settings": "⚙️ Slippage Settings",
        "btn_withdraw": "💸 Withdraw SOL",
        "btn_refresh": "🔄 Refresh Balance",
        "btn_lang": "🌐 Language: English 🇬🇧",
        "btn_lang_toggle": "🌐 Switch to العربية 🇸🇦",
        "btn_back": "🔙 Back to Dashboard",
        "btn_buy": "Buy",
        "btn_sell": "Sell",
        "btn_custom_buy": "✏️ Custom Amount",
        "btn_cancel": "❌ Cancel",
        "btn_dexscreener": "📈 DexScreener Chart",
        "btn_rugcheck": "🛡️ RugCheck Report",
        "enabled": "⚡ ON",
        "disabled": "⚪ OFF",
        "wallet_card_title": "💳 <b>Your Solana Trading Wallet</b>",
        "wallet_card_deposit_note": "Deposit SOL to this address to start trading. You own the private keys non-custodially.",
        "btn_export_key": "🔑 Export Private Key",
        "key_warning": "⚠️ <b>KEEP PRIVATE KEYS SECRET!</b> Never share your private key with anyone.",
        "referral_card_title": "🤝 <b>Affiliate & Referral Program</b>",
        "referral_card_body": (
            "Earn <b>25% lifetime commission</b> from trading fees paid by users you invite!\n\n"
            "🔗 <b>Your Exclusive Referral Link</b>:\n"
            "<code>{ref_link}</code>\n\n"
            "👥 <b>Total Invited</b>: <code>{total_ref}</code> users\n"
            "💰 <b>Total Earned</b>: <code>{earnings:.4f} SOL</code>\n\n"
            "Commissions are automatically credited to your trading wallet on every swap."
        ),
        "autobuy_title": "🎯 <b>Auto-Snipe & Instant Buy Settings</b>",
        "autobuy_body": (
            "Status: <b>{status}</b>\n"
            "Default Buy Amount: <code>{amount:.2f} SOL</code>\n\n"
            "When enabled, pasting any valid token Contract Address (CA) will immediately execute a swap without asking for confirmation."
        ),
        "btn_toggle_autobuy": "Toggle Auto-Buy",
        "settings_title": "⚙️ <b>Trading & Slippage Settings</b>",
        "settings_body": (
            "Current Slippage Tolerance: <b>{slippage:.1f}%</b>\n\n"
            "Select your preferred slippage tolerance below:"
        ),
        "withdraw_title": "💸 <b>Withdraw SOL to External Wallet</b>",
        "withdraw_body": (
            "Available Balance: <code>{balance:.4f} SOL</code>\n\n"
            "To withdraw funds to Phantom or any external Solana wallet, use:\n"
            "<code>/withdraw [DESTINATION_ADDRESS] [AMOUNT]</code>\n\n"
            "Example: <code>/withdraw 7kz1mcQcaZhYzFUHBFHH6s5tGrDHc7gNhN5WAUyXyq5r 0.5</code>"
        ),
        "positions_title": "📊 <b>Your Open Token Positions</b>",
        "no_positions": "No open token holdings found. Paste a token address to start trading!",
        "snipe_guide_title": "⚡ <b>Instant Sniper Mode</b>",
        "snipe_guide_body": (
            "Simply send or paste any of the following into this chat:\n"
            "• Solana Contract Address (Base58 Mint)\n"
            "• DexScreener URL\n"
            "• Pump.fun URL\n"
            "• Solscan / Photon / Birdeye URL\n\n"
            "The bot will automatically extract the mint, run a full security scan, and open instant trading controls."
        ),
        "refresh_toast": "✅ Balance updated to latest state!",
        "lang_switched_toast": "Language switched to English 🇬🇧",
        "help_title": "❓ <b>Popcorn Solana Sniper & Trading Bot Guide</b> ⚡",
        "help_body": (
            "━━━━━━━━━━━━━━━━━━━\n"
            "• <code>/start</code> - Open Main Dashboard\n"
            "• <code>/trending</code> - View Trending Solana Tokens\n"
            "• <code>/referral</code> - Affiliate Link & Rewards (25%)\n"
            "• <code>/wallet</code> - View Wallet, Deposit & Export Keys\n"
            "• <code>/withdraw [ADDRESS] [AMOUNT]</code> - Withdraw SOL\n"
            "• <code>/positions</code> - View Open Token Holdings\n"
            "• <code>/settings</code> - Configure Slippage & Language\n\n"
            "💡 <b>To snipe a token</b>: Paste any CA or DexScreener link directly here!"
        )
    },
    "ar": {
        "welcome_title": "⚡ <b>مرحباً بك في بوت قنص وتداول سولانا فائق السرعة!</b> 🎯",
        "trader": "👤 <b>المتداول</b>",
        "wallet_dedicated": "💳 <b>محفظتك المخصصة (اضغط للنسخ)</b>",
        "current_balance": "💰 <b>الرصيد الحالي</b>",
        "platform_fee": "🛡️ <b>رسوم المنصة المعتمدة</b>: <code>1.0%</code> (مقتطعة آلياً عبر Jupiter)",
        "updated_at": "🕒 <b>وقت التحديث</b>",
        "how_to_start_title": "💡 <b>كيف تبدأ التداول فورياً؟</b>",
        "how_to_start_steps": (
            "1. انسخ عنوان محفظتك أعلاه وقم بإيداع أي رصيد SOL من Phantom أو أي منصة.\n"
            "2. الصق أي رابط أو عنوان عقد (CA) هنا مباشرة.\n"
            "3. سيقوم البوت بفحص أمان العملة (RugCheck) وإظهار أزرار الشراء بنقرة واحدة!"
        ),
        "btn_snipe_guide": "⚡ قنص فوري (أرسل العقد أو الرابط)",
        "btn_trending": "🔥 تريند سولانا اللحظي",
        "btn_wallet": "💳 المحفظة والإيداع",
        "btn_referral": "🤝 نظام الإحالات والأرباح",
        "btn_positions": "📊 صفقاتي المفتوحة",
        "btn_autobuy": "🎯 الشراء التلقائي",
        "btn_settings": "⚙️ إعدادات الانزلاق",
        "btn_withdraw": "💸 سحب SOL للخارج",
        "btn_refresh": "🔄 تحديث الرصيد",
        "btn_lang": "🌐 اللغة: العربية 🇸🇦",
        "btn_lang_toggle": "🌐 Switch to English 🇬🇧",
        "btn_back": "🔙 العودة للرئيسية",
        "btn_buy": "شراء",
        "btn_sell": "بيع",
        "btn_custom_buy": "✏️ شراء بمبلغ مخصص",
        "btn_cancel": "❌ إلغاء",
        "btn_dexscreener": "📈 شارت DexScreener",
        "btn_rugcheck": "🛡️ تقرير RugCheck",
        "enabled": "⚡ مفعل",
        "disabled": "⚪ معطل",
        "wallet_card_title": "💳 <b>محفظة تداول سولانا الخاصة بك</b>",
        "wallet_card_deposit_note": "أودع رصيد SOL إلى هذا العنوان للبدء فوراً. المفاتيح مشفرة ومحفوظة لك حصرياً.",
        "btn_export_key": "🔑 تصدير المفتاح الخاص",
        "key_warning": "⚠️ <b>تحذير أمني شديد:</b> لا تشارك مفتاحك الخاص مع أي شخص إطلاقاً.",
        "referral_card_title": "🤝 <b>نظام الإحالات والأرباح التشاركية</b>",
        "referral_card_body": (
            "اربح <b>25% عمولة أبدية</b> من رسوم التداول المدفوعة بواسطة المستخدمين الذين تدعوهم!\n\n"
            "🔗 <b>رابط الإحالة الحصري الخاص بك</b>:\n"
            "<code>{ref_link}</code>\n\n"
            "👥 <b>إجمالي المدعوين</b>: <code>{total_ref}</code> مستخدم\n"
            "💰 <b>إجمالي الأرباح المكتسبة</b>: <code>{earnings:.4f} SOL</code>\n\n"
            "تودع العمولات تلقائياً في محفظة تداولك مع كل صفقة منفذة."
        ),
        "autobuy_title": "🎯 <b>إعدادات القنص والشراء التلقائي</b>",
        "autobuy_body": (
            "الحالة: <b>{status}</b>\n"
            "مبلغ الشراء التلقائي: <code>{amount:.2f} SOL</code>\n\n"
            "عند تفعيل هذا الخيار، سيقوم البوت بالشراء الفوري بمجرد لصق أي عنوان عملة دون الحاجة لطلب التأكيد."
        ),
        "btn_toggle_autobuy": "تبديل الشراء التلقائي",
        "settings_title": "⚙️ <b>إعدادات التداول والانزلاق السعري</b>",
        "settings_body": (
            "نسبة الانزلاق الحالية (Slippage): <b>{slippage:.1f}%</b>\n\n"
            "اختر نسبة الانزلاق المعتمدة للصفقات السريعة:"
        ),
        "withdraw_title": "💸 <b>سحب رصيد SOL لمحفظة خارجية</b>",
        "withdraw_body": (
            "الرصيد المتاح: <code>{balance:.4f} SOL</code>\n\n"
            "لسحب الرصيد إلى محفظة Phantom أو أي محفظة خارجية، أرسل الأمر:\n"
            "<code>/withdraw [عنوان_المحفظة] [المبلغ]</code>\n\n"
            "مثال: <code>/withdraw 7kz1mcQcaZhYzFUHBFHH6s5tGrDHc7gNhN5WAUyXyq5r 0.5</code>"
        ),
        "positions_title": "📊 <b>صفقاتك والعملات المفتوحة</b>",
        "no_positions": "لا توجد صفقات أو أرصدة عملات حالية. الصق عنوان عملة للبدء فوراً!",
        "snipe_guide_title": "⚡ <b>دليل القنص الفوري</b>",
        "snipe_guide_body": (
            "أرسل أو الصق أي مما يلي هنا في المحادثة مباشرة:\n"
            "• عنوان عقد العملة (Solana Mint Address)\n"
            "• رابط DexScreener للعملة\n"
            "• رابط Pump.fun\n"
            "• رابط Solscan / Photon / Birdeye\n\n"
            "سيقوم البوت باستخراج العقد وفحصه أمنياً وعرض أزرار التنفيذ الفوري."
        ),
        "refresh_toast": "✅ الرصيد محدّث لأحدث قيمة!",
        "lang_switched_toast": "تم تحويل اللغة إلى العربية 🇸🇦",
        "help_title": "❓ <b>دليل استخدام بوت قنص وتداول سولانا</b> ⚡",
        "help_body": (
            "━━━━━━━━━━━━━━━━━━━\n"
            "• <code>/start</code> - فتح لوحة التحكم الرئيسية\n"
            "• <code>/trending</code> - عرض أكثر عملات سولانا رواجاً\n"
            "• <code>/referral</code> - رابط الإحالة ومكافآت دعوة الأصدقاء (25%)\n"
            "• <code>/wallet</code> - عرض المحفظة والإيداع وتصدير المفاتيح\n"
            "• <code>/withdraw [العنوان] [المبلغ]</code> - سحب رصيد SOL\n"
            "• <code>/positions</code> - عرض صفقاتك والعملات المفتوحة\n"
            "• <code>/settings</code> - ضبط نسبة الانزلاق واللغة\n\n"
            "💡 <b>للقنص الفوري</b>: الصق عنوان أي عملة أو رابط DexScreener هنا مباشرة!"
        )
    }
}


def t(key: str, lang: str = "en", **kwargs) -> str:
    """Translates a message key to the requested language with optional parameter formatting."""
    lang_dict = MESSAGES.get(lang, MESSAGES["en"])
    text = lang_dict.get(key, MESSAGES["en"].get(key, key))
    if kwargs:
        try:
            return text.format(**kwargs)
        except Exception:
            return text
    return text
