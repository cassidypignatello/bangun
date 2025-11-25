"""
Payment processing and webhook endpoints
"""

from datetime import datetime

from fastapi import APIRouter, HTTPException, Request, status

from app.config import get_settings
from app.integrations.midtrans import create_payment_transaction, verify_signature
from app.integrations.supabase import (
    save_payment,
    update_payment_status,
)
from app.middleware.rate_limit import HEAVY_LIMIT, limiter
from app.schemas.payment import MidtransWebhook, UnlockRequest, UnlockResponse

router = APIRouter()


@router.post("/unlock", status_code=status.HTTP_200_OK)
@limiter.limit(HEAVY_LIMIT)
async def unlock_worker_details(request: Request, unlock_req: UnlockRequest):
    """
    Create payment transaction to unlock worker details

    Args:
        unlock_req: Unlock request with worker ID and payment method

    Returns:
        UnlockResponse: Payment URL and transaction details
    """
    # Fixed unlock price: 50,000 IDR
    unlock_price_idr = 50000

    try:
        # Create Midtrans transaction
        transaction = await create_payment_transaction(
            worker_id=unlock_req.worker_id,
            amount_idr=unlock_price_idr,
            payment_method=unlock_req.payment_method.value,
            return_url=unlock_req.return_url,
        )

        # Save transaction to database
        transaction_data = {
            "transaction_id": transaction["transaction_id"],
            "order_id": transaction["order_id"],
            "worker_id": unlock_req.worker_id,
            "amount_idr": unlock_price_idr,
            "status": "pending",
            "payment_method": unlock_req.payment_method.value,
            "payment_url": transaction["payment_url"],
            "created_at": datetime.utcnow().isoformat(),
        }

        await save_payment(transaction_data)

        return UnlockResponse(
            transaction_id=transaction["transaction_id"],
            payment_url=transaction["payment_url"],
            amount_idr=unlock_price_idr,
            expires_at=datetime.utcnow(),  # Should be calculated from Midtrans
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Payment creation failed: {str(e)}",
        )


@router.post("/webhooks/midtrans", status_code=status.HTTP_200_OK)
async def midtrans_webhook(webhook: MidtransWebhook):
    """
    Handle Midtrans payment webhook notifications

    Verifies signature and updates transaction status.

    Args:
        webhook: Midtrans webhook payload

    Returns:
        dict: Webhook processing result
    """
    settings = get_settings()

    # Verify webhook signature
    is_valid = verify_signature(
        order_id=webhook.order_id,
        status_code=webhook.status_code,
        gross_amount=webhook.gross_amount,
        signature=webhook.signature_key,
        server_key=settings.midtrans_server_key,
    )

    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid signature"
        )

    # Map Midtrans status to our internal status
    status_mapping = {
        "capture": "completed",
        "settlement": "completed",
        "pending": "pending",
        "deny": "failed",
        "cancel": "cancelled",
        "expire": "expired",
        "failure": "failed",
    }

    internal_status = status_mapping.get(webhook.transaction_status, "unknown")

    # Update transaction in database
    try:
        await update_payment_status(
            webhook.order_id,
            internal_status,
            midtrans_transaction_id=webhook.transaction_id,
            payment_type=webhook.payment_type,
            fraud_status=webhook.fraud_status,
            updated_at=datetime.utcnow().isoformat(),
        )

        return {
            "status": "processed",
            "order_id": webhook.order_id,
            "internal_status": internal_status,
            "ok": True,
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Webhook processing failed: {str(e)}",
        )
