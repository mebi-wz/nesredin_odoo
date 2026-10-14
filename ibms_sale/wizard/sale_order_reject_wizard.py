# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class SaleOrderRejectWizard(models.TransientModel):
    _name = 'sale.order.reject.wizard'
    _description = 'Reject Sales Order Wizard'

    order_id = fields.Many2one(
        'sale.order',
        string='Sales Order',
        required=True,
        default=lambda self: self.env.context.get('active_id'),
    )
    reason = fields.Text(
        string='Reason for Rejection',
        required=True,
        help="State why this sales order is being rejected back to draft."
    )

    def action_confirm_rejection(self):
        self.ensure_one()
        if not self.env.user.has_group('sales_team.group_sale_manager'):
            raise UserError(_("Only Sales Managers can reject sales orders."))

        order = self.order_id
        order.write({
            'state': 'draft',
            'rejection_reason': self.reason,
            'approver_id': False,
            'approval_date': False,
        })
        order.message_post(
            body=_(
                "<b>Order Rejected</b> by %(user)s.<br/>"
                "<b>Reason:</b> %(reason)s"
            ) % {
                'user': self.env.user.name,
                'reason': self.reason,
            },
            message_type='comment',
            subtype_xmlid='mail.mt_comment',
        )
        return {'type': 'ir.actions.act_window_close'}
