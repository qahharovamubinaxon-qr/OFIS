from src.pdf import alliance_fields as af


def test_catalogue_has_the_alliance_fields():
    for key in ("fio_upper", "surname", "name", "patronymic", "gender",
                "ud_number", "dolzhnost", "start_date", "end_date"):
        assert key in af.CATALOGUE, key
        assert key in af.SAMPLES, key


def test_image_fields_are_photo_and_signature():
    assert af.IMG_KEYS == ("img_photo", "img_sign")
    assert set(af.IMG_KEYS) <= set(af.IMG_LABELS)


def test_field_dataclass_roundtrips():
    f = af.Field(key="ud_number", page=1, x=0.5, baseline=0.4, size=0.03)
    assert af.Field.from_dict(f.as_dict()).key == "ud_number"
