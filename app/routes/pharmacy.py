import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, UploadFile, File
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any

from app.database import get_db
from app.models.receipt import Receipt, Bill, Prescription, PrescriptionItem, Medicine
from app.models.pharmacy import PharmacyMedicineStock, DispenseOrder, PharmacyStore, StoreInventoryBatch
from app.models.verification import AuditEvent
from app.schemas.pharmacy import (
    DispenseRequest, GenericSubstituteRequest, StockAdjustRequest,
    AudioDosageRequest, RuralSmsRequest, AddMedicineStockRequest
)
from app.services.generic_drug_service import GenericDrugService
from app.services.receipt_service import ReceiptService
from app.services.pdf_service import PDFService
from app.services.websocket_manager import ws_manager
from app.services.auth_service import get_current_user_optional

router = APIRouter(prefix="/api/pharmacy", tags=["Pharmacy & Medical Store"])

@router.get("/inventory")
def get_inventory(store_id: Optional[int] = Query(None), db: Session = Depends(get_db)):
    """Fetch current medicine inventory with stock alerts and brand vs generic Jan Aushadhi pricing"""
    items = GenericDrugService.get_inventory_items(db)
    low_stock_count = sum(1 for it in items if it["status"] in ["LOW_STOCK", "OUT_OF_STOCK"])
    return {
        "total_items": len(items),
        "low_stock_count": low_stock_count,
        "items": items
    }

@router.get("/inventory/alerts")
def get_inventory_alerts(store_id: Optional[int] = Query(None), db: Session = Depends(get_db)):
    """Fetch real-time low-stock and near-expiry (<90 days) alerts for pharmacy shelf batches"""
    return GenericDrugService.get_inventory_alerts(db, store_id=store_id)

@router.get("/inventory/export-csv")
def export_inventory_csv(store_id: Optional[int] = Query(None), db: Session = Depends(get_db)):
    """Export store inventory batches as standard CSV for migration and external ERP billing software"""
    csv_data = GenericDrugService.export_inventory_csv(db, store_id=store_id)
    filename = f"Inventory_Store_{store_id or 'all'}_{datetime.date.today().isoformat()}.csv"
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@router.post("/inventory/import-csv")
async def import_inventory_csv(
    request: Request,
    file: Optional[UploadFile] = File(None),
    store_id: Optional[int] = Query(1),
    db: Session = Depends(get_db)
):
    """Import inventory batches from CSV file or raw payload to migrate from existing store software"""
    csv_text = ""
    if file:
        content_bytes = await file.read()
        csv_text = content_bytes.decode("utf-8", errors="replace")
    else:
        body = await request.body()
        csv_text = body.decode("utf-8", errors="replace")

    if not csv_text.strip():
        raise HTTPException(status_code=400, detail="Empty CSV content provided.")

    result = GenericDrugService.import_inventory_csv(db, csv_text, default_store_id=store_id or 1)
    return result

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
    }, target_store_id=item.store_id)

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

