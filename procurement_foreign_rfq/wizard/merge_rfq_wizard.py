from odoo import models, fields, api, _
from odoo.exceptions import UserError

class ForeignRFQMergeWizard(models.TransientModel):
    _name = 'foreign.rfq.merge.wizard'
    _description = 'Merge Foreign PRs into RFQ'

    vendor_id = fields.Many2one(
        'res.partner',
        string='Vendor',
        domain=[('supplier_rank', '>', 0)],
        required=True
    )
    requisition_ids = fields.Many2many(
        'foreign.purchase.requisition',
        'foreign_rfq_merge_wizard_rel',
        'wizard_id', 'requisition_id',
        string='Requisitions',
        readonly=True
    )

    @api.model
    def default_get(self, fields_list):
        res = super(ForeignRFQMergeWizard, self).default_get(fields_list)
        if self._context.get('active_model') == 'foreign.purchase.requisition' and self._context.get('active_ids'):
            res['requisition_ids'] = [(6, 0, self._context.get('active_ids'))]
        return res

    def action_merge(self):
        self.ensure_one()
        if not self.requisition_ids:
            raise UserError(_("No requisitions selected to merge."))

        # Check if all selected PRs are approved
        if any(req.state != 'approved' for req in self.requisition_ids):
            raise UserError(_("Only CEO Approved requisitions can be merged into an RFQ."))

        rfq_lines = []
        for req in self.requisition_ids:
            for line in req.line_ids:
                rfq_lines.append((0, 0, {
                    'product_id': line.product_id.id,
                    'description': line.description,
                    'quantity': line.quantity,
                    'uom_id': line.product_uom_id.id,
                    'estimated_cost': line.unit_price,
                    'price_unit': line.unit_price,
                }))

        rfq_vals = {
            'vendor_id': self.vendor_id.id,
            'requisition_ids': [(6, 0, self.requisition_ids.ids)],
            'line_ids': rfq_lines,
            'date_rfq': fields.Date.context_today(self),
        }

        rfq = self.env['foreign.rfq'].create(rfq_vals)
        self.requisition_ids.write({'state': 'rfq_created'})

        return {
            'type': 'ir.actions.act_window',
            'name': _('Foreign RFQ'),
            'res_model': 'foreign.rfq',
            'res_id': rfq.id,
            'view_mode': 'form',
            'target': 'current',
        }
