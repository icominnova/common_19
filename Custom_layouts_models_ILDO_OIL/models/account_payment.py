from num2words import num2words

from odoo import models


class AccountPayment(models.Model):
    _inherit = "account.payment"

    def ildo_amount_to_text(self):
        self.ensure_one()
        amount = self.currency_id.round(self.amount)
        integer_amount = int(amount)
        decimal_amount = int(round((amount - integer_amount) * 100))
        words = num2words(integer_amount, lang="fr")
        currency_words = "franc CFA" if integer_amount == 1 else "francs CFA"
        result = f"{words} {currency_words}"
        if decimal_amount:
            decimal_words = num2words(decimal_amount, lang="fr")
            centime_words = "centime" if decimal_amount == 1 else "centimes"
            result += f" et {decimal_words} {centime_words}"
        return result[:1].upper() + result[1:]
