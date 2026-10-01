from odoo import models, fields, api, _
from odoo.exceptions import UserError
from markupsafe import Markup

class LocalRFQ(models.Model):
    _name = 'local.rfq'
    _description = 'Local Request for Quotation / Comparison Sheet'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name desc'

    name = fields.Char(
        string='Reference',
        required=True,
        copy=False,
        readonly=True,
        default='New',
        tracking=True
    )
    date_rfq = fields.Date(
        string='Date',
        default=fields.Date.context_today,
        required=True,
        tracking=True
    )
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)
    committee_ids = fields.Many2many('hr.employee', string='Committee')
    for_pharmacy = fields.Boolean(string='For Pharmacy', default=False)
    requested_by = fields.Many2one(
        'res.users',
        string='Procurement Officer',
        default=lambda self: self.env.user,
        readonly=True,
        tracking=True
    )
    
    # Link to Requisition
    requisition_id = fields.Many2one(
        'local.purchase.requisition',
        string='Purchase Requisition',
        required=True,
        readonly=True
    )

    # Vendor Management
    vendor_ids = fields.Many2many(
        'res.partner',
        string='Suppliers',
        domain=[('supplier_rank', '>', 0)]
    )
    
    # Comparison Logic
    winner_selection_method = fields.Selection([
        ('financial', 'Financial Only'),
        ('technical', 'Technical Only'),
        ('price', 'Lowest Price'),
        ('total', 'Total Score')
    ], string='Winner Selection Method', default='price')

    quote_ids = fields.One2many('local.rfq.quote', 'rfq_id', string='Comparison Sheet')
    
    # We remove the generic line_ids as they are now handled by quote_ids linked to PR lines
    # line_ids = fields.One2many(...) 

    po_ids = fields.One2many('purchase.order', 'local_rfq_id', string='Purchase Orders')
    po_count = fields.Integer(compute='_compute_po_count')
    
    amount_total = fields.Float(string='Total Amount', compute='_compute_amount_total', store=True, tracking=True)
    
    # Renaming to committee_action_ids to match the new model, keeping 'approval_ids' as a legacy name if needed, but better to migrate. 
    # For now, let's keep the field name 'approval_ids' to avoid heavy refactoring if other modules depend on it, 
    # BUT update the relation to the new model.
    approval_ids = fields.One2many('local.rfq.committee.action', 'rfq_id', string='Committee Actions', readonly=True)
    
    committee_status_html = fields.Html(compute='_compute_committee_status_html', string='Committee Status')

    state = fields.Selection([
        ('draft', 'Draft'),
        ('winner-picked', 'Waiting Committee Check'),
        ('checked', 'Waiting Committee Approval'),
        ('committee-approved', 'Waiting GM/CEO Approval'),
        ('on-progress', 'On Progress'),
        ('approved', 'Approved / Ready for PO'),
        ('po_created', 'PO Created'),
        ('cancel', 'Cancelled'),
    ], default='draft', string="Status", tracking=True)

    @api.depends('po_ids')
    def _compute_po_count(self):
        for rec in self:
            rec.po_count = len(rec.po_ids)

    @api.depends('quote_ids.selected', 'quote_ids.total_price')
    def _compute_amount_total(self):
        for rec in self:
            rec.amount_total = sum(rec.quote_ids.filtered(lambda q: q.selected).mapped('total_price'))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                company_id = vals.get('company_id') or self.env.company.id
                self._ensure_company_sequence(company_id)
                vals['name'] = self.env['ir.sequence'].with_company(company_id).next_by_code('local.rfq') or 'New'
        return super().create(vals_list)

    def _ensure_company_sequence(self, company_id):
        """Automatically create a separate sequence for a company if it doesn't exist."""
        Sequence = self.env['ir.sequence'].sudo()
        exists = Sequence.search([('code', '=', 'local.rfq'), ('company_id', '=', company_id)], limit=1)
        if not exists:
            template = Sequence.search([('code', '=', 'local.rfq'), ('company_id', '=', False)], limit=1)
            if template:
                template.copy({
                    'company_id': company_id,
                    'name': f"{template.name} ({self.env['res.company'].browse(company_id).name})"
                })

    def action_submit(self):
        selected_quotes = self.quote_ids.filtered(lambda q: q.selected)
        if not selected_quotes:
            raise UserError(_("Please select winning vendors in the Comparison Sheet."))
        self.write({'state': 'winner-picked'})
        self._notify_next_approver('winner-picked')

    @api.depends('approval_ids', 'committee_ids', 'state')
    def _compute_committee_status_html(self):
        for rec in self:
            rec.committee_status_html = ""

    def action_check(self):
        self.ensure_one()
        if self.state != 'winner-picked':
            raise UserError(_("Check is only allowed in 'Winner Picked' state."))
        
        # Validation: Must be in committee
        # Fix: Compare users, not employee vs user
        # if self.committee_ids:
        #     committee_users = self.committee_ids.mapped('user_id')
        #     if self.env.user not in committee_users:
        #          raise UserError(_("Only checking committee members can perform this action."))

        if not self.env.user.has_group('procurement_local_rfq.group_local_rfq_committee'):
             raise UserError(_("Only committee members can perform this action."))

        # Check if already checked
        if self.approval_ids.filtered(lambda a: a.user_id == self.env.user and a.action_type == 'check'):
            raise UserError(_("You have already checked this RFQ."))

        # Record Check
        self.env['local.rfq.committee.action'].create({
            'rfq_id': self.id,
            'user_id': self.env.user.id,
            'approval_date': fields.Datetime.now(),
            'action_type': 'check'
        })
        self.message_post(body=_("Committee member %s checked the RFQ.") % self.env.user.name)

        # Transition Logic: 3 committee members must check
        checked_count = len(self.approval_ids.filtered(lambda a: a.action_type == 'check'))
        if checked_count >= 3:
            self.write({'state': 'checked'})
            self.message_post(body=_("Committee check completed (3 members). Moving to 'Checked' state."))
            self._notify_next_approver('checked')
    
    def action_committee_approve(self):
        self.ensure_one()
        if self.state != 'checked':
            raise UserError(_("Committee Approval is only allowed in 'Checked' state."))
        
        if not self.env.user.has_group('procurement_local_rfq.group_local_rfq_committee'):
             raise UserError(_("Only committee members can perform this action."))

        # Check if already voted (approve or reject)
        if self.approval_ids.filtered(lambda a: a.user_id == self.env.user and a.action_type in ['approve', 'reject']):
            raise UserError(_("You have already voted on this RFQ."))

        # Record Approve
        self.env['local.rfq.committee.action'].create({
            'rfq_id': self.id,
            'user_id': self.env.user.id,
            'approval_date': fields.Datetime.now(),
            'action_type': 'approve'
        })
        self.message_post(body=_("Committee member %s approved the RFQ.") % self.env.user.name)

        # Transition Logic: 2 approvals required
        approval_count = len(self.approval_ids.filtered(lambda a: a.action_type == 'approve'))
        if approval_count >= 2:
            self.write({'state': 'committee-approved'})
            self.message_post(body=_("Committee approval secured (2 votes). Moving to 'Committee Approved'."))
            self._notify_next_approver('committee-approved')

    def action_committee_reject(self):
        self.ensure_one()
        if self.state != 'checked':
            raise UserError(_("Committee Rejection is only allowed in 'Checked' state."))
        
        if not self.env.user.has_group('procurement_local_rfq.group_local_rfq_committee'):
             raise UserError(_("Only committee members can perform this action."))

        # Check if already voted
        if self.approval_ids.filtered(lambda a: a.user_id == self.env.user and a.action_type in ['approve', 'reject']):
            raise UserError(_("You have already voted on this RFQ."))

        # Record Reject
        self.env['local.rfq.committee.action'].create({
            'rfq_id': self.id,
            'user_id': self.env.user.id,
            'approval_date': fields.Datetime.now(),
            'action_type': 'reject'
        })
        self.message_post(body=_("Committee member %s rejected the RFQ.") % self.env.user.name)

    def action_approve(self):
        self.ensure_one()
        next_state = False
        if self.state == 'committee-approved':
            threshold = self.company_id.pr_ceo_approval_threshold
            if self.amount_total <= threshold:
                next_state = 'approved'
                self.message_post(body=_("CEO approval skipped as amount (%.2f) is below or equal to threshold (%.2f)." % (self.amount_total, threshold)))
            else:
                next_state = 'approved' # Fallback or CEO step if we had one.
                # Actually, the user suggested GM/CEO as a single step or GM then CEO if threshold.
                # In PR we had 'budget_approved' as the CEO step.
                # Here 'ceo-approved' was used. Let's keep it if we want a separate CEO step.
                # But looking at 'state' selection above, I removed 'ceo-approved' to simplify.
                # If they want a separate CEO step for RFQ:
                # next_state = 'budget_approved' (Wait, I didn't add it to selection).
                
                # Let's re-read the request: "Procurement Committee → GM/CEO → Purchase Officer"
                # This implies GM/CEO is the final approval step.
                next_state = 'approved'

        if next_state:
            self.write({'state': next_state})
            self.message_post(body=_(self._description + " moved to %s by %s" % (next_state.replace('-', ' ').replace('_', ' ').capitalize(), self.env.user.name)))
            self._notify_next_approver(next_state)
        else:
            raise UserError(_("No further processing step for the current state or requirement not met (e.g., 3 committee checks)."))

    def action_reject(self):
        self.write({'state': 'cancel'})
        self._notify_next_approver('cancel')

    def _notify_next_approver(self, next_state):
        # Clear old activities for this record first
        self.activity_unlink(['mail.mail_activity_data_todo'])

        # Notify requester of the update
        requester_user = self.requested_by if self.requested_by else self.create_uid
        if requester_user:
            self.activity_schedule(
                'mail.mail_activity_data_todo',
                user_id=requester_user.id,
                summary=_("Local RFQ Update: %s") % self.name,
                note=_("Your local RFQ (%s) is now in state: %s.") % (self.name, next_state.replace('_', ' ').replace('-', ' ').capitalize())
            )

        group_xmlid_map = {
            'winner-picked': 'procurement_local_rfq.group_local_rfq_committee',
            'checked': 'procurement_local_rfq.group_local_rfq_committee',
            'committee-approved': 'procurement_local_purchase.group_local_purchase_pr_manager', # GM/CEO
        }
        
        group_xmlid = group_xmlid_map.get(next_state)
        if not group_xmlid:
            return

        group = self.env.ref(group_xmlid, raise_if_not_found=False)
        if not group:
            return

        company_id = self.sudo().company_id.id
        users = group.sudo().user_ids.filtered(lambda u: u.company_id.id == company_id or company_id in u.company_ids.ids)
        if not users:
            return

        for user in users:
            self.activity_schedule(
                'mail.mail_activity_data_todo',
                user_id=user.id,
                summary=_("RFQ Action Required"),
                note=_("Local RFQ (%s) is awaiting your action (State: %s).") % (self.name, next_state)
            )

    def action_cancel(self):
        self.write({'state': 'cancel'})
        self._notify_next_approver('cancel')

    def action_draft(self):
        self.write({'state': 'draft'})
        self._notify_next_approver('draft')

    # ---- Auto generate quotes when vendor added ----
    @api.onchange('vendor_ids', 'show_financial', 'show_technical')
    def _onchange_vendor_ids(self):
        for rec in self:
            if not rec.requisition_id:
                continue

            vendors = rec.vendor_ids
            quote_commands = []

            # 1. Keep existing quotes that are still valid
            valid_existing_quotes = rec.quote_ids.filtered(lambda q: q.partner_id in vendors)
            # We don't need to re-add them if we are just returning commands for OnChange
            # But for correct behavior in UI, commonly we reconstruct or just add new.
            # Odoo's onchange behaves diff than write. 
            # Ideally we want to ensure all combinations exist.
            
            # Simple approach for OnChange:
            # We can't easily "keep" without risking duplication if we aren't careful in OnChange context.
            # However, typically we just append new ones. 
            
            existing_pairs = {(q.pr_line_id.id, q.partner_id.id) for q in rec.quote_ids}

            # 2. Add quotes for missing combinations
            for vendor in vendors:
                for line in rec.requisition_id.line_ids:
                    if (line.id, vendor.id) not in existing_pairs:
                        quote_commands.append((0, 0, {
                            'pr_line_id': line.id,
                            'product_id': line.product_id.id,
                            'partner_id': vendor.id,
                        }))

            # 3. Remove quotes for de-selected vendors
            # specific to onchange logic
            quotes_to_remove = rec.quote_ids.filtered(lambda q: q.partner_id not in vendors)
            for q in quotes_to_remove:
                quote_commands.append((2, q.id))

            rec.quote_ids = quote_commands

    def action_select_winners(self):
        self.ensure_one()
        # 1. Clear all previous selections
        self.quote_ids.write({'selected': False})
        
        # 2. Group by product line and pick based on winner selection method
        pr_lines = self.quote_ids.mapped('pr_line_id')
        for line in pr_lines:
            quotes = self.quote_ids.filtered(lambda q: q.pr_line_id == line)
            if not quotes:
                continue
            
            winner = self.env['local.rfq.quote']
            
            if self.winner_selection_method == 'financial':
                max_val = max(quotes.mapped('financial_percent') or [0.0])
                winner = quotes.filtered(lambda q: q.financial_percent == max_val)
            elif self.winner_selection_method == 'technical':
                max_val = max(quotes.mapped('technical_percent') or [0.0])
                winner = quotes.filtered(lambda q: q.technical_percent == max_val)
            elif self.winner_selection_method == 'price':
                # Skip zero prices - find the best valid quote
                valid_quotes = quotes.filtered(lambda q: q.price_unit > 0)
                if valid_quotes:
                    min_price = min(valid_quotes.mapped('price_unit'))
                    winner = valid_quotes.filtered(lambda q: q.price_unit == min_price)
                else:
                    winner = quotes[:1]
            else:  # 'total'
                max_val = max(quotes.mapped('total_percent') or [0.0])
                winner = quotes.filtered(lambda q: q.total_percent == max_val)
            
            if winner:
                # Pick the first one in case of a value tie
                winner[:1].write({'selected': True})
        
        return True

 
    def action_view_comparison_matrix(self):
        self.ensure_one()
        action = self.env.ref('procurement_local_rfq.action_local_rfq_comparison_matrix').read()[0]
        action['domain'] = [('rfq_id', '=', self.id)]
        return action

    def action_create_po(self):
        self.ensure_one()
        selected_quotes = self.quote_ids.filtered(lambda q: q.selected)
        if not selected_quotes:
            raise UserError(_("Please select winning vendors in the Comparison Sheet."))

        pos = self.env['purchase.order']
        vendors = selected_quotes.mapped('partner_id')

        for vendor in vendors:
            vendor_quotes = selected_quotes.filtered(lambda q: q.partner_id == vendor)
            po_vals = {
                'partner_id': vendor.id,
                'origin': self.name,
                'local_rfq_id': self.id,
                'state': 'draft',
                'order_line': [(0, 0, {
                    'product_id': quote.product_id.id,
                    'product_qty': quote.pr_line_id.quantity, # Assuming quantity is on PR line
                    'name': quote.product_id.display_name,
                    'price_unit': quote.price_unit,
                    'date_planned': fields.Datetime.now(),
                    'analytic_distribution': {str(quote.pr_line_id.cost_center_id.id): 100} if quote.pr_line_id.cost_center_id else False,
                }) for quote in vendor_quotes],
            }
            pos |= self.env['purchase.order'].create(po_vals)

        self.write({'state': 'po_created'})
        return self.action_view_pos()

    def action_view_pos(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Purchase Orders'),
            'res_model': 'purchase.order',
            'view_mode': 'list,form',
            'domain': [('local_rfq_id', '=', self.id)],
            'context': {'default_local_rfq_id': self.id},
        }

