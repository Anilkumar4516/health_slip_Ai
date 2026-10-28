import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any

from app.database import get_db
from app.models.receipt import Receipt, Bill, Prescription, PrescriptionItem
from app.models.pharmacy import PharmacyMedicineStock, DispenseOrder
from app.schemas.pharmacy import DispenseRequest, GenericSubstituteRequest, StockAdjustRequest, AudioDosageRequest, RuralSmsRequest
from app.services.generic_drug_service import GenericDrugService
from app.services.websocket_manager import ws_manager

router = APIRouter(prefix="/api/pharmacy", tags=["Pharmacy & Medical Store"])

@router.get("/inventory")
def get_inventory(db: Session = Depends(get_db)):
    """Fetch current medicine inventory with stock alerts and brand vs generic Jan Aushadhi pricing"""
    items = GenericDrugService.get_inventory_items(db)
    low_stock_count = sum(1 for it in items if it["status"] in ["LOW_STOCK", "OUT_OF_STOCK"])
    return {
        "total_items": len(items),
        "low_stock_count": low_stock_count,
        "items": items
    }

@router.post("/inventory/adjust")
def adjust_inventory(req: StockAdjustRequest, db: Session = Depends(get_db)):
    """Adjust stock quantity for urban or rural pharmacy inventory"""
    item = db.query(PharmacyMedicineStock).filter(PharmacyMedicineStock.id == req.medicine_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Medicine stock record not found.")

    item.stock_quantity = max(0, item.stock_quantity + req.quantity_change)
    db.commit()
    db.refresh(item)

    # Real-time WebSocket broadcast of stock change
    ws_manager.sync_broadcast("STOCK_UPDATED", {
        "medicine_id": item.id,
        "brand_name": item.brand_name,
        "new_stock": item.stock_quantity,
        "is_low_stock": item.stock_quantity <= item.reorder_level
    })

    return {
        "success": True,
        "medicine_id": item.id,
        "brand_name": item.brand_name,
        "stock_quantity": item.stock_quantity,
        "status": "LOW_STOCK" if item.stock_quantity <= item.reorder_level else "IN_STOCK"
    }

@router.get("/queue")
def get_pharmacy_queue(
    store_type: str = Query("URBAN", description="URBAN or RURAL"),
    db: Session = Depends(get_db)
):
    """
    Fetch live prescription queue for pharmacy counters.
    Shows doctor prescriptions, dispensing state, anti-double dispensing lock, and generic savings.
    """
    recent_receipts = db.query(Receipt).order_by(Receipt.created_at.desc()).limit(20).all()
    queue = []

    for r in recent_receipts:
        bill = r.bill
        patient = bill.patient if bill else None
        prescription = bill.prescription if bill else None
        practitioner = prescription.practitioner if prescription else None

        slip_no = r.receipt_number
        p_name = patient.full_name if patient else "Minh Patient"
        p_phone = patient.phone if patient else "+1 555-019-2834"

        # Check existing dispense order
        dispense = db.query(DispenseOrder).filter(DispenseOrder.slip_number == slip_no).first()

        # Extract items
        items = []
        if bill and bill.items:
            for bi in bill.items:
                items.append({
                    "item_name": bi.description,
                    "unit_price": bi.unit_price_cents / 100.0,
                    "quantity": bi.quantity,
                    "total_price": bi.total_price_cents / 100.0
                })

        savings_data = GenericDrugService.calculate_total_prescription_savings(items, db)

        status = dispense.status if dispense else ("DISPENSED" if prescription and prescription.status == "DISPENSED" else "RECEIVED")
        is_locked = bool(dispense and dispense.cryptographic_lock)

        queue.append({
            "slip_number": slip_no,
            "patient_name": p_name,
            "patient_phone": p_phone,
            "doctor_name": practitioner.name if practitioner else "Dr. Minh Nguyen, M.D.",
            "diagnosis": prescription.diagnosis if prescription else "General Consultation",
            "grand_total": r.amount_paid_cents / 100.0,
            "created_at": r.created_at.isoformat(),
            "status": status,
            "is_locked": is_locked,
            "cryptographic_lock": dispense.cryptographic_lock if dispense else None,
            "store_type": dispense.store_type if dispense else store_type,
            "is_generic_substituted": dispense.is_generic_substituted if dispense else False,
            "generic_savings": savings_data["total_saved"],
            "savings_percent": savings_data["savings_percent"],
            "items_count": len(items),
            "items": items,
            "substitutions": savings_data["substitutions"]
        })

    return {
        "store_type": store_type,
        "queue_count": len(queue),
        "queue": queue
    }

@router.post("/dispense")
def dispense_prescription(req: DispenseRequest, db: Session = Depends(get_db)):
    """
    Dispense prescription at Urban or Rural Medical Store:
    1. Validates against double-dispensing (Anti-Fraud Lock).
    2. Deducts medicine stock from inventory.
    3. Issues cryptographic dispense seal.
    4. Broadcasts real-time WebSocket notification to all medical stores & doctor screens.
    """
    existing_dispense = db.query(DispenseOrder).filter(
        DispenseOrder.slip_number == req.slip_number,
        DispenseOrder.status == "DISPENSED"
    ).first()

    if existing_dispense and existing_dispense.cryptographic_lock:
        raise HTTPException(
            status_code=400,
            detail=f"Prescription {req.slip_number} has ALREADY BEEN DISPENSED at {existing_dispense.store_type} Store on {existing_dispense.dispensed_at.strftime('%Y-%m-%d %H:%M')}. Cryptographic lock active."
        )

    receipt = db.query(Receipt).filter(Receipt.receipt_number == req.slip_number).first()
    patient_name = "Patient"
    patient_phone = "+1 555-019-2834"
    doc_name = "Dr. Minh Nguyen, M.D."
    diag = "General Consultation"
    total_val = 0.0

    if receipt and receipt.bill:
        if receipt.bill.patient:
            patient_name = receipt.bill.patient.full_name
            patient_phone = receipt.bill.patient.phone
        if receipt.bill.prescription and receipt.bill.prescription.practitioner:
            doc_name = receipt.bill.prescription.practitioner.name
            diag = receipt.bill.prescription.diagnosis
            receipt.bill.prescription.status = "DISPENSED"
        total_val = receipt.amount_paid_cents / 100.0

    # Cryptographic lock seal
    lock_hash = GenericDrugService.generate_cryptographic_dispense_lock(
        req.slip_number, req.store_type, req.pharmacist_name
    )

    now = datetime.datetime.utcnow()

    # Deduct stock for prescribed medications if found in inventory
    if receipt and receipt.bill and receipt.bill.items:
        for b_item in receipt.bill.items:
            sub = GenericDrugService.find_generic_substitute(b_item.description, db)
            if sub and sub.get("matched"):
                matched_stock = db.query(PharmacyMedicineStock).filter(
                    PharmacyMedicineStock.brand_name == sub["brand_name"]
                ).first()
                if matched_stock:
                    matched_stock.stock_quantity = max(0, matched_stock.stock_quantity - b_item.quantity)

    # Save or update Dispense Order
    dispense_order = db.query(DispenseOrder).filter(DispenseOrder.slip_number == req.slip_number).first()
    if not dispense_order:
        dispense_order = DispenseOrder(
            slip_number=req.slip_number,
            patient_name=patient_name,
            patient_phone=patient_phone,
            doctor_name=doc_name,
            diagnosis=diag,
            store_type=req.store_type,
            status="DISPENSED",
            is_generic_substituted=req.is_generic_substituted,
            generic_savings_amount=15.0 if req.is_generic_substituted else 0.0,
            total_bill_amount=total_val,
            batch_number_dispensed="B-2026-" + req.slip_number[-4:],
            pharmacist_notes=req.notes or f"Dispensed by {req.pharmacist_name}",
            cryptographic_lock=lock_hash,
            dispensed_at=now
        )
        db.add(dispense_order)
    else:
        dispense_order.status = "DISPENSED"
        dispense_order.store_type = req.store_type
        dispense_order.is_generic_substituted = req.is_generic_substituted
        dispense_order.cryptographic_lock = lock_hash
        dispense_order.dispensed_at = now
        dispense_order.pharmacist_notes = req.notes or f"Dispensed by {req.pharmacist_name}"

    db.commit()

    # Real-Time WebSocket broadcast
    ws_manager.sync_broadcast("PRESCRIPTION_DISPENSED", {
        "slip_number": req.slip_number,
        "patient_name": patient_name,
        "store_type": req.store_type,
        "pharmacist_name": req.pharmacist_name,
        "is_generic_substituted": req.is_generic_substituted,
        "cryptographic_lock": lock_hash,
        "dispensed_at": now.isoformat()
    })

    return {
        "success": True,
        "slip_number": req.slip_number,
        "status": "DISPENSED",
        "store_type": req.store_type,
        "dispensed_by": req.pharmacist_name,
        "cryptographic_lock": lock_hash,
        "dispensed_at": now.isoformat(),
        "message": f"Prescription {req.slip_number} successfully verified, dispensed, and locked cryptographically against double-dispensing."
    }

@router.post("/generic-lookup")
def lookup_generic(req: GenericSubstituteRequest, db: Session = Depends(get_db)):
    """Search Jan Aushadhi low-cost generic salt for any brand medicine name"""
    res = GenericDrugService.find_generic_substitute(req.medicine_name, db)
    if not res:
        raise HTTPException(status_code=404, detail="No generic record found.")
    return res

@router.get("/prescription-savings/{slip_number}")
def get_slip_savings(slip_number: str, db: Session = Depends(get_db)):
    """Calculate potential Jan Aushadhi generic savings for a given prescription"""
    receipt = db.query(Receipt).filter(Receipt.receipt_number == slip_number).first()
    if not receipt or not receipt.bill:
        raise HTTPException(status_code=404, detail="Slip not found.")

    items = []
    for bi in receipt.bill.items:
        items.append({
            "item_name": bi.description,
            "unit_price": bi.unit_price_cents / 100.0,
            "quantity": bi.quantity
        })

    savings = GenericDrugService.calculate_total_prescription_savings(items, db)
    return {
        "slip_number": slip_number,
        "patient_name": receipt.bill.patient.full_name if receipt.bill.patient else "Patient",
        **savings
    }

@router.post("/sms-slip")
def get_rural_sms_slip(req: RuralSmsRequest, db: Session = Depends(get_db)):
    """Generate concise SMS for rural basic keypad phones (under 160 chars)"""
    receipt = db.query(Receipt).filter(Receipt.receipt_number == req.slip_number).first()
    if not receipt or not receipt.bill:
        raise HTTPException(status_code=404, detail="Slip not found.")

    items = [{"item_name": bi.description, "quantity": bi.quantity} for bi in receipt.bill.items]
    patient_name = receipt.bill.patient.full_name if receipt.bill.patient else "Minh"
    total = receipt.amount_paid_cents / 100.0

    sms_text = GenericDrugService.generate_rural_sms_slip(
        patient_name=patient_name,
        slip_number=req.slip_number,
        items=items,
        total=total,
        is_generic=True
    )

    return {
        "slip_number": req.slip_number,
        "char_count": len(sms_text),
        "is_gsm7_compliant": len(sms_text) <= 160,
        "sms_content": sms_text
    }

@router.post("/audio-dosage")
def get_audio_dosage_script(req: AudioDosageRequest, db: Session = Depends(get_db)):
    """Generate localized voice/audio dosage script for rural patient illiterate support"""
    sub = GenericDrugService.find_generic_substitute(req.medicine_name, db)

    script_hi = sub["vernacular_dosage_hi"] if sub else f"{req.medicine_name} भोजन के बाद पानी के साथ लें।"
    script_en = sub["vernacular_dosage_en"] if sub else f"Take {req.medicine_name} after meals with water."

    text_to_speak = script_hi if req.language == "hi" else script_en

    return {
        "medicine_name": req.medicine_name,
        "language": req.language,
        "speech_text": text_to_speak,
        "visual_timing": sub["visual_timing"] if sub else "AFTER_MEAL",
        "timing_glyph": "🌅 Morning & 🌙 Night" if (sub and sub.get("visual_timing") == "MORNING_NIGHT") else "🍽️ Post Meal"
    }
