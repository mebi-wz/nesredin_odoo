from markupsafe import Markup
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
        order = self.order_id
        if not order.is_sales_approver:
            raise UserError(_("Only Sales Managers or General Managers can reject sales orders."))

        order.write({
            'state': 'draft',
            'rejection_reason': self.reason,
            'quotation_approver_id': False,
            'quotation_approval_date': False,
            'discount_approver_id': False,
            'discount_approval_date': False,
            'approver_id': False,
            'approval_date': False,
        })
        order.message_post(
            body=Markup(
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
