from unittest.mock import MagicMock, patch

from backend.app.services.system_field_defaults import ensure_system_field_defaults


def test_overview_extraction_rule_is_not_seeded():
    database = MagicMock()
    database.get_lims_field.return_value = {"fieldCode": "existing"}
    database.list_system_field_rules.side_effect = lambda code: (
        [] if code == "narrative.chapter" else [{"sourceType": "FIXED"}]
    )

    with patch("backend.app.services.system_field_defaults._field_code", side_effect=lambda _, code: code):
        ensure_system_field_defaults(database)

    database.save_system_field_rule.assert_not_called()
