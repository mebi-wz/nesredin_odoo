from odoo import models, fields, api, _
from odoo.exceptions import UserError

class ForeignPurchaseRequisition(models.Model):
    _inherit = 'foreign.purchase.requisition'

    rfq_ids = fields.Many2many('foreign.rfq', compute='_compute_rfq_ids', string='Foreign RFQs')
    rfq_count = fields.Integer(compute='_compute_rfq_count')

    def _compute_rfq_ids(self):
        for rec in self:
            rec.rfq_ids = self.env['foreign.rfq'].search(['|', ('requisition_id', '=', rec.id), ('requisition_ids', 'in', rec.id)])

    @api.depends('rfq_ids')
    def _compute_rfq_count(self):
        for rec in self:
            rec.rfq_count = len(rec.rfq_ids)

    def action_create_rfq(self):
        self.ensure_one()
        rfq = self.env['foreign.rfq'].create({
            'requisition_id': self.id,
            'line_ids': [
                (0, 0, {
                    'product_id': line.product_id.id,
                    'description': line.description,
                    'quantity': line.quantity,
                    'uom_id': line.product_uom_id.id,
                    'price_unit': line.unit_price,
                    'cost_center_id': line.cost_center_id.id,
                }) for line in self.line_ids
            ]
        })
        self.write({'state': 'rfq_created'})
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'foreign.rfq',
            'view_mode': 'form',
            'res_id': rfq.id,
        }

    def action_view_rfqs(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id("procurement_foreign_rfq.action_foreign_rfq")
        if self.rfq_count > 1:
            action['domain'] = [('id', 'in', self.rfq_ids.ids)]
        elif self.rfq_count == 1:
            action['views'] = [(self.env.ref('procurement_foreign_rfq.view_foreign_rfq_form').id, 'form')]
            action['res_id'] = self.rfq_ids.id
        else:
            action['domain'] = [('id', 'in', [])]
        return action
