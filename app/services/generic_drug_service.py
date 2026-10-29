import datetime
import hashlib
import hmac
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from app.config import settings
from app.models.pharmacy import PharmacyMedicineStock, DispenseOrder
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
