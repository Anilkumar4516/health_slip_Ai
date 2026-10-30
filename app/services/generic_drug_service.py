import csv
import io
import datetime
import hashlib
import hmac
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from app.config import settings
from app.models.pharmacy import PharmacyMedicineStock, DispenseOrder, StoreInventoryBatch
from app.models.receipt import Receipt, Bill, Prescription, PrescriptionItem, Medicine

class GenericDrugService:
    DEFAULT_DRUG_DATABASE = [
        {
            "brand_name": "Augmentin 625mg",
            "generic_name": "Amoxicillin (500mg) + Potassium Clavulanate (125mg)",
            "dosage_form": "Tablet",
            "strength": "625mg",
            "batch_number": "AUG-2026-X1",
            "stock_quantity": 45,
            "reorder_level": 15,
            "unit_price_brand": 18.50,
            "unit_price_generic": 3.80,
            "savings_percent": 79.5,
            "vernacular_dosage_te": "ఉదయం మరియు రాత్రి భోజనం తర్వాత 1 మాత్ర వేసుకోండి. పూర్తి 5 రోజుల కోర్సు పూర్తి చేయండి.",
            "vernacular_dosage_en": "Take 1 tablet twice daily after meals. Complete the entire 5-day course.",
            "visual_timing": "MORNING_NIGHT",
            "is_controlled": False
        },
        {
            "brand_name": "Crocin 650mg",
            "generic_name": "Paracetamol (Acetaminophen) 650mg",
            "dosage_form": "Tablet",
            "strength": "650mg",
            "batch_number": "CRC-2026-P2",
            "stock_quantity": 250,
            "reorder_level": 30,
            "unit_price_brand": 3.50,
            "unit_price_generic": 0.65,
            "savings_percent": 81.4,
            "vernacular_dosage_te": "జ్వరం లేదా తలనొప్పి ఉన్నప్పుడు భోజనం తర్వాత నీటితో 1 మాత్ర తీసుకోండి.",
            "vernacular_dosage_en": "Take 1 tablet after food with water when fever or pain occurs.",
            "visual_timing": "AFTER_MEAL",
            "is_controlled": False
        },
        {
            "brand_name": "Ibuprofen 400mg",
            "generic_name": "Ibuprofen 400mg Film-Coated",
            "dosage_form": "Tablet",
            "strength": "400mg",
            "batch_number": "IBU-2026-M4",
            "stock_quantity": 120,
            "reorder_level": 25,
            "unit_price_brand": 12.00,
            "unit_price_generic": 2.40,
            "savings_percent": 80.0,
            "vernacular_dosage_te": "నొప్పి మరియు వాపు కొరకు ఎల్లప్పుడూ భోజనం తర్వాత నీటితో 1 మాత్ర తీసుకోండి. ఖాళీ కడుపుతో తీసుకోకూడదు.",
            "vernacular_dosage_en": "Take 1 pill after meals with water. Never take on an empty stomach.",
            "visual_timing": "AFTER_MEAL",
            "is_controlled": False
        },
        {
            "brand_name": "Pan-D Capsule",
            "generic_name": "Pantoprazole (40mg) + Domperidone (30mg) SR",
            "dosage_form": "Capsule",
            "strength": "40mg/30mg",
            "batch_number": "PND-2026-C8",
            "stock_quantity": 80,
            "reorder_level": 20,
            "unit_price_brand": 19.00,
            "unit_price_generic": 3.20,
            "savings_percent": 83.2,
            "vernacular_dosage_te": "ఉదయం అల్పాహారానికి అరగంట ముందు ఖాళీ కడుపుతో 1 క్యాప్సూల్ నీటితో తీసుకోండి.",
            "vernacular_dosage_en": "Take 1 capsule on an empty stomach 30 minutes before breakfast.",
            "visual_timing": "MORNING",
            "is_controlled": False
        },
        {
            "brand_name": "Azithral 500mg",
            "generic_name": "Azithromycin 500mg",
            "dosage_form": "Tablet",
            "strength": "500mg",
            "batch_number": "AZT-2026-F3",
            "stock_quantity": 18,  # Low stock warning
            "reorder_level": 20,
            "unit_price_brand": 13.50,
            "unit_price_generic": 2.90,
            "savings_percent": 78.5,
            "vernacular_dosage_te": "రోజుకు 1 సారి మాత్రమే భోజనానికి 1 గంట ముందు లేదా 2 గంటల తర్వాత 3 రోజులు తీసుకోండి.",
            "vernacular_dosage_en": "Take once daily 1 hour before or 2 hours after meals for 3 days.",
            "visual_timing": "MORNING",
            "is_controlled": False
        },
        {
            "brand_name": "Lipitor 10mg",
            "generic_name": "Atorvastatin Calcium 10mg",
            "dosage_form": "Tablet",
            "strength": "10mg",
            "batch_number": "LIP-2026-D9",
            "stock_quantity": 95,
            "reorder_level": 15,
            "unit_price_brand": 11.00,
            "unit_price_generic": 1.80,
            "savings_percent": 83.6,
            "vernacular_dosage_te": "రాత్రి పడుకునే ముందు భోజనం తర్వాత రోజూ 1 మాత్ర తీసుకోండి.",
            "vernacular_dosage_en": "Take 1 tablet every night at bedtime after dinner.",
            "visual_timing": "NIGHT",
            "is_controlled": False
        },
        {
            "brand_name": "Glycomet-GP 1",
            "generic_name": "Metformin (500mg) + Glimepiride (1mg)",
            "dosage_form": "Tablet",
            "strength": "500mg/1mg",
            "batch_number": "GLY-2026-T5",
            "stock_quantity": 160,
            "reorder_level": 30,
            "unit_price_brand": 9.50,
            "unit_price_generic": 1.90,
            "savings_percent": 80.0,
            "vernacular_dosage_te": "ఉదయం అల్పాహారంతో లేదా వెంటనే ముందు 1 మాత్ర తీసుకోండి. షుగర్ నియంత్రణలో ఉంచుకోండి.",
            "vernacular_dosage_en": "Take 1 tablet with or just before your morning meal.",
            "visual_timing": "MORNING",
            "is_controlled": False
        },
        {
            "brand_name": "Allegra 120mg",
            "generic_name": "Fexofenadine HCl / Cetirizine 10mg",
            "dosage_form": "Tablet",
            "strength": "120mg",
            "batch_number": "ALG-2026-R7",
            "stock_quantity": 70,
            "reorder_level": 20,
            "unit_price_brand": 11.50,
            "unit_price_generic": 1.40,
            "savings_percent": 87.8,
            "vernacular_dosage_te": "అలెర్జీ మరియు తుమ్ముల ఉపశమనం కోసం రాత్రి 1 మాత్ర తీసుకోండి. కొద్దిగా నిద్ర రావచ్చు.",
            "vernacular_dosage_en": "Take 1 tablet at night for allergy and sneezing relief.",
            "visual_timing": "NIGHT",
            "is_controlled": False
        }
    ]

    @classmethod
    def seed_inventory_if_empty(cls, db: Session):
        """Seed pre-configured inventory into pharmacy_medicine_stock"""
        try:
            count = db.query(PharmacyMedicineStock).count()
            if count == 0:
                for item in cls.DEFAULT_DRUG_DATABASE:
                    stock = PharmacyMedicineStock(**item)
                    db.add(stock)
                db.commit()
                print("[Pharmacy] Initialized Urban & Rural Medical Store Medicine Inventory!")
        except Exception as e:
            db.rollback()
            print(f"[Pharmacy] Inventory seed note: {e}")

    @classmethod
    def get_inventory_items(cls, db: Session) -> List[Dict[str, Any]]:
        """Fetch all stocked medicines with stock status alerts"""
        stocks = db.query(PharmacyMedicineStock).order_by(PharmacyMedicineStock.stock_quantity.asc()).all()
        if not stocks:
            cls.seed_inventory_if_empty(db)
            stocks = db.query(PharmacyMedicineStock).order_by(PharmacyMedicineStock.stock_quantity.asc()).all()

        result = []
        for s in stocks:
            status = "IN_STOCK"
            if s.stock_quantity <= 0:
                status = "OUT_OF_STOCK"
            elif s.stock_quantity <= s.reorder_level:
                status = "LOW_STOCK"

            result.append({
                "id": s.id,
                "brand_name": s.brand_name,
                "generic_name": s.generic_name,
                "dosage_form": s.dosage_form,
                "strength": s.strength,
                "batch_number": s.batch_number,
                "stock_quantity": s.stock_quantity,
                "reorder_level": s.reorder_level,
                "status": status,
                "unit_price_brand": s.unit_price_brand,
                "unit_price_generic": s.unit_price_generic,
                "savings_percent": s.savings_percent,
                "vernacular_dosage_te": s.vernacular_dosage_te or "భోజనం తర్వాత నీటితో తీసుకోండి",
                "vernacular_dosage_en": s.vernacular_dosage_en,
                "visual_timing": s.visual_timing,
                "is_controlled": s.is_controlled
            })
        return result

    @classmethod
    def find_generic_substitute(cls, medicine_name: str, db: Session) -> Optional[Dict[str, Any]]:
        """Search for generic equivalent by brand or generic name"""
        q = (medicine_name or "").strip().lower()
        if not q:
            return None

        # Exact or partial match in DB
        stocks = db.query(PharmacyMedicineStock).all()
        if not stocks:
            cls.seed_inventory_if_empty(db)
            stocks = db.query(PharmacyMedicineStock).all()
        for s in stocks:
            b_low = s.brand_name.lower()
            g_low = s.generic_name.lower()
            if q in b_low or b_low in q or q in g_low or g_low in q:
                savings_amount = round(s.unit_price_brand - s.unit_price_generic, 2)
                return {
                    "matched": True,
                    "brand_name": s.brand_name,
                    "generic_name": s.generic_name,
                    "dosage_form": s.dosage_form,
                    "strength": s.strength,
                    "brand_price": s.unit_price_brand,
                    "generic_price": s.unit_price_generic,
                    "savings_amount": savings_amount,
                    "savings_percent": s.savings_percent,
                    "vernacular_dosage_te": s.vernacular_dosage_te or "భోజనం తర్వాత నీటితో తీసుకోండి",
                    "vernacular_dosage_en": s.vernacular_dosage_en,
                    "visual_timing": s.visual_timing,
                    "batch_number": s.batch_number,
                    "stock_available": s.stock_quantity
                }

        # Fallback heuristic calculation if not in catalog
        return {
            "matched": False,
            "brand_name": medicine_name,
            "generic_name": f"Generic {medicine_name} Salt (Jan Aushadhi)",
            "dosage_form": "Tablet",
            "strength": "Standard",
            "brand_price": 12.00,
            "generic_price": 2.50,
            "savings_amount": 9.50,
            "savings_percent": 79.2,
            "vernacular_dosage_te": "భోజనం తర్వాత నీటితో 1 మాత్ర తీసుకోండి.",
            "vernacular_dosage_en": "Take 1 tablet after meals with water.",
            "visual_timing": "AFTER_MEAL",
            "batch_number": "GEN-2026-001",
            "stock_available": 50
        }

    @classmethod
    def calculate_total_prescription_savings(cls, items: List[Dict[str, Any]], db: Session) -> Dict[str, Any]:
        """Calculate total Jan Aushadhi generic savings for a patient's prescription"""
        total_brand = 0.0
        total_generic = 0.0
        substitutions = []

        for item in items:
            name = item.get("item_name") or item.get("medicine_name") or ""
            qty = int(item.get("quantity") or 1)
            u_price = float(item.get("unit_price") or 0.0)

            sub = cls.find_generic_substitute(name, db)
            if sub:
                brand_cost = (sub["brand_price"] if u_price <= 0 else u_price) * qty
                generic_cost = sub["generic_price"] * qty
                diff = round(brand_cost - generic_cost, 2)
                total_brand += brand_cost
                total_generic += generic_cost
                substitutions.append({
                    "original_name": name,
                    "generic_name": sub["generic_name"],
                    "brand_cost": brand_cost,
                    "generic_cost": generic_cost,
                    "saved": max(0.0, diff),
                    "savings_percent": sub["savings_percent"],
                    "vernacular_te": sub.get("vernacular_dosage_te") or "భోజనం తర్వాత నీటితో తీసుకోండి",
                    "vernacular_en": sub["vernacular_dosage_en"],
                    "visual_timing": sub["visual_timing"]
                })

        total_saved = max(0.0, round(total_brand - total_generic, 2))
        pct = round((total_saved / total_brand * 100), 1) if total_brand > 0 else 0.0

        return {
            "total_brand_cost": round(total_brand, 2),
            "total_generic_cost": round(total_generic, 2),
            "total_saved": total_saved,
            "savings_percent": pct,
            "substitutions": substitutions
        }

    @classmethod
    def generate_cryptographic_dispense_lock(cls, slip_number: str, store_type: str, pharmacist: str) -> str:
        """Create cryptographic proof of dispense to prevent double-dispensing in other stores"""
        now_iso = datetime.datetime.utcnow().isoformat()
        payload = f"{slip_number}|{store_type}|{pharmacist}|{now_iso}".encode("utf-8")
        return hmac.new(settings.SECRET_KEY.encode("utf-8"), payload, hashlib.sha256).hexdigest()

    @classmethod
    def generate_rural_sms_slip(cls, patient_name: str, slip_number: str, items: List[Dict[str, Any]], total: float, is_generic: bool) -> str:
        """
        Generate lightweight SMS (GSM-7 compatible < 160 chars) for rural feature phones:
        e.g., 'Rx HSL-2026-94670 for Rajesh: Crocin(1-0-1 post meals). Total: ₹20.00 (JanAushadhi Saved 80%). Help: 1800-MED-CARE'
        """
        med_summaries = []
        for it in items[:2]:
            name = it.get("item_name") or it.get("medicine_name") or "Med"
            short_name = name.split()[0]
            timing = it.get("timing_slot") or "1-0-1"
            med_summaries.append(f"{short_name}({timing})")

        meds_str = ", ".join(med_summaries)
        gen_tag = " [Generic Saved 80%]" if is_generic else ""
        sms = f"HealthSlip {slip_number} for {patient_name.split()[0]}: {meds_str}. Total: ₹{total:.2f}{gen_tag}. Helpln: 1800-HEALTH-AI"
        return sms[:158]

    @classmethod
    def decrement_stock_fefo(cls, db: Session, medicine_name: str, quantity_to_deduct: int, store_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Auto-decrement stock on dispense using FEFO (First-Expiry-First-Out) logic.
        Deducts from earliest expiring batch first.
        """
        today = datetime.date.today()
        clean_name = medicine_name.split()[0].strip().lower()

        # Query active batches ordered by earliest expiry date (FEFO)
        query = db.query(StoreInventoryBatch).filter(
            (StoreInventoryBatch.brand_name.ilike(f"%{clean_name}%") | StoreInventoryBatch.generic_name.ilike(f"%{clean_name}%")),
            StoreInventoryBatch.quantity > 0,
            StoreInventoryBatch.expiry_date >= today
        )
        if store_id:
            query = query.filter(StoreInventoryBatch.store_id == store_id)

        batches = query.order_by(StoreInventoryBatch.expiry_date.asc()).all()

        remaining_needed = quantity_to_deduct
        batches_deducted = []

        for b in batches:
            if remaining_needed <= 0:
                break
            deduct_qty = min(b.quantity, remaining_needed)
            b.quantity -= deduct_qty
            remaining_needed -= deduct_qty
            batches_deducted.append({
                "batch_no": b.batch_no,
                "expiry_date": b.expiry_date.isoformat(),
                "quantity_deducted": deduct_qty,
                "remaining_in_batch": b.quantity
            })

        # Also decrement legacy PharmacyMedicineStock for backward compatibility
        med_stock = db.query(PharmacyMedicineStock).filter(
            PharmacyMedicineStock.brand_name.ilike(f"%{clean_name}%")
        ).first()
        if med_stock:
            med_stock.stock_quantity = max(0, med_stock.stock_quantity - quantity_to_deduct)

        db.flush()
        return {
            "success": True,
            "batches_deducted": batches_deducted,
            "quantity_fulfilled": quantity_to_deduct - remaining_needed,
            "shortfall": max(0, remaining_needed)
        }

    @classmethod
    def get_inventory_alerts(cls, db: Session, store_id: Optional[int] = None) -> Dict[str, Any]:
        """Fetch low-stock and near-expiry (<90 days) inventory alerts"""
        today = datetime.date.today()
        near_expiry_cutoff = today + datetime.timedelta(days=90)

        # 1. Near-expiry batches
        batch_q = db.query(StoreInventoryBatch).filter(StoreInventoryBatch.quantity > 0)
        if store_id:
            batch_q = batch_q.filter(StoreInventoryBatch.store_id == store_id)

        near_expiry = []
        expired = []
        for b in batch_q.all():
            if b.expiry_date < today:
                expired.append({
                    "batch_no": b.batch_no,
                    "brand_name": b.brand_name,
                    "quantity": b.quantity,
                    "expiry_date": b.expiry_date.isoformat(),
                    "days_expired": (today - b.expiry_date).days
                })
            elif b.expiry_date <= near_expiry_cutoff:
                near_expiry.append({
                    "batch_no": b.batch_no,
                    "brand_name": b.brand_name,
                    "quantity": b.quantity,
                    "expiry_date": b.expiry_date.isoformat(),
                    "days_remaining": (b.expiry_date - today).days
                })

        # 2. Low-stock alerts
        stock_q = db.query(PharmacyMedicineStock)
        if store_id:
            stock_q = stock_q.filter(PharmacyMedicineStock.store_id == store_id)

        low_stock = []
        for s in stock_q.all():
            if s.stock_quantity <= s.reorder_level:
                low_stock.append({
                    "id": s.id,
                    "brand_name": s.brand_name,
                    "generic_name": s.generic_name,
                    "current_stock": s.stock_quantity,
                    "reorder_level": s.reorder_level,
                    "status": "OUT_OF_STOCK" if s.stock_quantity == 0 else "LOW_STOCK"
                })

        return {
            "store_id": store_id,
            "low_stock_count": len(low_stock),
            "near_expiry_count": len(near_expiry),
            "expired_count": len(expired),
            "low_stock_items": low_stock,
            "near_expiry_batches": near_expiry,
            "expired_batches": expired
        }

    @classmethod
    def export_inventory_csv(cls, db: Session, store_id: Optional[int] = None) -> str:
        """Export inventory batches as CSV for migration and third-party pharmacy POS integration"""
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "store_id", "brand_name", "generic_name", "batch_no",
            "expiry_date", "quantity", "mrp", "purchase_price",
            "hsn_code", "gst_rate", "drug_schedule"
        ])

        batch_q = db.query(StoreInventoryBatch)
        if store_id:
            batch_q = batch_q.filter(StoreInventoryBatch.store_id == store_id)
        batches = batch_q.all()

        if batches:
            for b in batches:
                writer.writerow([
                    b.store_id, b.brand_name, b.generic_name, b.batch_no,
                    b.expiry_date.isoformat(), b.quantity, b.mrp, b.purchase_price,
                    b.hsn_code, b.gst_rate, b.drug_schedule
                ])
        else:
            # Fallback to PharmacyMedicineStock records
            stock_q = db.query(PharmacyMedicineStock)
            if store_id:
                stock_q = stock_q.filter(PharmacyMedicineStock.store_id == store_id)
            for s in stock_q.all():
                writer.writerow([
                    s.store_id or (store_id or 1),
                    s.brand_name,
                    s.generic_name,
                    s.batch_number or "B-2026-001",
                    (datetime.date.today() + datetime.timedelta(days=730)).isoformat(),
                    s.stock_quantity,
                    s.unit_price_brand,
                    s.unit_price_generic,
                    "3004",
                    12.0,
                    s.drug_schedule or "OTC"
                ])

        return output.getvalue()

    @classmethod
    def import_inventory_csv(cls, db: Session, csv_content: str, default_store_id: int = 1) -> Dict[str, Any]:
        """Import batches from CSV, upserting into StoreInventoryBatch and PharmacyMedicineStock"""
        reader = csv.DictReader(io.StringIO(csv_content.strip()))
        imported_count = 0
        errors = []

        for row_idx, row in enumerate(reader, start=1):
            try:
                brand = (row.get("brand_name") or "").strip()
                if not brand:
                    continue
                generic = (row.get("generic_name") or brand).strip()
                batch_no = (row.get("batch_no") or f"BATCH-{row_idx}").strip().upper()
                exp_str = (row.get("expiry_date") or "").strip()
                
                # Parse date
                try:
                    if "/" in exp_str:
                        parts = exp_str.split("/")
                        if len(parts) == 3:
                            exp_date = datetime.date(int(parts[2]), int(parts[1]), int(parts[0]))
                        elif len(parts) == 2:
                            exp_date = datetime.date(int(parts[1]), int(parts[0]), 28)
                        else:
                            exp_date = datetime.date.today() + datetime.timedelta(days=365)
                    elif "-" in exp_str:
                        exp_date = datetime.date.fromisoformat(exp_str)
                    else:
                        exp_date = datetime.date.today() + datetime.timedelta(days=365)
                except Exception:
                    exp_date = datetime.date.today() + datetime.timedelta(days=365)

                qty = int(row.get("quantity") or 0)
                mrp = float(row.get("mrp") or 0.0)
                purchase_price = float(row.get("purchase_price") or (mrp * 0.7))
                hsn = (row.get("hsn_code") or "3004").strip()
                gst_rate = float(row.get("gst_rate") or 12.0)
                drug_schedule = (row.get("drug_schedule") or "OTC").strip().upper()
                target_store_id = int(row.get("store_id") or default_store_id)

                # Upsert StoreInventoryBatch
                existing_batch = db.query(StoreInventoryBatch).filter(
                    StoreInventoryBatch.store_id == target_store_id,
                    StoreInventoryBatch.brand_name == brand,
                    StoreInventoryBatch.batch_no == batch_no
                ).first()

                if existing_batch:
                    existing_batch.quantity = qty
                    existing_batch.mrp = mrp
                    existing_batch.purchase_price = purchase_price
                    existing_batch.expiry_date = exp_date
                    existing_batch.hsn_code = hsn
                    existing_batch.gst_rate = gst_rate
                    existing_batch.drug_schedule = drug_schedule
                else:
                    new_batch = StoreInventoryBatch(
                        store_id=target_store_id,
                        brand_name=brand,
                        generic_name=generic,
                        batch_no=batch_no,
                        expiry_date=exp_date,
                        quantity=qty,
                        mrp=mrp,
                        purchase_price=purchase_price,
                        hsn_code=hsn,
                        gst_rate=gst_rate,
                        drug_schedule=drug_schedule
                    )
                    db.add(new_batch)

                # Also sync into PharmacyMedicineStock
                stock_rec = db.query(PharmacyMedicineStock).filter(
                    PharmacyMedicineStock.brand_name == brand
                ).first()
                if stock_rec:
                    stock_rec.stock_quantity = max(stock_rec.stock_quantity, qty)
                    stock_rec.unit_price_brand = mrp
                else:
                    db.add(PharmacyMedicineStock(
                        store_id=target_store_id,
                        brand_name=brand,
                        generic_name=generic,
                        batch_number=batch_no,
                        stock_quantity=qty,
                        reorder_level=20,
                        unit_price_brand=mrp,
                        unit_price_generic=round(mrp * 0.25, 2),
                        savings_percent=75.0,
                        drug_schedule=drug_schedule
                    ))

                imported_count += 1
            except Exception as e:
                errors.append(f"Row {row_idx}: {str(e)}")

        db.commit()
        return {
            "success": True,
            "batches_imported": imported_count,
            "errors": errors
        }
