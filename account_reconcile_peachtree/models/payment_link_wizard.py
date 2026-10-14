# -*- coding: utf-8 -*-
from odoo import api, fields, models

class PaymentLinkWizard(models.TransientModel):
    _inherit = 'payment.link.wizard'

    @api.depends('res_model', 'res_id')
    def _compute_company_id(self):
        valid_links = self.filtered(lambda l: l.res_model)
        for link in (self - valid_links):
            link.company_id = False
        if valid_links:
            super(PaymentLinkWizard, valid_links)._compute_company_id()

    @api.depends('amount', 'currency_id', 'partner_id', 'company_id', 'res_model', 'res_id')
    def _compute_link(self):
        valid_links = self.filtered(lambda l: l.res_model)
        for link in (self - valid_links):
            link.link = False
        if valid_links:
            super(PaymentLinkWizard, valid_links)._compute_link()
