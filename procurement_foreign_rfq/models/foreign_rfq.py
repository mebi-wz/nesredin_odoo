from odoo import models, fields, api, _
from odoo.exceptions import UserError

class PurchasePortLoading(models.Model):
    _name = 'purchase.port.loading'
    _description = 'Port of Loading'
    _order = 'name desc'

    name = fields.Char(string='Port Name', required=True)
    port_type = fields.Selection([
        ('loading', 'Port of Loading'),
        ('discharge', 'Port of Discharge'),
        ('final_destination', 'Final Destination'),
    ], string='Port Type', required=True)



class ForeignRFQ(models.Model):
    _name = 'foreign.rfq'
    _description = 'Foreign Request for Quotation'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name desc'

    name = fields.Char(
        string='Reference',
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _('New')
    )
    vendor_id = fields.Many2one(
        'res.partner',
        string='Vendor',
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id), ('vendor_type', '=', 'foreign')]",
        required=False,
        tracking=True
    )

    currency_id = fields.Many2one('res.currency', string='Currency', required=True, default=lambda self: self.env.company.currency_id, tracking=True)
    exchange_rate = fields.Float(string='Exchange Rate', compute='_compute_exchange_rate', store=True, tracking=True, help='Exchange rate applied if supplier currency differs from payment currency')

    @api.depends('currency_id', 'date_rfq', 'company_id')
    def _compute_exchange_rate(self):
        for rec in self:
            if rec.currency_id and rec.company_id:
                rec.exchange_rate = rec.currency_id._get_conversion_rate(
                    rec.currency_id,
                    rec.company_id.currency_id,
                    rec.company_id,
                    rec.date_rfq or fields.Date.context_today(rec)
                )
            else:
                rec.exchange_rate = 1.0
    requisition_id = fields.Many2one(
        'foreign.purchase.requisition',
        string='Foreign Requisition',
        readonly=True,
        tracking=True
    )
    requisition_ids = fields.Many2many(
        'foreign.purchase.requisition',
        'foreign_rfq_requisition_rel',
        'rfq_id', 'requisition_id',
        string='Foreign Requisitions',
        readonly=True,
        tracking=True
    )
    date_rfq = fields.Date(
        string='RFQ Date',
        default=fields.Date.context_today,
        required=True,
        tracking=True
    )
    state = fields.Selection([
        ('draft', 'Draft'),
        ('submitted', 'Waiting Verification'),
        ('verified', 'Waiting CEO Approval'),
        ('pending_currency', 'Pending Currency'),
        ('approved', 'Currency Approved'),
        ('po_created', 'PO Created'),
        ('rejected', 'Rejected'),
        ('cancel', 'Cancelled'),
    ], string='Status', default='draft', tracking=True)







    # Approval Workflow Fields
    op_approval_date = fields.Datetime(string='OP Approval Date', readonly=True)
    op_approved_by = fields.Many2one('res.users', string='OP Approved By', readonly=True)
    approval_date = fields.Datetime(string='CEO Approval Date', readonly=True)
    approved_by = fields.Many2one('res.users', string='CEO Approved By', readonly=True)
    rejection_reason = fields.Text(string='Rejection Reason', readonly=True)


    line_ids = fields.One2many(
        'foreign.rfq.line',
        'rfq_id',
        string='Lines',
        tracking=True
    )

    # Proforma Invoice Fields (Extended)
    proforma_invoice_no = fields.Char(string='Proforma Invoice Number', tracking=True)
    proforma_invoice_date = fields.Date(string='Proforma Invoice Date', default=fields.Date.context_today, required=True, tracking=True)

    pi_amount = fields.Monetary(string='PI Amount', compute='_compute_amount_total', store=True, currency_field='pi_currency_id', tracking=True)
    pi_currency_id = fields.Many2one('res.currency', string='PI Currency', required=True, default=lambda self: self.env.company.currency_id, tracking=True)
    pi_attachment_ids = fields.Many2many('ir.attachment', string='PI Attachments')

    # Payment and Shipping Info
    payment_terms = fields.Selection([
        ('cad', 'CAD'),
        ('lc', 'LC'),
        ('tt', 'TT'),
        ('franco', 'FRANCO'),
    ], string='Payment Term', default="lc")

    incoterm = fields.Many2one('account.incoterms', string="Incoterm")
    shipping_method = fields.Selection([
        ('sea', 'Sea Freight'),
        ('air', 'Air Freight'),
        ('land', 'Land Transport'),
    ], string='Shipping Method')

    mod_of_shipment = fields.Selection([
        ('air', 'AIR'),
        ('sea', 'SEA'),
    ], string="Mode of Shipment", default='air')

    # Ports
    port_of_loading = fields.Many2one('purchase.port.loading', string="Port Of Loading", domain="[('port_type', '=', 'loading')]")
    port_of_discharge = fields.Many2one('purchase.port.loading', string="Port Of Discharge", domain="[('port_type', '=', 'discharge')]")
    port_of_final_destination = fields.Many2one('purchase.port.loading', string="Port Of Final Destination", domain="[('port_type', '=', 'final_destination')]")

    # Tracking & Other
    terms_conditions = fields.Text(string='Terms and Conditions')
    validity_period = fields.Date(string='Validity Until')
    estimated_delivery_date = fields.Date(string='Estimated Delivery Date')
    shipping_origin = fields.Char(string='Shipping Origin')
    shipping_destination = fields.Char(string='Shipping Destination')
    custom_duty_tax = fields.Float(string="Custom Duty Tax")
    country_of_origin = fields.Many2one('res.country', string='Country of Origin')
    
    amount_total = fields.Float(string='Total Amount', compute='_compute_amount_total', store=True)
    amount_total_etb = fields.Float(string='Total Amount (ETB)', compute='_compute_amount_total', store=True)
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)
    purchase_order_id = fields.Many2one('purchase.order', string='Purchase Order', readonly=True)
    po_count = fields.Integer(compute='_compute_po_count')
    
    # Currency Request Integration
    currency_request_ids = fields.One2many('procurement.currency.request', 'rfq_id', string='Currency Requests')

    is_currency_approved = fields.Boolean(compute='_compute_is_currency_approved', string="Is Currency Approved")
    has_currency_request = fields.Boolean(compute='_compute_has_currency_request', string="Has Currency Request")
    currency_count=fields.Integer(compute='_compute_currency_count', string="Currency Count")
    
    @api.depends('currency_request_ids')
    def _compute_currency_count(self):
        for rec in self:
            rec.currency_count = len(rec.currency_request_ids)
    @api.depends('currency_request_ids')
    def _compute_has_currency_request(self):
        for rec in self:
            rec.has_currency_request = bool(rec.currency_request_ids)

    @api.depends('currency_request_ids.state')
    def _compute_is_currency_approved(self):
        for rec in self:
            rec.is_currency_approved = any(req.state == 'approved' for req in rec.currency_request_ids)



    @api.depends('line_ids.price_subtotal', 'line_ids.price_subtotal_etb', 'currency_id', 'pi_currency_id')
    def _compute_amount_total(self):
        for rec in self:
            rec.amount_total = sum(rec.line_ids.mapped('price_subtotal'))
            rec.amount_total_etb = sum(rec.line_ids.mapped('price_subtotal_etb'))
            
            # Update pi_amount based on pi_currency_id
            if rec.pi_currency_id and rec.currency_id and rec.pi_currency_id != rec.currency_id:
                # Convert amount_total from currency_id to pi_currency_id
                rec.pi_amount = rec.currency_id._convert(
                    rec.amount_total,
                    rec.pi_currency_id,
                    rec.company_id,
                    rec.date_rfq or fields.Date.context_today()
                )
            else:
                rec.pi_amount = rec.amount_total

    @api.depends('purchase_order_id')
    def _compute_po_count(self):
        for rec in self:
            rec.po_count = 1 if rec.purchase_order_id else 0

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('foreign.rfq') or _('New')
        return super().create(vals_list)

    def action_submit_for_approval(self):
        self.ensure_one()
        if not self.proforma_invoice_no:
            raise UserError(_("Please provide the Proforma Invoice Number."))
        self.write({'state': 'submitted'})

    def action_approve(self):
        self.ensure_one()
        if self.state == 'draft' and not self.vendor_id:
            raise UserError(_("Please specify a Vendor before submitting the RFQ."))
        if self.state == 'draft' and not self.proforma_invoice_no:
            raise UserError(_("Please provide the Proforma Invoice Number."))
        state_map = {
            'draft': 'submitted',
            'submitted': 'verified',
            'verified': 'pending_currency',
        }

        next_state = state_map.get(self.state)
        if next_state:
            vals = {'state': next_state}
            if next_state == 'pending_currency':
                vals.update({
                    'approval_date': fields.Datetime.now(),
                    'approved_by': self.env.user.id
                })
            self.write(vals)
            self._notify_next_approver(next_state)

            if next_state == 'pending_currency':
                # Automatically create Currency Request if none exists that is not cancelled
                if not any(req.state != 'cancelled' for req in self.currency_request_ids):
                    employee = self.env['hr.employee'].search([('user_id', '=', self.env.user.id)], limit=1)
                    bank_id = False
                    if self.vendor_id and self.vendor_id.bank_ids and self.vendor_id.bank_ids[0].bank_id:
                        bank_id = self.vendor_id.bank_ids[0].bank_id.id
                    
                    currency_request_vals = {
                        'rfq_id': self.id,
                        'supplier_id': self.vendor_id.id if self.vendor_id else False,
                        'proforma_invoice': self.proforma_invoice_no,
                        'currency_id': self.currency_id.id if self.currency_id else False,
                        'total_amount_usd': self.amount_total,
                        'company_id': self.company_id.id,
                        'department_id': employee.department_id.id if employee and employee.department_id else False,
                        'bank_id': bank_id,
                        'requested_by': self.env.user.id,
                        'date_request': fields.Datetime.now(),
                        'exchange_rate': self.exchange_rate,
                    }
                    
                    amount_total_etb = self.amount_total * self.exchange_rate
                    if amount_total_etb:
                        currency_request_vals['amount_in_word'] = self.env.company.currency_id.amount_to_text(amount_total_etb)
                    
                    self.env['procurement.currency.request'].create(currency_request_vals)

        else:
            raise UserError(_("No further approval step for the current state."))

    def _notify_next_approver(self, next_state):
        # Clear old activities for this record first
        self.activity_unlink(['mail.mail_activity_data_todo'])

        # Notify requester (creator) of the update
        requester_user = self.create_uid
        if requester_user:
            self.activity_schedule(
                'mail.mail_activity_data_todo',
                user_id=requester_user.id,
                summary=_("Foreign RFQ Update: %s") % self.name,
                note=_("Your foreign RFQ (%s) is now in state: %s.") % (self.name, next_state.replace('_', ' ').replace('-', ' ').capitalize())
            )

        group_xmlid_map = {
            'submitted': 'procurement_foreign_purchase.group_foreign_purchase_manager', # Verify button
            'verified': 'procurement_foreign_purchase.group_foreign_purchase_ceo', # CEO Approve button
            'pending_currency': 'procurement_foreign_purchase.group_foreign_purchase_manager', # Request Currency
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
                summary=_("Foreign RFQ Action Required"),
                note=_("Foreign RFQ (%s) is awaiting your action (State: %s).") % (self.name, next_state)
            )

    def action_request_currency(self):
        self.ensure_one()
        # Get current user's department using sudo to avoid access error
        employee = self.env['hr.employee'].sudo().search([('user_id', '=', self.env.user.id)], limit=1)
        return {
            'type': 'ir.actions.act_window',
            'name': _('Currency Request'),
            'res_model': 'procurement.currency.request',
            'view_mode': 'form',
            'context': {
                'default_rfq_id': self.id,
                'default_supplier_id': self.vendor_id.id,
                'default_proforma_invoice': self.proforma_invoice_no,
                'default_currency_id': self.currency_id.id,
                'default_total_amount_usd': self.amount_total,
                'default_company_id': self.company_id.id,
                'default_department_id': employee.department_id.id if employee and employee.department_id else False,
                'default_bank_id': self.vendor_id.bank_ids[0].bank_id.id if self.vendor_id.bank_ids and self.vendor_id.bank_ids[0].bank_id else False,
                'default_requested_by': self.env.user.id,
                'default_date_request': fields.Datetime.now(),
                'default_exchange_rate': self.exchange_rate,
                'default_proforma_invoice_no': self.proforma_invoice_no,
            },
        }


    def action_reject(self, reason):
        self.ensure_one()
        self.write({
            'state': 'rejected',
            'rejection_reason': reason
        })
        self._notify_next_approver('rejected')

    def action_create_po(self):
        self.ensure_one()
        if self.state != 'approved':
            raise UserError(_("RFQ must be in 'Currency Approved' state to create a Purchase Order."))


        
        po_vals = {
            'partner_id': self.vendor_id.id,
            'origin': self.name,
            'requisition_ref': ", ".join(self.requisition_ids.mapped('name')) if self.requisition_ids else (self.requisition_id.name if self.requisition_id else self.name),
            'foreign_rfq_id': self.id,
            'request_type': 'foreign',
            'date_order': fields.Datetime.now(),
            'currency_id': self.currency_id.id,
            'exchange_rate': self.exchange_rate,
            'order_line': [
                (0, 0, {
                    'product_id': line.product_id.id,
                    'name': line.product_id.display_name,
                    'product_description': line.description,
                    'line_no': line.line_no,
                    'product_qty': line.quantity,
                    'price_unit': line.price_unit_etb,
                    'price_unit_usd': line.price_unit,
                    'date_planned': fields.Datetime.now(),
                    'product_uom_id': line.uom_id.id if line.uom_id else line.product_id.uom_id.id,
                    'analytic_distribution': {str(line.cost_center_id.id): 100} if line.cost_center_id else False,
                })

                for line in self.line_ids
            ],
            'company_id': self.company_id.id,
        }



        po = self.env['purchase.order'].create(po_vals)
        self.write({'state': 'po_created', 'purchase_order_id': po.id})

        return {
            'type': 'ir.actions.act_window',
            'name': _('Purchase Order'),
            'res_model': 'purchase.order',
            'res_id': po.id,
            'view_mode': 'form',
        }

    def action_view_purchase_order(self):
        self.ensure_one()
        if not self.purchase_order_id:
            return False
        return {
            'type': 'ir.actions.act_window',
            'name': _('Purchase Order'),
            'res_model': 'purchase.order',
            'res_id': self.purchase_order_id.id,
            'view_mode': 'form',
        }

    def action_view_currency_requests(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Currency Requests'),
            'res_model': 'procurement.currency.request',
            'view_mode': 'list,form',
            'domain': [('rfq_id', '=', self.id)],
            'context': {'default_rfq_id': self.id},
        }

    def action_cancel(self):
        self.write({'state': 'cancel'})
        self._notify_next_approver('cancel')

    def action_draft(self):
        self.write({'state': 'draft'})
        self._notify_next_approver('draft')

