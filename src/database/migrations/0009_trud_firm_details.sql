-- A trud firm may now be typed in by hand instead of uploading two templates:
-- the program builds the уведомление and the трудовой договор from these.
ALTER TABLE trud_firms ADD COLUMN legal_form TEXT;
ALTER TABLE trud_firms ADD COLUMN short_name TEXT;
ALTER TABLE trud_firms ADD COLUMN inn TEXT;
ALTER TABLE trud_firms ADD COLUMN kpp TEXT;
ALTER TABLE trud_firms ADD COLUMN ogrn TEXT;
ALTER TABLE trud_firms ADD COLUMN okved TEXT;
ALTER TABLE trud_firms ADD COLUMN address TEXT;
ALTER TABLE trud_firms ADD COLUMN district TEXT;
ALTER TABLE trud_firms ADD COLUMN mvd_office TEXT;
ALTER TABLE trud_firms ADD COLUMN director TEXT;
ALTER TABLE trud_firms ADD COLUMN director_position TEXT;
ALTER TABLE trud_firms ADD COLUMN phone TEXT;
ALTER TABLE trud_firms ADD COLUMN stamp_path TEXT;
