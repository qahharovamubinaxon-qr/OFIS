-- Structured address parts for registration addresses (built-from-blank flow).
-- Nullable: rows created from an uploaded ready-made template leave them empty.

ALTER TABLE registration_addresses ADD COLUMN oblast TEXT;
ALTER TABLE registration_addresses ADD COLUMN raion TEXT;
ALTER TABLE registration_addresses ADD COLUMN gorod TEXT;
ALTER TABLE registration_addresses ADD COLUMN ulitsa TEXT;
ALTER TABLE registration_addresses ADD COLUMN dom TEXT;
ALTER TABLE registration_addresses ADD COLUMN korpus TEXT;
ALTER TABLE registration_addresses ADD COLUMN stroenie TEXT;
ALTER TABLE registration_addresses ADD COLUMN kvartira TEXT;
ALTER TABLE registration_addresses ADD COLUMN regional_number TEXT;
