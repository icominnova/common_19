{
    "name": "Sunsoft SECeF",

    "version": "19.0.1.0.11",

    "summary": (
        "Intégration SECeF Burkina Faso "
        "pour SunApp"
    ),

    "description": """
Sunsoft SECeF
=============

Module d'intégration entre Odoo / SunApp et le système
électronique certifié de facturation du Burkina Faso.

Architecture :

Odoo / SunApp
    -> Plateforme centrale Sunsoft SECeF
    -> Agent Windows Sunsoft SECeF
    -> sunsoft_mcf
    -> FIS-NANO
    -> DGI Burkina Faso

Le module utilise une architecture de type outbox afin
de conserver durablement les identifiants de requêtes
fiscales avant toute communication réseau.
""",

    "author": "Sougrinooma Jean De Dieu KAFANDO",

    "website": (
        "https://web.facebook.com/odoobf"
    ),

    "category": "Accounting/Accounting",

    "license": "LGPL-3",

    "depends": [
        "account",
        "product",
        "sale",
        "stock",
    ],

    "external_dependencies": {
        "python": [
            "requests",
        ],
    },

    "data": [
        "security/secef_report_security.xml",
        "security/ir.model.access.csv",

        "data/secef_cron.xml",
        "data/secef_report_sequence.xml",

        "views/account_move_views.xml",
        "views/account_tax_views.xml",
        "views/product_template_views.xml",
        "views/res_partner_views.xml",
        "views/res_config_settings_views.xml",
        "views/report_invoice_secef.xml",
        "views/secef_report_views.xml",
        "views/secef_report_wizard_views.xml",
        "views/report_secef_x.xml",
        "views/report_secef_a.xml",
    ],

    "installable": True,

    "application": False,

    "auto_install": False,
}