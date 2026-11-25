from collections import defaultdict
from decimal import (
    Decimal,
    InvalidOperation,
    ROUND_HALF_UP,
)

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class SecefReport(models.Model):
    _name = "sunsoft.secef.report"
    _description = "Rapport statistique SECeF"
    _order = "generated_at desc, id desc"

    _name_unique = models.Constraint(
        "UNIQUE(name)",
        "La reference du rapport SECeF doit etre unique.",
    )

    name = fields.Char(
        string="Reference",
        required=True,
        readonly=True,
        copy=False,
        index=True,
    )

    report_type = fields.Selection(
        selection=[
            ("x_daily", "Rapport X quotidien"),
            ("x_periodic", "Rapport X periodique"),
            ("z", "Rapport Z"),
            ("a", "Rapport A"),
        ],
        string="Type de rapport",
        required=True,
        readonly=True,
        copy=False,
        index=True,
    )

    company_id = fields.Many2one(
        comodel_name="res.company",
        string="Societe",
        required=True,
        readonly=True,
        copy=False,
        index=True,
    )

    isf = fields.Char(
        string="ISF",
        readonly=True,
        copy=False,
    )

    period_start = fields.Datetime(
        string="Debut de periode",
        required=True,
        readonly=True,
        copy=False,
        index=True,
    )

    period_end = fields.Datetime(
        string="Fin de periode",
        required=True,
        readonly=True,
        copy=False,
        index=True,
    )

    generated_at = fields.Datetime(
        string="Date de generation",
        required=True,
        readonly=True,
        copy=False,
        index=True,
    )

    previous_report_id = fields.Many2one(
        comodel_name="sunsoft.secef.report",
        string="Rapport precedent",
        readonly=True,
        copy=False,
        ondelete="restrict",
    )

    transaction_ids = fields.Many2many(
        comodel_name="sunsoft.secef.transaction",
        relation="sunsoft_secef_report_transaction_rel",
        column1="report_id",
        column2="transaction_id",
        string="Transactions SECeF",
        readonly=True,
        copy=False,
    )

    move_ids = fields.Many2many(
        comodel_name="account.move",
        relation="sunsoft_secef_report_move_rel",
        column1="report_id",
        column2="move_id",
        string="Factures",
        readonly=True,
        copy=False,
    )

    snapshot_json = fields.Json(
        string="Snapshot du rapport",
        required=True,
        readonly=True,
        copy=False,
    )

    state = fields.Selection(
        selection=[
            ("generated", "Genere"),
        ],
        string="Etat",
        default="generated",
        required=True,
        readonly=True,
        copy=False,
    )

    # ---------------------------------------------------------
    # Protection du journal fiscal
    # ---------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.context.get(
            "_secef_report_generation"
        ):
            raise UserError(
                _(
                    "Les rapports SECeF doivent etre "
                    "generes par le moteur fiscal."
                )
            )

        return super().create(vals_list)

    def write(self, vals):
        raise UserError(
            _(
                "Un rapport SECeF genere est immuable."
            )
        )

    def unlink(self):
        raise UserError(
            _(
                "Un rapport SECeF genere ne peut "
                "pas etre supprime."
            )
        )

    def copy(self, default=None):
        raise UserError(
            _(
                "Un rapport SECeF ne peut pas "
                "etre duplique."
            )
        )

    # ---------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------

    @api.model
    def _secef_decimal(
        self,
        value,
        default="0",
    ):
        if value in (
            None,
            "",
            False,
        ):
            value = default

        try:
            return Decimal(
                str(value)
            )
        except (
            InvalidOperation,
            TypeError,
            ValueError,
        ) as exc:
            raise UserError(
                _(
                    "Valeur numerique SECeF "
                    "invalide : %s"
                )
                % value
            ) from exc

    @api.model
    def _secef_money(
        self,
        value,
    ):
        return format(
            self._secef_decimal(
                value
            ).quantize(
                Decimal("0.01"),
                rounding=ROUND_HALF_UP,
            ),
            "f",
        )

    @api.model
    def _secef_quantity_value(
        self,
        value,
    ):
        return format(
            self._secef_decimal(
                value
            ).quantize(
                Decimal("0.001"),
                rounding=ROUND_HALF_UP,
            ),
            "f",
        )

    @api.model
    def _secef_company(
        self,
        company=None,
    ):
        if company is None:
            company = self.env.company

        elif isinstance(
            company,
            int,
        ):
            company = (
                self.env[
                    "res.company"
                ]
                .browse(company)
                .exists()
            )

        if not company:
            raise UserError(
                _(
                    "Societe SECeF introuvable."
                )
            )

        company.ensure_one()

        if company not in self.env.companies:
            raise UserError(
                _(
                    "Vous n'avez pas acces a cette "
                    "societe SECeF."
                )
            )

        return company

    @api.model
    def _secef_last_z(
        self,
        company,
    ):
        return self.search(
            [
                (
                    "company_id",
                    "=",
                    company.id,
                ),
                (
                    "report_type",
                    "=",
                    "z",
                ),
                (
                    "state",
                    "=",
                    "generated",
                ),
            ],
            order=(
                "period_end desc, "
                "id desc"
            ),
            limit=1,
        )

    @api.model
    def _secef_completed_transactions(
        self,
        company,
        period_start,
        period_end,
        start_exclusive=False,
    ):
        domain = [
            (
                "company_id",
                "=",
                company.id,
            ),
            (
                "state",
                "=",
                "completed",
            ),
            (
                "move_id.secef_state",
                "=",
                "certified",
            ),
            (
                "move_id.move_type",
                "in",
                (
                    "out_invoice",
                    "out_refund",
                ),
            ),
            (
                "move_id.secef_datetime",
                "<=",
                period_end,
            ),
        ]

        if period_start:
            domain.append(
                (
                    "move_id.secef_datetime",
                    (
                        ">"
                        if start_exclusive
                        else ">="
                    ),
                    period_start,
                )
            )

        transactions = (
            self.env[
                "sunsoft.secef.transaction"
            ]
            .search(
                domain,
                order="id asc",
            )
        )

        # Une facture peut avoir connu plusieurs
        # tentatives. Une seule transaction completed
        # doit participer au resume fiscal.
        latest_by_move = {}

        for transaction in transactions:
            latest_by_move[
                transaction.move_id.id
            ] = transaction

        return self.env[
            "sunsoft.secef.transaction"
        ].browse(
            [
                transaction.id
                for transaction
                in latest_by_move.values()
            ]
        )

    @api.model
    def _secef_incomplete_transactions(
        self,
        company,
        period_start,
        period_end,
        start_exclusive=False,
    ):
        domain = [
            (
                "company_id",
                "=",
                company.id,
            ),
            (
                "state",
                "in",
                (
                    "pending",
                    "processing",
                    "failed",
                    "unknown",
                ),
            ),
            (
                "move_id.move_type",
                "in",
                (
                    "out_invoice",
                    "out_refund",
                ),
            ),
            (
                "move_id.secef_state",
                "in",
                (
                    "pending",
                    "processing",
                    "failed",
                    "unknown",
                ),
            ),
            (
                "create_date",
                "<=",
                period_end,
            ),
        ]

        if period_start:
            domain.append(
                (
                    "create_date",
                    (
                        ">"
                        if start_exclusive
                        else ">="
                    ),
                    period_start,
                )
            )

        return self.env[
            "sunsoft.secef.transaction"
        ].search(
            domain,
            order="id asc",
        )

    @api.model
    def _secef_default_period_start(
        self,
        company,
        period_end,
    ):
        """
        Avant le premier Z, le X doit commencer
        a la premiere transaction fiscale connue.

        On utilise create_date comme borne initiale
        commune afin de ne pas perdre une vente
        incomplete lorsqu'aucune facture certifiee
        n'existe encore.
        """
        transaction = (
            self.env[
                "sunsoft.secef.transaction"
            ]
            .search(
                [
                    (
                        "company_id",
                        "=",
                        company.id,
                    ),
                    (
                        "move_id.move_type",
                        "in",
                        (
                            "out_invoice",
                            "out_refund",
                        ),
                    ),
                    (
                        "create_date",
                        "<=",
                        period_end,
                    ),
                ],
                order=(
                    "create_date asc, "
                    "id asc"
                ),
                limit=1,
            )
        )

        if (
            transaction
            and transaction.create_date
        ):
            return transaction.create_date

        return period_end

    # ---------------------------------------------------------
    # Paiements
    # ---------------------------------------------------------

    @api.model
    def _secef_accumulate_payments(
        self,
        totals,
        payments,
        expected_total,
    ):
        expected_total = (
            self._secef_decimal(
                expected_total
            )
        )

        # Dans le protocole MCF, l'absence
        # de donnees de paiement declenche
        # le paiement especes du solde.
        if not payments:
            totals["E"] += (
                expected_total
            )
            return

        remaining = expected_total

        for payment in payments:

            if not isinstance(
                payment,
                dict,
            ):
                raise UserError(
                    _(
                        "Structure de paiement "
                        "SECeF invalide."
                    )
                )

            payment_type = (
                payment.get(
                    "payment_type"
                )
                or payment.get(
                    "type"
                )
                or "E"
            )

            payment_type = (
                str(payment_type)
                .strip()
                .upper()
            )

            raw_amount = payment.get(
                "amount"
            )

            if raw_amount in (
                None,
                "",
            ):
                amount = remaining
            else:
                amount = (
                    self._secef_decimal(
                        raw_amount
                    )
                )

            totals[
                payment_type
            ] += amount

            remaining -= amount

        # Le protocole complete le solde
        # restant en especes.
        if remaining > 0:
            totals["E"] += remaining

    # ---------------------------------------------------------
    # Reductions commerciales
    # ---------------------------------------------------------

    @api.model
    def _secef_move_reductions(
        self,
        move,
    ):
        commercial = []
        other = []

        for line in (
            move.invoice_line_ids
        ):
            if line.display_type in (
                "line_section",
                "line_note",
            ):
                continue

            discount = (
                self._secef_decimal(
                    line.discount or 0
                )
            )

            if discount > 0:
                gross = (
                    self._secef_decimal(
                        line.price_unit
                    )
                    * self._secef_decimal(
                        line.quantity
                    )
                )

                amount = (
                    gross
                    * discount
                    / Decimal("100")
                )

                commercial.append({
                    "invoice_number":
                        move.name,

                    "product_code":
                        (
                            line.product_id
                            .default_code
                            or ""
                        ),

                    "product_name":
                        (
                            line.name
                            or ""
                        ),

                    "rate":
                        format(
                            discount,
                            "f",
                        ),

                    "amount":
                        self._secef_money(
                            amount
                        ),
                })

            if (
                self._secef_decimal(
                    line.price_total
                )
                < 0
            ):
                other.append({
                    "invoice_number":
                        move.name,

                    "product_code":
                        (
                            line.product_id
                            .default_code
                            or ""
                        ),

                    "description":
                        (
                            line.name
                            or ""
                        ),

                    "amount":
                        self._secef_money(
                            abs(
                                self._secef_decimal(
                                    line.price_total
                                )
                            )
                        ),
                })

        return commercial, other

    # ---------------------------------------------------------
    # Snapshot X
    # ---------------------------------------------------------

    @api.model
    def _secef_build_x_snapshot(
        self,
        company,
        report_type,
        period_start,
        period_end,
        start_exclusive=False,
    ):
        completed = (
            self
            ._secef_completed_transactions(
                company,
                period_start,
                period_end,
                start_exclusive=(
                    start_exclusive
                ),
            )
        )

        incomplete = (
            self
            ._secef_incomplete_transactions(
                company,
                period_start,
                period_end,
                start_exclusive=(
                    start_exclusive
                ),
            )
        )

        invoice_types = {}

        payment_totals = (
            defaultdict(Decimal)
        )

        invoice_rows = []

        commercial_discounts = []

        other_sales_reductions = []

        isf_values = set()

        move_ids = set()

        transaction_ids = set(
            completed.ids
        )

        transaction_ids.update(
            incomplete.ids
        )

        for transaction in completed:

            move = transaction.move_id

            move_ids.add(
                move.id
            )

            payload = (
                transaction.request_payload
                or {}
            )

            if not isinstance(
                payload,
                dict,
            ):
                raise UserError(
                    _(
                        "Payload fiscal invalide "
                        "pour %s."
                    )
                    % move.display_name
                )

            invoice_payload = (
                payload.get(
                    "invoice"
                )
                or {}
            )

            if not isinstance(
                invoice_payload,
                dict,
            ):
                raise UserError(
                    _(
                        "Bloc invoice invalide "
                        "pour %s."
                    )
                    % move.display_name
                )

            invoice_type = (
                str(
                    invoice_payload.get(
                        "invoice_type"
                    )
                    or ""
                )
                .strip()
                .upper()
            )

            if not invoice_type:
                raise UserError(
                    _(
                        "Type de facture SECeF "
                        "absent pour %s."
                    )
                    % move.display_name
                )

            expected_total = (
                self._secef_decimal(
                    payload.get(
                        "expected_total",
                        move.amount_total,
                    )
                )
            )

            current = (
                invoice_types.setdefault(
                    invoice_type,
                    {
                        "invoice_count": 0,
                        "total": Decimal("0"),
                        "taxable": Decimal("0"),
                        "tax": Decimal("0"),
                        "tax_groups": {},
                    },
                )
            )

            current[
                "invoice_count"
            ] += 1

            current[
                "total"
            ] += expected_total

            tax_rows = []

            tax_summary = (
                move._get_secef_tax_summary()
                or []
            )

            payload_items = (
                payload.get("items")
                or []
            )

            certified_tax_keys = set()

            for item in payload_items:

                if not isinstance(
                    item,
                    dict,
                ):
                    raise UserError(
                        _(
                            "Article certifie invalide "
                            "pour %s."
                        )
                        % move.display_name
                    )

                tax_group = str(
                    item.get(
                        "tax_group"
                    )
                    or ""
                ).strip()

                tax_rate = (
                    self._secef_decimal(
                        item.get(
                            "tax_rate",
                            0,
                        )
                    )
                )

                if not tax_group:
                    raise UserError(
                        _(
                            "Groupe fiscal certifie "
                            "absent pour %s."
                        )
                        % move.display_name
                    )

                certified_tax_keys.add(
                    (
                        tax_group,
                        tax_rate,
                    )
                )

            current_tax_keys = {
                (
                    str(
                        tax_row.get(
                            "group"
                        )
                        or ""
                    ).strip(),
                    self._secef_decimal(
                        tax_row.get(
                            "rate",
                            0,
                        )
                    ),
                )
                for tax_row
                in tax_summary
            }

            if (
                certified_tax_keys
                != current_tax_keys
            ):
                raise UserError(
                    _(
                        "La configuration fiscale "
                        "actuelle de %s differe du "
                        "payload certifie. Le rapport "
                        "est bloque afin d'eviter un "
                        "recalcul fiscal incoherent."
                    )
                    % move.display_name
                )

            for tax_row in tax_summary:

                group_code = str(
                    tax_row.get(
                        "group"
                    )
                    or "UNKNOWN"
                )

                base = (
                    self._secef_decimal(
                        tax_row.get(
                            "base",
                            0,
                        )
                    )
                )

                tax = (
                    self._secef_decimal(
                        tax_row.get(
                            "tax",
                            0,
                        )
                    )
                )

                total = (
                    self._secef_decimal(
                        tax_row.get(
                            "total",
                            base + tax,
                        )
                    )
                )

                is_exempt = bool(
                    tax_row.get(
                        "is_exempt"
                    )
                )

                if not is_exempt:
                    current[
                        "taxable"
                    ] += base

                current[
                    "tax"
                ] += tax

                group_summary = (
                    current[
                        "tax_groups"
                    ].setdefault(
                        group_code,
                        {
                            "base":
                                Decimal("0"),
                            "tax":
                                Decimal("0"),
                            "total":
                                Decimal("0"),
                        },
                    )
                )

                group_summary[
                    "base"
                ] += base

                group_summary[
                    "tax"
                ] += tax

                group_summary[
                    "total"
                ] += total

                tax_rows.append({
                    "group":
                        group_code,

                    "base":
                        self._secef_money(
                            base
                        ),

                    "tax":
                        self._secef_money(
                            tax
                        ),

                    "total":
                        self._secef_money(
                            total
                        ),

                    "rate":
                        str(
                            tax_row.get(
                                "rate",
                                "",
                            )
                        ),

                    "is_exempt":
                        is_exempt,
                })

            self._secef_accumulate_payments(
                payment_totals,
                payload.get(
                    "payments"
                ),
                expected_total,
            )

            (
                commercial,
                other,
            ) = (
                self._secef_move_reductions(
                    move
                )
            )

            commercial_discounts.extend(
                commercial
            )

            other_sales_reductions.extend(
                other
            )

            raw_isf = (
                invoice_payload.get(
                    "sfe_id"
                )
            )

            if raw_isf:
                isf_values.add(
                    str(raw_isf)
                )

            invoice_rows.append({
                "transaction_id":
                    transaction.id,

                "request_uid":
                    transaction.request_uid,

                "invoice_number":
                    move.name,

                "invoice_type":
                    invoice_type,

                "certified_at":
                    fields.Datetime.to_string(
                        move.secef_datetime
                    ),

                "expected_total":
                    self._secef_money(
                        expected_total
                    ),

                "fiscal_counter":
                    move.secef_fiscal_counter,

                "total_counter":
                    move.secef_total_counter,

                "mid":
                    move.secef_mid or "",

                "signature":
                    move.secef_signature or "",

                "taxes":
                    tax_rows,
            })

        # Plusieurs ISF dans le meme rapport
        # signifieraient une incoherence de
        # configuration ou de perimetre.
        if len(isf_values) > 1:
            raise UserError(
                _(
                    "Plusieurs ISF sont presents "
                    "dans la periode du rapport."
                )
            )

        company_isf = (
            company.secef_sfe_id
            or ""
        )

        isf = (
            company_isf
            or (
                next(
                    iter(isf_values)
                )
                if isf_values
                else ""
            )
        )

        if not isf:
            raise UserError(
                _(
                    "ISF absent : le rapport SECeF "
                    "ne peut pas etre genere."
                )
            )

        # Conversion Decimal -> JSON.
        invoice_type_json = {}

        for (
            invoice_type,
            values,
        ) in sorted(
            invoice_types.items()
        ):

            groups_json = {}

            for (
                group_code,
                group_values,
            ) in sorted(
                values[
                    "tax_groups"
                ].items()
            ):
                groups_json[
                    group_code
                ] = {
                    "base":
                        self._secef_money(
                            group_values[
                                "base"
                            ]
                        ),

                    "tax":
                        self._secef_money(
                            group_values[
                                "tax"
                            ]
                        ),

                    "total":
                        self._secef_money(
                            group_values[
                                "total"
                            ]
                        ),
                }

            invoice_type_json[
                invoice_type
            ] = {
                "invoice_count":
                    values[
                        "invoice_count"
                    ],

                "total":
                    self._secef_money(
                        values[
                            "total"
                        ]
                    ),

                "taxable":
                    self._secef_money(
                        values[
                            "taxable"
                        ]
                    ),

                "tax":
                    self._secef_money(
                        values[
                            "tax"
                        ]
                    ),

                "tax_groups":
                    groups_json,
            }

        payment_json = {
            payment_type:
                self._secef_money(
                    amount
                )
            for (
                payment_type,
                amount,
            ) in sorted(
                payment_totals.items()
            )
        }

        incomplete_by_move = {}

        for transaction in incomplete:
            move = transaction.move_id

            move_ids.add(
                move.id
            )

            incomplete_by_move[
                move.id
            ] = transaction

        incomplete_rows = []

        for transaction in (
            incomplete_by_move.values()
        ):
            incomplete_rows.append({
                "transaction_id":
                    transaction.id,

                "request_uid":
                    transaction.request_uid,

                "invoice_number":
                    (
                        transaction.move_id.name
                        or ""
                    ),

                "state":
                    transaction.state,

                "error_message":
                    (
                        transaction.error_message
                        or ""
                    ),
            })

        snapshot = {
            "schema_version": 1,

            "report_type":
                report_type,

            "identity": {
                "commercial_name":
                    company.name or "",

                "ifu":
                    company.vat or "",

                "isf":
                    isf or "",
            },

            "period": {
                "start":
                    fields.Datetime.to_string(
                        period_start
                    ),

                "end":
                    fields.Datetime.to_string(
                        period_end
                    ),

                "start_exclusive":
                    bool(
                        start_exclusive
                    ),
            },

            "summary": {
                "invoice_types":
                    invoice_type_json,

                "payments":
                    payment_json,

                "commercial_discounts":
                    commercial_discounts,

                "other_sales_reductions":
                    other_sales_reductions,

                "incomplete_sales_count":
                    len(
                        incomplete_rows
                    ),

                "completed_invoice_count":
                    len(
                        completed
                    ),
            },

            "invoices":
                invoice_rows,

            "incomplete_sales":
                incomplete_rows,
        }

        return {
            "snapshot":
                snapshot,

            "isf":
                isf or "",

            "transaction_ids":
                sorted(
                    transaction_ids
                ),

            "move_ids":
                sorted(
                    move_ids
                ),
        }

    # ---------------------------------------------------------
    # Generation
    # ---------------------------------------------------------

    @api.model
    def _secef_report_reference(
        self,
        report_type,
        company,
        generated_at,
    ):
        prefix = {
            "x_daily": "XQ",
            "x_periodic": "XP",
            "z": "Z",
            "a": "A",
        }[
            report_type
        ]

        sequence = (
            self.env["ir.sequence"]
            .sudo()
            .next_by_code(
                "sunsoft.secef.report"
            )
        )

        if not sequence:
            raise UserError(
                _(
                    "La sequence des rapports "
                    "SECeF est introuvable."
                )
            )

        return (
            f"{prefix}/"
            f"{company.id}/"
            f"{sequence}"
        )

    @api.model
    def generate_x_daily(
        self,
        company=None,
        period_end=None,
    ):
        company = (
            self._secef_company(
                company
            )
        )

        period_end = (
            fields.Datetime.to_datetime(
                period_end
                or fields.Datetime.now()
            )
        )

        last_z = (
            self._secef_last_z(
                company
            )
        )

        if last_z:
            period_start = (
                last_z.period_end
            )
            start_exclusive = True
        else:
            period_start = (
                self
                ._secef_default_period_start(
                    company,
                    period_end,
                )
            )
            start_exclusive = False

        result = (
            self._secef_build_x_snapshot(
                company,
                "x_daily",
                period_start,
                period_end,
                start_exclusive=(
                    start_exclusive
                ),
            )
        )

        generated_at = (
            fields.Datetime.now()
        )

        reference = (
            self._secef_report_reference(
                "x_daily",
                company,
                generated_at,
            )
        )

        result["snapshot"] = dict(
            result["snapshot"]
        )

        result["snapshot"][
            "reference"
        ] = reference

        result["snapshot"][
            "generated_at"
        ] = fields.Datetime.to_string(
            generated_at
        )

        return (
            self
            .sudo()
            .with_context(
                _secef_report_generation=True
            )
            .create({
                "name":
                    reference,

                "report_type":
                    "x_daily",

                "company_id":
                    company.id,

                "isf":
                    result["isf"],

                "period_start":
                    period_start,

                "period_end":
                    period_end,

                "generated_at":
                    generated_at,

                "previous_report_id":
                    (
                        last_z.id
                        if last_z
                        else False
                    ),

                "transaction_ids":
                    [
                        (
                            6,
                            0,
                            result[
                                "transaction_ids"
                            ],
                        )
                    ],

                "move_ids":
                    [
                        (
                            6,
                            0,
                            result[
                                "move_ids"
                            ],
                        )
                    ],

                "snapshot_json":
                    result[
                        "snapshot"
                    ],

                "state":
                    "generated",
            })
        )

    @api.model
    def generate_x_periodic(
        self,
        period_start,
        period_end,
        company=None,
    ):
        company = (
            self._secef_company(
                company
            )
        )

        period_start = (
            fields.Datetime.to_datetime(
                period_start
            )
        )

        period_end = (
            fields.Datetime.to_datetime(
                period_end
            )
        )

        if (
            not period_start
            or not period_end
        ):
            raise UserError(
                _(
                    "La periode du rapport X "
                    "est obligatoire."
                )
            )

        if period_end < period_start:
            raise UserError(
                _(
                    "La fin de periode ne peut "
                    "pas preceder le debut."
                )
            )

        result = (
            self._secef_build_x_snapshot(
                company,
                "x_periodic",
                period_start,
                period_end,
                start_exclusive=False,
            )
        )

        generated_at = (
            fields.Datetime.now()
        )

        reference = (
            self._secef_report_reference(
                "x_periodic",
                company,
                generated_at,
            )
        )

        result["snapshot"] = dict(
            result["snapshot"]
        )

        result["snapshot"][
            "reference"
        ] = reference

        result["snapshot"][
            "generated_at"
        ] = fields.Datetime.to_string(
            generated_at
        )

        return (
            self
            .sudo()
            .with_context(
                _secef_report_generation=True
            )
            .create({
                "name":
                    reference,

                "report_type":
                    "x_periodic",

                "company_id":
                    company.id,

                "isf":
                    result["isf"],

                "period_start":
                    period_start,

                "period_end":
                    period_end,

                "generated_at":
                    generated_at,

                "transaction_ids":
                    [
                        (
                            6,
                            0,
                            result[
                                "transaction_ids"
                            ],
                        )
                    ],

                "move_ids":
                    [
                        (
                            6,
                            0,
                            result[
                                "move_ids"
                            ],
                        )
                    ],

                "snapshot_json":
                    result[
                        "snapshot"
                    ],

                "state":
                    "generated",
            })
        )


    def action_print_x(self):
        self.ensure_one()

        if self.report_type not in (
            "x_daily",
            "x_periodic",
        ):
            raise UserError(
                _(
                    "Ce document n'est pas "
                    "un rapport X."
                )
            )

        return (
            self.env.ref(
                "sunsoft_secef."
                "action_report_secef_x"
            )
            .report_action(self)
        )


    def action_print_z(self):
        self.ensure_one()

        if self.report_type != "z":
            raise UserError(
                _(
                    "Ce document n'est pas "
                    "un rapport Z."
                )
            )

        return (
            self.env.ref(
                "sunsoft_secef."
                "action_report_secef_z"
            )
            .report_action(self)
        )

    @api.model
    def generate_z(
        self,
        company=None,
        period_end=None,
    ):
        """
        Genere le Z depuis le dernier Z.

        Le Z constitue le nouveau point de
        cloture statistique de la societe.
        """

        if not self.env.user.has_group(
            "account.group_account_manager"
        ):
            raise UserError(
                _(
                    "Seul un responsable "
                    "comptable peut generer "
                    "un rapport Z SECeF."
                )
            )

        company = (
            self._secef_company(
                company
            )
        )

        now = fields.Datetime.now()

        period_end = (
            fields.Datetime.to_datetime(
                period_end
                or now
            )
        )

        if not period_end:
            raise UserError(
                _(
                    "La date de cloture Z "
                    "est obligatoire."
                )
            )

        if period_end > now:
            raise UserError(
                _(
                    "Un rapport Z ne peut pas "
                    "cloturer une periode future."
                )
            )

        # -----------------------------------------------------
        # Verrou de concurrence
        # -----------------------------------------------------
        #
        # Deux utilisateurs ne doivent jamais
        # pouvoir creer simultanement deux Z
        # utilisant le meme dernier Z.
        #
        # Le verrou est conserve jusqu'au commit
        # ou rollback de la transaction Odoo.
        # -----------------------------------------------------

        self.env.cr.execute(
            """
            SELECT id
              FROM res_company
             WHERE id = %s
             FOR UPDATE
            """,
            [company.id],
        )

        last_z = (
            self._secef_last_z(
                company
            )
        )

        if last_z:

            if (
                period_end
                <= last_z.period_end
            ):
                raise UserError(
                    _(
                        "La nouvelle cloture Z "
                        "doit etre posterieure "
                        "au dernier Z (%s)."
                    )
                    % fields.Datetime.to_string(
                        last_z.period_end
                    )
                )

            period_start = (
                last_z.period_end
            )

            start_exclusive = True

        else:

            period_start = (
                self
                ._secef_default_period_start(
                    company,
                    period_end,
                )
            )

            start_exclusive = False

        result = (
            self._secef_build_x_snapshot(
                company,
                "z",
                period_start,
                period_end,
                start_exclusive=(
                    start_exclusive
                ),
            )
        )

        generated_at = (
            fields.Datetime.now()
        )

        reference = (
            self._secef_report_reference(
                "z",
                company,
                generated_at,
            )
        )

        snapshot = dict(
            result["snapshot"]
        )

        snapshot[
            "reference"
        ] = reference

        snapshot[
            "generated_at"
        ] = fields.Datetime.to_string(
            generated_at
        )

        snapshot[
            "closure"
        ] = {
            "is_closing_report":
                True,

            "previous_z_reference":
                (
                    last_z.name
                    if last_z
                    else ""
                ),

            "previous_z_id":
                (
                    last_z.id
                    if last_z
                    else False
                ),

            "closed_until":
                fields.Datetime.to_string(
                    period_end
                ),
        }

        report = (
            self
            .sudo()
            .with_context(
                _secef_report_generation=True
            )
            .create({
                "name":
                    reference,

                "report_type":
                    "z",

                "company_id":
                    company.id,

                "isf":
                    result["isf"],

                "period_start":
                    period_start,

                "period_end":
                    period_end,

                "generated_at":
                    generated_at,

                "previous_report_id":
                    (
                        last_z.id
                        if last_z
                        else False
                    ),

                "transaction_ids":
                    [
                        (
                            6,
                            0,
                            result[
                                "transaction_ids"
                            ],
                        )
                    ],

                "move_ids":
                    [
                        (
                            6,
                            0,
                            result[
                                "move_ids"
                            ],
                        )
                    ],

                "snapshot_json":
                    snapshot,

                "state":
                    "generated",
            })
        )

        return report


    @api.model
    def _secef_last_a(
        self,
        company,
    ):
        return self.search(
            [
                (
                    "company_id",
                    "=",
                    company.id,
                ),
                (
                    "report_type",
                    "=",
                    "a",
                ),
                (
                    "state",
                    "=",
                    "generated",
                ),
            ],
            order=(
                "generated_at desc, "
                "id desc"
            ),
            limit=1,
        )

    @api.model
    def _secef_default_a_period_start(
        self,
        company,
        period_end,
    ):
        move = (
            self.env[
                "account.move"
            ]
            .sudo()
            .search(
                [
                    (
                        "company_id",
                        "=",
                        company.id,
                    ),
                    (
                        "secef_state",
                        "=",
                        "certified",
                    ),
                    (
                        "move_type",
                        "in",
                        (
                            "out_invoice",
                            "out_refund",
                        ),
                    ),
                    (
                        "secef_datetime",
                        "!=",
                        False,
                    ),
                    (
                        "secef_datetime",
                        "<=",
                        period_end,
                    ),
                    (
                        "secef_transaction_ids.state",
                        "=",
                        "completed",
                    ),
                ],
                order=(
                    "secef_datetime asc, "
                    "id asc"
                ),
                limit=1,
            )
        )

        if (
            move
            and move.secef_datetime
        ):
            return (
                move.secef_datetime
            )

        return period_end


    @api.model
    def _secef_a_item_product(
        self,
        transaction,
        item_index,
        item,
    ):
        """
        Retrouve le product.product correspondant
        a un item fiscal certifie.

        Nouvelles transactions :
        utilise la metadonnee Odoo locale capturee
        au moment de la demande de certification.

        Transactions historiques :
        applique un rapprochement strict et bloque
        toute ambiguite.
        """

        move = transaction.move_id

        metadata = (
            transaction.local_item_metadata
            or {}
        )

        if metadata:

            if not isinstance(
                metadata,
                dict,
            ):
                raise UserError(
                    _(
                        "Metadonnees locales SECeF "
                        "invalides pour %s."
                    )
                    % move.display_name
                )

            metadata_items = (
                metadata.get("items")
                or []
            )

            if not isinstance(
                metadata_items,
                list,
            ):
                raise UserError(
                    _(
                        "Liste de metadonnees locales "
                        "SECeF invalide pour %s."
                    )
                    % move.display_name
                )

            matches = [
                row
                for row in metadata_items
                if (
                    isinstance(
                        row,
                        dict,
                    )
                    and row.get(
                        "item_index"
                    )
                    == item_index
                )
            ]

            if len(matches) != 1:
                raise UserError(
                    _(
                        "La metadonnee produit de "
                        "l'article fiscal #%s de %s "
                        "est absente ou ambigue."
                    )
                    % (
                        item_index,
                        move.display_name,
                    )
                )

            metadata_row = matches[0]

            move_line_id = (
                metadata_row.get(
                    "move_line_id"
                )
            )

            product_id = (
                metadata_row.get(
                    "product_id"
                )
            )

            move_line = (
                self.env[
                    "account.move.line"
                ]
                .browse(
                    move_line_id
                )
                .exists()
            )

            if (
                not move_line
                or move_line.move_id
                != move
            ):
                raise UserError(
                    _(
                        "La ligne Odoo liee a "
                        "l'article fiscal #%s de %s "
                        "est invalide."
                    )
                    % (
                        item_index,
                        move.display_name,
                    )
                )

            if product_id:

                product = (
                    self.env[
                        "product.product"
                    ]
                    .browse(
                        product_id
                    )
                    .exists()
                )

                if not product:
                    raise UserError(
                        _(
                            "Le produit Odoo lie a "
                            "l'article fiscal #%s de %s "
                            "est introuvable."
                        )
                        % (
                            item_index,
                            move.display_name,
                        )
                    )

                if (
                    move_line.product_id
                    and move_line.product_id
                    != product
                ):
                    raise UserError(
                        _(
                            "Incoherence entre la ligne "
                            "de facture et le produit "
                            "memorise pour l'article "
                            "fiscal #%s de %s."
                        )
                        % (
                            item_index,
                            move.display_name,
                        )
                    )

                return product

            if bool(
                item.get(
                    "is_downpayment"
                )
            ):
                return self.env[
                    "product.product"
                ]

            if move_line.product_id:
                return move_line.product_id

            raise UserError(
                _(
                    "Aucun produit Odoo n'est lie "
                    "a l'article fiscal #%s de %s."
                )
                % (
                    item_index,
                    move.display_name,
                )
            )

        # -----------------------------------------------------
        # Fallback historique
        # -----------------------------------------------------

        item_name = str(
            item.get("name")
            or ""
        ).strip()

        item_code = str(
            item.get("internal_code")
            or ""
        ).strip()

        item_type = str(
            item.get("item_type")
            or ""
        ).strip()

        tax_group = str(
            item.get("tax_group")
            or ""
        ).strip()

        tax_rate = (
            self._secef_decimal(
                item.get(
                    "tax_rate",
                    0,
                )
            )
        )

        quantity = (
            self._secef_decimal(
                item.get(
                    "quantity",
                    0,
                )
            )
            .quantize(
                Decimal("0.001"),
                rounding=ROUND_HALF_UP,
            )
        )

        is_downpayment = bool(
            item.get(
                "is_downpayment"
            )
        )

        product_ids = set()

        invoice_lines = (
            move.invoice_line_ids.filtered(
                lambda line:
                    line.display_type
                    == "product"
            )
        )

        for line in invoice_lines:

            if (
                line.is_downpayment
                and line.quantity < 0
            ):
                continue

            product = line.product_id

            if not product:
                continue

            candidate_name = (
                line.name
                or product.display_name
                or ""
            ).strip()

            candidate_code = (
                product.default_code
                or ""
            ).strip()

            candidate_type = (
                product.product_tmpl_id
                .secef_item_type
                or ""
            ).strip()

            if candidate_name != item_name:
                continue

            if candidate_code != item_code:
                continue

            if candidate_type != item_type:
                continue

            if (
                bool(
                    line.is_downpayment
                )
                != is_downpayment
            ):
                continue

            line_quantity = (
                self._secef_decimal(
                    line.quantity
                )
                .quantize(
                    Decimal("0.001"),
                    rounding=ROUND_HALF_UP,
                )
            )

            if line_quantity != quantity:
                continue

            taxes = line.tax_ids

            if len(taxes) != 1:
                continue

            tax = taxes[0]

            candidate_group = (
                tax.secef_tax_group
                or ""
            ).strip()

            candidate_rate = (
                self._secef_decimal(
                    tax.amount
                )
            )

            if candidate_group != tax_group:
                continue

            if candidate_rate != tax_rate:
                continue

            product_ids.add(
                product.id
            )

        if len(product_ids) == 1:
            return self.env[
                "product.product"
            ].browse(
                next(
                    iter(product_ids)
                )
            )

        if (
            not product_ids
            and is_downpayment
        ):
            return self.env[
                "product.product"
            ]

        if not product_ids:
            raise UserError(
                _(
                    "Impossible d'identifier de "
                    "maniere certaine le produit "
                    "Odoo de l'article fiscal '%s' "
                    "sur la facture %s."
                )
                % (
                    item_name,
                    move.display_name,
                )
            )

        raise UserError(
            _(
                "Plusieurs produits Odoo "
                "correspondent a l'article fiscal "
                "'%s' de la facture %s. "
                "Le rapport A est bloque."
            )
            % (
                item_name,
                move.display_name,
            )
        )

    @api.model
    def _secef_a_stock_quantity(
        self,
        product,
        company,
    ):
        if not product:
            return Decimal("0")

        scoped_product = (
            product
            .sudo()
            .with_company(
                company
            )
            .with_context(
                allowed_company_ids=[
                    company.id
                ]
            )
        )

        return self._secef_decimal(
            scoped_product.qty_available
        )

    @api.model
    def _secef_build_a_snapshot(
        self,
        company,
        period_start,
        period_end,
        start_exclusive=False,
    ):
        transactions = (
            self
            ._secef_completed_transactions(
                company,
                period_start,
                period_end,
                start_exclusive=(
                    start_exclusive
                ),
            )
        )

        rows = {}
        categories = defaultdict(
            lambda: {
                "quantity_sold":
                    Decimal("0"),

                "quantity_returned":
                    Decimal("0"),

                "amount_collected":
                    Decimal("0"),

                "amount_returned":
                    Decimal("0"),
            }
        )

        isf_values = set()

        for transaction in transactions:

            move = transaction.move_id

            payload = (
                transaction.request_payload
                or {}
            )

            if not isinstance(
                payload,
                dict,
            ):
                raise UserError(
                    _(
                        "Payload SECeF invalide "
                        "pour %s."
                    )
                    % move.display_name
                )

            invoice_payload = (
                payload.get("invoice")
                or {}
            )

            items = (
                payload.get("items")
                or []
            )

            if not isinstance(
                invoice_payload,
                dict,
            ):
                raise UserError(
                    _(
                        "Bloc invoice SECeF "
                        "invalide pour %s."
                    )
                    % move.display_name
                )

            if not isinstance(
                items,
                list,
            ):
                raise UserError(
                    _(
                        "Liste d'articles SECeF "
                        "invalide pour %s."
                    )
                    % move.display_name
                )

            raw_isf = (
                invoice_payload.get(
                    "sfe_id"
                )
            )

            if raw_isf:
                isf_values.add(
                    str(raw_isf)
                )

            is_refund = (
                move.move_type
                == "out_refund"
            )

            for item_index, item in enumerate(
                items
            ):

                if not isinstance(
                    item,
                    dict,
                ):
                    raise UserError(
                        _(
                            "Article fiscal invalide "
                            "pour %s."
                        )
                        % move.display_name
                    )

                product = (
                    self
                    ._secef_a_item_product(
                        transaction,
                        item_index,
                        item,
                    )
                )

                item_name = str(
                    item.get("name")
                    or ""
                ).strip()

                item_code = str(
                    item.get(
                        "internal_code"
                    )
                    or ""
                ).strip()

                item_type = str(
                    item.get(
                        "item_type"
                    )
                    or ""
                ).strip()

                product_category = (
                    (
                        product.categ_id.complete_name
                        or product.categ_id.name
                        or ""
                    )
                    if product
                    else "Sans produit / acompte"
                )

                tax_group = str(
                    item.get(
                        "tax_group"
                    )
                    or ""
                ).strip()

                tax_rate = (
                    self._secef_decimal(
                        item.get(
                            "tax_rate",
                            0,
                        )
                    )
                )

                unit_price = (
                    self._secef_decimal(
                        item.get(
                            "unit_price",
                            0,
                        )
                    )
                )

                quantity = (
                    self._secef_decimal(
                        item.get(
                            "quantity",
                            0,
                        )
                    )
                )

                amount = (
                    self._secef_decimal(
                        item.get(
                            "amount",
                            0,
                        )
                    )
                )

                key = (
                    product.id
                    if product
                    else 0,
                    item_code,
                    item_name,
                    product_category,
                    item_type,
                    tax_group,
                    format(
                        tax_rate,
                        "f",
                    ),
                    format(
                        unit_price,
                        "f",
                    ),
                )

                if key not in rows:

                    rows[key] = {
                        "product_id":
                            (
                                product.id
                                if product
                                else False
                            ),

                        "product_code":
                            item_code,

                        "product_name":
                            item_name,

                        "product_category":
                            product_category,

                        "secef_item_type":
                            item_type,

                        "tax_group":
                            tax_group,

                        "tax_rate":
                            tax_rate,

                        "unit_price":
                            unit_price,

                        "quantity_sold":
                            Decimal("0"),

                        "quantity_returned":
                            Decimal("0"),

                        "amount_collected":
                            Decimal("0"),

                        "amount_returned":
                            Decimal("0"),
                    }

                row = rows[key]

                category = categories[
                    product_category
                ]

                if is_refund:

                    row[
                        "quantity_returned"
                    ] += quantity

                    row[
                        "amount_returned"
                    ] += amount

                    category[
                        "quantity_returned"
                    ] += quantity

                    category[
                        "amount_returned"
                    ] += amount

                else:

                    row[
                        "quantity_sold"
                    ] += quantity

                    row[
                        "amount_collected"
                    ] += amount

                    category[
                        "quantity_sold"
                    ] += quantity

                    category[
                        "amount_collected"
                    ] += amount

        if len(isf_values) > 1:
            raise UserError(
                _(
                    "Plusieurs ISF sont presents "
                    "dans la periode du rapport A."
                )
            )

        company_isf = (
            company.secef_sfe_id
            or ""
        )

        isf = (
            company_isf
            or (
                next(
                    iter(isf_values)
                )
                if isf_values
                else ""
            )
        )

        if not isf:
            raise UserError(
                _(
                    "ISF absent : le rapport A "
                    "ne peut pas etre genere."
                )
            )

        item_rows = []

        for row in rows.values():

            product_id = row[
                "product_id"
            ]

            product = (
                self.env[
                    "product.product"
                ].browse(
                    product_id
                )
                if product_id
                else self.env[
                    "product.product"
                ]
            )

            stock_quantity = (
                self
                ._secef_a_stock_quantity(
                    product,
                    company,
                )
            )

            amount_collected = (
                row[
                    "amount_collected"
                ]
            )

            amount_returned = (
                row[
                    "amount_returned"
                ]
            )

            item_rows.append({
                "product_id":
                    product_id,

                "product_code":
                    row[
                        "product_code"
                    ],

                "product_name":
                    row[
                        "product_name"
                    ],

                "product_category":
                    row[
                        "product_category"
                    ],

                "secef_item_type":
                    row[
                        "secef_item_type"
                    ],

                "tax_group":
                    row[
                        "tax_group"
                    ],

                "tax_rate":
                    format(
                        row[
                            "tax_rate"
                        ],
                        "f",
                    ),

                "unit_price":
                    self._secef_money(
                        row[
                            "unit_price"
                        ]
                    ),

                "quantity_sold":
                    self._secef_quantity_value(
                        row[
                            "quantity_sold"
                        ]
                    ),

                "quantity_returned":
                    self._secef_quantity_value(
                        row[
                            "quantity_returned"
                        ]
                    ),

                "quantity_in_stock":
                    self._secef_quantity_value(
                        stock_quantity
                    ),

                "amount_collected":
                    self._secef_money(
                        amount_collected
                    ),

                "amount_returned":
                    self._secef_money(
                        amount_returned
                    ),

                "net_amount":
                    self._secef_money(
                        amount_collected
                        - amount_returned
                    ),
            })

        item_rows.sort(
            key=lambda row: (
                row["product_category"],
                row["secef_item_type"],
                row["product_code"],
                row["product_name"],
                row["unit_price"],
                row["tax_rate"],
            )
        )

        category_rows = []

        for (
            category_name,
            values,
        ) in sorted(
            categories.items()
        ):

            amount_collected = (
                values[
                    "amount_collected"
                ]
            )

            amount_returned = (
                values[
                    "amount_returned"
                ]
            )

            category_rows.append({
                "category":
                    category_name,

                "quantity_sold":
                    self._secef_quantity_value(
                        values[
                            "quantity_sold"
                        ]
                    ),

                "quantity_returned":
                    self._secef_quantity_value(
                        values[
                            "quantity_returned"
                        ]
                    ),

                "amount_collected":
                    self._secef_money(
                        amount_collected
                    ),

                "amount_returned":
                    self._secef_money(
                        amount_returned
                    ),

                "net_amount":
                    self._secef_money(
                        amount_collected
                        - amount_returned
                    ),
            })

        snapshot = {
            "schema_version":
                1,

            "report_type":
                "a",

            "identity": {
                "commercial_name":
                    company.name or "",

                "ifu":
                    company.vat or "",

                "isf":
                    isf,
            },

            "period": {
                "start":
                    fields.Datetime.to_string(
                        period_start
                    ),

                "end":
                    fields.Datetime.to_string(
                        period_end
                    ),

                "start_exclusive":
                    bool(
                        start_exclusive
                    ),
            },

            "stock_scope": {
                "company_id":
                    company.id,

                "company_name":
                    company.name or "",

                "scope":
                    (
                        "all_internal_locations_"
                        "available_to_company"
                    ),

                "captured_at":
                    fields.Datetime.to_string(
                        period_end
                    ),
            },

            "categories":
                category_rows,

            "items":
                item_rows,

            "summary": {
                "transaction_count":
                    len(transactions),

                "item_row_count":
                    len(item_rows),
            },
        }

        return {
            "snapshot":
                snapshot,

            "isf":
                isf,

            "transaction_ids":
                transactions.ids,

            "move_ids":
                transactions
                .mapped("move_id")
                .ids,
        }


    def action_print_a(self):
        self.ensure_one()

        if self.report_type != "a":
            raise UserError(
                _(
                    "Ce document n'est pas "
                    "un rapport A."
                )
            )

        return (
            self.env.ref(
                "sunsoft_secef."
                "action_report_secef_a"
            )
            .report_action(self)
        )


    @api.model
    def generate_a(
        self,
        company=None,
    ):
        """
        Genere le rapport A depuis la generation
        du rapport A precedent.

        La quantite en stock est capturee au moment
        exact de la generation puis figee dans le
        snapshot du rapport.
        """

        if not self.env.user.has_group(
            "account.group_account_manager"
        ):
            raise UserError(
                _(
                    "Seul un responsable "
                    "comptable peut generer "
                    "un rapport A SECeF."
                )
            )

        company = (
            self._secef_company(
                company
            )
        )

        # Evite deux rapports A concurrents
        # utilisant le meme marqueur precedent.
        self.env.cr.execute(
            """
            SELECT id
              FROM res_company
             WHERE id = %s
             FOR UPDATE
            """,
            [company.id],
        )

        generated_at = (
            fields.Datetime.now()
        )

        last_a = (
            self._secef_last_a(
                company
            )
        )

        if last_a:

            if (
                generated_at
                <= last_a.generated_at
            ):
                raise UserError(
                    _(
                        "La nouvelle generation A "
                        "doit etre posterieure "
                        "au rapport A precedent."
                    )
                )

            period_start = (
                last_a.generated_at
            )

            start_exclusive = True

        else:

            period_start = (
                self
                ._secef_default_a_period_start(
                    company,
                    generated_at,
                )
            )

            start_exclusive = False

        result = (
            self._secef_build_a_snapshot(
                company,
                period_start,
                generated_at,
                start_exclusive=(
                    start_exclusive
                ),
            )
        )

        reference = (
            self._secef_report_reference(
                "a",
                company,
                generated_at,
            )
        )

        snapshot = dict(
            result["snapshot"]
        )

        snapshot[
            "reference"
        ] = reference

        snapshot[
            "generated_at"
        ] = fields.Datetime.to_string(
            generated_at
        )

        snapshot[
            "marker"
        ] = {
            "previous_a_reference":
                (
                    last_a.name
                    if last_a
                    else ""
                ),

            "previous_a_id":
                (
                    last_a.id
                    if last_a
                    else False
                ),

            "generated_at":
                fields.Datetime.to_string(
                    generated_at
                ),
        }

        return (
            self
            .sudo()
            .with_context(
                _secef_report_generation=True
            )
            .create({
                "name":
                    reference,

                "report_type":
                    "a",

                "company_id":
                    company.id,

                "isf":
                    result["isf"],

                "period_start":
                    period_start,

                "period_end":
                    generated_at,

                "generated_at":
                    generated_at,

                "previous_report_id":
                    (
                        last_a.id
                        if last_a
                        else False
                    ),

                "transaction_ids":
                    [
                        (
                            6,
                            0,
                            result[
                                "transaction_ids"
                            ],
                        )
                    ],

                "move_ids":
                    [
                        (
                            6,
                            0,
                            result[
                                "move_ids"
                            ],
                        )
                    ],

                "snapshot_json":
                    snapshot,

                "state":
                    "generated",
            })
        )
