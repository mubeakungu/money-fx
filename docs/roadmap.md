# Roadmap: must-haves vs nice-to-haves

## MVP must-haves (built)

These five are the minimum for the core loop of sign up, fund, trade, see results. Remove any one and the product does not work.

| Feature | Why it is a must-have | Status |
|---|---|---|
| Account management | Nothing else can be tied to a user without it | Done: sign up, login, profile, password change |
| Wallet | Orders need a balance to draw from | Done: USD wallet, simulated deposit/withdraw, ledger |
| Order placement | It is the product | Done: market and limit, buy and sell, cancel |
| Portfolio tracking | Users must see what they own and whether they are up or down | Done: holdings, P&L, allocation |
| Real-time charts | Users will not trade without seeing price | Done: live candlesticks from the mock feed |

## Must-have before real money

Required before any real user deposits real funds. These are legal and safety requirements, not features.

1. **Live market data** for every asset class (e.g. Polygon or Twelve Data for stocks/forex/commodities, an exchange API such as Binance or Coinbase for crypto).
2. **Real execution venue / broker**: today orders fill against simulated prices. You need a liquidity provider or broker API (e.g. Alpaca for US stocks, a prime broker or FX LP for forex, an exchange for crypto), or a licence to act as market maker.
3. **Payment provider** for deposits and withdrawals (Stripe, M-Pesa / Daraja, bank rails) with webhooks instead of instant fake settlement.
4. **KYC / AML**: identity verification (e.g. Sumsub, Onfido), sanctions screening, transaction monitoring.
5. **Licensing**: a forex/CFD broker, crypto exchange and stock broker are each regulated separately (e.g. CMA in Kenya, FCA, CySEC). This decides which markets you can legally offer and where.
6. **Security hardening**: email verification, 2FA, password reset, rate limiting, refresh tokens, audit log, secrets management, Postgres with row locking for balance updates.

## Nice-to-haves (after launch)

- ~~Stop-loss and take-profit orders~~ (done for bots)
- Leverage, margin and short selling (common for forex and CFDs, heavily regulated)
- Multi-currency wallets (hold EUR, KES, BTC directly) and FX conversion
- Watchlists and price alerts (push/email)
- Technical indicators and drawing tools on charts
- Order book / depth view for crypto
- Portfolio performance history chart and downloadable statements
- Demo vs live account toggle
- Mobile app (React Native can reuse much of the frontend logic)
- Social / copy trading
- Admin back office: user management, KYC review, manual balance adjustments, reporting

## Trading bot (added)

Bots run strategies automatically in paper mode or on an OANDA account; see README. Next steps:
- ~~Short selling for bots~~ (done: long only, short only, or both ways)
- ~~Position sizing by risk per trade, daily loss limit~~ (done)
- Trailing stop-loss
- Telegram or email alerts on every bot trade
- Parameter sweep: backtest a grid of settings and rank them
- Run the bot 24/7 on a small cloud server (it must stay on to act on signals)