class ForeignRFQLine(models.Model):
    _name = 'foreign.rfq.line'
    _description = 'Foreign RFQ Line'

    rfq_id = fields.Many2one('foreign.rfq', string='RFQ', ondelete='cascade')
    line_no = fields.Integer(string="Line No", compute="_compute_line_no", store=True)
    product_id = fields.Many2one('product.product', string='Product', required=True)
    hs_code = fields.Char(string="HS Code")
    hs_description = fields.Char(string="HS Description")
    description = fields.Char(string='Description')
    cost_center_id = fields.Many2one('account.analytic.account', string='Cost Center')

    quantity = fields.Float(string='Quantity', default=1.0)
    uom_id = fields.Many2one('uom.uom', string='Unit of Measure')
    estimated_cost = fields.Float(string='Estimated Cost', digits='Product Price', readonly=True)
    price_unit = fields.Float(string='Unit Price', digits='Product Price')
    price_subtotal = fields.Float(string='Subtotal', compute='_compute_price_subtotal', store=True)

    # ETB Fields
    price_unit_etb = fields.Float(string='Unit Price (ETB)', compute='_compute_etb_values', store=True)
    price_subtotal_etb = fields.Float(string='Subtotal (ETB)', compute='_compute_etb_values', store=True)

    @api.depends('rfq_id', 'rfq_id.line_ids')
    def _compute_line_no(self):
        for rfq in self.mapped('rfq_id'):
            for index, line in enumerate(rfq.line_ids.sorted('id'), start=1):
                line.line_no = index


    @api.depends('quantity', 'price_unit')
    def _compute_price_subtotal(self):
        for line in self:
            line.price_subtotal = line.quantity * line.price_unit

    @api.depends('price_unit', 'price_subtotal', 'rfq_id.exchange_rate')
    def _compute_etb_values(self):
        for line in self:
            exchange_rate = line.rfq_id.exchange_rate or 1.0
            line.price_unit_etb = line.price_unit * exchange_rate
            line.price_subtotal_etb = line.price_subtotal * exchange_rate

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            self.description = self.product_id.display_name
            self.price_unit = self.product_id.standard_price
            self.uom_id = self.product_id.uom_id.id

