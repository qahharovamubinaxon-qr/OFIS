-- Hostel registrations reuse the registration_addresses table with kind='hostel'.
-- Hostels additionally carry an organization name, ИНН and room (комната).
ALTER TABLE registration_addresses ADD COLUMN kind TEXT NOT NULL DEFAULT 'regular';
ALTER TABLE registration_addresses ADD COLUMN organization_name TEXT;
ALTER TABLE registration_addresses ADD COLUMN inn TEXT;
ALTER TABLE registration_addresses ADD COLUMN komnata TEXT;