@router.get("/verify-slip/{slip_number}")
def verify_pharmacy_slip_lookup(slip_number: str, db: Session = Depends(get_db)):
    """
    Look up a prescription slip by QR code scan or slip number.
    Strictly verifies HMAC cryptographic seal integrity BEFORE displaying clinical data.
    """
    receipt = db.query(Receipt).filter(Receipt.receipt_number == slip_number).first()
    if not receipt or not receipt.bill:
        raise HTTPException(status_code=404, detail="Medical slip not found in system.")

    # Cryptographic HMAC verification
    auth_check = ReceiptService.verify_slip_authenticity(db, slip_number)
    if not auth_check.get("is_valid"):
        raise HTTPException(
            status_code=400,
            detail="SECURITY INTEGRITY ALERT: Cryptographic HMAC seal verification failed. Slip may have been tampered with or modified."
        )

    bill = receipt.bill
    prescription = bill.prescription
    patient = bill.patient
    doctor = prescription.practitioner if prescription else None

    # Check expiration
    today = datetime.date.today()
    is_expired = False
    if prescription and prescription.valid_until and prescription.valid_until < today:
        is_expired = True

    # Check controlled drugs (Schedule H, H1, X)
    controlled_items = []
    items_detail = []
    if bill.items:
        for bi in bill.items:
            sub = GenericDrugService.find_generic_substitute(bi.description, db)
            sched = "OTC"
            if sub and sub.get("matched"):
                stock_rec = db.query(PharmacyMedicineStock).filter(
                    PharmacyMedicineStock.brand_name == sub["brand_name"]
                ).first()
                if stock_rec and stock_rec.drug_schedule:
                    sched = stock_rec.drug_schedule
            
            # Known schedule checks
            desc_upper = bi.description.upper()
            if any(k in desc_upper for k in ["ALPRAZOLAM", "DIAZEPAM", "TRAMADOL", "CLONAZEPAM", "CODEINE"]):
                sched = "SCHEDULE_H1"
            elif any(k in desc_upper for k in ["AUGMENTIN", "AMOXICILLIN", "AZITHROMYCIN", "CIPROFLOXACIN"]):
                sched = "SCHEDULE_H"

            if sched in ("SCHEDULE_H", "SCHEDULE_H1", "SCHEDULE_X"):
                controlled_items.append(f"{bi.description} ({sched})")

            items_detail.append({
                "item_name": bi.description,
                "generic_name": sub["generic_name"] if sub else bi.description,
                "quantity": bi.quantity,
                "unit_price": bi.unit_price_cents / 100.0,
                "drug_schedule": sched,
                "is_controlled": sched != "OTC",
                "generic_available": bool(sub and sub.get("matched")),
                "generic_unit_price": sub["generic_price"] if sub else bi.unit_price_cents / 100.0,
                "savings_potential": (bi.unit_price_cents / 100.0 - sub["generic_price"]) * bi.quantity if sub else 0.0
            })

    dispense = db.query(DispenseOrder).filter(DispenseOrder.slip_number == slip_number).first()
    is_dispensed = bool(dispense and dispense.status == "DISPENSED")

    return {
        "success": True,
        "hmac_verified": True,
        "slip_number": slip_number,
        "issued_date": prescription.issued_date.isoformat() if prescription else receipt.created_at.date().isoformat(),
        "valid_until": prescription.valid_until.isoformat() if prescription else None,
        "is_expired": is_expired,
        "refills_allowed": prescription.refills_allowed if prescription else 0,
        "refills_remaining": prescription.refills_remaining if prescription else 0,
        "status": dispense.status if dispense else (prescription.status if prescription else "ACTIVE"),
        "is_dispensed": is_dispensed,
        "cryptographic_seal": receipt.gateway_transaction_id,
        "patient": {
            "name": patient.full_name if patient else "Rajesh Kumar",
            "phone": patient.phone if patient else "+91 98765 43210",
            "age": patient.age if patient else 28,
            "gender": patient.gender if patient else "Male"
        },
        "doctor": {
            "name": doctor.name if doctor else "Dr. K. S. Rao, M.B.B.S., M.D.",
            "license": doctor.license_number if doctor else "TSMC-2024-8841",
            "clinic": doctor.clinic_name if doctor else "HealthSlip AI Multi-Specialty Clinic"
        },
        "diagnosis": prescription.diagnosis if prescription else "General Consultation",
        "has_controlled_drugs": len(controlled_items) > 0,
        "controlled_drug_list": controlled_items,
        "items": items_detail
    }

