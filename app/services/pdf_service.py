import io
import datetime
from types import SimpleNamespace
import qrcode
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch

class PDFService:
    @staticmethod
    def generate_receipt_pdf(slip_input) -> bytes:
        """Generate high quality, professional medical receipt & prescription slip PDF"""
        # Convert dict to object if passed as dict
        if isinstance(slip_input, dict):
            slip = SimpleNamespace(
                slip_number=slip_input.get("slip_number", "HSL-2026-00000"),
                verification_hash=slip_input.get("verification_hash", "0"*64),
                visit_date=slip_input.get("visit_date") or datetime.datetime.utcnow(),
                payment_status=slip_input.get("payment_status", "PAID"),
                subtotal=slip_input.get("subtotal", 0.0),
                tax_percent=slip_input.get("tax_percent", 5.0),
                tax_amount=slip_input.get("tax_amount", 0.0),
                discount_amount=slip_input.get("discount_amount", 0.0),
                insurance_covered=slip_input.get("insurance_covered", 0.0),
                grand_total=slip_input.get("grand_total", 0.0),
                diagnosis=slip_input.get("diagnosis", "Clinical Consultation"),
                symptoms=slip_input.get("symptoms", "General routine checkup"),
                doctor=SimpleNamespace(
                    name=slip_input.get("doctor_name", "Dr. K. S. Rao, M.B.B.S., M.D."),
                    clinic_name=slip_input.get("clinic_name", "HealthSlip AI Multi-Specialty Clinic & Seva Kendra"),
                    license_number="TSMC-2024-8841",
                    specialization="General & Internal Medicine"
                ),
                patient=SimpleNamespace(
                    full_name=slip_input.get("patient_name", "Rajesh Kumar"),
                    age=slip_input.get("patient_age", 28),
                    gender=slip_input.get("patient_gender", "Male"),
                    phone=slip_input.get("patient_phone", "+91 98765 43210"),
                    blood_group="O+"
                ),
                items=[SimpleNamespace(**it) if isinstance(it, dict) else it for it in slip_input.get("items", [])],
                reminders=[SimpleNamespace(**r) if isinstance(r, dict) else r for r in slip_input.get("reminders", [])]
            )
        else:
            slip = slip_input

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            rightMargin=36,
            leftMargin=36,
            topMargin=36,
            bottomMargin=36
        )

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'ClinicTitle',
            parent=styles['Heading1'],
            fontSize=18,
            leading=22,
            textColor=colors.HexColor("#1E3A8A"),
            fontName='Helvetica-Bold'
        )
        subtitle_style = ParagraphStyle(
            'ClinicSubtitle',
            parent=styles['Normal'],
            fontSize=9,
            leading=12,
            textColor=colors.HexColor("#4B5563"),
            fontName='Helvetica'
        )
        section_style = ParagraphStyle(
            'SectionHeader',
            parent=styles['Heading2'],
            fontSize=11,
            leading=14,
            textColor=colors.HexColor("#1E3A8A"),
            fontName='Helvetica-Bold',
            spaceBefore=6,
            spaceAfter=4
        )
        body_style = ParagraphStyle(
            'ReceiptBody',
            parent=styles['Normal'],
            fontSize=9,
            leading=12,
            textColor=colors.HexColor("#1F2937")
        )
        small_style = ParagraphStyle(
            'SmallMuted',
            parent=styles['Normal'],
            fontSize=8,
            leading=10,
            textColor=colors.HexColor("#6B7280")
        )

        elements = []

        # 1. Header with QR Code & Clinic Branding
        qr = qrcode.QRCode(version=1, box_size=3, border=1)
        qr.add_data(f"VERIFY:{slip.slip_number}|HASH:{slip.verification_hash[:16]}")
        qr.make(fit=True)
        qr_img = qr.make_image(fill_color="#1E3A8A", back_color="white")
        qr_buffer = io.BytesIO()
        qr_img.save(qr_buffer, format="PNG")
        qr_buffer.seek(0)
        reportlab_qr = Image(qr_buffer, width=1.1*inch, height=1.1*inch)

        clinic_name = getattr(slip.doctor, "clinic_name", "HealthSlip AI Multi-Specialty Clinic & Seva Kendra")
        doctor_name = getattr(slip.doctor, "name", "Dr. K. S. Rao, M.B.B.S., M.D.")
        license_num = getattr(slip.doctor, "license_number", "TSMC-2024-8841")
        specialty = getattr(slip.doctor, "specialization", "General Medicine")

        clinic_text = f"""
        <b>{clinic_name}</b><br/>
        Attending Physician: {doctor_name} ({license_num})<br/>
        Specialty: {specialty}<br/>
        Official Health Slip & Patient Receipt System (healthslip_prod)
        """
        clinic_para = Paragraph(clinic_text, subtitle_style)

        v_date = slip.visit_date if isinstance(slip.visit_date, datetime.datetime) else datetime.datetime.utcnow()
        header_table = Table(
            [[Paragraph(f"<b>HEALTHSLIP AI</b>", title_style), reportlab_qr],
             [clinic_para, Paragraph(f"<b>Receipt #:</b> {slip.slip_number}<br/><b>Date:</b> {v_date.strftime('%d %b %Y %H:%M')}<br/><b>Status:</b> {slip.payment_status}", small_style)]],
            colWidths=[5.0*inch, 2.2*inch]
        )
        header_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ]))
        elements.append(header_table)
        elements.append(Spacer(1, 10))
        elements.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#2563EB"), spaceBefore=2, spaceAfter=8))

        # 2. Patient Demographics & Clinical Summary
        p_name = getattr(slip.patient, "full_name", "Rajesh Kumar")
        p_age = getattr(slip.patient, "age", 28)
        p_gender = getattr(slip.patient, "gender", "Male")
        p_phone = getattr(slip.patient, "phone", "+91 98765 43210")
        p_blood = getattr(slip.patient, "blood_group", "O+")

        patient_data = [
            [
                Paragraph(f"<b>Patient Name:</b> {p_name}", body_style),
                Paragraph(f"<b>Age / Gender:</b> {p_age} Y / {p_gender}", body_style)
            ],
            [
                Paragraph(f"<b>Contact:</b> {p_phone}", body_style),
                Paragraph(f"<b>Blood Group:</b> {p_blood}", body_style)
            ],
            [
                Paragraph(f"<b>Diagnosis:</b> {slip.diagnosis or 'Consultation'}", body_style),
                Paragraph(f"<b>Symptoms:</b> {slip.symptoms or 'Standard checkup'}", body_style)
            ]
        ]
        patient_table = Table(patient_data, colWidths=[3.6*inch, 3.6*inch])
        patient_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#F3F4F6")),
            ('PADDING', (0, 0), (-1, -1), 5),
            ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor("#E5E7EB")),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#E5E7EB"))
        ]))
        elements.append(patient_table)
        elements.append(Spacer(1, 12))

        # 3. Itemized Medical Billing Table
        elements.append(Paragraph("ITEMIZED MEDICAL BILL & SERVICES", section_style))
        item_rows = [
            [Paragraph("<b>#</b>", body_style),
             Paragraph("<b>Description / Service</b>", body_style),
             Paragraph("<b>Type</b>", body_style),
             Paragraph("<b>Qty</b>", body_style),
             Paragraph("<b>Unit (INR)</b>", body_style),
             Paragraph("<b>Total (INR)</b>", body_style)]
        ]

        idx = 1
        for item in slip.items:
            i_name = getattr(item, "item_name", "Medical Service")
            i_type = getattr(item, "item_type", "MEDICATION")
            i_qty = getattr(item, "quantity", 1)
            i_unit = getattr(item, "unit_price", 0.0)
            i_total = getattr(item, "total_price", i_unit * i_qty)
            i_inst = getattr(item, "instructions", "")

            item_rows.append([
                Paragraph(str(idx), small_style),
                Paragraph(f"<b>{i_name}</b>" + (f"<br/><font color='#6B7280'>{i_inst}</font>" if i_inst else ""), small_style),
                Paragraph(i_type, small_style),
                Paragraph(str(i_qty), small_style),
                Paragraph(f"INR {i_unit:.2f}", small_style),
                Paragraph(f"INR {i_total:.2f}", small_style)
            ])
            idx += 1

        # Summary rows
        item_rows.append(["", "", "", "", Paragraph("<b>Subtotal:</b>", small_style), Paragraph(f"INR {slip.subtotal:.2f}", small_style)])
        item_rows.append(["", "", "", "", Paragraph(f"<b>Tax ({slip.tax_percent}%):</b>", small_style), Paragraph(f"INR {slip.tax_amount:.2f}", small_style)])
        if slip.discount_amount > 0:
            item_rows.append(["", "", "", "", Paragraph("<b>Discount:</b>", small_style), Paragraph(f"-INR {slip.discount_amount:.2f}", small_style)])
        item_rows.append(["", "", "", "", Paragraph("<b>Grand Total:</b>", body_style), Paragraph(f"<b>INR {slip.grand_total:.2f}</b>", body_style)])

        items_table = Table(item_rows, colWidths=[0.3*inch, 3.4*inch, 1.2*inch, 0.5*inch, 0.9*inch, 0.9*inch])
        items_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#EEF2F6")),
            ('ALIGN', (0, 0), (0, -1), 'CENTER'),
            ('ALIGN', (3, 0), (3, -1), 'CENTER'),
            ('ALIGN', (4, 0), (-1, -1), 'RIGHT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, len(slip.items)), 0.5, colors.HexColor("#E5E7EB")),
            ('PADDING', (0, 0), (-1, -1), 4),
            ('LINEBELOW', (0, 0), (-1, 0), 1, colors.HexColor("#2563EB")),
            ('BACKGROUND', (4, -1), (5, -1), colors.HexColor("#FEF3C7")),
        ]))
        elements.append(items_table)
        elements.append(Spacer(1, 12))

        # 4. Medication Reminders & Dosage Schedule
        if slip.reminders:
            elements.append(Paragraph("SCHEDULED MEDICATION DOSAGE & REMINDERS", section_style))
            med_rows = [
                [Paragraph("<b>Medicine</b>", body_style),
                 Paragraph("<b>Dosage</b>", body_style),
                 Paragraph("<b>Slot</b>", body_style),
                 Paragraph("<b>Scheduled Time</b>", body_style),
                 Paragraph("<b>Instructions</b>", body_style)]
            ]
            for rem in slip.reminders:
                m_name = getattr(rem, "medicine_name", "Medicine")
                m_dose = getattr(rem, "dosage", "1 pill")
                m_slot = getattr(rem, "timing_slot", "MORNING")
                m_time = getattr(rem, "schedule_time", "12:00 am")
                m_inst = getattr(rem, "instructions", "Take with water")

                med_rows.append([
                    Paragraph(f"<b>{m_name}</b>", small_style),
                    Paragraph(m_dose, small_style),
                    Paragraph(m_slot, small_style),
                    Paragraph(m_time, small_style),
                    Paragraph(m_inst, small_style)
                ])
            med_table = Table(med_rows, colWidths=[1.8*inch, 1.0*inch, 1.0*inch, 1.2*inch, 2.2*inch])
            med_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#F0FDF4")),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#DCFCE7")),
                ('PADDING', (0, 0), (-1, -1), 4),
            ]))
            elements.append(med_table)
            elements.append(Spacer(1, 10))

        # 5. Security & Tamper-Proof Cryptographic Verification Footer
        security_text = f"""
        <b>CRYPTOGRAPHIC VERIFICATION SEAL (HMAC-SHA256)</b><br/>
        Digital Hash: <font face="Courier">{slip.verification_hash}</font><br/>
        This official document has been digitally generated and sealed by HealthSlip AI on MySQL database healthslip_prod.<br/>
        Scan QR code above to verify authenticity with public hospital register.
        """
        sec_table = Table([[Paragraph(security_text, small_style)]], colWidths=[7.2*inch])
        sec_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
            ('BOX', (0, 0), (-1, -1), 1, colors.HexColor("#CBD5E1")),
            ('PADDING', (0, 0), (-1, -1), 6)
        ]))
        elements.append(sec_table)

        doc.build(elements)
        buffer.seek(0)
        return buffer.getvalue()

    @staticmethod
    def generate_gst_tax_invoice_pdf(invoice_data: dict) -> bytes:
        """
        Generate Indian GST-Compliant Pharmacy Tax Invoice PDF.
        Includes GSTIN, Drug License numbers (20-B/21-B), HSN Codes, CGST/SGST split,
        FEFO batch numbers, expiry dates, and Jan Aushadhi generic savings.
        """
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            rightMargin=36,
            leftMargin=36,
            topMargin=36,
            bottomMargin=36
        )

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'GSTTitle',
            parent=styles['Heading1'],
            fontSize=16,
            leading=20,
            textColor=colors.HexColor("#0F172A"),
            fontName="Helvetica-Bold"
        )
        sub_style = ParagraphStyle(
            'GSTSub',
            parent=styles['Normal'],
            fontSize=8,
            leading=11,
            textColor=colors.HexColor("#475569")
        )
        bold_small = ParagraphStyle(
            'GSTBoldSmall',
            parent=styles['Normal'],
            fontSize=8,
            leading=11,
            fontName="Helvetica-Bold",
            textColor=colors.HexColor("#0F172A")
        )
        table_hdr = ParagraphStyle(
            'GSTHdr',
            parent=styles['Normal'],
            fontSize=8,
            leading=10,
            fontName="Helvetica-Bold",
            textColor=colors.HexColor("#FFFFFF")
        )
        table_cell = ParagraphStyle(
            'GSTCell',
            parent=styles['Normal'],
            fontSize=8,
            leading=10,
            textColor=colors.HexColor("#1E293B")
        )

        elements = []

        store_info = invoice_data.get("store_info", {})
        patient = invoice_data.get("patient", {})
        doctor = invoice_data.get("doctor", {})
        financials = invoice_data.get("financials", {})
        items = invoice_data.get("items", [])
        seal = invoice_data.get("cryptographic_seal", "0" * 64)

        # 1. Store Header & Title
        store_name = store_info.get("name", "HealthSlip Central Pharmacy & Seva Kendra")
        store_dl = store_info.get("dl_number", "20-B/TS/48912 & 21-B/TS/48913")
        store_gstin = store_info.get("gstin", "36AAAAA0000A1Z5")
        store_addr = store_info.get("address", "Hyderabad, Telangana - 500020")
        store_phone = store_info.get("phone", "+91 98765 00002")

        header_html = f"""
        <b>{store_name}</b><br/>
        <font size="8" color="#475569">{store_addr} | Phone: {store_phone}<br/>
        <b>Drug License No:</b> {store_dl} | <b>GSTIN:</b> {store_gstin}</font>
        """

        inv_num = invoice_data.get("invoice_number", "INV-2026-001")
        inv_date = invoice_data.get("date", datetime.datetime.utcnow().strftime("%d %b %Y"))
        slip_num = invoice_data.get("slip_number", "HSL-2026-00000")

        inv_meta_html = f"""
        <div align="right">
        <b><font size="11" color="#0369A1">TAX INVOICE</font></b><br/>
        <font size="8"><b>Invoice No:</b> {inv_num}<br/>
        <b>Date:</b> {inv_date}<br/>
        <b>Rx Slip No:</b> {slip_num}</font>
        </div>
        """

        top_table = Table([
            [Paragraph(header_html, sub_style), Paragraph(inv_meta_html, sub_style)]
        ], colWidths=[4.2*inch, 3.0*inch])
        top_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('PADDING', (0, 0), (-1, -1), 0),
        ]))
        elements.append(top_table)
        elements.append(Spacer(1, 8))
        elements.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#0284C7"), spaceAfter=8))

        # 2. Patient & Prescribing Doctor Details
        p_name = patient.get("name", "Rajesh Kumar")
        p_phone = patient.get("phone", "+91 98765 43210")
        p_age_gender = f"{patient.get('age', 28)} Y / {patient.get('gender', 'MALE')}"

        d_name = doctor.get("name", "Dr. K. S. Rao, M.B.B.S., M.D.")
        d_lic = doctor.get("license", "TSMC-2024-8841")
        d_clinic = doctor.get("clinic", "HealthSlip Clinic")

        info_rows = [
            [
                Paragraph("<b>PATIENT DETAILS (Billed To):</b>", bold_small),
                Paragraph("<b>PRESCRIBING PRACTITIONER:</b>", bold_small)
            ],
            [
                Paragraph(f"Name: <b>{p_name}</b> ({p_age_gender})<br/>Mobile: {p_phone}", sub_style),
                Paragraph(f"Doctor: <b>{d_name}</b><br/>Reg / License No: {d_lic}<br/>Clinic: {d_clinic}", sub_style)
            ]
        ]
        info_table = Table(info_rows, colWidths=[3.6*inch, 3.6*inch])
        info_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
            ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
            ('PADDING', (0, 0), (-1, -1), 5),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ]))
        elements.append(info_table)
        elements.append(Spacer(1, 10))

        # 3. Itemized GST Medicines Table
        med_rows = [[
            Paragraph("S.No", table_hdr),
            Paragraph("Medicine Description / Salt", table_hdr),
            Paragraph("HSN", table_hdr),
            Paragraph("Batch", table_hdr),
            Paragraph("Exp", table_hdr),
            Paragraph("Qty", table_hdr),
            Paragraph("Rate (₹)", table_hdr),
            Paragraph("GST %", table_hdr),
            Paragraph("Amount (₹)", table_hdr)
        ]]

        idx = 1
        for it in items:
            name = it.get("item_name") or it.get("medicine_name") or "Medicine"
            hsn = it.get("hsn_code") or "3004"
            batch = it.get("batch_no") or it.get("batch_number") or "B-2026-01"
            exp = it.get("expiry_date") or "12/28"
            qty = it.get("quantity") or 1
            rate = float(it.get("unit_price") or it.get("unit_price_generic") or 10.0)
            gst_pct = float(it.get("gst_rate") or 12.0)
            amt = float(it.get("total_price") or (rate * qty))

            med_rows.append([
                Paragraph(str(idx), table_cell),
                Paragraph(f"<b>{name}</b>", table_cell),
                Paragraph(hsn, table_cell),
                Paragraph(batch, table_cell),
                Paragraph(str(exp), table_cell),
                Paragraph(str(qty), table_cell),
                Paragraph(f"{rate:.2f}", table_cell),
                Paragraph(f"{gst_pct:.1f}%", table_cell),
                Paragraph(f"{amt:.2f}", table_cell)
            ])
            idx += 1

        med_table = Table(
            med_rows,
            colWidths=[0.4*inch, 2.3*inch, 0.6*inch, 0.8*inch, 0.6*inch, 0.4*inch, 0.7*inch, 0.6*inch, 0.8*inch]
        )
        med_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#0284C7")),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
            ('PADDING', (0, 0), (-1, -1), 4),
            ('ALIGN', (0, 0), (0, -1), 'CENTER'),
            ('ALIGN', (5, 0), (-1, -1), 'RIGHT'),
        ]))
        elements.append(med_table)
        elements.append(Spacer(1, 10))

        # 4. GST Tax Split & Financial Summary
        subtotal = float(financials.get("subtotal", 0.0))
        tax_amt = float(financials.get("tax_amount", 0.0))
        cgst_amt = round(tax_amt / 2.0, 2)
        sgst_amt = round(tax_amt / 2.0, 2)
        grand_total = float(financials.get("grand_total", subtotal + tax_amt))
        savings = float(financials.get("jan_aushadhi_savings", 0.0))

        summary_rows = [
            [
                Paragraph("<b>Taxable Subtotal:</b>", table_cell),
                Paragraph(f"₹ {subtotal:.2f}", table_cell)
            ],
            [
                Paragraph("<b>Central GST (CGST @ 6% / 2.5%):</b>", table_cell),
                Paragraph(f"₹ {cgst_amt:.2f}", table_cell)
            ],
            [
                Paragraph("<b>State GST (SGST @ 6% / 2.5%):</b>", table_cell),
                Paragraph(f"₹ {sgst_amt:.2f}", table_cell)
            ],
            [
                Paragraph("<b>Total GST Taxes:</b>", table_cell),
                Paragraph(f"₹ {tax_amt:.2f}", table_cell)
            ]
        ]
        if savings > 0:
            summary_rows.append([
                Paragraph("<font color='#059669'><b>Jan Aushadhi Generic Savings:</b></font>", table_cell),
                Paragraph(f"<font color='#059669'><b>- ₹ {savings:.2f}</b></font>", table_cell)
            ])
        summary_rows.append([
            Paragraph("<b><font size='10' color='#0F172A'>GRAND TOTAL (INR):</font></b>", table_cell),
            Paragraph(f"<b><font size='10' color='#0F172A'>₹ {grand_total:.2f}</font></b>", table_cell)
        ])

        sum_table = Table(summary_rows, colWidths=[2.5*inch, 1.2*inch])
        sum_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
            ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
            ('PADDING', (0, 0), (-1, -1), 4),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ]))

        # Place summary on right side
        empty_col = Table([[Paragraph("", sub_style)]], colWidths=[3.5*inch])
        fin_wrap = Table([[empty_col, sum_table]], colWidths=[3.5*inch, 3.7*inch])
        fin_wrap.setStyle(TableStyle([('PADDING', (0, 0), (-1, -1), 0)]))
        elements.append(fin_wrap)
        elements.append(Spacer(1, 12))

        # 5. Pharmacist Certification & Cryptographic Verification Seal
        footer_html = f"""
        <b>Pharmacist Dispense Declaration:</b> Certified that medications dispensed above strictly comply with Doctor's prescription.
        Controlled Drug records maintained under Drugs and Cosmetics Rules.<br/>
        <b>Cryptographic Seal (HMAC-SHA256):</b> <font face="Courier" size="7">{seal}</font><br/>
        <i>Computer generated GST tax invoice. No signature required.</i>
        """
        footer_table = Table([[Paragraph(footer_html, sub_style)]], colWidths=[7.2*inch])
        footer_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#F1F5F9")),
            ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor("#94A3B8")),
            ('PADDING', (0, 0), (-1, -1), 6)
        ]))
        elements.append(footer_table)

        doc.build(elements)
        buffer.seek(0)
        return buffer.getvalue()
