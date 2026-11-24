from odoo import models


class IldoGeneralLedgerInitialColumn(models.Model):
    _inherit = "account.report"

    def _init_options_columns(self, options, previous_options):
        super()._init_options_columns(
            options,
            previous_options,
        )

        general_ledger = self.env.ref(
            "account_reports.general_ledger_report",
            raise_if_not_found=False,
        )

        if not general_ledger or self.id != general_ledger.id:
            return

        if "filter_search_bar" in options:
            search = options.get("filter_search_bar")
        else:
            search = (previous_options or {}).get(
                "filter_search_bar"
            )

        search = str(search or "").strip()

        show_initial = (
            search.isdigit()
            and search.startswith(("4", "5"))
        )

        if not show_initial:
            options["columns"] = [
                column
                for column in options["columns"]
                if column.get("expression_label")
                != "ildo_initial_balance"
            ]
