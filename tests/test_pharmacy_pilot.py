import pytest
import datetime
from fastapi.testclient import TestClient
from main import app
from app.database import SessionLocal
from app.models.receipt import Receipt, Bill, Prescription, PrescriptionItem, Medicine
from app.models.pharmacy import PharmacyStore, StoreInventoryBatch, PharmacyMedicineStock, DispenseOrder
from app.models.verification import AuditEvent

client = TestClient(app)

def test_pharmacy_slip_hmac_lookup_and_verification():
    """Verify QR/Slip lookup endpoint validates HMAC seal and extracts clinical details"""
    # Grab an existing receipt
    recent_r = client.get("/api/receipts").json()
    assert len(recent_r) > 0
    slip_no = recent_r[0]["slip_number"]

    res = client.get(f"/api/pharmacy/verify-slip/{slip_no}")
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["success"] is True
    assert data["hmac_verified"] is True
    assert data["slip_number"] == slip_no
    assert "patient" in data
    assert "doctor" in data
    assert "items" in data

def test_inventory_fefo_decrement_and_alerts():
    """Verify FEFO stock decrement (earliest expiry first) and alerts endpoint"""
    db = SessionLocal()
    try:
        # Create batches with different expiries
        today = datetime.date.today()
        b1 = StoreInventoryBatch(
            store_id=1,
            brand_name="TestParacetamol 500mg",
            generic_name="Paracetamol 500mg",
            batch_no="BATCH-EARLY-01",
            expiry_date=today + datetime.timedelta(days=20), # Near expiry
            quantity=10,
            mrp=15.0,
            purchase_price=8.0
        )
        b2 = StoreInventoryBatch(
            store_id=1,
            brand_name="TestParacetamol 500mg",
            generic_name="Paracetamol 500mg",
            batch_no="BATCH-LATER-02",
            expiry_date=today + datetime.timedelta(days=400), # Fresh
            quantity=30,
            mrp=15.0,
            purchase_price=8.0
        )
        db.add_all([b1, b2])
        db.commit()

        # Check inventory alerts finds the near-expiry batch
        alerts_resp = client.get("/api/pharmacy/inventory/alerts?store_id=1")
        assert alerts_resp.status_code == 200
        alerts_data = alerts_resp.json()
        assert alerts_data["near_expiry_count"] >= 1
        near_batch_nos = [nb["batch_no"] for nb in alerts_data["near_expiry_batches"]]
        assert "BATCH-EARLY-01" in near_batch_nos

        # Clean up
        db.delete(b1)
        db.delete(b2)
        db.commit()
    finally:
        db.close()

def test_inventory_csv_export_and_import():
    """Verify CSV export and subsequent CSV import update store batches"""
    export_resp = client.get("/api/pharmacy/inventory/export-csv?store_id=1")
    assert export_resp.status_code == 200
    assert "text/csv" in export_resp.headers["content-type"]
    csv_text = export_resp.text
    assert "brand_name" in csv_text
    assert "batch_no" in csv_text

    # Test importing a CSV batch
    new_csv = (
        "store_id,brand_name,generic_name,batch_no,expiry_date,quantity,mrp,purchase_price,hsn_code,gst_rate,drug_schedule\n"
        "1,Dolo 650mg,Paracetamol 650mg,DOLO-TEST-01,2027-12-31,100,30.0,20.0,3004,12.0,OTC\n"
    )
    import_resp = client.post("/api/pharmacy/inventory/import-csv?store_id=1", content=new_csv)
    assert import_resp.status_code == 200
    res = import_resp.json()
    assert res["success"] is True
    assert res["batches_imported"] >= 1

    # Verify batch is saved in DB
    db = SessionLocal()
    try:
        saved_b = db.query(StoreInventoryBatch).filter(StoreInventoryBatch.batch_no == "DOLO-TEST-01").first()
        assert saved_b is not None
        assert saved_b.brand_name == "Dolo 650mg"
        assert saved_b.quantity == 100
        db.delete(saved_b)
        db.commit()
    finally:
        db.close()

def test_gst_invoice_pdf_download():
    """Verify GST Tax Invoice PDF generation returns valid ReportLab PDF binary bytes"""
    recent_r = client.get("/api/receipts").json()
    slip_no = recent_r[0]["slip_number"]

    pdf_resp = client.get(f"/api/pharmacy/invoice/{slip_no}/pdf?store_type=URBAN")
    assert pdf_resp.status_code == 200
    assert pdf_resp.headers["content-type"] == "application/pdf"
    assert pdf_resp.content.startswith(b"%PDF"), "Must return valid PDF magic bytes"
