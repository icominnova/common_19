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
        options = dict(options)

        existing_domain = list(options.get("forced_domain") or [])

        # 1. Exclure les écritures antérieures à la période choisie.
        date_from = options["date"]["date_from"]

        existing_domain.append(
            ("date", ">=", date_from)
        )

        # 2. Conserver la recherche par préfixe du numéro de compte.
        search = (options.get("filter_search_bar") or "").strip()

        if search and search.isdigit():
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