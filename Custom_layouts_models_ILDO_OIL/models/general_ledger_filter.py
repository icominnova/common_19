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

        # Recherche par prefixe du numero de compte.
        search = (options.get("filter_search_bar") or "").strip()

        # Reprendre la logique de la Balance comptable :
        # activer le traitement du solde initial pour
        # les recherches numeriques commencant par 4 ou 5.
        is_opening_balance_search = (
            search.isdigit()
            and search.startswith(("4", "5"))
        )

        # Pour les comptes 4 et 5, ne pas exclure les
        # ecritures anterieures a la periode.
        # Le moteur Odoo utilise sa requete "from_beginning"
        # pour calculer les soldes d'ouverture.
        #
        # Pour les autres comptes, conserver notre filtre
        # de dates existant.
        if not is_opening_balance_search:
            date_from = options["date"]["date_from"]

            existing_domain.append(
                ("date", ">=", date_from)
            )

        # Conserver la recherche par prefixe du compte.
        if search.isdigit():
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

    def _report_custom_engine_general_ledger(
        self,
        expressions,
        options,
        date_scope,
        current_groupby,
        next_groupby,
        offset=0,
        limit=None,
        warnings=None,
    ):
        # Premier calcul : moteur Odoo avec les options
        # normales du Grand livre general.
        result = super()._report_custom_engine_general_ledger(
            expressions,
            options,
            date_scope,
            current_groupby,
            next_groupby,
            offset=offset,
            limit=limit,
            warnings=warnings,
        )

        search = (
            options.get("filter_search_bar") or ""
        ).strip()

        applies = (
            search.isdigit()
            and search.startswith(("4", "5"))
        )

        # Ne pas toucher aux autres recherches.
        if not applies:
            return self._ildo_with_initial_balance(result, current_groupby, applies)

        # Ne pas modifier les lignes des ecritures
        # ni la construction du solde initial.
        if current_groupby not in (None, "account_id"):
            return self._ildo_with_initial_balance(result, current_groupby, applies)

        # Second calcul : mouvements de la periode.
        period_options = dict(options)

        period_domain = list(
            options.get("forced_domain") or []
        )

        period_domain.append(
            ("date", ">=", options["date"]["date_from"])
        )

        period_options["forced_domain"] = period_domain

        period_result = (
            super()._report_custom_engine_general_ledger(
                expressions,
                period_options,
                date_scope,
                current_groupby,
                next_groupby,
                offset=offset,
                limit=limit,
                warnings=warnings,
            )
        )

        # TOTAL GENERAL :
        # Debit/Credit = periode.
        # Solde = solde cumule natif.
        if current_groupby is None:
            for field in ("debit", "credit"):
                result[field] = period_result.get(
                    field,
                    0.0,
                )
            return self._ildo_with_initial_balance(result, current_groupby, applies)

        # TOTAUX PAR COMPTE :
        # conserver tous les comptes du premier calcul,
        # meme sans mouvement pendant la periode.
        movements_by_account = dict(period_result)

        for account_id, account_values in result:
            period_values = movements_by_account.get(
                account_id,
                {},
            )

            for field in ("debit", "credit"):
                account_values[field] = period_values.get(
                    field,
                    0.0,
                )

        return self._ildo_with_initial_balance(result, current_groupby, applies)


    def _ildo_with_initial_balance(
        self,
        result,
        current_groupby,
        active,
    ):
        """
        Calculer le solde initial des comptes 4 et 5.

        Solde initial = Solde final
                        - Debit periode
                        + Credit periode.

        Aucun mouvement comptable n'est modifie.
        """

        def opening_balance(values):
            balance = values.get("balance") or 0.0
            debit = values.get("debit") or 0.0
            credit = values.get("credit") or 0.0

            return balance - debit + credit

        if current_groupby is None:

            result["ildo_initial_balance"] = (
                opening_balance(result)
                if active
                else None
            )

            return result

        for grouping_key, values in result:

            initial = None

            if active:

                if current_groupby == "account_id":
                    initial = opening_balance(values)

                elif (
                    current_groupby == "id_with_accumulated_balance"
                    and str(grouping_key).startswith(
                        "balance_line_"
                    )
                ):
                    initial = values.get("balance")

            values["ildo_initial_balance"] = initial

        return result
