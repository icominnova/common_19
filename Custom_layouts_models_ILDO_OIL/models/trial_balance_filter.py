
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
        """
        Balance comptable ILDO OIL.

        Ne pas ajouter la colonne Solde initial.

        Le moteur standard conserve les colonnes Débit et Crédit
        de la période et calcule le Solde final à partir de
        ces mouvements uniquement.
        """
        return headers, groups, columns
