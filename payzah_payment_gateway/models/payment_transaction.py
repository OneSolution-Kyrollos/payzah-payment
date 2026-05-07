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
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.addons.payment import utils as payment_utils
import requests
import json
import logging

_logger = logging.getLogger(__name__)


class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'
    paymentid = fields.Char('PaymentID')
    trackid = fields.Char()

    def _get_specific_rendering_values(self, processing_values):
        """
        Processes specific rendering values for payment execution based on the provider.

        This method extends the behavior of a parent implementation to include additional
        logic specific to the 'payzah' provider. If the provider code is not 'payzah',
        it will return the result from the parent class. Otherwise, it will execute the
        payment process.

        :param processing_values: A dictionary containing processing values required
                                  for rendering.
        :type processing_values: Dict
        :return: If the provider code is not 'payzah', returns the result of calling
                 the parent class method. If the provider code is 'payzah', returns
                 the value from the payment execution process.
        :rtype: Any
        """
        res = super()._get_specific_rendering_values(processing_values)
        if self.provider_code != 'payzah':
            return res
        return self.execute_payment()

    def execute_payment(self):
        """
        Executes a payment using the Payzah payment gateway. This method handles:
        - Validation to ensure there are no already paid invoices related to the payment.
        - Creating and sending the payment request to the payment gateway.
        - Processing the response and retrieving the payment redirection URL.

        :raises ValidationError: When there is a connection error with the payment gateway, or if the
            payment gateway fails to provide a payment URL in its response.
        :return: A dictionary containing the URL for redirecting to the Payzah payment gateway.
        :rtype: Dict
        """
        self.ensure_one()

        # -------------------------------------------------------
        # Check if already paid
        # CASE 1: Direct invoice payment
        # CASE 2: Sale order payment
        # -------------------------------------------------------
        invoices_to_check = self.invoice_ids  # direct invoices
        for sale in self.sale_order_ids:  # sale order invoices
            invoices_to_check |= sale.invoice_ids

        for invoice in invoices_to_check:
            if invoice.payment_state in ('paid', 'in_payment'):
                base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
                return {'api_url': f"{base_url}/payment/payzah/already_paid/{invoice.id}"}

        # -------------------------------------------------------
        # Proceed with payment
        # -------------------------------------------------------
        provider = self.provider_id
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        api_url = f"{provider._payzah_get_api_url()}ws/paymentgateway/index"

        payment_type = 1 if self.payment_method_code == 'payzah_knet' else 2

        payload = {
            "trackid": self.id,
            "amount": self.amount,
            "success_url": f"{base_url}/payment/payzah/_return_url",
            "error_url": f"{base_url}/payment/payzah/failed",
            "language": "ENG",
            "currency": 414,
            "payment_type": payment_type,
            "udf1": self.sale_order_ids[0].id if self.sale_order_ids else "",
            "udf2": self.invoice_ids[0].id if self.invoice_ids else "",
            "udf3": "", "udf4": "", "udf5": "",
        }

        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'Authorization': provider.payzah_token,
        }

        try:
            response = requests.post(api_url, headers=headers, json=payload, timeout=30)
            response.raise_for_status()
            response_data = response.json()
        except requests.exceptions.RequestException as e:
            raise ValidationError(_("Payzah: Connection error — %s") % str(e))

        _logger.info("Payzah API response: %s", response_data)

        data = response_data.get('data', {})
        if not data or 'PaymentUrl' not in data:
            raise ValidationError(
                _("Payzah: Could not generate payment link. Response: %s") % response_data
            )

        self.write({
            'paymentid': data['PaymentID'],
            'trackid': str(self.id),
        })

        redirect_url = data.get('transit_url') if provider.payzah_url_type == 'transit' else data.get('direct_url')
        redirect_url = redirect_url or data['PaymentUrl']

        return {'api_url': redirect_url}

    def _get_tx_from_notification_data(self, provider_code, notification_data):
        """
        Extracts and validates the transaction associated with the provided provider code
        and notification data. The method retrieves payment details using Payzah's API
        and ensures that a matching transaction exists.

        The function primarily serves as an integration point with the Payzah payment
        provider system. It verifies transaction details by sending a POST request to
        Payzah's API. The retrieved details are then checked against existing
        transactions in the system.

        :param provider_code: The short code identifying the payment provider.
        :type provider_code: Str
        :param notification_data: Data received as a notification from the payment
            provider, typically containing payment identifiers.
        :type notification_data: Dict
        :return: The transaction retrieved based on the notification data, if valid.
        :rtype: Recordset
        :raises ValidationError: If no matching transaction is found for the provided
            data.
        """
        api_key = self.env['payment.provider'].search([('code', '=', 'payzah')]).payzah_token
        base_api_url = self.env['payment.provider'].search([('code', '=', 'payzah')])._payzah_get_api_url()

        url = f"{base_api_url}ws/paymentgateway/get-payment-details"
        paymentid = notification_data.get('paymentId')
        trackId = notification_data.get('trackId')
        payload = json.dumps({
            "trackid": trackId,
            "payment_id": paymentid
        })
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'Authorization': api_key,
        }

        response = requests.request("POST", url, headers=headers, data=payload)
        response_data = response.json()
        tx = super()._get_tx_from_notification_data(provider_code,
                                                    notification_data)
        if provider_code != 'payzah' or len(tx) == 1:
            return tx
        tx = self.search([('id', '=', trackId), ('provider_code', '=', 'payzah')])
        if not tx:
            raise ValidationError(
                "payzah: " + _(
                    "No transaction found matching reference %s.",
                    trackId)
            )
        return tx

    def _handle_notification_data(self, provider_code, notification_data):
        """
        Processes notification data for a specific provider and executes corresponding
        callback logic. The method retrieves transaction details from the given
        notification data, processes the data, and then triggers the relevant callback.

        :param provider_code: Code identifying the notification provider.
        :type provider_code: Str
        :param notification_data: Data received from the notification provider.
        :type notification_data: Dict
        :return: A transaction object associated with the processed notification data.
        :rtype: Any
        """
        tx = self._get_tx_from_notification_data(provider_code,
                                                 notification_data)
        tx._process_notification_data(notification_data)
        tx._execute_callback()
        return tx

    def _process_notification_data(self, notification_data):
        """
        Processes the notification data received for the Payzah provider. This method
        analyzes the payment status within the notification, updates the corresponding
        state, and takes further actions based on the specific status values.

        :param notification_data: A dictionary containing the notification payload for
            the payment provider.
        :type notification_data: Dict
        :return: None
        """
        super()._process_notification_data(notification_data)
        if self.provider_code != 'payzah':
            return

        payment_status = notification_data.get('paymentStatus')

        if payment_status == 'CAPTURED':
            self._set_done()
            self._finalize_success_processing()
        elif payment_status == 'CANCELED':
            self._set_canceled()
        elif payment_status == 'VOIDED':
            self._set_pending()
        else:
            self._set_error("Payzah: unexpected status %s" % payment_status)

    def _finalize_success_processing(self):
        """
        Finalizes the processing of a payment transaction when it is marked as successful.

        This method performs the following operations depending on the transaction context:
        - Handles the sale orders associated with the transaction.
          Confirms their state, generates related invoices if needed, and processes payments for the invoices.
        - Handles invoices directly associated with the transaction, if present, and ensures they are paid.

        If sale orders are in a draft or sent state, the method confirms them. It ensures
        that deliveries are marked as completed before creating invoices, assigns transaction
        information to invoices, and processes payment for them.

        Similarly, for invoices directly associated with the transaction that are not canceled,
        the method attempts to complete their payments. Payments will not be created for invoices
        that are already paid or in payment.

        :param invoice: An invoice created or processed in the transaction.
        :type invoice: account.move
        :return: None
        """
        self.ensure_one()
        _logger.info("Payzah: finalizing tx %s | sale_orders: %s | invoices: %s",
                     self.reference, self.sale_order_ids.mapped('name'), self.invoice_ids.mapped('name'))

        def _register_payment(invoice):
            if invoice.state == 'draft':
                invoice.action_post()
            if invoice.payment_state in ('paid', 'in_payment'):
                _logger.info("Payzah: invoice %s already paid, skipping", invoice.name)
                return
            try:
                payment_obj = self.env['account.payment.register'].with_context(
                    active_model='account.move',
                    active_ids=invoice.ids
                ).sudo().create({
                    'payment_date': invoice.date,
                    'amount': self.amount,
                    'currency_id': self.currency_id.id,
                })._create_payments()
                self.payment_id = payment_obj.id
                _logger.info("Payzah: payment created for invoice %s", invoice.name)
            except Exception as e:
                _logger.warning("Payzah: payment failed for %s: %s", invoice.name, str(e))

        # -------------------------------------------------------
        # CASE 1: SALE ORDER
        # -------------------------------------------------------
        if self.sale_order_ids:
            for sale in self.sale_order_ids:
                if sale.state in ('draft', 'sent'):
                    sale.action_confirm()

                if not sale.invoice_ids:
                    try:
                        for line in sale.order_line:
                            if line.qty_delivered == 0:
                                line.qty_delivered = line.product_uom_qty
                        invoices = sale._create_invoices()
                        invoices.write({'transaction_ids': [(4, self.id)]})
                        _logger.info("Payzah: invoice created for sale %s: %s",
                                     sale.name, invoices.mapped('name'))
                    except Exception as e:
                        _logger.warning("Payzah: invoice creation failed for %s: %s",
                                        sale.name, str(e))

                for invoice in sale.invoice_ids.filtered(lambda i: i.state != 'cancel'):
                    _register_payment(invoice)

        # -------------------------------------------------------
        # CASE 2: INVOICE ONLY (skip if already handled via sale order)
        # -------------------------------------------------------
        elif self.invoice_ids:
            for invoice in self.invoice_ids.filtered(lambda i: i.state != 'cancel'):
                _register_payment(invoice)