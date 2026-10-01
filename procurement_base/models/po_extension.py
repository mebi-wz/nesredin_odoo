from odoo import models, fields, api

class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    # You can add fields or logic here to link back to requisitions if needed
    # For example, a field to store the source requisition reference
    requisition_ref = fields.Char(string='Requisition Reference')    
    request_type = fields.Selection([
        ('local', 'Local'),
        ('foreign', 'Foreign'),
    ], string='Request Type', default='local')
    
    partner_id = fields.Many2one(
        'res.partner',
        string='Vendor',
        required=True,
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id), ('vendor_type', '=', request_type)]"
    )

    # Moving local_requisition_id here to ensure it is available for Filter Domains in purchase_local_basic
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                request_type = vals.get('request_type') or self.env.context.get('default_request_type')
                is_foreign = request_type == 'foreign' or vals.get('foreign_purchase_request_id') or vals.get('foreign_rfq_id') or self.env.context.get('default_foreign_purchase_request_id')
                is_local = request_type == 'local' or vals.get('local_purchase_request_id') or vals.get('local_rfq_id') or self.env.context.get('default_local_purchase_request_id')
                
                if is_foreign:
                    vals['request_type'] = 'foreign'
                    company_id = vals.get('company_id') or self.env.company.id
                    self._ensure_company_sequence(company_id, 'purchase.order.foreign')
                    vals['name'] = self.env['ir.sequence'].with_company(company_id).next_by_code('purchase.order.foreign') or 'PO-F0001'
                elif is_local:
                    vals['request_type'] = 'local'
                    company_id = vals.get('company_id') or self.env.company.id
                    self._ensure_company_sequence(company_id, 'purchase.order.local')
                    vals['name'] = self.env['ir.sequence'].with_company(company_id).next_by_code('purchase.order.local') or 'PO-L0001'
        return super(PurchaseOrder, self).create(vals_list)

    def _ensure_company_sequence(self, company_id, code):
        """Automatically create a separate sequence for a company if it doesn't exist."""
        Sequence = self.env['ir.sequence'].sudo()
        exists = Sequence.search([('code', '=', code), ('company_id', '=', company_id)], limit=1)
        if not exists:
            template = Sequence.search([('code', '=', code), ('company_id', '=', False)], limit=1)
            if template:
                template.copy({
                    'company_id': company_id,
                    'name': f"{template.name} ({self.env['res.company'].browse(company_id).name})"
                })

    def _prepare_picking(self):
        res = super()._prepare_picking()
        if self.company_id.set_po_date_as_receipt_date and self.date_planned:
            res['scheduled_date'] = self.date_planned
        return res

    def _create_picking(self):
        res = super()._create_picking()
        if self.company_id.set_po_date_as_receipt_date and self.date_planned:
            for picking in self.picking_ids:
                if picking.scheduled_date != self.date_planned:
                    picking.write({'scheduled_date': self.date_planned})
        return res