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
        for rec in self:
            if not rec.id:
                rec.due_amount = 0.0
                continue
            try:
                rec_sudo = rec.sudo()
                rec.due_amount = (rec_sudo.credit or 0.0) - (rec_sudo.debit or 0.0)
            except Exception:
                rec.due_amount = 0.0

    @api.depends('due_amount', 'credit', 'warning_stage', 'blocking_stage', 'active_limit')
    def _compute_credit_status(self):
        for partner in self:
            if not partner.id or not getattr(partner, 'active_limit', False):
                partner.credit_status = 'normal'
                continue
            try:
                partner_sudo = partner.sudo()
                due_amt = getattr(partner_sudo, 'due_amount', 0.0) or 0.0
                credit_amt = getattr(partner_sudo, 'credit', 0.0) or 0.0
                amount = max(due_amt, credit_amt)
                blocking = getattr(partner_sudo, 'blocking_stage', 0.0) or 0.0
                warning = getattr(partner_sudo, 'warning_stage', 0.0) or 0.0
                if blocking > 0 and amount >= blocking:
                    partner.credit_status = 'blocked'
                elif warning > 0 and amount >= warning:
                    partner.credit_status = 'warning'
                else:
                    partner.credit_status = 'normal'
            except Exception:
                partner.credit_status = 'normal'
