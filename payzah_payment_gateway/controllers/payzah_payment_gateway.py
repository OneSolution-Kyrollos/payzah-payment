# -*- coding: utf-8 -*-
#############################################################################
# This module defines the PaymentPayzahController class, which implements
# HTTP endpoints for handling interactions with the Payzah payment gateway
# in an Odoo application. It includes routes for payment status handling,
# success, and failure responses.
#
# Classes:
#     PaymentPayzahController: HTTP controller for Payzah payment gateway
#     integration. Provides routes for multiple payment workflow scenarios.
#############################################################################
import ast
from odoo import http
from odoo.http import request
import logging

_logger = logging.getLogger(__name__)


class PaymentPayzahController(http.Controller):

    @http.route('/payment/payzah/already_paid/<int:invoice_id>',
                type='http', auth='public', website=True)
    def payzah_already_paid(self, invoice_id, **kwargs):
        """
        Handles the scenario where a payment for a specific invoice has already been successfully
        completed using the Payzah payment gateway. It searches for the completed transaction
        associated with the given invoice.

        :param invoice_id: The unique identifier of the invoice for which the payment status
            is being checked.
        :type invoice_id: int
        :param kwargs: Additional keyword arguments that may be passed during the HTTP route
            call.
        :type kwargs: dict
        :return: Renders the HTML template for the already paid notification form, including
            details of the completed transaction (if found).
        :rtype: werkzeug.wrappers.Response
        """
        done_tx = request.env['payment.transaction'].sudo().search([
            ('invoice_ids', 'in', invoice_id),
            ('provider_code', '=', 'payzah'),
            ('state', '=', 'done'),
        ], limit=1)
        return request.render(
            'payzah_payment_gateway.payzah_payment_gateway_already_paid_form',
            {'tx': done_tx}
        )

    @http.route('/payment/payzah/response', type='http', auth='public',
                website=True, methods=['POST'], csrf=False, save_session=False)
    def payzah_payment_response(self, **data):
        """
        Handle the Payzah payment response.

        This method is bound to the HTTP route `/payment/payzah/response` and is invoked
        when the payment response is received via a POST request. It processes the payment
        data and renders the payment gateway form with the extracted information.

        :param data: The payment response data received as part of the POST request.
        :type data: dict
        :return: The rendered payment gateway form with the processed payment details.
        :rtype: werkzeug.wrappers.Response
        """
        payment_data = ast.literal_eval(data["data"])
        vals = {
            'customer': payment_data["CustomerName"],
            'currency': payment_data["DisplayCurrencyIso"],
            'mobile': payment_data["CustomerMobile"],
            'invoice_amount': payment_data["InvoiceValue"],
            'address': payment_data["CustomerAddress"],
            'payment_url': payment_data["PaymentUrl"],

        }
        return request.render(
            "payzah_payment_gateway.payzah_payment_gateway_form", vals)

    @http.route('/payment/payzah/_return_url', type='http', auth='public',
                methods=['GET', 'POST'], csrf=False)
    def payzah_return_url(self, **data):
        """
        Handles the return URL callback from the Payzah payment gateway. This method processes
        the payment response data received from Payzah, updates the corresponding transaction
        record in the system, and redirects the user to the appropriate status page based on
        the payment outcome.

        :param data: Data received from the Payzah payment gateway as URL query parameters
            or POST form data.
        :type data: dict
        :return: A response directing the user to a payment status page. The page can be
            a success page, a failure page, or a default status page based on the payment
            result.
        :rtype: werkzeug.wrappers.Response
        """
        _logger.info("Payzah return data: %s", data)

        payment_status = data.get('paymentStatus')
        track_id = data.get('trackId')

        if not track_id:
            _logger.error("Payzah: missing trackId in return data")
            return request.redirect('/payment/status')

        tx = request.env['payment.transaction'].sudo().search(
            [('id', '=', track_id)], limit=1
        )
        if not tx:
            _logger.error("Payzah: no transaction found for trackId %s", track_id)
            return request.redirect('/payment/status')

        # Restore session so /payment/status can track it
        request.session['__payment_monitored_tx_id__'] = [tx.id]

        # Restore sale order session if present
        udf1 = data.get('UDF1') or data.get('udf1')
        if udf1:
            sale_order = request.env['sale.order'].sudo().browse(int(udf1))
            if sale_order.exists():
                request.session['sale_last_order_id'] = [sale_order.id]

        if payment_status == 'CAPTURED':
            tx._handle_notification_data('payzah', data)
            return request.redirect('/payment/payzah/success')
        elif payment_status == 'CANCELED':
            tx._set_canceled()
            return request.redirect('/payment/payzah/failed')
        elif payment_status == 'VOIDED':
            tx._set_pending()
            return request.redirect('/payment/payzah/failed')
        else:
            tx._set_error("Payzah: unexpected status %s" % payment_status)
            return request.redirect('/payment/payzah/failed')

    @http.route('/payment/payzah/success', type='http', auth='public', website=True)
    def payzah_success(self):
        """
        Handles the success callback after a Payzah payment transaction.

        This controller method is triggered when the payment gateway redirects the
        user back after a successful payment. It retrieves the transaction ID from
        the session, validates it, and then renders the success page displaying
        details of the transaction.

        :return: A redirection to the shop page if no transaction ID is found or a
            rendered success page showing transaction details.
        :rtype: werkzeug.wrappers.Response
        """
        tx_id = request.session.get('__payment_monitored_tx_id__')
        if not tx_id:
            return request.redirect('/shop')
        tx = request.env['payment.transaction'].sudo().browse(tx_id[0])
        return request.render(
            'payzah_payment_gateway.payzah_payment_gateway_success_form',
            {'tx': tx}
        )

    @http.route('/payment/payzah/failed', type='http', auth='public', website=True)
    def payzah_failed(self):
        """
        Handles the failed payment scenario for the Payzah payment gateway.

        This endpoint is invoked when a payment transaction using the Payzah
        gateway fails. It retrieves the failed transaction from the session,
        redirects the user to the shop page if no transaction is found, and
        renders the failed payment form otherwise.

        :return: A redirection to the shop page if no transaction is found in
                 the session; otherwise, renders the Payzah failed payment form.
        """
        tx_id = request.session.get('__payment_monitored_tx_id__')
        if not tx_id:
            return request.redirect('/shop')
        tx = request.env['payment.transaction'].sudo().browse(tx_id[0])
        return request.render(
            'payzah_payment_gateway.payzah_payment_gateway_failed_form',
            {'tx': tx}
        )
