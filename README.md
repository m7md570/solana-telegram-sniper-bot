# ⚡ Solana High-Velocity Telegram Sniper & Trading Bot

[![Telegram](https://img.shields.io/badge/Live_Bot-@PopcornSniperBot-2CA5E0?logo=telegram&logoColor=white)](https://t.me/PopcornSniperBot)
[![Release](https://img.shields.io/badge/Release-v3.73.0-blue.svg)](https://github.com/m7md570/solana-telegram-sniper-bot/releases)
[![Tests](https://img.shields.io/badge/Tests-95%2F95%20Passing-brightgreen.svg)](test_bot.py)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![Network](https://img.shields.io/badge/Solana-Mainnet--Beta-9945FF.svg)](https://solana.com)
[![Routing](https://img.shields.io/badge/DEX%20Routing-Jupiter%20V6-FBA434.svg)](https://jup.ag)
[![Audit](https://img.shields.io/badge/Security-RugCheck%20Certified-00FFA3.svg)](https://rugcheck.xyz)

A production-grade, ultra-low latency **Solana Telegram Trading & Sniper Bot** built with Python, Jupiter V6 Swap Routing, and RugCheck token security auditing. Designed for high-frequency decentralized token trading with automated on-chain developer fee distribution.

---

## 🌟 Key Features

* **⚡ Sub-400ms Swap Execution:** Direct routing via Jupiter V6 Swap API with automated slippage protection and dynamic priority fee injection.
* **💱 Live Swap Simulation Engine:** Pre-trade routing simulation (`/quote`, `/sim`) displaying guaranteed output, price impact, DEX route, and 1-click execution across interactive size tiers (`0.05`, `0.1`, `0.5`, `1.0 SOL`).
* **🎯 1-Click Interactive Telegram UI:** Instant inline buttons for `[Buy 0.1 SOL]`, `[Buy 0.5 SOL]`, `[Buy 1.0 SOL]`, and `[Sell 25% / 50% / 100%]`.
* **🛡️ Built-in RugCheck & DexScreener Scanner:** Automatically scans any pasted Solana Contract Address (CA) for freeze authority, mint authority, honeypot traps, and liquidity lock status.
* **🔐 Local Non-Custodial Key Security:** Generates distinct trading wallets for each Telegram user, encrypted locally using AES-256 (Fernet) with instant Base58 export capability.
* **💼 Real-Time Portfolio & Liquidation Cockpit:** Live token valuation (`/positions`, `/portfolio`) with direct 1-click Quote simulation and Price radar shortcuts.
* **💰 Automated On-Chain Developer Monetization:** Integrated with Jupiter's on-chain fee mechanism (`platformFeeBps`), routing trading fees directly to the developer payout wallet on every single swap.

---

## 🏛️ System Architecture

```
                  ┌──────────────────────────────────────────────┐
                  │          Telegram User Interface             │
                  │    (Inline Keyboards & 1-Click Buttons)      │
                  └──────────────────────┬───────────────────────┘
                                         │
                         Token CA Paste  │  1-Click Buy/Sell
                                         ▼
                  ┌──────────────────────────────────────────────┐
                  │            Token Audit & Security            │
                  │  (RugCheck API + DexScreener Price Stream)   │
                  └──────────────────────┬───────────────────────┘
                                         │
                                         ▼
┌────────────────────────────────────────────────────────────────────────┐
│                   Jupiter V6 Execution & Fee Engine                    │
│                                                                        │
│   • Multi-DEX Route Discovery (Raydium, Orca, Meteora, Phoenix)        │
│   • Platform Fee Attribution: Programmatic Developer Commission        │
│   • Offline Serialization & Signing via `solders.VersionedTransaction` │
└────────────────────────────────────┬───────────────────────────────────┘
                                     │
                                     ▼
                  ┌──────────────────────────────────────────────┐
                  │             Solana RPC Cluster               │
                  │       (Instant Mainnet-Beta Broadcast)       │
                  └──────────────────────────────────────────────┘
```

---

## 💸 Developer Monetization Architecture

The bot utilizes Jupiter's decentralized protocol fee routing (`platformFeeBps`):
* Every trade executed through the bot programmatically deducts a platform fee (default: `100 BPS = 1.0%`).
* Fees are deposited on-chain into the configured developer wallet:
  ```
  7kz1mcQcaZhYzFUHBFHH6s5tGrDHc7gNhN5WAUyXyq5r
  ```
* No user custody required. All routing is verified and settled directly by Solana smart contracts.

---

## 🚀 Quick Start Guide

### 1. Prerequisites
* Python 3.10+
* Git
* A Telegram Bot Token from [@BotFather](https://t.me/BotFather)

### 2. Installation
```bash
# Clone the repository
git clone https://github.com/m7md570/solana-telegram-sniper-bot.git
cd solana-telegram-sniper-bot

# Install dependencies
pip install -r requirements.txt
```

### 3. Configuration
Copy the template environment file:
```bash
cp .env.example .env
```
Edit `.env` and provide your credentials:
```env
TELEGRAM_BOT_TOKEN="your_bot_token_from_botfather"
DEVELOPER_WALLET="7kz1mcQcaZhYzFUHBFHH6s5tGrDHc7gNhN5WAUyXyq5r"
BOT_MASTER_KEY="your_custom_secure_encryption_key"
```

### 4. Run Verification Test Suite
Ensure all components, wallet encryption, RugCheck scanner, and Jupiter routing pass:
```bash
python test_bot.py
```
Expected output:
```
Ran 85 tests in 24.1s -> OK
```

### 5. Launch the Bot
```bash
python telegram_bot.py
```

---

## 📱 Bot Commands & Usage

| Command | Action |
|---|---|
| `/start` | Initializes user trading wallet and opens the main dashboard |
| `/search [TICKER]` | Resolves any Solana token by ticker or name via DexScreener API |
| `/price [CA/TICKER]` | Quick token price, 24h change, liquidity & chart radar (aliases: `/c`, `/chart`, `/p`) |
| `/audit [CA/TICKER]` | Direct RugCheck security & DexScreener financial audit scanner (aliases: `/scan`, `/check`) |
| `/quote [AMT] [CA]` | Live Jupiter V6 Swap Simulation with guaranteed minimum, price impact & 1-click execution (`/sim`, `/simulate`) |
| `/ping` / `/speed` | Live Solana Primary RPC & Jupiter V6 routing latency benchmark |
| `/buy [CA/TICKER] [SOL]` | Instant direct buy (supports flexible order `/buy 0.1 bonk` or default `/buy bonk`) |
| `/sell [CA/TICKER] [%/all]` | Instant market sell (supports `/sell 50 bonk`, `/sell all bonk`, or `/sell bonk`) |
| `/autobuy [AMT/off]` | Instant Auto-Buy Sniper on CA paste (configurable SOL amount) |
| `/presets [AMT]` | Configures default 1-click quick-buy sizes (e.g. `/presets 0.25`, aliases: `/preset`, `/quickbuy`) |
| `/slippage [PCT]` | Sets precision custom slippage tolerance (e.g. `/slippage 1.5`, alias: `/slip`) |
| `/panic` / `/sellall` | 1-Click Emergency liquidation: market sells 100% of all holdings back to SOL |
| `/tp [PCT]` / `/sl [PCT]` | Autonomous Take-Profit target (+%) and Stop-Loss limit (-%) triggers |
| `/alerts` | Autonomous price volatility & momentum radar alerts (±10%, alias: `/alert`) |
| `/surge` / `/gainers` | Real-time Solana high-velocity gainers & surge radar (1h/24h, alias: `/pump`) |
| `/history` / `/trades` | Full trade history terminal with Solscan on-chain transaction links & CSV export |
| `/gas` / `/priority` | Configures Priority Gas speed tiers (Normal 50k, Turbo 250k, Ultra 1M) |
| `/watchlist` | Displays personalized token watchlist with live batch prices and 24h changes |
| `/track [CA/TICKER]` | Adds any token to user watchlist for continuous tracking |
| `/untrack [CA/TICKER]` | Removes a tracked token from watchlist (supports `/remove` or `/untrack all`) |
| `/clearwatchlist` | Purges all tracked tokens from watchlist with 1 click (alias: `/purge`) |
| `/trending` | Real-time DexScreener Solana trending tokens radar (alias: `/hot`) |
| `/pnl` | Executive trading performance card (total volume, trades count, and X sharing) |
| `/referral` | Viral 25% lifetime referral program link and rewards tracker |
| `/wallet` | Non-custodial wallet management, deposit address, balance, and key export (`/bal`, `/balance`) |
| `/qr` / `/deposit` | Generates deposit QR code and dedicated Solana address for Phantom/Solflare |
| `/withdraw [ADDR] [SOL/all]` | Withdraws SOL directly to Phantom or external wallet (supports 'all' / 'max') |
| `/positions` | Lists all currently held SPL token balances with 1-click Sell & Quote buttons (`/portfolio`, `/holdings`) |
| `/tour` | Interactive 3-step onboarding guide explaining deposits, sniping, and take-profit |
| `/reset` / `/defaults` | Restores all trading settings (slippage, gas, auto-buy) to recommended defaults |
| `/version` / `/about` | Displays live bot release version, architecture specs, and GitHub releases link |
| `/cancel` | Aborts any active custom buy amount or custom sell percentage prompt |
| `/settings` | Dual-mode configuration for slippage, priority fee, and bilingual UI |

---

## 🧪 Benchmark & Quality Assurance

* **RPC Broadcast Latency:** < 350ms via Jupiter V6
* **Unit Test Coverage:** 85/85 comprehensive tests passing (`test_bot.py`, 100% pass rate)
* **Security Checks:** Zero plain-text private key logging. Local AES-256 database encryption.
* **Token-2022 Compatibility:** Multi-program discovery across SPL Token and Token-2022 programs.
* **MEV Defense:** Dynamic price-impact slippage auto-scaling and anti-sandwich protection.

---

## 📄 License
This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.
