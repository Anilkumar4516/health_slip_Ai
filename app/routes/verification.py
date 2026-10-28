from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas.receipt import PublicVerificationResponse
from app.services.receipt_service import ReceiptService
from app.models.verification import AuditLog

router = APIRouter(prefix="/api/verify", tags=["Public Verification"])

@router.get("/{slip_number}", response_model=PublicVerificationResponse)
def verify_receipt_qr(slip_number: str, request: Request, db: Session = Depends(get_db)):
    """
    Public receipt authenticity verification endpoint.
    Verifies cryptographic HMAC signature against stored records without exposing sensitive medical data.
    """
    result = ReceiptService.verify_slip_authenticity(db, slip_number)

    client_ip = request.client.host if request.client else "127.0.0.1"
    db.add(AuditLog(
        action="QR_SCANNED",
        resource_type="receipts",
        resource_id=slip_number,
        ip_address=client_ip,
        payload_after={"status": "SUCCESS" if result["is_valid"] else "FAILED", "tamper": result["tamper_proof_status"]}
    ))
    db.commit()

    return PublicVerificationResponse(**result)

@router.get("/{slip_number}/qr")
def get_receipt_qr_image(slip_number: str):
    """Generate and stream local QR code image without third-party dependencies"""
    import io
    import qrcode
    from fastapi.responses import Response

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=5,
        border=2,
    )
    qr.add_data(f"VERIFY:{slip_number}")
    qr.make(fit=True)
    img = qr.make_image(fill_color="#1E3A8A", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return Response(content=buf.getvalue(), media_type="image/png")
