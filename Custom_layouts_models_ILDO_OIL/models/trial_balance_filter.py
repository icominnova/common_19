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
        """Supprimer le Solde initial de la Balance comptable."""
        return headers, groups, columns