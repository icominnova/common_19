from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    # =========================================================
    # Remises SECeF
    # =========================================================

    secef_discount_type = fields.Selection(
        selection=[
            ("percent", "Pourcentage"),
            ("fixed", "Montant fixe"),
        ],
        string="Type de remise",
        default="percent",
    )

    secef_discount_amount = fields.Monetary(
        string="Remise montant",
        currency_field="currency_id",
        default=0.0,
        help=(
            "Montant fixe de remise appliqué au montant "
            "brut total de la ligne."
        ),
    )

    def _secef_fixed_discount_rate(self):
        """
        Calcule le pourcentage Odoo équivalent à une
        remise fixe appliquée au total brut de la ligne.
        """

        self.ensure_one()

        fixed_amount = (
            self.secef_discount_amount
            or 0.0
        )

        if fixed_amount < 0:
            raise ValidationError(
                _(
                    "La remise en montant ne peut pas "
                    "être négative."
                )
            )

        gross_amount = abs(
            (self.price_unit or 0.0)
            * (self.quantity or 0.0)
        )

        if not fixed_amount:
            return 0.0

        if not gross_amount:
            raise ValidationError(
                _(
                    "Impossible d'appliquer une remise "
                    "fixe sur une ligne dont le montant "
                    "brut est nul."
                )
            )

        if fixed_amount >= gross_amount:
            raise ValidationError(
                _(
                    "La remise fixe (%s) doit être "
                    "strictement inférieure au montant "
                    "brut de la ligne (%s)."
                )
                % (
                    fixed_amount,
                    gross_amount,
                )
            )

        return (
            fixed_amount
            / gross_amount
            * 100.0
        )

    def _secef_sync_fixed_discount(self):
        """
        Synchronise la remise fixe avec le champ standard
        discount d'Odoo.

        Les calculs comptables et fiscaux restent ainsi
        entièrement gérés par le moteur standard Odoo.
        """

        if self.env.context.get(
            "secef_skip_discount_sync"
        ):
            return

        for line in self:
            if line.display_type:
                continue

            if (
                line.secef_discount_type
                != "fixed"
            ):
                continue

            rate = (
                line._secef_fixed_discount_rate()
            )

            if abs(
                (line.discount or 0.0)
                - rate
            ) > 1e-9:
                line.with_context(
                    secef_skip_discount_sync=True
                ).write({
                    "discount": rate,
                })

    @api.onchange(
        "secef_discount_type",
        "secef_discount_amount",
        "price_unit",
        "quantity",
    )
    def _onchange_secef_discount(self):
        for line in self:
            if line.display_type:
                continue

            if (
                line.secef_discount_type
                == "fixed"
            ):
                line.discount = (
                    line._secef_fixed_discount_rate()
                )

            else:
                line.secef_discount_amount = 0.0

    @api.constrains(
        "secef_discount_type",
        "secef_discount_amount",
        "price_unit",
        "quantity",
    )
    def _check_secef_discount_values(self):
        for line in self:
            if line.display_type:
                continue

            if (
                line.secef_discount_type
                == "fixed"
            ):
                line._secef_fixed_discount_rate()

            elif (
                line.secef_discount_amount
                and line.secef_discount_amount > 0
            ):
                raise ValidationError(
                    _(
                        "Une remise en montant ne peut "
                        "être utilisée que lorsque le "
                        "type de remise est "
                        "'Montant fixe'."
                    )
                )

    # =========================================================
    # Protection après certification
    # =========================================================

    def _check_secef_certified_move(self):
        """Protège les lignes d'une facture SECeF certifiée."""

        protected_lines = self.filtered(
            lambda line:
                line.move_id.move_type == "out_invoice"
                and line.move_id.secef_state == "certified"
        )

        if protected_lines:
            raise UserError(
                _(
                    "Cette ligne appartient à une facture déjà "
                    "certifiée SECeF et ne peut plus être modifiée."
                )
            )

    def write(self, vals):
        protected_fields = {
            "product_id",
            "name",
            "quantity",
            "price_unit",
            "discount",
            "secef_discount_type",
            "secef_discount_amount",
            "tax_ids",
            "account_id",
            "display_type",
        }

        if protected_fields.intersection(vals):
            self._check_secef_certified_move()

        # En mode pourcentage, une remise fixe résiduelle
        # doit être supprimée.
        if (
            vals.get("secef_discount_type")
            == "percent"
        ):
            vals = dict(vals)
            vals["secef_discount_amount"] = 0.0

        result = super().write(vals)

        if (
            not self.env.context.get(
                "secef_skip_discount_sync"
            )
            and {
                "secef_discount_type",
                "secef_discount_amount",
                "price_unit",
                "quantity",
            }.intersection(vals)
        ):
            self._secef_sync_fixed_discount()

        return result

    @api.model_create_multi
    def create(self, vals_list):
        protected_fields = {
            "product_id",
            "name",
            "quantity",
            "price_unit",
            "discount",
            "secef_discount_type",
            "secef_discount_amount",
            "tax_ids",
            "account_id",
            "display_type",
        }

        move_ids = {
            vals.get("move_id")
            for vals in vals_list
            if vals.get("move_id")
        }

        if move_ids:
            certified_moves = (
                self.env["account.move"]
                .browse(list(move_ids))
                .filtered(
                    lambda move:
                        move.move_type
                        == "out_invoice"
                        and move.secef_state
                        == "certified"
                )
            )

            certified_move_ids = set(
                certified_moves.ids
            )

            for vals in vals_list:
                if (
                    vals.get("move_id")
                    in certified_move_ids
                    and protected_fields
                    .intersection(vals)
                ):
                    raise UserError(
                        _(
                            "Impossible d'ajouter une "
                            "ligne à une facture déjà "
                            "certifiée SECeF."
                        )
                    )

        lines = super().create(vals_list)

        lines._secef_sync_fixed_discount()

        return lines

    def unlink(self):
        self._check_secef_certified_move()
        return super().unlink()
