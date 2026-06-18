-- ===========================================================
-- Optional sample data for MediTrack.
-- Includes one overdue record so the dashboard's "overdue
-- maintenance" panel has something to show during the demo.
--
-- Run with:
--   mysql -h <DB_HOST> -u <DB_USER> -p meditrack < deployment/seed_data.sql
-- ===========================================================

USE meditrack;

INSERT INTO equipment (equipment_name, serial_number, department, purchase_date, status)
VALUES
    ('Ventilator',        'VEN-1001', 'ICU',         '2021-03-12', 'Active'),
    ('Infusion Pump',     'IPM-2044', 'Emergency',   '2022-07-01', 'Active'),
    ('Defibrillator',     'DEF-3310', 'ICU',         '2020-11-20', 'Under Maintenance'),
    ('Patient Monitor',   'MON-4470', 'Pediatrics',  '2023-01-15', 'Active');

-- A maintenance log entry whose next_due_date is in the past,
-- so this ventilator will show up as overdue on the dashboard.
INSERT INTO maintenance_log
    (equipment_id, maintenance_date, technician_name, issue_reported, resolution_notes, next_due_date)
VALUES
    (1, '2025-12-01', 'R. Mehta', 'Routine calibration', 'Calibrated and tested OK', '2026-06-01');

-- A healthy, up-to-date record for contrast.
INSERT INTO maintenance_log
    (equipment_id, maintenance_date, technician_name, issue_reported, resolution_notes, next_due_date)
VALUES
    (2, '2026-05-10', 'A. Khan', 'Scheduled service', 'Replaced battery, passed test', '2026-11-10');