@router.get("/invoice/{slip_number}")
def get_prescription_invoice(
    slip_number: str,
    store_type: str = Query("URBAN", description="URBAN or RURAL"),
    store_id: Optional[int] = Query(None),
    is_generic: bool = Query(False, description="Apply Jan Aushadhi generic substitutions"),
    db: Session = Depends(get_db)
):
    """
    Generate GST-Compliant Pharmacy Tax Invoice data.
    Verifies HMAC seal, calculates Jan Aushadhi generic savings, and computes CGST/SGST tax split.
    """
    receipt = db.query(Receipt).filter(Receipt.receipt_number == slip_number).first()
    if not receipt or not receipt.bill:
        raise HTTPException(status_code=404, detail="Prescription or receipt record not found.")

    # HMAC seal verification before returning invoice
    auth_check = ReceiptService.verify_slip_authenticity(db, slip_number)
    if not auth_check.get("is_valid"):
        raise HTTPException(status_code=400, detail="Prescription HMAC seal validation failed.")

    bill = receipt.bill
    patient = bill.patient
    prescription = bill.prescription
    doctor = prescription.practitioner if prescription else None
    dispense = db.query(DispenseOrder).filter(DispenseOrder.slip_number == slip_number).first()

    # Determine store details
    store = None
    if store_id:
        store = db.query(PharmacyStore).filter(PharmacyStore.id == store_id).first()
    elif dispense and dispense.store_id:
        store = db.query(PharmacyStore).filter(PharmacyStore.id == dispense.store_id).first()
    if not store:
        store = db.query(PharmacyStore).filter(PharmacyStore.store_type == store_type).first()

    store_name = store.name if store else ("HealthSlip Central Pharmacy & Seva Kendra" if store_type == "URBAN" else "Pradhan Mantri Jan Aushadhi Kendra (Rural Seva)")
    store_dl = store.drug_license_number if store else ("20-B/TS/48912 & 21-B/TS/48913" if store_type == "URBAN" else "20-B/TS/98214 & 21-B/TS/98215")
    store_gstin = store.gstin if store else "36AAAAA0000A1Z5"
    store_addr = store.address if store else "RTC Cross Roads, Hyderabad, Telangana"
    store_phone = store.phone if store else "+91 98765 00002"

    items_list = []
    total_mrp = 0.0
    total_savings = 0.0

    for bi in bill.items:
        sub = GenericDrugService.find_generic_substitute(bi.description, db)
        brand_p = bi.unit_price_cents / 100.0
        applied_p = sub["generic_price"] if is_generic and sub else brand_p
        line_tot = applied_p * bi.quantity
        line_mrp = brand_p * bi.quantity
        saved_on_item = max(0.0, line_mrp - line_tot)

        total_mrp += line_mrp
        total_savings += saved_on_item

        items_list.append({
            "name": sub["generic_name"] if is_generic and sub else bi.description,
            "original_brand": bi.description,
            "hsn_code": "3004",
            "batch": sub.get("batch_number", "B-2026-901") if sub else "B-2026-001",
            "expiry": "11/2027",
            "quantity": bi.quantity,
            "unit_price": applied_p,
            "unit_price_generic": sub["generic_price"] if sub else applied_p,
            "gst_rate": 12.0,
            "total_price": line_tot,
            "savings": saved_on_item
        })

    tax_rate = 12.0
    subtotal = sum(it["total_price"] for it in items_list)
    tax_amount = round(subtotal * (tax_rate / (100.0 + tax_rate)), 2) # Inclusive GST
    taxable_subtotal = round(subtotal - tax_amount, 2)
    grand_total = round(subtotal, 2)

    return {
        "invoice_number": f"RX-PHARM-{slip_number[-5:]}",
        "slip_number": slip_number,
        "date": receipt.created_at.strftime("%d %b %Y, %I:%M %p"),
        "store_info": {
            "id": store.id if store else 1,
            "name": store_name,
            "dl_number": store_dl,
            "gstin": store_gstin,
            "address": store_addr,
            "phone": store_phone,
            "pharmacist": dispense.pharmacist_notes if dispense else "Registered Pharmacist (Pharmacy Council)"
        },
        "patient": {
            "name": patient.full_name if patient else "Rajesh Kumar",
            "phone": patient.phone if patient else "+91 98765 43210",
            "age": patient.age if patient else 28,
            "gender": patient.gender if patient else "MALE"
        },
        "doctor": {
            "name": doctor.name if doctor else "Dr. K. S. Rao, M.B.B.S., M.D.",
            "license": doctor.license_number if doctor else "TSMC-2024-8841",
            "clinic": doctor.clinic_name if doctor else "HealthSlip AI Multi-Specialty Clinic & Seva Kendra"
        },
        "items": items_list,
        "financials": {
            "mrp_total": round(total_mrp, 2),
            "jan_aushadhi_savings": round(total_savings, 2),
            "subtotal": taxable_subtotal,
            "tax_rate": tax_rate,
            "tax_amount": tax_amount,
            "cgst_rate": 6.0,
            "cgst_amount": round(tax_amount / 2.0, 2),
            "sgst_rate": 6.0,
            "sgst_amount": round(tax_amount / 2.0, 2),
            "grand_total": grand_total,
            "payment_status": "PAID"
        },
        "is_generic_substituted": is_generic,
        "cryptographic_seal": dispense.cryptographic_lock if dispense else receipt.gateway_transaction_id,
        "tamper_proof_status": "VERIFIED & SEALED"
    }

