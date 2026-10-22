# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class AssetRequestRejectWizard(models.TransientModel):
    _name = 'am.asset.request.reject.wizard'
    _description = 'Asset Request Rejection Wizard'

    reason = fields.Text(string='Rejection Reason', required=True)
    handover_id = fields.Many2one('am.asset.handover.request', string='Handover Request')
    temporary_id = fields.Many2one('am.asset.temporary.request', string='Store Request')

    def action_confirm_reject(self):
        self.ensure_one()
        clean_reason = (self.reason or '').strip()
        if not clean_reason:
            raise UserError(_("Please provide a reason for the rejection."))

        if self.handover_id:
            self.handover_id.action_reject(reason=clean_reason)
        elif self.temporary_id:
            self.temporary_id.action_reject(reason=clean_reason)
        return {'type': 'ir.actions.act_window_close'}
