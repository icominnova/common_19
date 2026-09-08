from num2words import num2words

from odoo import models


def _quantity_to_words(record, quantity):
    """Convert a quantity using the current report/user language."""
    lang_code = record.env.context.get("lang") or record.env.user.lang or "fr_FR"
    language = lang_code.split("_", 1)[0].split("-", 1)[0]
    try:
        return num2words(quantity, lang=language)
    except (NotImplementedError, ValueError):
        return num2words(quantity, lang="fr")


class StockMove(models.Model):
    _inherit = "stock.move"

    def qty_to_words(self):
        self.ensure_one()
        return _quantity_to_words(self, self.product_uom_qty)


class PurchaseOrderLine(models.Model):
    _inherit = "purchase.order.line"

    def qty_to_words(self):
        self.ensure_one()
        return _quantity_to_words(self, self.product_qty)
