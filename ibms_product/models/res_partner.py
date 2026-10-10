# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    customer_type = fields.Selection([
        ('retailer', 'Retailer'),
        ('wholesaler', 'Wholesaler'),
    ], string='Customer Type', default='retailer', required=True, tracking=True,
       help="Categorizes customer as Retailer or Wholesaler to automatically determine product selling price.")

    credit_status = fields.Selection([
        ('normal', 'Normal'),
        ('warning', 'Warning'),
        ('blocked', 'Blocked'),
    ], string='Credit Status', compute='_compute_credit_status')

    def compute_due_amount(self):
        try:
            super().compute_due_amount()
        except Exception:
            pass
        for rec in self:
            if not rec.id:
                rec.due_amount = 0.0

    @api.depends('due_amount', 'credit', 'warning_stage', 'blocking_stage', 'active_limit')
    def _compute_credit_status(self):
        for partner in self:
            if not partner.id or not getattr(partner, 'active_limit', False):
                partner.credit_status = 'normal'
                continue
            due_amt = getattr(partner, 'due_amount', 0.0) or 0.0
            credit_amt = getattr(partner, 'credit', 0.0) or 0.0
            amount = max(due_amt, credit_amt)
            if getattr(partner, 'blocking_stage', 0.0) > 0 and amount >= partner.blocking_stage:
                partner.credit_status = 'blocked'
            elif getattr(partner, 'warning_stage', 0.0) > 0 and amount >= partner.warning_stage:
                partner.credit_status = 'warning'
            else:
                partner.credit_status = 'normal'
