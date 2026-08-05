# In a new file models/account_move.py
from odoo import models, _
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = 'account.move'

    def _get_payzah_transactions(self):
        """Get all Payzah transactions linked to this invoice sorted by date desc."""
        return self.env['payment.transaction'].search([
            ('invoice_ids', 'in', self.id),
            ('provider_code', '=', 'payzah'),
            ('state', '=', 'done'),
        ], order='id desc')

    def action_post(self):
        res = super().action_post()
        # When a credit note is posted, trigger Payzah refunds
        for move in self:
            if move.move_type == 'out_refund' and move.reversed_entry_id:
                move._process_payzah_refund()
        return res

    def _process_payzah_refund(self):
        """Process Payzah refund when credit note is posted."""
        self.ensure_one()
        original_invoice = self.reversed_entry_id
        if not original_invoice:
            return

        payzah_txs = original_invoice._get_payzah_transactions()
        if not payzah_txs:
            return

        # Get refund reason from credit note ref field
        refund_reason = self.ref or self.narration or _("Refund via Odoo Credit Note")

        refund_amount_remaining = self.amount_total
        _logger.info(
            "Payzah: processing refund of %s for invoice %s, reason: %s",
            refund_amount_remaining, original_invoice.name, refund_reason
        )

        for tx in payzah_txs:
            if refund_amount_remaining <= 0:
                break

            refund_from_tx = min(refund_amount_remaining, tx.amount)

            try:
                tx._send_refund_request(
                    amount_to_refund=refund_from_tx,
                    reason=refund_reason
                )
                _logger.info(
                    "Payzah: refunded %s from tx %s (ref: %s)",
                    refund_from_tx, tx.id, tx.payzah_reference_code
                )
                refund_amount_remaining -= refund_from_tx
            except Exception as e:
                _logger.warning(
                    "Payzah: refund failed for tx %s: %s", tx.id, str(e)
                )