from templates import HTML_TEMPLATE


def test_phase2_i18n_keys_present_both_langs():
    for key in ("please_confirm", "confirm", "type_to_confirm"):
        assert HTML_TEMPLATE.count(key + ":") >= 2, f"{key} missing from a language dict"
