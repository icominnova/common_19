from odoo import models


class IldoGeneralLedgerFilter(models.AbstractModel):
    _inherit = "account.general.ledger.report.handler"

    def _get_query(
        self,
        options,
        current_groupby,
        order_by_account=False,
        offset=0,
        limit=None,
    ):
        search = (options.get("filter_search_bar") or "").strip()

        if search and search.isdigit():
            # Copie des options pour ne pas modifier
            # celles utilisées ailleurs par le rapport.
            options = dict(options)

            # Conserver tous les filtres existants.
            existing_domain = list(
                options.get("forced_domain") or []
            )

            # Filtrer sur le début du numéro de compte.
            existing_domain.append(
                ("account_id.code", "=ilike", f"{search}%")
            )

            options["forced_domain"] = existing_domain

        return super()._get_query(
            options,
            current_groupby,
            order_by_account=order_by_account,
            offset=offset,
            limit=limit,
        )