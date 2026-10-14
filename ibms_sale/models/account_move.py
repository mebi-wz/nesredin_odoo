# -*- coding: utf-8 -*-
from odoo import api, fields, models


class AccountMove(models.Model):
    _inherit = 'account.move'

    payment_proof = fields.Binary(
        string='Payment Proof / Receipt',
        attachment=True,
        copy=False,
        help="Upload payment screenshot, bank transfer slip, Telebirr/CBE Birr confirmation, or receipt.",
    )
    payment_proof_filename = fields.Char(string='Payment Proof Filename', copy=False)
    payment_note = fields.Char(
        string='Payment Note / Reference',
        copy=False,
        help="Notes about payment, e.g. Transaction ID, bank deposit reference, Telebirr/CBE Birr confirmation code, etc.",
    )
    sale_type = fields.Selection([
        ('cash', 'Cash Sale'),
        ('credit', 'Credit Sale'),
    ], string='Sale Type', readonly=True, copy=False)
