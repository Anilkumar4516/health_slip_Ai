import io
from fastapi import APIRouter, Depends, HTTPException, Query, Response, Request
from sqlalchemy.orm import Session
from typing import List, Optional
from app.database import get_db
from app.models.receipt import Bill, Receipt
from app.schemas.receipt import HealthSlipCreate, HealthSlipResponse, HealthSlipSummary
from app.schemas.ai import AIExtractRequest, AIExtractedResponse
from app.services.receipt_service import ReceiptService
from app.services.ai_service import AIService
from app.services.pdf_service import PDFService
from app.models.verification import AuditEvent

router = APIRouter(prefix="/api/receipts", tags=["Receipts"])

@router.post("/ai-parse", response_model=AIExtractedResponse)
def parse_clinical_notes_with_ai(req: AIExtractRequest, db: Session = Depends(get_db)):
    """
    AI-Assisted clinical extraction:
    Transforms unstructured doctor's clinical notes into structured billing items,
    medication schedules with dosage timings, and patient safety warnings.
    """
    try:
        extracted = AIService.parse_clinical_notes(req)
        return extracted
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI Parsing failed: {str(e)}")

@router.post("", response_model=HealthSlipResponse)
def create_receipt(slip_data: HealthSlipCreate, request: Request, db: Session = Depends(get_db)):
    """
    Create an official medical receipt / health slip with cryptographic HMAC verification seal
    directly in MySQL healthslip_prod database.
    """
    try:
        slip_dict = ReceiptService.create_health_slip(db, slip_data)
        return HealthSlipResponse(**slip_dict)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Failed to create receipt in healthslip_prod: {str(e)}")

@router.get("", response_model=List[HealthSlipSummary])
def list_receipts(
    search: Optional[str] = Query(None, description="Search by patient name, phone, or slip number"),
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """List recent health slips from MySQL healthslip_prod database"""
    receipts = db.query(Receipt).order_by(Receipt.created_at.desc()).limit(limit).all()
    summaries = []
    for r in receipts:
        bill = r.bill
        patient = bill.patient if bill else None
        practitioner = bill.prescription.practitioner if bill and bill.prescription else None

        p_name = patient.full_name if patient else "Rajesh Kumar"
        p_phone = patient.phone if patient else "+91 98765 43210"

        if search:
            s_low = search.strip().lower()
            if s_low not in r.receipt_number.lower() and s_low not in p_name.lower() and s_low not in p_phone:
                continue

        summaries.append(HealthSlipSummary(
            id=r.id,
            slip_number=r.receipt_number,
            visit_date=r.created_at,
            patient_name=p_name,
            patient_phone=p_phone,
            doctor_name=practitioner.name if practitioner else "Dr. K. S. Rao, M.B.B.S., M.D.",
            diagnosis=bill.prescription.diagnosis if bill and bill.prescription else "General Consultation",
            grand_total=r.amount_paid_cents / 100.0,
            payment_status="PAID" if r.payment_status == "SUCCESS" else r.payment_status,
            status=bill.status if bill else "ACTIVE",
            created_at=r.created_at
        ))
    return summaries

@router.get("/{slip_id}", response_model=HealthSlipResponse)
def get_receipt_details(slip_id: int, db: Session = Depends(get_db)):
    """Fetch complete details of a single receipt from MySQL healthslip_prod"""
    receipt = db.query(Receipt).filter((Receipt.id == slip_id) | (Receipt.bill_id == slip_id)).first()
    if not receipt:
        raise HTTPException(status_code=404, detail="Medical receipt not found.")

    slip_dict = ReceiptService.build_slip_view_model(receipt.bill, receipt)
    return HealthSlipResponse(**slip_dict)

@router.get("/{slip_id}/pdf")
def download_receipt_pdf(slip_id: int, db: Session = Depends(get_db)):
    """Generate and stream PDF receipt from MySQL healthslip_prod"""
    receipt = db.query(Receipt).filter((Receipt.id == slip_id) | (Receipt.bill_id == slip_id)).first()
    if not receipt:
        raise HTTPException(status_code=404, detail="Receipt not found")

    slip_dict = ReceiptService.build_slip_view_model(receipt.bill, receipt)
    pdf_bytes = PDFService.generate_receipt_pdf(slip_dict)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=HealthSlip_{receipt.receipt_number}.pdf"}
    )