class LocalRFQQuote(models.Model):
    _name = 'local.rfq.quote'
    _description = 'Local RFQ Quote / Comparison Line'

    rfq_id = fields.Many2one('local.rfq', string='RFQ', ondelete='cascade')
    
    # Link to Original PR Line to track quantity and product
    pr_line_id = fields.Many2one(
        'local.purchase.requisition.line',
        string='PR Line',
        required=True,
        ondelete='restrict'
    )
    product_id = fields.Many2one('product.product', string='Product', related='pr_line_id.product_id')
    partner_id = fields.Many2one('res.partner', string='Vendor', required=True, domain="[('vendor_type', '=', 'local')]")
    cost_center_id = fields.Many2one('account.analytic.account', string='Cost Center', related='pr_line_id.cost_center_id')
    
    price_unit = fields.Float(string='Unit Price')
    delivery_date = fields.Date(string='Expected Delivery')
    selected = fields.Boolean(string='Selected', default=False)
    
    financial_percent = fields.Float(string='Financial %')
    technical_percent = fields.Float(string='Technical %')
    total_percent = fields.Float(string='Total %', compute='_compute_total_percent', store=True)

    total_price = fields.Float(string='Total Price', compute='_compute_total_price', store=True)

    @api.depends('price_unit', 'pr_line_id.quantity')
    def _compute_total_price(self):
        for rec in self:
            rec.total_price = rec.price_unit * (rec.pr_line_id.quantity if rec.pr_line_id else 0.0)

    @api.depends('financial_percent', 'technical_percent')
    def _compute_total_percent(self):
        for rec in self:
            rec.total_percent = (rec.financial_percent + rec.technical_percent) / 2

