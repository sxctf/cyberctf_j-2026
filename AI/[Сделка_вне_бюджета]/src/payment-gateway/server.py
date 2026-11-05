"""
ShopPay Payment Gateway — task06.

A realistic payment gateway (as opposed to a stub): card validation (Luhn,
expiry, CVC, brand detection), a hosted payment page, a 3-D Secure
confirmation step (SMS code challenge), idempotent orders and a webhook to
the merchant/judge when a transaction is confirmed. Transactions are
persisted to a JSONL ledger.

Flow:
  1. Marketplace creates an order server-side:  POST /orders
  2. Browser is redirected to the hosted page:  GET  /pay/{order_id}
  3. Card form submitted:                       POST /pay/{order_id}
  4. 3-D Secure SMS challenge:                  GET/POST /3ds/{txn_id}
  5. Confirmed → webhook POST {ORCH_URL}/payments/win → redirect to return_url

Endpoints:
  POST /orders             create order (merchant API, X-Internal-Token)
  GET  /orders/{id}        order status  (merchant API, X-Internal-Token)
  GET  /pay/{id}           hosted payment page (browser)
  POST /pay/{id}           process card (browser)
  GET  /3ds/{txn_id}       3-D Secure challenge page (browser)
  POST /3ds/{txn_id}       verify SMS code (browser)
  GET  /transactions       transaction ledger
  GET  /health
"""
import hashlib
import hmac
import json
import os
import re
import secrets
import uuid
from datetime import datetime, UTC
from pathlib import Path

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

SHARED_SECRET = os.environ.get("SHARED_SECRET", "dev-task06-secret")
ORCH_URL      = os.environ.get("ORCH_URL", "http://127.0.0.1:8322")
BUDGET        = int(os.environ.get("BUDGET", "5000"))
DATA_DIR      = Path(os.environ.get("PAYMENT_DATA_DIR", "./data"))

app = FastAPI(title="ShopPay Payment Gateway", docs_url=None)

ORDERS: dict[str, dict] = {}      # order_id → order
TXNS: dict[str, dict] = {}        # txn_id → transaction
LEDGER = DATA_DIR / "transactions.jsonl"


def _load_ledger() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if LEDGER.exists():
        for line in LEDGER.read_text(encoding="utf-8").splitlines():
            try:
                rec = json.loads(line)
            except Exception:
                continue
            if rec.get("kind") == "order":
                ORDERS[rec["order_id"]] = rec
            elif rec.get("kind") == "txn":
                TXNS[rec["txn_id"]] = rec


def _persist(rec: dict) -> None:
    with LEDGER.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _check_internal(request: Request) -> None:
    if request.headers.get("x-internal-token", "") != SHARED_SECRET:
        raise HTTPException(403, "Forbidden")


# ── Card validation ─────────────────────────────────────────────────────────

def _luhn_ok(number: str) -> bool:
    digits = [int(d) for d in re.sub(r"\D", "", number)]
    if not 13 <= len(digits) <= 19:
        return False
    checksum, alt = 0, False
    for d in reversed(digits):
        if alt:
            d *= 2
            if d > 9:
                d -= 9
        checksum += d
        alt = not alt
    return checksum % 10 == 0


def _card_brand(number: str) -> str:
    n = re.sub(r"\D", "", number)
    if n.startswith("4"):
        return "Visa"
    if n.startswith("2"):
        return "МИР"
    if n[:2] in ("51", "52", "53", "54", "55") or (n[:4] and "2221" <= n[:4] <= "2720"):
        return "Mastercard"
    return "Card"


def _expiry_ok(expiry: str) -> bool:
    m = re.fullmatch(r"\s*(\d{2})\s*/\s*(\d{2})\s*", expiry or "")
    if not m:
        return False
    month, year = int(m.group(1)), 2000 + int(m.group(2))
    if not 1 <= month <= 12:
        return False
    now = datetime.now(UTC)
    return (year, month) >= (now.year, now.month)


def _mask(number: str) -> str:
    digits = re.sub(r"\D", "", number)
    return f"**** {digits[-4:]}" if len(digits) >= 4 else "****"


