-- Where a hostel wants the stay-start date inside the «Отметка о подтверждении»
-- box: the centre of the printed date, in points on the form's second page.
-- Marked once per hostel by the operator; NULL means the form's default spot.
ALTER TABLE registration_addresses ADD COLUMN stay_from_x REAL;
ALTER TABLE registration_addresses ADD COLUMN stay_from_y REAL;
