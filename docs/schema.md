# Database schema

SQLite in development (`backend/moneyfx.db`, created on first start), Postgres-ready via
`MONEYFX_DATABASE_URL`. Defined in `backend/app/models.py`. All money columns are
`NUMERIC(24, 8)` and handled as Python `Decimal`, never float.

```
users 1──1 accounts 1──* wallets 1──* transactions
                   │
                   ├──* orders    *──1 instruments
                   └──* positions *──1 instruments
```

| Table | Purpose | Key columns |
|---|---|---|
| `users` | Login identity and profile | `email` (unique), `password_hash` (bcrypt), `full_name`, `country` |
| `accounts` | Trading account, one per user for now | `user_id`, `base_currency` (USD), `status` (active / suspended / closed) |
| `wallets` | Cash balance per currency | `account_id` + `currency` (unique), `balance`, `locked` (cash reserved by open buy limit orders). `available = balance - locked` |
| `transactions` | Ledger of every balance change | `type` (deposit / withdrawal / trade_buy / trade_sell), signed `amount`, `balance_after`, `method`, `reference`, `order_id` |
| `instruments` | Tradable markets across forex, crypto, stocks, commodities | `symbol`, `asset_class`, `quote_currency`, `price_decimals`, `qty_decimals`, `min_qty`, plus mock-feed params `base_price`, `volatility`, `spread_bps` |
| `orders` | Every order, including rejected ones | `side`, `type` (market / limit), `quantity`, `limit_price`, `status` (open / filled / cancelled / rejected), `filled_price`, `reserved`, `reject_reason` |
| `positions` | Current holding per instrument | `account_id` + `instrument_id` (unique), `quantity`, `avg_price`, `realized_pnl` |

## Market data

Prices are not stored. `backend/app/market.py` generates them as a deterministic function of
symbol and time (multi-scale fractal noise that behaves like a random walk), so quotes, candles and fills always agree and
any history range can be served without a tick table. Buys fill at the ask and sells at the
bid, with a per-instrument spread.

To go live, replace `MockFeed` with a provider that implements `quote(symbol)` and
`candles(symbol, interval, limit)`. At that point add a `candles` table (instrument_id,
interval, open_time, o/h/l/c/v) to cache history from the provider.

## Trading rules (MVP)

- Long only: you can sell only what you hold. Holdings committed to open sell limit orders cannot be sold twice.
- Market orders fill immediately against the current quote, or are recorded as `rejected` with a reason.
- Limit orders reserve cash (buys) and rest as `open`; a background task checks them every second and fills at the quote once the limit is reached. A marketable limit fills immediately at the better market price.
- Deposits and withdrawals are simulated and settle instantly.

## Bots

| Table | Purpose | Key columns |
|---|---|---|
| `bots` | One automated strategy on one instrument | `broker` (paper / oanda), `strategy`, `params` (JSON), `interval`, `trade_size_usd`, `stop_loss_pct`, `take_profit_pct`, `status` (running / stopped / error), open position (`position_qty`, `entry_price`, `external_trade_id` for OANDA), `last_candle_time`, stats (`realized_pnl`, `trades_closed`, `wins`) |
| `bot_trades` | Every open and close a bot made | `action` (open / close), `reason` (signal / stop_loss / take_profit / manual / closed_on_oanda), `quantity`, `price`, `pnl`, `order_id` (paper) or `external_id` (OANDA trade ID) |
| `bot_logs` | Human-readable activity log | `level`, `message` |

Existing SQLite databases pick up the new tables automatically on start (`create_all`).
