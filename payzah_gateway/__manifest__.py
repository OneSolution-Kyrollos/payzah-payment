# -*- coding: utf-8 -*-
{
    'name': 'Payzah Payment Gateway',
    'summary': "Payzah Payment Gateway for Odoo 18",
    'description': """
Payzah Payment Gateway Integration for Odoo 18
Supports Knet and Credit Card payments.
Developed by One Solutions - Kuwait
Contact: +96592229650
    """,
    'author': "Payzah",
    'company': 'Payzah',
    'maintainer': 'Kyrollos Zaki | +96592229650',
    'website': "https://payzah.com",
    'license': 'LGPL-3',
    'category': 'Accounting/Payment Acquirers',
    'version': '18.0.1.0.0',
    'depends': [
        'payment',
        'account',
        'website',
        'website_sale',
    ],
    'data': [
        'views/payment_provider_view.xml',
        'views/payment_transaction_view.xml',
        'views/payment_payzah_templates.xml',
        'views/payzah_payment_template.xml',
        'data/payment_provider_data.xml',
    ],
    'demo': [],
    'images': ['static/description/images.png'],
    'installable': True,
    'auto_install': False,
    'application': False,
}