from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

class StoreRequisition(models.Model):
    _inherit = 'store.requisition'

    pr_ids = fields.One2many('local.purchase.requisition', 'store_requisition_id', string="Purchase Requisitions")
    pr_count = fields.Integer(compute='_compute_pr_count')

    @api.depends('pr_ids')
    def _compute_pr_count(self):
        for rec in self:
            rec.pr_count = len(rec.pr_ids)

    def action_view_prs(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Purchase Requisitions',
            'res_model': 'local.purchase.requisition',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.pr_ids.ids)],
            'context': {'default_store_requisition_id': self.id},
        }

    def action_create_pr(self):
        """Create Purchase Requisition directly (only when no stock available)"""
        self.ensure_one()
        
        pr_vals = {
            'requested_by': self.requested_by.id,
            'purpose': f"Shortage from Store Requisition {self.name}",
            'cost_center_id': self.cost_center_id.id,
            'department_id': self.department_id.id,
            'store_requisition_id': self.id,
            'state': self.state,
            'line_ids': []
        }
        
        lines_added = False
        for line in self.line_ids:
            qty_needed = line.quantity - line.qty_transferred
            
            if qty_needed > 0:
                pr_vals['line_ids'].append((0, 0, {
                    'product_id': line.product_id.id,
                    'unit_price': line.unit_price,
                    'account_id': line.account_id.id if line.account_id else False,
                    'description': line.product_id.name,
                    'budget_category_id': line.budget_category_id.id if line.budget_category_id else False,
                    'remaining_budget': line.remaining_budget,
                    'quantity': qty_needed,
                    'product_uom_id': line.product_id.uom_id.id,
                    'cost_center_id': line.cost_center_id.id if line.cost_center_id else False,
                }))
                lines_added = True
        
        if not lines_added:
            raise UserError(_("No items to create Purchase Requisition for."))

        pr = self.env['local.purchase.requisition'].create(pr_vals)
        
        # Move state to waiting
        if self.state != 'waiting':
            self.write({'state': 'waiting'})
            
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'local.purchase.requisition',
            'res_id': pr.id,
            'view_mode': 'form',
            'target': 'current',
        }
class StoreRequisitionWizard(models.TransientModel):
    _inherit = 'store.requisition.wizard'
    def action_create_siv_and_pr(self):
        self.ensure_one()
        
        if not any(l.issued_qty > 0 for l in self.line_ids):
            # It's possible to just create a PR without any SIV if no stock is available.
            # But normally the wizard enforces partial stock. Let's allow 0 SIV here if needed.
            pass

        # Validate wizard lines and write adjusted quantities back to requisition lines
        # Read from the linked requisition_line_id to avoid relying on readonly wizard fields
        for l in self.line_ids:
            req_line = l.requisition_line_id
            remaining_qty = req_line.quantity
            if l.issued_qty > remaining_qty:
                raise ValidationError(_("Issued quantity for %s cannot exceed requested quantity (%s).") % (req_line.product_id.name, remaining_qty))
            if l.issued_qty > req_line.qty_on_hand:
                raise ValidationError(_("Issued quantity for %s cannot exceed available stock (%s).") % (req_line.product_id.name, req_line.qty_on_hand))
            
            req_line.issued_qty = l.issued_qty

        requisition = self.requisition_id

        # ---------------------------
        # Create SIV (Stock Picking)
        # ---------------------------
        if any(l.issued_qty > 0 for l in self.line_ids):
            picking_type = requisition.warehouse_id.int_type_id or self.env['stock.picking.type'].search([
                ('warehouse_id', '=', requisition.warehouse_id.id),
                ('code', '=', 'internal')
            ], limit=1)

            if not picking_type:
                raise UserError(
                    _("No internal picking type found for warehouse %s. Please ensure an 'Internal Transfer' sequence is configured.") % requisition.warehouse_id.name
                )

            # Determine the partner for the picking.
            requester_partner = requisition.requested_by.partner_id
            if not requester_partner:
                # Fallback to the user who created the record if no partner is linked to the employee
                requester_partner = requisition.create_uid.partner_id

            # property_stock_customer is company-dependent; safely get its id to avoid errors
            # when the partner doesn't have the property configured for the current company.
            customer_location = requester_partner and requester_partner.with_company(
                requisition.company_id
            ).property_stock_customer
            dest_location_id = (
                customer_location and customer_location.id
            ) or picking_type.default_location_dest_id.id
            
            if not dest_location_id:
                raise UserError(
                    _("No destination location defined for this warehouse.")
                )

            move_lines = []

            for line in requisition.line_ids:
                if line.issued_qty > 0:
                    move_lines.append((0, 0, {
                        'product_id': line.product_id.id,
                        'product_uom_qty': line.issued_qty,
                        'product_uom': line.product_id.uom_id.id,
                        'location_id': requisition.location_id.id,
                        'location_dest_id': dest_location_id,
                    }))

            if move_lines:
                picking = self.env['stock.picking'].create({
                    'picking_type_id': picking_type.id,
                    'location_id': requisition.location_id.id,
                    'location_dest_id': dest_location_id,
                    'origin': requisition.name,
                    'partner_id': requester_partner.id,
                    'user_id': self.env.user.id, # Set current user as responsible
                    'store_requisition_id': requisition.id,
                    'move_ids': move_lines,
                })

                picking.action_confirm()

        # ---------------------------
        # Create Purchase Requisition
        # ---------------------------
        pr_lines = []

        for line in requisition.line_ids:
            # Recompute remaining based on requested - transferred (which was updated when picking was created if auto-validated, but picking is just confirmed here)
            # The PR should cover requested - already_transferred - newly_issued_qty
            remaining_to_pr = (line.quantity - line.qty_transferred) - line.issued_qty
            if remaining_to_pr > 0:
                pr_lines.append((0, 0, {
                    'product_id': line.product_id.id,
                    'quantity': remaining_to_pr,
                    'description': line.product_id.name,
                    'account_id': line.account_id.id if line.account_id else False,
                    'budget_category_id': line.budget_category_id.id if line.budget_category_id else False,
                    'unit_price': line.unit_price,
                    'product_uom_id': line.product_id.uom_id.id,
                    'cost_center_id': line.cost_center_id.id if line.cost_center_id else False,
                }))

        if pr_lines:
            self.env['local.purchase.requisition'].create({
                'requested_by': requisition.requested_by.id,
                'store_requisition_id': requisition.id,
                'cost_center_id': requisition.cost_center_id.id,
                'department_id': requisition.department_id.id,
                'purpose': f"Shortage from Store Requisition {requisition.name}",
                'state': requisition.state,
                'company_id': requisition.company_id.id,
                'line_ids': pr_lines,
            })
            # Ensure state moves to 'waiting' if not already there
            if requisition.state != 'waiting':
                requisition.write({'state': 'waiting'})

        return {'type': 'ir.actions.act_window_close'}