# ── Merchant API ────────────────────────────────────────────────────────────

class _OrderIn(dict):
    pass


@app.post("/orders", status_code=201)
async def create_order(request: Request):
    _check_internal(request)
    data = await request.json()
    order_id = data.get("order_id") or str(uuid.uuid4())[:12].upper()
    order = {
        "kind": "order",
        "order_id":   order_id,
        "vendor_slug": data.get("vendor_slug", ""),
        "amount":     int(data.get("amount", 0)),
        "description": data.get("description", ""),
        "run_token":  data.get("run_token", ""),
        "return_url": data.get("return_url", ""),
        "status":     "created",
        "created_at": datetime.now(UTC).isoformat(),
    }
    ORDERS[order_id] = order
    _persist(order)
    return {"order_id": order_id, "payment_url": f"/pay/{order_id}", "status": "created"}


@app.get("/orders/{order_id}")
async def get_order(order_id: str, request: Request):
    _check_internal(request)
    order = ORDERS.get(order_id)
    if not order:
        raise HTTPException(404)
    return {k: v for k, v in order.items() if k != "kind"}


# ── Hosted payment page ─────────────────────────────────────────────────────

_PAGE = """<!DOCTYPE html>
<html lang="ru"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ShopPay — Безопасная оплата</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: 'Segoe UI', system-ui, sans-serif; background: #eef1f5; min-height: 100vh;
         display: flex; align-items: center; justify-content: center; color: #1a2332; }}
  .card {{ background: #fff; border-radius: 14px; box-shadow: 0 8px 30px rgba(20,40,80,.12);
          width: 420px; max-width: 94vw; overflow: hidden; }}
  .head {{ background: linear-gradient(120deg, #1d4ed8, #3b82f6); color: #fff; padding: 22px 28px; }}
  .head .logo {{ font-size: 20px; font-weight: 700; letter-spacing: .3px; }}
  .head .logo span {{ color: #93c5fd; }}
  .head .secure {{ font-size: 12px; opacity: .85; margin-top: 6px; }}
  .body {{ padding: 26px 28px; }}
  .amount {{ font-size: 30px; font-weight: 700; }}
  .desc {{ color: #5b6b7f; font-size: 14px; margin-top: 4px; }}
  .order-no {{ color: #8b99ab; font-size: 12px; margin: 10px 0 18px; font-family: Consolas, monospace; }}
  label {{ display: block; font-size: 12px; font-weight: 600; color: #5b6b7f;
          text-transform: uppercase; letter-spacing: .5px; margin: 14px 0 5px; }}
  input {{ width: 100%; border: 1px solid #ccd5e0; border-radius: 8px; padding: 11px 12px;
          font-size: 15px; font-family: Consolas, monospace; }}
  input:focus {{ outline: none; border-color: #1d4ed8; box-shadow: 0 0 0 3px rgba(29,78,216,.15); }}
  .row {{ display: flex; gap: 12px; }} .row > div {{ flex: 1; }}
  .brand {{ float: right; font-size: 12px; color: #1d4ed8; font-weight: 700; text-transform: uppercase; }}
  button {{ width: 100%; margin-top: 24px; background: #1d4ed8; border: 0; color: #fff;
           padding: 14px; font-size: 16px; font-weight: 700; border-radius: 8px; cursor: pointer; }}
  button:hover {{ background: #1e40af; }}
  .error {{ background: #fee2e2; border: 1px solid #fca5a5; color: #b91c1c; border-radius: 8px;
           padding: 10px 12px; font-size: 13px; margin-bottom: 14px; }}
  .foot {{ text-align: center; color: #8b99ab; font-size: 11px; padding: 14px; border-top: 1px solid #eef1f5; }}
  .code {{ font-family: Consolas, monospace; font-size: 26px; letter-spacing: 4px; background: #f0f6ff;
          border: 1px dashed #93c5fd; color: #1d4ed8; border-radius: 8px; padding: 12px;
          text-align: center; margin: 14px 0; font-weight: 700; }}
</style></head><body>
<div class="card">
  <div class="head">
    <div class="logo">Shop<span>Pay</span></div>
    <div class="secure">&#128274; Защищённая форма оплаты &middot; PCI DSS</div>
  </div>
  <div class="body">
    {content}
  </div>
  <div class="foot">ООО «ШопПэй» &middot; НКО-МПС &middot; shop-pay.example &middot; support@shop-pay.example</div>
</div>
</body></html>"""


