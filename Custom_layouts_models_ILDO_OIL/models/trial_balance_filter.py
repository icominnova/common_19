from odoo import models


class IldoTrialBalanceReportHandler(models.AbstractModel):
    _inherit = "account.trial.balance.report.handler"

    def _add_initial_column(
        self,
        report,
        options,
        headers,
        groups,
        columns,
        date_to,
        block_id,
        fiscal_year_start,
    ):
        """Afficher le solde initial pour toutes les recherches commencant par 4 ou 5."""
        search = (options.get("filter_search_bar") or "").strip()

        if not search.startswith(("4", "5")):
            return headers, groups, columns

        return super()._add_initial_column(
            report,
            options,
            headers,
            groups,
            columns,
            date_to,
            block_id,
            fiscal_year_start,
        )