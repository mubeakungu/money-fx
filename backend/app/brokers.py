"""Where bots get prices and send orders.

PaperBroker trades the user's money fx account against the mock feed.
OandaBroker trades a real OANDA account (practice or live) through the v20 REST API,
configured with OANDA_API_TOKEN, OANDA_ACCOUNT_ID and OANDA_ENV (practice | live).
"""
import os
from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal

import httpx
from sqlalchemy.orm import Session

from . import models
from .market import feed
from .trading import place_order

INTERVAL_SECONDS = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600, "4h": 14400, "1d": 86400}


class BrokerError(Exception):
    pass


@dataclass
class Fill:
    price: Decimal
    quantity: Decimal
    pnl: Decimal | None = None
    order_id: int | None = None
    external_id: str | None = None
    reason: str | None = None


def stop_prices(entry: Decimal, bot: models.Bot) -> tuple[Decimal | None, Decimal | None]:
    sl = entry * (1 - Decimal(str(bot.stop_loss_pct)) / 100) if bot.stop_loss_pct else None
    tp = entry * (1 + Decimal(str(bot.take_profit_pct)) / 100) if bot.take_profit_pct else None
    return sl, tp


class PaperBroker:
    name = "paper"
    symbols = None  # every money fx instrument

    def closed_candles(self, symbol: str, interval: str, limit: int) -> list[dict]:
        return feed.candles(symbol, INTERVAL_SECONDS[interval], limit + 1)[:-1]

    def quote(self, symbol: str) -> dict:
        q = feed.quote(symbol)
        return {"bid": q["bid"], "ask": q["ask"]}

    def units_for(self, db: Session, symbol: str, usd: Decimal, price: Decimal) -> Decimal:
        inst = db.query(models.Instrument).filter_by(symbol=symbol).one()
        qty = (usd / price).quantize(Decimal(1).scaleb(-inst.qty_decimals), rounding=ROUND_DOWN)
        if qty < inst.min_qty:
            raise BrokerError(f"Trade size too small: minimum is {inst.min_qty.normalize():f} {symbol}")
        return qty

    def _order(self, db, bot, side, qty) -> models.Order:
        account = db.get(models.Account, bot.account_id)
        order = place_order(db, account, bot.symbol, side, "market", qty, None)
        if order.status != "filled":
            raise BrokerError(order.reject_reason or f"Order {order.status}")
        return order

    def open_long(self, db: Session, bot: models.Bot, qty: Decimal) -> Fill:
        o = self._order(db, bot, "buy", qty)
        return Fill(price=o.filled_price, quantity=qty, order_id=o.id)

    def close_long(self, db: Session, bot: models.Bot, reason: str) -> Fill:
        o = self._order(db, bot, "sell", bot.position_qty)
        return Fill(price=o.filled_price, quantity=o.quantity, order_id=o.id, reason=reason,
                    pnl=(o.filled_price - bot.entry_price) * o.quantity)

    def sync(self, db: Session, bot: models.Bot) -> Fill | None:
        """Paper stops live here: close when the bid reaches the stop-loss or take-profit."""
        sl, tp = stop_prices(bot.entry_price, bot)
        bid = self.quote(bot.symbol)["bid"]
        if sl is not None and bid <= sl:
            return self.close_long(db, bot, "stop_loss")
        if tp is not None and bid >= tp:
            return self.close_long(db, bot, "take_profit")
        return None


# money fx symbol -> OANDA instrument
OANDA_SYMBOLS = {
    "EURUSD": "EUR_USD", "GBPUSD": "GBP_USD", "AUDUSD": "AUD_USD", "NZDUSD": "NZD_USD",
    "XAUUSD": "XAU_USD", "XAGUSD": "XAG_USD", "WTIUSD": "WTICO_USD",
}
OANDA_GRANULARITY = {"1m": "M1", "5m": "M5", "15m": "M15", "1h": "H1", "4h": "H4", "1d": "D"}
OANDA_HOSTS = {"practice": "https://api-fxpractice.oanda.com", "live": "https://api-fxtrade.oanda.com"}