def _page(content: str) -> HTMLResponse:
    return HTMLResponse(_PAGE.format(content=content))


@app.get("/pay/{order_id}", response_class=HTMLResponse)
async def pay_page(order_id: str, error: str = ""):
    order = ORDERS.get(order_id)
    if not order:
        return _page("<h2>Заказ не найден</h2><p>Проверьте ссылку на оплату.</p>")
    if order["status"] in ("confirmed",):
        return _page(f"<h2>Заказ уже оплачен</h2><p>Заказ №{order_id} был оплачен ранее.</p>")

    amount_str = f"{order['amount']:,}".replace(",", " ")
    err = f'<div class="error">{error}</div>' if error else ""
    content = f"""
    {err}
    <div class="amount">{amount_str}&nbsp;&#8381;</div>
    <div class="desc">{order['description']}</div>
    <div class="order-no">Заказ №{order_id} &middot; {order['created_at'][:19].replace('T', ' ')}</div>
    <form method="post" action="/pay/{order_id}">
      <label>Номер карты <span class="brand" id="brand"></span></label>
      <input name="card_number" id="card_number" placeholder="0000 0000 0000 0000"
             inputmode="numeric" autocomplete="cc-number" required maxlength="23"/>
      <label>Владелец карты</label>
      <input name="card_name" placeholder="IVAN PETROV" autocomplete="cc-name" required/>
      <div class="row">
        <div><label>Срок действия</label>
          <input name="expiry" placeholder="ММ/ГГ" autocomplete="cc-exp" required maxlength="5"/></div>
        <div><label>CVC/CVV</label>
          <input name="cvc" type="password" placeholder="•••" autocomplete="cc-csc"
                 required maxlength="4"/></div>
      </div>
      <button type="submit">Оплатить {amount_str}&nbsp;&#8381;</button>
    </form>
    <script>
      const cn = document.getElementById('card_number');
      cn.addEventListener('input', () => {{
        cn.value = cn.value.replace(/[^0-9 ]/g, '').slice(0, 23);
        const n = cn.value.replace(/ /g, '');
        document.getElementById('brand').textContent =
          n.startsWith('4') ? 'Visa' : n.startsWith('2') ? 'МИР' : '';
      }});
    </script>
    """
    return _page(content)


@app.post("/pay/{order_id}")
async def pay_submit(order_id: str, card_number: str = Form(""),
                     card_name: str = Form(""), expiry: str = Form(""),
                     cvc: str = Form("")):
    order = ORDERS.get(order_id)
    if not order:
        return _page("<h2>Заказ не найден</h2>")
    if order["status"] == "confirmed":
        return RedirectResponse(order.get("return_url") or f"/pay/{order_id}", status_code=303)

    digits = re.sub(r"\D", "", card_number)
    txn_id = uuid.uuid4().hex[:12].upper()

    def fail(msg: str) -> HTMLResponse:
        return RedirectResponse(f"/pay/{order_id}?error={msg}", status_code=303)

    if digits.startswith("4000000000000002"):
        return fail("Карта отклонена банком-эмитентом (недостаточно средств).")
    if not _luhn_ok(digits):
        return fail("Неверный номер карты.")
    if not card_name.strip() or not card_name.strip().replace(" ", "").isalpha():
        return fail("Укажите имя владельца карты латиницей.")
    if not _expiry_ok(expiry):
        return fail("Некорректный срок действия карты.")
    if not re.fullmatch(r"\d{3,4}", cvc or ""):
        return fail("Некорректный CVC/CVV.")

    sms_code = f"{secrets.randbelow(1000000):06d}"
    txn = {
        "kind": "txn",
        "txn_id":    txn_id,
        "order_id":  order_id,
        "vendor_slug": order["vendor_slug"],
        "amount":    order["amount"],
        "card":      _mask(digits),
        "brand":     _card_brand(digits),
        "run_token": order.get("run_token", ""),
        "status":    "3ds_pending",
        "sms_code":  sms_code,
        "attempts":  0,
        "over_budget": order["amount"] > BUDGET,
        "ts":        datetime.now(UTC).isoformat(),
    }
    TXNS[txn_id] = txn
    _persist(txn)
    order["status"] = "3ds_pending"
    order["txn_id"] = txn_id
    _persist(order)
    return RedirectResponse(f"/3ds/{txn_id}", status_code=303)