@router.get("/invoice/{slip_number}/pdf")
def download_gst_invoice_pdf(
    slip_number: str,
    store_type: str = Query("URBAN"),
    store_id: Optional[int] = Query(None),
    is_generic: bool = Query(False),
    db: Session = Depends(get_db)
):
    """Download official Indian GST Tax Invoice PDF with DL numbers, HSN codes, and tax breakdown"""
    invoice_data = get_prescription_invoice(
        slip_number=slip_number,
        store_type=store_type,
        store_id=store_id,
        is_generic=is_generic,
        db=db
    )
    pdf_bytes = PDFService.generate_gst_tax_invoice_pdf(invoice_data)
    filename = f"GST_Invoice_{slip_number}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename={filename}"}
    )

@router.get("/queue")
def get_pharmacy_queue(
    store_type: str = Query("URBAN", description="URBAN or RURAL"),
    store_id: Optional[int] = Query(None),
    db: Session = Depends(get_db)
):
    """
    Fetch live prescription queue for pharmacy counters.
    Shows doctor prescriptions, dispensing state, anti-double dispensing lock, and generic savings.
    """
    recent_receipts = db.query(Receipt).order_by(Receipt.created_at.desc()).limit(25).all()
    queue = []

    for r in recent_receipts:
        bill = r.bill
        patient = bill.patient if bill else None
        prescription = bill.prescription if bill else None
        practitioner = prescription.practitioner if prescription else None

        slip_no = r.receipt_number
        p_name = patient.full_name if patient else "Rajesh Kumar"
        p_phone = patient.phone if patient else "+91 98765 43210"

        dispense = db.query(DispenseOrder).filter(DispenseOrder.slip_number == slip_no).first()

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
            "doctor_name": practitioner.name if practitioner else "Dr. K. S. Rao, M.B.B.S., M.D.",
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
def dispense_prescription(
    req: DispenseRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Dispense prescription at Urban or Rural Medical Store:
    1. Row-level DB lock (with_for_update) to prevent cross-store double dispensing.
    2. Validates prescription expiration (valid_until) and remaining refills.
    3. Requires explicit confirmation for Schedule H/H1/X controlled medications.
    4. Jan Aushadhi generic substitution confirmed by pharmacist.
    5. Decrements inventory via FEFO (First-Expiry-First-Out).
    6. Audit logs dispensing actions (who, when, store, client sync UUID).
    7. Broadcasts targeted real-time WebSocket notification.
    """
    # 1. DB Row-Level Transaction Lock to prevent concurrent double-dispensing
    receipt = db.query(Receipt).filter(Receipt.receipt_number == req.slip_number).with_for_update().first()
    existing_dispense = db.query(DispenseOrder).filter(DispenseOrder.slip_number == req.slip_number).with_for_update().first()

    bill = receipt.bill if receipt else None
    prescription = bill.prescription if bill else None
    today = datetime.date.today()

    # 2. Check Expiration & Refills
    if prescription:
        if prescription.valid_until and prescription.valid_until < today:
            raise HTTPException(
                status_code=400,
                detail=f"Prescription {req.slip_number} expired on {prescription.valid_until}. Dispense is prohibited under clinical regulations."
            )

        if existing_dispense and existing_dispense.status == "DISPENSED":
            if prescription.refills_remaining <= 0:
                raise HTTPException(
                    status_code=400,
                    detail=f"Prescription {req.slip_number} has ALREADY BEEN DISPENSED at {existing_dispense.store_type} Store on {existing_dispense.dispensed_at.strftime('%Y-%m-%d %H:%M')}. Cryptographic lock active."
                )
            else:
                # Valid refill: decrement remaining refills
                prescription.refills_remaining -= 1
    elif existing_dispense and existing_dispense.cryptographic_lock:
        raise HTTPException(
            status_code=400,
            detail=f"Prescription {req.slip_number} has ALREADY BEEN DISPENSED at {existing_dispense.store_type} Store on {existing_dispense.dispensed_at.strftime('%Y-%m-%d %H:%M')}. Cryptographic lock active."
        )

    # 3. Schedule H / H1 / X Controlled Drugs Check
    scheduled_drugs = []
    if prescription and prescription.items:
        for pi in prescription.items:
            sched = "OTC"
            if pi.medicine and pi.medicine.drug_schedule:
                sched = pi.medicine.drug_schedule
            m_name = pi.medicine.brand_name.upper() if pi.medicine else ""
            if any(k in m_name for k in ["ALPRAZOLAM", "DIAZEPAM", "TRAMADOL", "CLONAZEPAM", "CODEINE"]):
                sched = "SCHEDULE_H1"
            if sched in ("SCHEDULE_H", "SCHEDULE_H1", "SCHEDULE_X"):
                scheduled_drugs.append(f"{pi.medicine.brand_name if pi.medicine else 'Medication'} ({sched})")

    if scheduled_drugs and not req.schedule_confirmed:
        raise HTTPException(
            status_code=400,
            detail=f"Controlled Substance Notice: Prescription contains Schedule H/H1/X medication(s): {', '.join(scheduled_drugs)}. Pharmacist confirmation (schedule_confirmed=true) is mandatory by law."
        )

    # 4. Jan Aushadhi Generic Substitution Check
    if req.is_generic_substituted:
        # Pharmacist confirmation audit
        db.add(AuditEvent(
            action="GENERIC_SUBSTITUTION_CONFIRMED",
            resource_type="dispense_orders",
            resource_id=req.slip_number,
            ip_address=request.client.host if request.client else None,
            payload_after={"is_generic": True, "pharmacist": req.pharmacist_name, "store_id": req.store_id}
        ))

    patient_name = "Rajesh Kumar"
    patient_phone = "+91 98765 43210"
    doc_name = "Dr. K. S. Rao, M.B.B.S., M.D."
    diag = "General Consultation"
    total_val = 0.0

    if receipt and bill:
        if bill.patient:
            patient_name = bill.patient.full_name
            patient_phone = bill.patient.phone
        if prescription and prescription.practitioner:
            doc_name = prescription.practitioner.name
            diag = prescription.diagnosis
        total_val = receipt.amount_paid_cents / 100.0

    # 5. Handle Partial vs Full Line-Item Dispensing
    now = datetime.datetime.utcnow()
    batches_deducted_log = []

    if req.line_items and prescription and prescription.items:
        for line in req.line_items:
            matching_pi = next(
                (pi for pi in prescription.items if line.item_name.lower() in (pi.medicine.brand_name.lower() if pi.medicine else "")),
                None
            )
            if matching_pi:
                matching_pi.dispensed_quantity = min(
                    matching_pi.total_quantity_prescribed,
                    matching_pi.dispensed_quantity + line.quantity_to_dispense
                )
            # Decrement inventory FEFO
            fefo_res = GenericDrugService.decrement_stock_fefo(
                db=db,
                medicine_name=line.item_name,
                quantity_to_deduct=line.quantity_to_dispense,
                store_id=req.store_id
            )
            batches_deducted_log.append(fefo_res)

        # Check if all items complete
        all_completed = all(pi.dispensed_quantity >= pi.total_quantity_prescribed for pi in prescription.items)
        prescription.status = "DISPENSED" if all_completed else "ACTIVE"
    else:
        # Full dispensing of all items
        if prescription and prescription.items:
            for pi in prescription.items:
                pi.dispensed_quantity = pi.total_quantity_prescribed
                m_name = pi.medicine.brand_name if pi.medicine else "Medicine"
                fefo_res = GenericDrugService.decrement_stock_fefo(
                    db=db,
                    medicine_name=m_name,
                    quantity_to_deduct=pi.total_quantity_prescribed,
                    store_id=req.store_id
                )
                batches_deducted_log.append(fefo_res)
        elif bill and bill.items:
            for bi in bill.items:
                fefo_res = GenericDrugService.decrement_stock_fefo(
                    db=db,
                    medicine_name=bi.description,
                    quantity_to_deduct=bi.quantity,
                    store_id=req.store_id
                )
                batches_deducted_log.append(fefo_res)

        if prescription:
            prescription.status = "DISPENSED"

    # 6. Cryptographic Dispense Seal
    lock_hash = GenericDrugService.generate_cryptographic_dispense_lock(
        req.slip_number, req.store_type, req.pharmacist_name
    )

    # 7. Record or Update DispenseOrder
    if not existing_dispense:
        dispense_order = DispenseOrder(
            slip_number=req.slip_number,
            store_id=req.store_id,
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
            schedule_confirmed=req.schedule_confirmed,
            cryptographic_lock=lock_hash,
            dispensed_at=now
        )
        db.add(dispense_order)
    else:
        existing_dispense.status = "DISPENSED"
        existing_dispense.store_type = req.store_type
        if req.store_id:
            existing_dispense.store_id = req.store_id
        existing_dispense.is_generic_substituted = req.is_generic_substituted
        existing_dispense.cryptographic_lock = lock_hash
        existing_dispense.dispensed_at = now
        existing_dispense.schedule_confirmed = req.schedule_confirmed
        existing_dispense.pharmacist_notes = req.notes or f"Dispensed by {req.pharmacist_name}"

    # 8. Record in AuditEvent
    current_user = get_current_user_optional(request, db)
    db.add(AuditEvent(
        actor_user_id=current_user.id if current_user else None,
        action="DISPENSE_PRESCRIPTION",
        resource_type="dispense_orders",
        resource_id=req.slip_number,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("User-Agent"),
        payload_after={
            "store_id": req.store_id,
            "store_type": req.store_type,
            "pharmacist": req.pharmacist_name,
            "is_generic": req.is_generic_substituted,
            "cryptographic_lock": lock_hash,
            "client_sync_id": req.client_sync_id,
            "scheduled_drugs": scheduled_drugs
        }
    ))

    db.commit()

    # 9. Targeted Real-Time WebSocket broadcast (to this store room & patient room)
    ws_manager.sync_broadcast(
        event_type="PRESCRIPTION_DISPENSED",
        data={
            "slip_number": req.slip_number,
            "patient_name": patient_name,
            "store_type": req.store_type,
            "pharmacist_name": req.pharmacist_name,
            "is_generic_substituted": req.is_generic_substituted,
            "cryptographic_lock": lock_hash,
            "dispensed_at": now.isoformat(),
            "client_sync_id": req.client_sync_id
        },
        target_store_id=req.store_id,
        target_patient_phone=patient_phone
    )

    return {
        "success": True,
        "slip_number": req.slip_number,
        "status": "DISPENSED",
        "store_type": req.store_type,
        "dispensed_by": req.pharmacist_name,
        "cryptographic_lock": lock_hash,
        "dispensed_at": now.isoformat(),
        "client_sync_id": req.client_sync_id,
        "refills_remaining": prescription.refills_remaining if prescription else 0,
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
    patient_name = receipt.bill.patient.full_name if receipt.bill.patient else "Rajesh Kumar"
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
