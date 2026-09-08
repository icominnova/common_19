from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """Remove the obsolete wizard-based third-party balance."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    legacy_xmlids = (
        "access_ildo_third_party_balance_wizard",
        "access_ildo_third_party_balance_wizard_readonly",
        "view_ildo_third_party_balance_wizard_form",
        "action_ildo_third_party_balance_wizard",
        "action_report_third_party_balance",
        "report_third_party_balance",
        "paperformat_third_party_balance",
    )
    xmlids = env["ir.model.data"].search(
        [
            ("module", "=", "Custom_layouts_models_ILDO_OIL"),
            ("name", "in", legacy_xmlids),
        ]
    )
    for xmlid in xmlids:
        record = env[xmlid.model].browse(xmlid.res_id).exists()
        if record:
            record.unlink()
    xmlids.unlink()

    cr.execute("DROP TABLE IF EXISTS ildo_third_party_balance_wizard CASCADE")
