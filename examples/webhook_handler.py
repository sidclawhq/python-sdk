"""FastAPI webhook verification example."""

# pip install fastapi uvicorn sidclaw

from sidclaw import verify_webhook_signature

# from fastapi import FastAPI, Request, HTTPException
# app = FastAPI()
#
# WEBHOOK_SECRET = "whsec_your_secret"
#
# @app.post("/webhook")
# async def handle_webhook(request: Request):
#     body = await request.body()
#     signature = request.headers.get("X-Webhook-Signature", "")
#
#     if not verify_webhook_signature(body, signature, WEBHOOK_SECRET):
#         raise HTTPException(status_code=401, detail="Invalid signature")
#
#     payload = await request.json()
#     event_type = payload.get("event_type")
#
#     if event_type == "approval.approved":
#         print(f"Approval granted: {payload}")
#     elif event_type == "approval.denied":
#         print(f"Approval denied: {payload}")
#
#     return {"ok": True}

print("Webhook handler example — install fastapi and uvicorn to run")