# Inherit Local Purchase Requisition to add link
class LocalPurchaseRequisition(models.Model):
    _inherit = 'local.purchase.requisition'

    rfq_ids = fields.One2many('local.rfq', 'requisition_id', string='RFQs')
    rfq_count = fields.Integer(compute='_compute_rfq_count')

    @api.depends('rfq_ids')
    def _compute_rfq_count(self):
        for rec in self:
            rec.rfq_count = len(rec.rfq_ids)

    def action_create_rfq(self):
        self.ensure_one()
        
        # Threshold Validation
        min_threshold = self.company_id.rfq_threshold_from
        max_threshold = self.company_id.rfq_threshold_to
        
        if not (min_threshold <= self.amount_total <= max_threshold):
            raise UserError(_("Total amount (%.2f) must be between %.2f and %.2f to create an RFQ.") % (
                self.amount_total, min_threshold, max_threshold))

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'local.rfq',
            'view_mode': 'form',
            'context': {'default_requisition_id': self.id},
            'target': 'current',
        }

    def action_view_rfqs(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('RFQs'),
            'res_model': 'local.rfq',
            'view_mode': 'list,form',
            'domain': [('requisition_id', '=', self.id)],
            'context': {'default_requisition_id': self.id},
        }

# Inherit Purchase Order to add link
class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    local_rfq_id = fields.Many2one('local.rfq', string='Source Local RFQ')

class LocalRFQCommitteeAction(models.Model):
    _name = 'local.rfq.committee.action'
    _description = 'Local RFQ Committee Action (Check/Approve/Reject)'
    _order = 'approval_date desc'

    rfq_id = fields.Many2one('local.rfq', string='RFQ', ondelete='cascade', required=True)
    user_id = fields.Many2one('res.users', string='User', required=True)
    approval_date = fields.Datetime(string='Date', required=True)
    action_type = fields.Selection([
        ('check', 'Checked'),
        ('approve', 'Approved'),
        ('reject', 'Rejected')
    ], string='Action', required=True)
    comment = fields.Text(string='Comment')
