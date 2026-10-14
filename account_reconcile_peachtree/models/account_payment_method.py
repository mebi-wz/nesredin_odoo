# -*- coding: utf-8 -*-
from odoo import api, fields, models

class AccountPaymentMethod(models.Model):
    _inherit = "account.payment.method"

    is_manual = fields.Boolean(
        string="Is Manual Equivalent",
        default=False,
        help="If checked, this payment method behaves exactly like Manual Payment, allowing you to define customized payment methods."
    )

    @api.model
    def _get_payment_method_information(self):
        res = super()._get_payment_method_information()
        
        # Check if the column 'is_manual' exists in the database table to avoid crashes during registry loading/upgrades
        self.env.cr.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='account_payment_method' AND column_name='is_manual'
        """)
        if self.env.cr.fetchone():
            manual_methods = self.env['account.payment.method'].sudo().search([('is_manual', '=', True)])
            for method in manual_methods:
                res[method.code] = {'mode': 'multi', 'type': ('bank', 'cash', 'credit')}
        return res
