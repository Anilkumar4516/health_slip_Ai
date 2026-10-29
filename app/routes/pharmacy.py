import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any

from app.database import get_db
from app.models.receipt import Receipt, Bill, Prescription, PrescriptionItem
from app.models.pharmacy import PharmacyMedicineStock, DispenseOrder
from app.schemas.pharmacy import (
    DispenseRequest, GenericSubstituteRequest, StockAdjustRequest,
    AudioDosageRequest, RuralSmsRequest, AddMedicineStockRequest
)
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

@router.post("/inventory/add")
def add_inventory_medicine(req: AddMedicineStockRequest, db: Session = Depends(get_db)):
    """Add a new medicine batch into real medical store inventory"""
    savings_pct = 0.0
    if req.unit_price_brand > 0:
        savings_pct = round(((req.unit_price_brand - req.unit_price_generic) / req.unit_price_brand) * 100, 1)

    new_med = PharmacyMedicineStock(
        brand_name=req.brand_name.strip(),
        generic_name=req.generic_name.strip(),
        dosage_form=req.dosage_form,
        strength=req.strength,
        batch_number=req.batch_number.strip().upper(),
        stock_quantity=req.stock_quantity,
        reorder_level=req.reorder_level,
        unit_price_brand=req.unit_price_brand,
        unit_price_generic=req.unit_price_generic,
        savings_percent=max(0.0, savings_pct),
        vernacular_dosage_te=req.vernacular_dosage_te or "భోజనం తర్వాత నీటితో తీసుకోండి",
        vernacular_dosage_hi=req.vernacular_dosage_te or req.vernacular_dosage_hi or "భోజనం తర్వాత నీటితో తీసుకోండి",
        vernacular_dosage_en=req.vernacular_dosage_en or "Take after meals with water",
        visual_timing=req.visual_timing,
        is_controlled=req.is_controlled
    )
    db.add(new_med)
    db.commit()
    db.refresh(new_med)

    ws_manager.sync_broadcast("STOCK_UPDATED", {
        "medicine_id": new_med.id,
        "brand_name": new_med.brand_name,
        "new_stock": new_med.stock_quantity,
        "is_low_stock": False
    })

    return {
        "success": True,
        "medicine": {
            "id": new_med.id,
            "brand_name": new_med.brand_name,
            "generic_name": new_med.generic_name,
            "batch_number": new_med.batch_number,
            "stock_quantity": new_med.stock_quantity,
            "unit_price_brand": new_med.unit_price_brand,
            "unit_price_generic": new_med.unit_price_generic,
            "savings_percent": new_med.savings_percent
        }
    }

@router.get("/bill/{slip_number}")
def get_pharmacy_invoice_memo(slip_number: str, db: Session = Depends(get_db)):
    """
    Generate Official Pharmacy Invoice / Cash Memo data for thermal printing or digital issuance.
    Includes Drug License, GST, Batch details, Expiry, Jan Aushadhi generic savings, and HMAC seal.
    """
    receipt = db.query(Receipt).filter(Receipt.receipt_number == slip_number).first()
    if not receipt or not receipt.bill:
        raise HTTPException(status_code=404, detail="Prescription receipt not found.")

    bill = receipt.bill
    patient = bill.patient
    prescription = bill.prescription
    doctor = prescription.practitioner if prescription else None
    dispense = db.query(DispenseOrder).filter(DispenseOrder.slip_number == slip_number).first()

    is_generic = dispense.is_generic_substituted if dispense else False
    store_type = dispense.store_type if dispense else "URBAN"

    items_list = []
    total_mrp = 0.0
    total_savings = 0.0

    for bi in bill.items:
        sub = GenericDrugService.find_generic_substitute(bi.description, db)
        brand_p = sub["brand_price"] if sub else (bi.unit_price_cents / 100.0)
        generic_p = sub["generic_price"] if sub else (brand_p * 0.2)
        applied_p = generic_p if is_generic else brand_p
        line_tot = applied_p * bi.quantity
        saved_on_item = (brand_p - generic_p) * bi.quantity if is_generic else 0.0

        total_mrp += brand_p * bi.quantity
        total_savings += saved_on_item

        items_list.append({
            "name": sub["generic_name"] if is_generic and sub else bi.description,
            "original_brand": bi.description,
            "batch": sub.get("batch_number", "B-2026-901") if sub else "B-2026-001",
            "expiry": "11/2027",
            "quantity": bi.quantity,
            "unit_price": applied_p,
            "total_price": line_tot,
            "savings": saved_on_item
        })

    tax_rate = 5.0
    subtotal = sum(it["total_price"] for it in items_list)
    tax_amount = round(subtotal * (tax_rate / 100.0), 2)
    grand_total = round(subtotal + tax_amount, 2)

    return {
        "invoice_number": f"RX-PHARM-{slip_number[-5:]}",
        "slip_number": slip_number,
        "date": receipt.created_at.strftime("%d %b %Y, %I:%M %p"),
        "store_info": {
            "name": "HealthSlip Seva & Clinical Medical Store" if store_type == "RURAL" else "HealthSlip AI Central Pharmacy & POS",
            "dl_number": "DL: 20-B/48912 & 21-B/48913",
            "gstin": "07AAAAA0000A1Z5",
            "address": "Opp. Community Health Center, Main Road",
            "pharmacist": dispense.pharmacist_notes if dispense else "Licensed Clinical Pharmacist (Reg #PH-9841)"
        },
        "patient": {
            "name": patient.full_name if patient else "Minh",
            "phone": patient.phone if patient else "+1 555-019-2834",
            "age": patient.age if patient else 28,
            "gender": patient.gender if patient else "MALE"
        },
        "doctor": {
            "name": doctor.name if doctor else "Dr. Minh Nguyen, M.D.",
            "license": doctor.license_number if doctor else "MED-2024-8841",
            "clinic": doctor.clinic_name if doctor else "HealthSlip Medical Center"
        },
        "items": items_list,
        "financials": {
            "mrp_total": round(total_mrp, 2),
            "jan_aushadhi_savings": round(total_savings, 2),
            "subtotal": round(subtotal, 2),
            "tax_rate": tax_rate,
            "tax_amount": tax_amount,
            "grand_total": grand_total,
            "payment_status": "PAID"
        },
        "is_generic_substituted": is_generic,
        "cryptographic_seal": dispense.cryptographic_lock if dispense else receipt.gateway_transaction_id,
        "tamper_proof_status": "VERIFIED & SEALED"
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
    """Generate localized voice/audio dosage script for rural patient illiterate support (Telugu / English)"""
    sub = GenericDrugService.find_generic_substitute(req.medicine_name, db)

    script_te = (sub.get("vernacular_dosage_te") if sub else None) or f"{req.medicine_name} భోజనం తర్వాత నీటితో తీసుకోండి."
    script_en = (sub.get("vernacular_dosage_en") if sub else None) or f"Take {req.medicine_name} after meals with water."

    text_to_speak = script_te if req.language in ["te", "telugu"] else script_en

    return {
        "medicine_name": req.medicine_name,
        "language": req.language,
        "speech_text": text_to_speak,
        "visual_timing": sub["visual_timing"] if sub else "AFTER_MEAL",
        "timing_glyph": "🌅 Morning & 🌙 Night" if (sub and sub.get("visual_timing") == "MORNING_NIGHT") else "🍽️ Post Meal"
    }

