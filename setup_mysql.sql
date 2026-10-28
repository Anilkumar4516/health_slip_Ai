-- ==============================================================
-- HealthSlip AI - Database Initialization Script for MySQL Workbench
-- ==============================================================

-- 1. Create the database
CREATE DATABASE IF NOT EXISTS healthslip_prod
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE healthslip_prod;


-- 2. Verify active database
SELECT DATABASE() AS Current_Database;

-- 3. The tables will be auto-created by HealthSlip AI SQLAlchemy ORM:
--    - doctors
--    - patients
--    - health_slips
--    - receipt_items
--    - medication_reminders
--    - otp_verifications
--    - audit_logs

-- 4. Useful queries to inspect data in MySQL Workbench:
-- SELECT * FROM health_slips;
-- SELECT * FROM receipt_items;
-- SELECT * FROM medication_reminders;
-- SELECT * FROM otp_verifications;
-- SELECT * FROM audit_logs;