class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    foreign_rfq_id = fields.Many2one('foreign.rfq', string='Source RFQ')
    currency_id = fields.Many2one('res.currency', string='Currency', required=True, default=lambda self: self.env.company.currency_id, tracking=True)
    company_currency_id = fields.Many2one('res.currency', string="Company Currency", related='company_id.currency_id', readonly=True)
    currency_id_etb = fields.Many2one(
        'res.currency',
        string="ETB Currency",
        compute="_compute_currency_id_etb"
    )
    exchange_rate = fields.Float(string='Exchange Rate', compute='_compute_exchange_rate', store=True, readonly=False)

    def _compute_currency_id_etb(self):
        etb_currency = self.env['res.currency'].with_context(active_test=False).search([('name', '=', 'ETB')], limit=1)
        for order in self:
            order.currency_id_etb = etb_currency or order.company_id.currency_id

    @api.depends('currency_id', 'date_order', 'company_id')
    def _compute_exchange_rate(self):
        for rec in self:
            if rec.currency_id and rec.company_id:
                rec.exchange_rate = rec.currency_id._get_conversion_rate(
                    rec.currency_id,
                    rec.company_id.currency_id,
                    rec.company_id,
                    rec.date_order or fields.Datetime.now()
                )
            else:
                rec.exchange_rate = 1.0

    amount_total_usd = fields.Monetary(
        string="Total Amount (USD)",
        currency_field="currency_id",
        compute="_compute_totals_foreign",
        store=True
    )
    amount_total_etb = fields.Monetary(
        string="Total Amount (ETB)",
        currency_field="currency_id_etb",
        compute="_compute_totals_foreign",
        store=True
    )
    amount_total_display = fields.Char(
        string="Total (ETB / USD)",
        compute="_compute_totals_foreign",
        store=True
    )

    @api.depends('order_line.price_subtotal_usd', 'order_line.price_subtotal_etb', 'exchange_rate', 'currency_id', 'request_type')
    def _compute_totals_foreign(self):
        for order in self:
            if order.request_type == 'foreign' and order.exchange_rate and order.exchange_rate > 1:
                rate = order.exchange_rate

                # Derive USD and ETB totals directly from lines — the source of truth
                usd_val = sum(order.order_line.mapped('price_subtotal_usd'))
                etb_val = sum(order.order_line.mapped('price_subtotal_etb'))

                # Fallback: if lines have no USD subtotals yet, divide amount_total by rate
                if not usd_val and order.amount_total:
                    usd_val = order.amount_total / rate
                    etb_val = order.amount_total

                order.amount_total_usd = usd_val
                order.amount_total_etb = etb_val
                curr_symbol = order.currency_id.symbol or order.currency_id.name or '$'
                curr_name = order.currency_id.name or 'USD'
                order.amount_total_display = f"Br {etb_val:,.2f} ({curr_symbol}{usd_val:,.2f} {curr_name})"
            else:
                order.amount_total_usd = order.amount_total
                order.amount_total_etb = order.amount_total
                curr_symbol = order.currency_id.symbol or 'Br'
                order.amount_total_display = f"{curr_symbol} {order.amount_total:,.2f}"