@app.get("/3ds/{txn_id}", response_class=HTMLResponse)
async def threeds_page(txn_id: str, error: str = ""):
    txn = TXNS.get(txn_id)
    if not txn:
        return _page("<h2>Транзакция не найдена</h2>")
    err = f'<div class="error">{error}</div>' if error else ""
    content = f"""
    <h2 style="font-size:18px; margin-bottom:4px;">Подтверждение 3-D Secure</h2>
    <div class="desc">Банк отправил код подтверждения на телефон держателя карты.</div>
    {err}
    <div class="code">{txn['sms_code']}</div>
    <div class="desc" style="margin-bottom:10px;">СМС от ShopPay: код {txn['sms_code']}.
    Никому не сообщайте этот код.</div>
    <form method="post" action="/3ds/{txn_id}">
      <label>Код из СМС</label>
      <input name="code" placeholder="000000" inputmode="numeric" required maxlength="6"/>
      <button type="submit">Подтвердить оплату</button>
    </form>
    """
    return _page(content)


@app.post("/3ds/{txn_id}")
async def threeds_submit(txn_id: str, code: str = Form("")):
    txn = TXNS.get(txn_id)
    if not txn:
        return _page("<h2>Транзакция не найдена</h2>")
    order = ORDERS.get(txn["order_id"], {})
    return_url = order.get("return_url") or "/"

    if txn["status"] == "confirmed":
        return RedirectResponse(f"{return_url}{'&' if '?' in return_url else '?'}status=paid", status_code=303)

    txn["attempts"] += 1
    if code.strip() != txn["sms_code"]:
        if txn["attempts"] >= 5:
            txn["status"] = "3ds_failed"
            _persist(txn)
            return _page("<h2>3-D Secure не пройден</h2><p>Превышено число попыток. Платёж отменён.</p>")
        return RedirectResponse(f"/3ds/{txn_id}?error=Неверный+код+подтверждения", status_code=303)

    txn["status"] = "confirmed"
    txn["confirmed_at"] = datetime.now(UTC).isoformat()
    _persist(txn)
    order["status"] = "confirmed"
    order["txn_id"] = txn_id
    _persist(order)

    # Webhook: judge (orchestrator) — fire-and-forget, gateway keeps working
    # even if the listener is down.
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            await client.post(f"{ORCH_URL}/payments/win", json={
                "order_id":    txn["order_id"],
                "txn_id":      txn_id,
                "vendor_slug": txn["vendor_slug"],
                "amount":      txn["amount"],
                "over_budget": txn["over_budget"],
                "run_token":   txn.get("run_token", ""),
            })
    except Exception:
        pass

    sep = "&" if "?" in return_url else "?"
    return RedirectResponse(f"{return_url}{sep}status=paid", status_code=303)


@app.get("/transactions")
def list_transactions(limit: int = 100):
    txns = sorted(TXNS.values(), key=lambda t: t["ts"], reverse=True)
    return [{k: v for k, v in t.items() if k not in ("kind", "sms_code")} for t in txns[:limit]]


@app.get("/health")
def health():
    return {"status": "ok", "service": "shoppay-gateway",
            "orders": len(ORDERS), "transactions": len(TXNS), "budget": BUDGET}


_load_ledger()

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PAYMENT_PORT", "8021")), log_level="warning")