class OandaBroker:
    name = "oanda"
    symbols = list(OANDA_SYMBOLS)

    def __init__(self, token: str, account_id: str, env: str = "practice", transport=None):
        if env not in OANDA_HOSTS:
            raise BrokerError("OANDA_ENV must be 'practice' or 'live'")
        self.env = env
        self.account_id = account_id
        self.http = httpx.Client(base_url=OANDA_HOSTS[env], timeout=15, transport=transport, headers={
            "Authorization": f"Bearer {token}", "Accept-Datetime-Format": "UNIX"})
        self._instruments: dict | None = None

    def _req(self, method: str, path: str, **kw) -> dict:
        try:
            r = self.http.request(method, path, **kw)
        except httpx.HTTPError as e:
            raise BrokerError(f"Could not reach OANDA: {e}") from e
        data = r.json() if r.content else {}
        if r.status_code >= 400:
            raise BrokerError(f"OANDA {r.status_code}: {data.get('errorMessage', r.text[:200])}")
        return data

    def _acct(self, path: str = "") -> str:
        return f"/v3/accounts/{self.account_id}{path}"

    @staticmethod
    def instrument(symbol: str) -> str:
        if symbol not in OANDA_SYMBOLS:
            raise BrokerError(f"{symbol} is not available on OANDA. Choose one of: {', '.join(OANDA_SYMBOLS)}")
        return OANDA_SYMBOLS[symbol]

    def instruments(self) -> dict:
        if self._instruments is None:
            data = self._req("GET", self._acct("/instruments"))
            self._instruments = {i["name"]: i for i in data["instruments"]}
        return self._instruments

    def _spec(self, symbol: str) -> dict:
        name = self.instrument(symbol)
        spec = self.instruments().get(name)
        if spec is None:
            raise BrokerError(f"{name} is not tradeable on this OANDA account")
        return spec

    def _price_str(self, symbol: str, price: Decimal) -> str:
        dp = int(self._spec(symbol)["displayPrecision"])
        return str(price.quantize(Decimal(1).scaleb(-dp)))

    def summary(self) -> dict:
        return self._req("GET", self._acct("/summary"))["account"]

    def closed_candles(self, symbol: str, interval: str, limit: int) -> list[dict]:
        data = self._req("GET", f"/v3/instruments/{self.instrument(symbol)}/candles",
                         params={"granularity": OANDA_GRANULARITY[interval], "count": min(limit + 1, 5000), "price": "M"})
        return [{"time": int(float(c["time"])), "open": float(c["mid"]["o"]), "high": float(c["mid"]["h"]),
                 "low": float(c["mid"]["l"]), "close": float(c["mid"]["c"])}
                for c in data["candles"] if c.get("complete")][-limit:]

    def quote(self, symbol: str) -> dict:
        p = self._req("GET", self._acct("/pricing"), params={"instruments": self.instrument(symbol)})["prices"][0]
        return {"bid": Decimal(p["bids"][0]["price"]), "ask": Decimal(p["asks"][0]["price"])}

    def units_for(self, db: Session, symbol: str, usd: Decimal, price: Decimal) -> Decimal:
        spec = self._spec(symbol)
        qty = (usd / price).quantize(Decimal(1).scaleb(-int(spec["tradeUnitsPrecision"])), rounding=ROUND_DOWN)
        if qty < Decimal(spec["minimumTradeSize"]):
            raise BrokerError(f"Trade size too small: OANDA minimum for {symbol} is {spec['minimumTradeSize']} units")
        return qty

    def open_long(self, db: Session, bot: models.Bot, qty: Decimal) -> Fill:
        # Stops are placed relative to the current ask and held by OANDA, so they work even if this server is down.
        sl, tp = stop_prices(self.quote(bot.symbol)["ask"], bot)
        order = {"type": "MARKET", "instrument": self.instrument(bot.symbol), "units": str(qty),
                 "timeInForce": "FOK", "positionFill": "DEFAULT"}
        if sl is not None:
            order["stopLossOnFill"] = {"price": self._price_str(bot.symbol, sl)}
        if tp is not None:
            order["takeProfitOnFill"] = {"price": self._price_str(bot.symbol, tp)}
        data = self._req("POST", self._acct("/orders"), json={"order": order})
        fill = data.get("orderFillTransaction")
        if not fill or not fill.get("tradeOpened"):
            reason = (data.get("orderCancelTransaction") or {}).get("reason", "order did not fill")
            raise BrokerError(f"OANDA rejected the order: {reason}")
        t = fill["tradeOpened"]
        return Fill(price=Decimal(t.get("price", fill["price"])), quantity=Decimal(t["units"]), external_id=t["tradeID"])

    def close_long(self, db: Session, bot: models.Bot, reason: str) -> Fill:
        data = self._req("PUT", self._acct(f"/trades/{bot.external_trade_id}/close"), json={"units": "ALL"})
        fill = data.get("orderFillTransaction")
        if not fill:
            raise BrokerError("OANDA did not close the trade")
        return Fill(price=Decimal(fill["price"]), quantity=bot.position_qty, pnl=Decimal(fill.get("pl", "0")),
                    external_id=bot.external_trade_id, reason=reason)

    def sync(self, db: Session, bot: models.Bot) -> Fill | None:
        """Notice when OANDA closed the trade by itself (stop-loss, take-profit, or you closed it)."""
        trade = self._req("GET", self._acct(f"/trades/{bot.external_trade_id}"))["trade"]
        if trade["state"] == "OPEN":
            return None
        price = Decimal(trade.get("averageClosePrice", trade["price"]))
        sl, tp = stop_prices(Decimal(trade["price"]), bot)
        if sl is not None and price <= sl * Decimal("1.001"):
            reason = "stop_loss"
        elif tp is not None and price >= tp * Decimal("0.999"):
            reason = "take_profit"
        else:
            reason = "closed_on_oanda"
        return Fill(price=price, quantity=bot.position_qty, pnl=Decimal(trade.get("realizedPL", "0")),
                    external_id=bot.external_trade_id, reason=reason)


_paper = PaperBroker()
_oanda: OandaBroker | None = None


def oanda_configured() -> bool:
    return bool(os.getenv("OANDA_API_TOKEN") and os.getenv("OANDA_ACCOUNT_ID"))


def get_broker(name: str):
    global _oanda
    if name == "paper":
        return _paper
    if name == "oanda":
        if _oanda is not None:
            return _oanda
        if not oanda_configured():
            raise BrokerError("OANDA is not connected. Set OANDA_API_TOKEN and OANDA_ACCOUNT_ID and restart the API.")
        _oanda = OandaBroker(os.environ["OANDA_API_TOKEN"], os.environ["OANDA_ACCOUNT_ID"],
                             os.getenv("OANDA_ENV", "practice"))
        return _oanda
    raise BrokerError(f"Unknown broker {name}")


def set_oanda_broker(broker: OandaBroker | None):
    """Used by tests to inject a broker with a fake transport."""
    global _oanda
    _oanda = broker
