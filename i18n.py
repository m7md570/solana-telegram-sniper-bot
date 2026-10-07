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
        "btn_tour": "🚀 Quick Tour (3 Steps)",
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
        "btn_custom_sell": "✏️ Custom %",
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
        "btn_pnl": "📈 PnL & Performance",
        "pnl_title": "📈 <b>Your Trading PnL & Performance</b> ⚡",
        "pnl_body": (
            "━━━━━━━━━━━━━━━━━━━\n"
            "👤 <b>Trader</b>: @{username}\n"
            "📊 <b>Total Trades Executed</b>: <code>{total_trades}</code>\n"
            "💸 <b>Total Volume Traded</b>: <code>{total_vol:.3f} SOL</code>\n"
            "⚡ <b>Routing Latency</b>: Sub-400ms via Jupiter V6\n"
            "━━━━━━━━━━━━━━━━━━━\n"
            "💡 <i>Keep sniping high-velocity memecoins with Popcorn!</i>"
        ),
        "search_prompt": "🔍 <b>Searching DexScreener for:</b> <code>{query}</code>...",
        "search_not_found": "❌ <b>No Solana token found matching:</b> <code>{query}</code>\nTry sending the exact Contract Address (CA).",
        "search_found_header": "🔍 <b>Search Result:</b> <code>{name} (${symbol})</code>",
        "btn_watchlist": "⭐ Watchlist",
        "btn_track": "⭐ Track",
        "btn_untrack": "🗑️ Untrack",
        "watchlist_title": "⭐ <b>Your Token Watchlist</b> ⚡",
        "watchlist_empty": "Your watchlist is empty!\nClick ⭐ on any token audit card or use <code>/track [CA_OR_TICKER]</code> to monitor tokens.",
        "watchlist_added": "⭐ Added to your watchlist!",
        "watchlist_removed": "🗑️ Removed from watchlist!",
        "custom_buy_prompt": "✏️ <b>Enter custom SOL amount to buy for ${symbol}:</b>\n\nReply to this message with a number (e.g. <code>0.02</code>, <code>0.15</code>, <code>2.5</code>):\n💡 <i>Type <code>/cancel</code> to abort.</i>",
        "custom_sell_prompt": "✏️ <b>Enter custom percentage of ${symbol} to sell (1-100%):</b>\n\nReply with a number (e.g. <code>25</code>, <code>50</code>, <code>75</code>, or <code>100</code>):\n💡 <i>Type <code>/cancel</code> to abort.</i>",
        "refresh_toast": "✅ Balance updated to latest state!",
        "lang_switched_toast": "Language switched to English 🇬🇧",
        "sell_syntax_help": (
            "ℹ️ <b>Instant Sell Syntax</b>:\n"
            "<code>/sell [CONTRACT_OR_TICKER] [PERCENT]</code>\n\n"
            "<b>Examples:</b>\n"
            "<code>/sell bonk 100</code> (Sell all BONK holdings)\n"
            "<code>/sell DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263 50</code> (Sell 50%)"
        ),
        "sell_no_balance": "❌ <b>No token balance found to sell for:</b> <code>{target}</code>",
        "sell_invalid_pct": "❌ Invalid percentage. Please specify between 1 and 100 (e.g. <code>50</code> or <code>100</code>).",
        "gas_title": "⚡ <b>Priority Gas Fee Settings</b>",
        "gas_body": (
            "Current Priority Gas: <b>{gas_sol:.5f} SOL</b> (<code>{gas_lamports:,} lamports</code>)\n"
            "Speed Tier: <b>{tier}</b>\n\n"
            "Select speed tier to accelerate your transactions:"
        ),
        "gas_tier_normal": "⚡ Normal (0.00005 SOL)",
        "gas_tier_turbo": "🚀 Turbo (0.00025 SOL)",
        "gas_tier_ultra": "🏎️ Ultra (0.001 SOL)",
        "btn_history": "📜 Trade History",
        "trades_history_title": "📜 <b>Recent Trade History</b> ⚡",
        "trades_no_history": "No trades executed yet. Paste a token CA or send a ticker to snipe your first memecoin!",
        "btn_surge": "🚀 Surge & Gainers",
        "surge_title": "🚀 <b>Solana High-Velocity Gainers & Surge Radar</b> ⚡",
        "surge_empty": "No high-velocity gainers detected at the moment. Please try again shortly.",
        "tp_syntax_help": "ℹ️ <b>Take-Profit Syntax</b>: <code>/tp [PERCENT]</code>\nExample: <code>/tp 50</code> (Auto sell at +50% gain)",
        "sl_syntax_help": "ℹ️ <b>Stop-Loss Syntax</b>: <code>/sl [PERCENT]</code>\nExample: <code>/sl 25</code> (Auto stop at -25% loss)",
        "tp_updated": "🎯 Take-Profit target set to +{pct}%!",
        "sl_updated": "🛑 Stop-Loss limit set to -{pct}%!",
        "price_alert_title": "🚨 <b>PRICE & VOLATILITY ALERT!</b> ⚡",
        "alerts_status_title": "🔔 <b>Price Movement Alerts Settings</b>",
        "alerts_status_body": (
            "Status: <b>{status}</b>\n"
            "Threshold: <code>±10%</code> price movement\n\n"
            "When enabled, Popcorn Bot automatically tracks all tokens on your watchlist "
            "and dispatches instant alerts with 1-click Snipe buttons when momentum or volatility strikes."
        ),
        "alerts_toggled": "🔔 Price alerts are now {status}!",
        "btn_ping": "⚡ Network Latency",
        "ping_title": "⚡ <b>Solana Network & RPC Latency Benchmark</b>",
        "ping_body": (
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "🌐 <b>Primary RPC:</b> <code>{rpc_ms:.0f} ms</code> ({rpc_status})\n"
            "🔀 <b>Jupiter V6 Routing:</b> <code>{jup_ms:.0f} ms</code> ({jup_status})\n"
            "⛓️ <b>Cluster Health:</b> <code>OK / 100% Finalized</code>\n"
            "🛡️ <b>Sandwich MEV Protection:</b> <code>ACTIVE</code>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "💡 <i>Sub-second routing ensures optimal entry on explosive memecoins!</i>"
        ),
        "audit_usage_help": "ℹ️ <b>Audit Syntax</b>: <code>/audit [CA_OR_TICKER]</code>\nExample: <code>/audit bonk</code>",
        "panic_confirm_title": "🚨 <b>EMERGENCY PANIC SELL-ALL (100%)</b>",
        "panic_confirm_body": (
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "⚠️ <b>Are you sure you want to market sell ALL open positions immediately?</b>\n\n"
            "This will liquidate 100% of all tokens in your wallet and convert them back into SOL via Jupiter V6.\n\n"
            "📊 Open Positions: <code>{count} tokens</code>"
        ),
        "btn_panic_confirm": "🚨 Liquidate All Positions (100%)",
        "btn_panic_execute": "🚨 YES, SELL ALL NOW!",
        "panic_success_title": "🎉 <b>EMERGENCY LIQUIDATION COMPLETED!</b> 🟢",
        "panic_success_body": (
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "✅ <b>Successfully Liquidated:</b> <code>{success_cnt}/{total_cnt} positions</code>\n"
            "💰 <b>Total Reclaimed:</b> <code>{total_sol:.4f} SOL</code> in wallet\n"
            "🛡️ <b>Platform Fee:</b> 1.0% settled automatically\n\n"
            "💡 <i>Your capital has been safely restored to SOL!</i>"
        ),
        "panic_no_positions": "ℹ️ <b>No open token holdings found to liquidate.</b>",
        "slippage_updated": "🎯 Slippage tolerance set to <b>{pct:.2f}%</b> (<code>{bps} BPS</code>)!",
        "btn_show_qr": "📲 Deposit QR Code",
        "btn_gas_radar": "⛽ Solana Network Gas",
        "gas_card_title": "⛽ <b>Solana Mainnet Gas & Priority Fee Radar</b> ⚡",
        "gas_card_body": (
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "🌐 <b>Network Congestion:</b> {congestion_badge}\n"
            "⚡ <b>Median Priority Fee:</b> <code>{median_fee:,} µLamports</code> (<code>{median_sol:.6f} SOL</code>)\n"
            "🚀 <b>Turbo Priority Fee (P95):</b> <code>{p95_fee:,} µLamports</code> (<code>{p95_sol:.6f} SOL</code>)\n"
            "🕒 <b>Sampled Blocks:</b> Recent 150 Slots on Mainnet\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "🎯 <b>Recommended Bot Settings:</b>\n"
            "• 🟢 Normal Speed: <code>{rec_normal:,} µLamports</code>\n"
            "• 🟡 Turbo Snipe: <code>{rec_turbo:,} µLamports</code>\n"
            "• 🔴 Ultra Alpha: <code>{rec_ultra:,} µLamports</code>\n\n"
            "💡 <i>Adjust priority gas in <code>/settings</code> or via <code>/gas [AMOUNT]</code>.</i>"
        ),
        "qr_card_title": "📲 <b>Solana Instant Deposit QR Code</b> 🏦",
        "qr_card_body": (
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "📍 <b>SOL Deposit Address (Tap to copy):</b>\n<code>{pubkey}</code>\n\n"
            "💰 <b>Current Balance:</b> <code>{balance:.4f} SOL</code>\n\n"
            "💡 <b>Scan with Mobile Wallet:</b>\n"
            "Open Phantom, Solflare, OKX, or Binance app on your phone, choose Send, and scan this QR code to deposit instantly!"
        ),

        "slippage_syntax_help": "ℹ️ <b>Slippage Syntax</b>: <code>/slippage [PERCENT]</code>\nExample: <code>/slippage 1.5</code> (or <code>/slip 2.0</code>)",
        "slippage_invalid": "❌ Please specify a slippage between 0.1% and 50.0% (e.g. <code>1.5</code>).",
        "autobuy_status_title": "🤖 <b>Auto-Buy Sniper Engine</b>",
        "autobuy_status_body": (
            "Status: <b>{status}</b>\n"
            "Amount: <code>{amt:.3f} SOL</code> per snipe\n\n"
            "When enabled, Popcorn Bot automatically executes an instant buy swap whenever you paste a Solana token Contract Address (CA)."
        ),
        "autobuy_updated": "🤖 Auto-Buy is now <b>{status}</b> (<code>{amt:.3f} SOL</code>)!",
        "autobuy_syntax_help": "ℹ️ <b>Auto-Buy Syntax</b>: <code>/autobuy [AMOUNT|on|off]</code>\nExample: <code>/autobuy 0.1</code> or <code>/autobuy off</code>",
        "price_card_title": "💵 <b>Token Price & Liquidity Radar</b>",
        "price_syntax_help": "ℹ️ <b>Price Syntax</b>: <code>/price [CA_OR_TICKER]</code>\nExample: <code>/price bonk</code>",
        "help_title": "❓ <b>Popcorn Solana Sniper & Trading Bot Guide</b> ⚡",
        "help_body": (
            "━━━━━━━━━━━━━━━━━━━\n"
            "• <code>/start</code> - Open Main Dashboard\n"
            "• <code>/tour</code> - 3-Step Quick Sniping Onboarding Guide\n"
            "• <code>/status</code> - Live Solana Cluster Slot & Bot Health Radar\n"
            "• <code>/fees</code> - Transparent 1.0% Fee Schedule & Payouts\n"
            "• <code>/search [TICKER]</code> - Search Token by Name or Symbol\n"
            "• <code>/price [CA/TICKER]</code> - Quick Price & Liquidity Radar\n"
            "• <code>/audit [CA/TICKER]</code> - Full Token Security & RugCheck Scan\n"
            "• <code>/ping</code> - Check Solana RPC & Jupiter Routing Speed\n"
            "• <code>/buy [CA/TICKER] [AMOUNT]</code> - Instant Custom Buy Snipe\n"
            "• <code>/sell [CA/TICKER] [PERCENT]</code> - Instant Market Sell (%)\n"
            "• <code>/autobuy [AMOUNT|off]</code> - Configure Instant Auto-Buy Sniper\n"
            "• <code>/slippage [PERCENT]</code> - Set Custom Slippage Tolerance (%)\n"
            "• <code>/surge</code> - View Explosive High-Velocity Gainers (1h/24h)\n"
            "• <code>/history</code> - View Recent Trade History & Solscan Links\n"
            "• <code>/alerts</code> - Toggle Autonomous Price Volatility Alerts\n"
            "• <code>/tp [PERCENT]</code> - Configure Auto Take-Profit Target (+%)\n"
            "• <code>/sl [PERCENT]</code> - Configure Auto Stop-Loss Limit (-%)\n"
            "• <code>/watchlist</code> - View Tracked Tokens & Live Prices\n"
            "• <code>/track [CA/TICKER]</code> - Add Token to Watchlist\n"
            "• <code>/trending</code> - View Trending Solana Tokens\n"
            "• <code>/pnl</code> - View Your Trading PnL & Performance\n"
            "• <code>/gas</code> - Configure Priority Gas & Speed Tiers\n"
            "• <code>/referral</code> - Affiliate Link & Rewards (25%)\n"
            "• <code>/wallet</code> - View Wallet, Deposit & Export Keys\n"
            "• <code>/qr</code> - Instant Deposit QR Code\n"
            "• <code>/withdraw [ADDRESS] [AMOUNT]</code> - Withdraw SOL\n"
            "• <code>/positions</code> - View Open Holdings with 1-Click Sell\n"
            "• <code>/panic</code> - Emergency Market Sell All Open Positions (100%)\n"
            "• <code>/settings</code> - Configure Slippage, Gas & Language\n\n"
            "💡 <b>To snipe a token</b>: Paste any CA, DexScreener link, or type a ticker (e.g. <code>BONK</code>) directly here!"
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
        "btn_tour": "🚀 جولة سريعة (3 خطوات)",
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
        "btn_custom_sell": "✏️ نسبة مخصصة %",
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
        "btn_pnl": "📈 بطاقة الأرباح (PnL)",
        "pnl_title": "📈 <b>بطاقة أداء وأرباح التداول (PnL)</b> ⚡",
        "pnl_body": (
            "━━━━━━━━━━━━━━━━━━━\n"
            "👤 <b>المتداول</b>: @{username}\n"
            "📊 <b>إجمالي الصفقات المنفذة</b>: <code>{total_trades}</code>\n"
            "💸 <b>حجم التداول الكلي</b>: <code>{total_vol:.3f} SOL</code>\n"
            "⚡ <b>سرعة التنفيذ</b>: أقل من 400ms عبر Jupiter V6\n"
            "━━━━━━━━━━━━━━━━━━━\n"
            "💡 <i>واصل اقتناص العملات الرائجة مع بوت Popcorn Sniper!</i>"
        ),
        "search_prompt": "🔍 <b>جاري البحث في DexScreener عن:</b> <code>{query}</code>...",
        "search_not_found": "❌ <b>لم يتم العثور على عملة سولانا مطابقة لـ:</b> <code>{query}</code>\nيرجى محاولة إرسال عنوان العقد الذكي (CA) مباشرة.",
        "search_found_header": "🔍 <b>نتيجة البحث:</b> <code>{name} (${symbol})</code>",
        "btn_watchlist": "⭐ قائمة المتابعة",
        "btn_track": "⭐ متابعة",
        "btn_untrack": "🗑️ إلغاء المتابعة",
        "watchlist_title": "⭐ <b>قائمة العملات المتابعة</b> ⚡",
        "watchlist_empty": "قائمة المتابعة فارغة!\nاضغط ⭐ في بطاقة أي عملة أو استخدم <code>/track [العقد_أو_الرمز]</code> لمتابعتها.",
        "watchlist_added": "⭐ تمت إضافة العملة إلى قائمة المتابعة!",
        "watchlist_removed": "🗑️ تمت إزالة العملة من قائمة المتابعة!",
        "custom_buy_prompt": "✏️ <b>أدخل مبلغ SOL المخصص لشراء ${symbol}:</b>\n\nقم بالرد برقم (مثال: <code>0.02</code> أو <code>0.15</code> أو <code>2.5</code>):\n💡 <i>اكتب <code>/cancel</code> للإلغاء.</i>",
        "custom_sell_prompt": "✏️ <b>أدخل النسبة المئوية المخصصة لبيع ${symbol} (من 1 إلى 100%):</b>\n\nقم بالرد برقم (مثال: <code>25</code> أو <code>50</code> أو <code>75</code> أو <code>100</code>):\n💡 <i>اكتب <code>/cancel</code> للإلغاء.</i>",
        "refresh_toast": "✅ الرصيد محدّث لأحدث قيمة!",
        "lang_switched_toast": "تم تحويل اللغة إلى العربية 🇸🇦",
        "sell_syntax_help": (
            "ℹ️ <b>صيغة البيع الفوري</b>:\n"
            "<code>/sell [العقد_أو_الرمز] [النسبة_المئوية]</code>\n\n"
            "<b>أمثلة:</b>\n"
            "<code>/sell bonk 100</code> (بيع 100% من رصيد العملة)\n"
            "<code>/sell DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263 50</code> (بيع 50%)"
        ),
        "sell_no_balance": "❌ <b>لا تملك رصيداً من هذه العملة للبيع:</b> <code>{target}</code>",
        "sell_invalid_pct": "❌ النسبة المئوية غير صحيحة. يرجى تحديد نسبة بين 1 و 100 (مثال: <code>50</code> أو <code>100</code>).",
        "gas_title": "⚡ <b>إعدادات رسوم أولوية الغاز (Priority Fee)</b>",
        "gas_body": (
            "رسوم أولوية الغاز الحالية: <b>{gas_sol:.5f} SOL</b> (<code>{gas_lamports:,} lamports</code>)\n"
            "فئة السرعة: <b>{tier}</b>\n\n"
            "اختر فئة السرعة لتسريع تأكيد صفقاتك على شبكة سولانا:"
        ),
        "gas_tier_normal": "⚡ عادي (0.00005 SOL)",
        "gas_tier_turbo": "🚀 سريع (0.00025 SOL)",
        "gas_tier_ultra": "🏎️ فائق السرعة (0.001 SOL)",
        "btn_history": "📜 سجل الصفقات",
        "trades_history_title": "📜 <b>سجل الصفقات المنفذة</b> ⚡",
        "trades_no_history": "لم يتم تنفيذ أي صفقات بعد. الصق عنوان أي عملة للبدء في قنص العملات فورياً!",
        "btn_surge": "🚀 العملات الأكثر صعوداً (Surge)",
        "surge_title": "🚀 <b>رادار العملات الأكثر صعوداً وزخماً (Surge)</b> ⚡",
        "surge_empty": "لم يتم رصد عملات صاعدة بزخم كافٍ حالياً. يرجى المحاولة بعد قليل.",
        "tp_syntax_help": "ℹ️ <b>صيغة جني الأرباح</b>: <code>/tp [النسبة]</code>\nمثال: <code>/tp 50</code> (جني الأرباح تلقائياً عند +50%)",
        "sl_syntax_help": "ℹ️ <b>صيغة وقف الخسارة</b>: <code>/sl [النسبة]</code>\nمثال: <code>/sl 25</code> (وقف الخسارة تلقائياً عند -25%)",
        "tp_updated": "🎯 تم ضبط هدف جني الأرباح إلى +{pct}%!",
        "sl_updated": "🛑 تم ضبط حد وقف الخسارة إلى -{pct}%!",
        "price_alert_title": "🚨 <b>تنبيه حركة وتقلبات السعر!</b> ⚡",
        "alerts_status_title": "🔔 <b>إعدادات تنبيهات حركة الأسعار والتقلبات</b>",
        "alerts_status_body": (
            "الحالة: <b>{status}</b>\n"
            "حساسية التنبيه: <code>±10%</code> تغيّر في السعر\n\n"
            "عند التفعيل، يراقب البوت عملات قائمة متابعتك آلياً ويرسل إشعارات فورية مع أزرار قنص بنقرة واحدة عند رصد أي صعود حاد أو تقلبات."
        ),
        "alerts_toggled": "🔔 تنبيهات الأسعار الآن {status}!",
        "btn_ping": "⚡ سرعة استجابة الشبكة",
        "ping_title": "⚡ <b>رادار سرعة واستجابة شبكة سولانا و Jupiter</b>",
        "ping_body": (
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "🌐 <b>خادم سولانا الرئيسي (RPC):</b> <code>{rpc_ms:.0f} ملي ثانية</code> ({rpc_status})\n"
            "🔀 <b>مسارات توجيه Jupiter V6:</b> <code>{jup_ms:.0f} ملي ثانية</code> ({jup_status})\n"
            "⛓️ <b>صحة واستقرار الشبكة:</b> <code>ممتازة / تأكيد لحظي</code>\n"
            "🛡️ <b>حماية ساندوتش MEV:</b> <code>مفعلة تلقائياً</code>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "💡 <i>زمن الاستجابة الفائق يضمن لك اقتناص العملات المتفجرة بأفضل سعر ممكن!</i>"
        ),
        "audit_usage_help": "ℹ️ <b>صيغة الفحص والتدقيق</b>: <code>/audit [العقد_أو_الرمز]</code>\nمثال: <code>/audit bonk</code>",
        "panic_confirm_title": "🚨 <b>تصفية وبيع طوارئ شامل لجميع الصفقات (100%)</b>",
        "panic_confirm_body": (
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "⚠️ <b>هل أنت متأكد من رغبتك في بيع وتصفية جميع صفقاتك المفتوحة فورياً بسعر السوق؟</b>\n\n"
            "سيقوم البوت ببيع 100% من جميع العملات المحتفظ بها في محفظتك وتحويلها بالكامل إلى SOL عبر Jupiter V6.\n\n"
            "📊 عدد الصفقات المفتوحة: <code>{count} عملات</code>"
        ),
        "btn_panic_confirm": "🚨 بيع وتصفية شاملة لجميع الصفقات (100%)",
        "btn_panic_execute": "🚨 نعم، قم ببيع وتصفية كل شيء الآن!",
        "panic_success_title": "🎉 <b>اكتملت تصفية الطوارئ بنجاح تام!</b> 🟢",
        "panic_success_body": (
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "✅ <b>تمت التصفية بنجاح:</b> <code>{success_cnt}/{total_cnt} صفقات</code>\n"
            "💰 <b>إجمالي المسترد في المحفظة:</b> <code>{total_sol:.4f} SOL</code>\n"
            "🛡️ <b>رسوم المنصة:</b> 1.0% مقتطعة آلياً\n\n"
            "💡 <i>تم تأمين رأس مالك واستعادته بالكامل كـ SOL!</i>"
        ),
        "panic_no_positions": "ℹ️ <b>لا توجد أي صفقات أو أرصدة عملات مفتوحة لتصفيتها.</b>",
        "slippage_updated": "🎯 تم ضبط نسبة الانزلاق المسموح إلى <b>{pct:.2f}%</b> (<code>{bps} BPS</code>)!",
        "btn_show_qr": "📲 رمز QR للإيداع",
        "btn_gas_radar": "⛽ رادار غاز سولانا",
        "gas_card_title": "⛽ <b>رادار رسوم الغاز وأولوية المعاملات على سولانا</b> ⚡",
        "gas_card_body": (
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "🌐 <b>حالة ازدحام الشبكة:</b> {congestion_badge}\n"
            "⚡ <b>متوسط رسوم الأولوية (Median):</b> <code>{median_fee:,} ميكرو-لامبورت</code> (<code>{median_sol:.6f} SOL</code>)\n"
            "🚀 <b>رسوم القنص التوربو (P95):</b> <code>{p95_fee:,} ميكرو-لامبورت</code> (<code>{p95_sol:.6f} SOL</code>)\n"
            "🕒 <b>عينة القياس:</b> آخر 150 كتلة حية على Mainnet\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "🎯 <b>الإعدادات الموصى بها للبوت:</b>\n"
            "• 🟢 السرعة العادية: <code>{rec_normal:,} ميكرو-لامبورت</code>\n"
            "• 🟡 قنص توربو: <code>{rec_turbo:,} ميكرو-لامبورت</code>\n"
            "• 🔴 قنص فائق (Ultra): <code>{rec_ultra:,} ميكرو-لامبورت</code>\n\n"
            "💡 <i>اضبط رسوم الغاز عبر <code>/settings</code> أو استخدم <code>/gas [المبلغ]</code>.</i>"
        ),
        "qr_card_title": "📲 <b>رمز QR للإيداع السريع</b> 🏦",
        "qr_card_body": (
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "📍 <b>عنوان إيداع SOL (اضغط للنسخ):</b>\n<code>{pubkey}</code>\n\n"
            "💰 <b>الرصيد المتاح:</b> <code>{balance:.4f} SOL</code>\n\n"
            "💡 <b>المسح عبر كاميرا الجوال:</b>\n"
            "افتح تطبيق Phantom أو Solflare أو منصات التداول، اختر إرسال (Send)، وامسح هذا الرمز لإيداع SOL فوراً!"
        ),

        "slippage_syntax_help": "ℹ️ <b>صيغة الانزلاق</b>: <code>/slippage [النسبة]</code>\nمثال: <code>/slippage 1.5</code> (أو <code>/slip 2.0</code>)",
        "slippage_invalid": "❌ يرجى تحديد نسبة انزلاق صالحة بين 0.1% و 50.0% (مثل <code>1.5</code>).",
        "autobuy_status_title": "🤖 <b>رادار القنص والشراء التلقائي (Auto-Buy)</b>",
        "autobuy_status_body": (
            "الحالة: <b>{status}</b>\n"
            "المبلغ: <code>{amt:.3f} SOL</code> لكل صفقة\n\n"
            "عند التفعيل، يقوم البوت فورياً بشراء العملة بالمبلغ المحدد بمجرد لصق عنوان عقدها (CA) دون الحاجة للضغط على أي زر."
        ),
        "autobuy_updated": "🤖 تم ضبط الشراء التلقائي: <b>{status}</b> (<code>{amt:.3f} SOL</code>)!",
        "autobuy_syntax_help": "ℹ️ <b>صيغة الشراء التلقائي</b>: <code>/autobuy [المبلغ|on|off]</code>\nمثال: <code>/autobuy 0.1</code> أو <code>/autobuy off</code>",
        "price_card_title": "💵 <b>رادار سعر وسيولة العملة اللحظي</b>",
        "price_syntax_help": "ℹ️ <b>صيغة فحص السعر</b>: <code>/price [العقد_أو_الرمز]</code>\nمثال: <code>/price bonk</code>",
        "help_title": "❓ <b>دليل استخدام بوت قنص وتداول سولانا</b> ⚡",
        "help_body": (
            "━━━━━━━━━━━━━━━━━━━\n"
            "• <code>/start</code> - فتح لوحة التحكم الرئيسية\n"
            "• <code>/tour</code> - جولة سريعة للقنص والربح في 3 خطوات\n"
            "• <code>/status</code> - رادار حالة شبكة سولانا وبلوك Mainnet وسرعة الـ RPC\n"
            "• <code>/fees</code> - جدول الرسوم الشفاف (1% وعوائد الإحالة 25%)\n"
            "• <code>/search [الرمز/الاسم]</code> - البحث عن العملات بالاسم أو الرمز\n"
            "• <code>/price [العقد/الرمز]</code> - فحص سريع للسعر والسيولة والماركت كاب\n"
            "• <code>/audit [العقد/الرمز]</code> - فحص وتدقيق أمان العقد و RugCheck\n"
            "• <code>/ping</code> - فحص سرعة استجابة خوادم سولانا و Jupiter\n"
            "• <code>/buy [العقد/الرمز] [المبلغ]</code> - قنص وشراء فوري بمبلغ مخصص\n"
            "• <code>/sell [العقد/الرمز] [النسبة]</code> - بيع فوري بنسبة مئوية (%)\n"
            "• <code>/autobuy [المبلغ|off]</code> - ضبط القنص والشراء التلقائي الفوري\n"
            "• <code>/slippage [النسبة]</code> - ضبط نسبة الانزلاق المخصصة (%)\n"
            "• <code>/surge</code> - رادار العملات المتفجرة الأكثر صعوداً (1h/24h)\n"
            "• <code>/history</code> - عرض سجل الصفقات المنفذة وروابط Solscan\n"
            "• <code>/alerts</code> - تفعيل أو تعطيل تنبيهات تقلبات الأسعار التلقائية\n"
            "• <code>/tp [النسبة]</code> - ضبط هدف جني الأرباح التلقائي (+%)\n"
            "• <code>/sl [النسبة]</code> - ضبط حد وقف الخسارة التلقائي (-%)\n"
            "• <code>/watchlist</code> - عرض قائمة العملات المتابعة وأسعارها اللحظية\n"
            "• <code>/track [العقد/الرمز]</code> - إضافة عملة إلى قائمة المتابعة\n"
            "• <code>/trending</code> - عرض أكثر عملات سولانا رواجاً\n"
            "• <code>/pnl</code> - عرض بطاقة الأرباح وإحصائيات التداول\n"
            "• <code>/gas</code> - ضبط رسوم الغاز وأولوية التنفيذ\n"
            "• <code>/referral</code> - رابط الإحالة ومكافآت دعوة الأصدقاء (25%)\n"
            "• <code>/wallet</code> - عرض المحفظة والإيداع وتصدير المفاتيح\n"
            "• <code>/qr</code> - رمز QR للإيداع الفوري\n"
            "• <code>/withdraw [العنوان] [المبلغ]</code> - سحب رصيد SOL\n"
            "• <code>/positions</code> - عرض صفقاتك المفتوحة مع أزرار البيع الفوري\n"
            "• <code>/panic</code> - تصفية وبيع طوارئ شامل لجميع الصفقات (100%)\n"
            "• <code>/settings</code> - ضبط نسبة الانزلاق ورسوم الغاز واللغة\n\n"
            "💡 <b>للقنص الفوري</b>: الصق عنوان أي عملة أو رابط أو اكتب رمزها (مثل <code>BONK</code>) هنا مباشرة!"
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