class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    line_no = fields.Integer(string="Line No", compute="_compute_line_no", store=True)
    product_description = fields.Char(
        string="Product Description",
        compute="_compute_product_description",
        store=True, readonly=False
    )

    # User enters this in USD (PO currency)
    price_unit_usd = fields.Float(
        string="Unit Price (USD)",
        digits='Product Price',
        related='price_unit',  # just mirrors price_unit, no need to store separately
        store=True,
        readonly=False
    )

    # Computed: USD × exchange_rate = ETB
    price_unit_etb = fields.Float(
        string="Unit Price (ETB)",
        digits='Product Price',
        compute="_compute_etb_fields",
        store=True
    )

    # Computed: qty × price_unit (in USD)
    price_subtotal_usd = fields.Float(
        string="Subtotal (USD)",
        compute="_compute_etb_fields",
        store=True
    )

    # Computed: qty × price_unit_etb (in ETB)
    price_subtotal_etb = fields.Float(
        string="Subtotal (ETB)",
        compute="_compute_etb_fields",
        store=True
    )

    @api.depends('price_unit', 'product_qty', 'order_id.exchange_rate')
    def _compute_etb_fields(self):
        for line in self:
            rate = line.order_id.exchange_rate or 1.0
            line.price_unit_etb = line.price_unit * rate
            line.price_subtotal_usd = line.product_qty * line.price_unit
            line.price_subtotal_etb = line.product_qty * line.price_unit_etb

    @api.depends('order_id', 'order_id.order_line')
    def _compute_line_no(self):
        for order in self.mapped('order_id'):
            for index, line in enumerate(order.order_line.sorted('id'), start=1):
                line.line_no = index

    @api.depends('product_id')
    def _compute_product_description(self):
        for line in self:
            if line.product_id:
                line.product_description = line.product_id.display_name


