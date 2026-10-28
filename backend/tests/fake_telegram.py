"""A tiny stand-in for the Telegram Bot API, for trying alerts locally:
    uvicorn tests.fake_telegram:app --port 8098
    TELEGRAM_BOT_TOKEN=x TELEGRAM_API_URL=http://localhost:8098 uvicorn app.main:app
Every /start message the app asks about is treated as sent; GET /sent lists the messages.
"""
from fastapi import FastAPI, Request

app = FastAPI()
sent: list[dict] = []
codes: list[str] = []


@app.post("/bot{token}/getMe")
def get_me(token: str):
    return {"ok": True, "result": {"username": "moneyfx_alerts_bot"}}


@app.post("/bot{token}/getUpdates")
def get_updates(token: str):
    return {"ok": True, "result": [{"update_id": i, "message": {"text": f"/start {c}", "chat": {"id": 5550000 + i}}}
                                   for i, c in enumerate(codes)]}


@app.post("/bot{token}/sendMessage")
async def send_message(token: str, request: Request):
    sent.append(await request.json())
    return {"ok": True, "result": {}}


@app.post("/press-start/{code}")
def press_start(code: str):
    codes.append(code)
    return {"ok": True}


@app.get("/sent")
def list_sent():
    return sent
