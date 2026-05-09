# -*- coding: utf-8 -*-
#############################################################################
#
#    Cybrosys Technologies Pvt. Ltd.
#
#    Copyright (C) 2022-TODAY Cybrosys Technologies(<https://www.cybrosys.com>)
#    Author: Cybrosys Techno Solutions(<https://www.cybrosys.com>)
#
#    You can modify it under the terms of the GNU LESSER
#    GENERAL PUBLIC LICENSE (LGPL v3), Version 3.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU LESSER GENERAL PUBLIC LICENSE (LGPL v3) for more details.
#
#    You should have received a copy of the GNU LESSER GENERAL PUBLIC LICENSE
#    (LGPL v3) along with this program.
#    If not, see <http://www.gnu.org/licenses/>.
#
#############################################################################


from odoo import fields, models, api, _


class PaymentProvider(models.Model):
    _inherit = 'payment.provider'

    code = fields.Selection(
        selection_add=[('payzah', "Payzah")],
        ondelete={'payzah': 'set default'}
    )
    payzah_token = fields.Char(string='Token')
    payzah_url_type = fields.Selection([
        ('transit', 'Payzah Layout'),
        ('direct', 'Direct Gateway'),
    ], string='Payment Page', default='transit', required=True)

    @api.model
    def _get_payment_method_information(self):
        """
        Overrides the `_get_payment_method_information` method to include custom
        payment method information for `payzah_knet` and `payzah_credit`. Each
        payment method is defined with its mode and domain.

        :return: A dictionary containing updated payment method information,
            including `payzah_knet` and `payzah_credit` payment methods.
        :rtype: Dict
        """
        res = super()._get_payment_method_information()
        res['payzah_knet'] = {'mode': 'unique', 'domain': [('type', '=', 'unknown')]}
        res['payzah_credit'] = {'mode': 'unique', 'domain': [('type', '=', 'unknown')]}
        return res

    def _payzah_get_api_url(self):
        """
        Determines the appropriate Payzah API URL based on the current state
        of the object. The resulting URL corresponds to either the test or
        production environment.

        :return: The API URL as a string.
        :rtype: Str
        """
        self.ensure_one()
        if self.state == 'test':
            return 'https://development.payzah.net/'  # test environment
        else:
            return 'https://payzah.net/production770/'  # live environment
