# -*- coding: utf-8 -*-
from odoo import models, fields, api, exceptions, _
from odoo.exceptions import ValidationError


class StoreRequisitionWizard(models.TransientModel):
    _name = 'store.requisition.wizard'
    _description = 'Store Requisition Partial Stock Wizard'

    requisition_id = fields.Many2one(
        'store.requisition',
        string='Requisition',
        required=True
    )

    message = fields.Html(
        string='Message',
        compute='_compute_message'
    )

    line_ids = fields.One2many(
        'store.requisition.wizard.line',
        'wizard_id',
        string='Lines'
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        requisition_id = self._context.get('default_requisition_id')
        if requisition_id:
            requisition = self.env['store.requisition'].browse(requisition_id)
            lines = []
            for line in requisition.line_ids:
                remaining_qty = line.quantity - line.qty_transferred
                if remaining_qty <= 0:
                    continue
                
                lines.append((0, 0, {
                    'requisition_line_id': line.id,
                    'product_id': line.product_id.id,
                    'qty_requested': line.quantity,
                    'qty_remaining': remaining_qty,
                    'qty_on_hand': line.qty_on_hand,
                    'issued_qty': line.issued_qty or min(remaining_qty, line.qty_on_hand)
                }))
            res.update({'line_ids': lines})
        return res

    @api.depends('requisition_id')
    def _compute_message(self):
        for wizard in self:
            if not wizard.requisition_id:
                wizard.message = ""
                continue
            
            lines_with_stock = []
            lines_without_stock = []

            for line in wizard.requisition_id.line_ids:
                remaining_qty = line.quantity - line.qty_transferred
                if remaining_qty <= 0:
                    continue

                if remaining_qty > line.qty_on_hand:
                    pr_qty = remaining_qty - max(0, line.qty_on_hand)
                    siv_qty = max(0, line.qty_on_hand)
                    
                    if siv_qty > 0:
                        lines_with_stock.append(
                            f"<li><b>{line.product_id.name}</b>: Partial stock ({siv_qty}). Shortage: {pr_qty}</li>"
                        )
                        lines_without_stock.append(
                            f"<li><b>{line.product_id.name}</b>: Need purchase order for {pr_qty}</li>"
                        )
                    else:
                        lines_without_stock.append(
                            f"<li><b>{line.product_id.name}</b>: No stock available (need {pr_qty})</li>"
                        )
                else:
                    lines_with_stock.append(
                        f"<li><b>{line.product_id.name}</b>: Full stock available ({remaining_qty})</li>"
                    )

            message = "<div style='margin:10px;'>"
            message += "<h4>Fulfillment Status</h4>"
            message += "<p>Review stock status below. You can issue available stock now or wait for purchase.</p>"

            if lines_with_stock:
                message += "<h5 style='color:green;'>Available to Issue:</h5><ul>"
                message += "".join(lines_with_stock)
                message += "</ul>"

            if lines_without_stock:
                message += "<h5 style='color:orange;'>Shortages:</h5><ul>"
                message += "".join(lines_without_stock)
                message += "</ul>"

            message += "</div>"
            wizard.message = message

    def action_create_siv_only(self):
        self.ensure_one()
        if not any(l.issued_qty > 0 for l in self.line_ids):
             raise ValidationError(_("Please enter at least one 'Qty to Issue' greater than 0 before proceeding."))

        # Write adjusted quantities back to requisition lines and validate
        # Read from the linked requisition_line_id to avoid relying on readonly wizard fields
        for line in self.line_ids:
            req_line = line.requisition_line_id
            remaining_qty = req_line.quantity - req_line.qty_transferred
            if line.issued_qty > remaining_qty:
                raise ValidationError(_("Issued quantity for %s cannot exceed requested quantity (%s).") % (req_line.product_id.name, remaining_qty))
            if line.issued_qty > req_line.qty_on_hand:
                raise ValidationError(_("Issued quantity for %s cannot exceed available stock (%s).") % (req_line.product_id.name, req_line.qty_on_hand))
            
            req_line.issued_qty = line.issued_qty
        
        return self.requisition_id.action_create_siv(skip_wizard=True)

    def action_cancel(self):
        return {'type': 'ir.actions.act_window_close'}


class StoreRequisitionWizardLine(models.TransientModel):
    _name = 'store.requisition.wizard.line'
    _description = 'Store Requisition Wizard Line'

    wizard_id = fields.Many2one('store.requisition.wizard', string='Wizard')
    requisition_line_id = fields.Many2one('store.requisition.line', string='Requisition Line')
    product_id = fields.Many2one('product.product', string='Product')
    qty_requested = fields.Float(string='Requested')
    qty_remaining = fields.Float(string='Remaining')
    qty_on_hand = fields.Float(string='On Hand')
    issued_qty = fields.Float(string='Qty to Issue')
