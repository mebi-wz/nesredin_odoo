from odoo import models, fields, api, tools, _
from odoo.exceptions import ValidationError, UserError


class PurchaseOrderForeignOps(models.Model):
    _inherit = 'purchase.order'

    # ============================================================
    # ORDERING - Import Permit
    # ============================================================
    import_permit_number = fields.Char(string="Import Permit Number", tracking=True)
    import_permit_date = fields.Date(string="Import Permit Date", tracking=True)
    import_permit_approved = fields.Boolean(string="Import Permit Approved", tracking=True)
    lpco_number = fields.Char(string="LPCO Number", tracking=True)
    
    import_permit_attachment = fields.Many2many(
        'ir.attachment', 'po_import_permit_attach_rel',
        string="Import Permit Attachments"
    )

    # ============================================================
    # ORDERING - Insurance
    # ============================================================
    insurance_policy_no = fields.Char(string="Insurance Policy No", tracking=True)
    insurer_name = fields.Char(string="Insurer Name", tracking=True)
    insurance_date = fields.Date(string="Insurance Date", tracking=True)
    insurance_premium_cost = fields.Float(string="Insurance Premium Cost", tracking=True)
    
    insurance_attachment = fields.Many2many(
        'ir.attachment', 'po_insurance_attach_rel',
        string="Insurance Attachments"
    )

    # ============================================================
    # ORDERING - LC (Letter of Credit) — separate model
    # ============================================================
    lc_ids = fields.One2many('foreign.lc', 'purchase_order_id', string='Letters of Credit')

    def action_view_lcs(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Letters of Credit'),
            'res_model': 'foreign.lc',
            'view_mode': 'list,form',
            'domain': [('purchase_order_id', '=', self.id)],
            'context': {'default_purchase_order_id': self.id},
        }

    def action_create_lc(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Create Payment Instrument'),
            'res_model': 'foreign.lc',
            'view_mode': 'form',
            'context': {
                'default_purchase_order_id': self.id,
                'default_amount': self.amount_total,
            },
        }

    def button_confirm(self):
        for order in self:
            if order.request_type == 'foreign' and not order.lc_ids:
                raise UserError(_("You cannot confirm a foreign Purchase Order without creating a Payment Instrument (LC, TT, or CAD) first."))
        return super().button_confirm()


    lc_count = fields.Integer(compute='_compute_lc_count', store=False)

    @api.depends('lc_ids')
    def _compute_lc_count(self):
        for rec in self:
            rec.lc_count = len(rec.lc_ids)

    landed_cost_count = fields.Integer(compute='_compute_landed_cost_count', store=False)

    @api.depends('picking_ids')
    def _compute_landed_cost_count(self):
        for rec in self:
            rec.landed_cost_count = self.env['stock.landed.cost'].sudo().search_count([('picking_ids', 'in', rec.picking_ids.ids)])

    def action_view_landed_costs(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Landed Costs'),
            'res_model': 'stock.landed.cost',
            'view_mode': 'list,form',
            'domain': [('picking_ids', 'in', self.picking_ids.ids)],
        }
    # ============================================================
    total_usd = fields.Float(string="Total USD", tracking=True)
    margin = fields.Float(string="Margin (%)", tracking=True)
    deposit_amount = fields.Float(string="Deposit Amount", tracking=True)
    deposit_date = fields.Date(string="Deposit Date", tracking=True)
    bank_service_charge = fields.Float(string="Bank Service Charge", tracking=True)

    margin_line_ids = fields.One2many(
        'purchase.import.margin',
        'import_id',
        string="Margins"
    )

    has_margin_lines = fields.Boolean(compute='_compute_has_margin_lines', store=False)
    has_standard_bill = fields.Boolean(compute='_compute_has_standard_bill', store=False)

    @api.depends('margin_line_ids')
    def _compute_has_margin_lines(self):
        for order in self:
            order.has_margin_lines = bool(order.margin_line_ids)

    @api.depends('invoice_ids', 'margin_line_ids.move_id')
    def _compute_has_standard_bill(self):
        for order in self:
            margin_moves = order.margin_line_ids.mapped('move_id')
            standard_invoices = order.invoice_ids.filtered(lambda inv: inv not in margin_moves and inv.state != 'cancel')
            order.has_standard_bill = bool(standard_invoices)

    # ============================================================
    # SHIPMENT
    # ============================================================
    # Shipment Document - Left Column
    first_shipment_amount = fields.Float(string="1st Shipment Amount", tracking=True)
    is_shipment_partial = fields.Boolean(string="Is Shipment Partial", tracking=True)
    est_ship_date = fields.Date(string="Est Ship Date", tracking=True)
    est_prod_comp_date = fields.Date(string="Est Prod Comp Date", tracking=True)
    scan_copy_received_date = fields.Date(string="Scan Copy Recived Date", tracking=True)
    ship_doc_org_received_date = fields.Date(string="Ship Doc Org Received Date", tracking=True)
    org_doc_sent_supp_bank = fields.Date(string="Org Doc Sent from Supp to App Bank", tracking=True)

    # Shipment Document - Right Column
    org_doc_sent_courier = fields.Date(string="Org Doc Sent from Supp to App Bank By Courier", tracking=True)
    courier_tracking_no = fields.Char(string="Courier Tracking No", tracking=True)
    org_doc_received_bank = fields.Date(string="Org Doc Received by App Bank", tracking=True)
    shipment_discrepancy = fields.Selection([
        ('yes', 'Yes'),
        ('no', 'No'),
    ], string="Discrepancy?", default='no', tracking=True)
    org_doc_collected_bank = fields.Date(string="Org Doc Collected from App Bank", tracking=True)
    shipment_exchange_rate = fields.Float(string="Exchange Rate", digits=(16, 4), tracking=True)
    lc_settlement = fields.Float(string="LC Settlement", tracking=True)
    settlement_date = fields.Date(string="Settlement Date", tracking=True)
    org_doc_handed_fin = fields.Date(string="Org Doc Handed to Fin", tracking=True)
    supplier_payment_date = fields.Date(string="Supplier Payment Date", tracking=True)

    # Deliver Order
    is_do = fields.Boolean(string="IS it DO", tracking=True)

    # Shipping Reconciliations
    shipping_reconciliation_ids = fields.One2many(
        'purchase.shipping.reconciliation',
        'purchase_order_id',
        string="Shipping Reconcilations"
    )

    margin_bill_status = fields.Selection([
        ('no', 'Nothing to Bill'),
        ('to_bill', 'Waiting for Margin Bill'),
        ('partial', 'Partially Billed'),
        ('full', 'Fully Billed'),
    ], string="Margin Bill Status", compute="_compute_margin_bill_status", store=True)

    @api.depends('margin_line_ids.move_id', 'margin_line_ids.margin_percent')
    def _compute_margin_bill_status(self):
        for rec in self:
            if not rec.margin_line_ids:
                rec.margin_bill_status = 'no'
                continue
            
            billed_lines = rec.margin_line_ids.filtered(lambda l: l.move_id)
            if not billed_lines:
                rec.margin_bill_status = 'to_bill'
                continue

            total_billed_percent = sum(billed_lines.mapped('margin_percent'))
            
            if total_billed_percent < 99.9:
                rec.margin_bill_status = 'partial'
            else:
                rec.margin_bill_status = 'full'

    def _compute_invoice(self):
        super()._compute_invoice()
        for order in self:
            # Find bills linked via po_import_id that aren't already included (e.g., margin bills)
            extra_invoices = self.env['account.move'].search([
                ('po_import_id', '=', order.id),
                ('move_type', 'in', ('in_invoice', 'in_refund')),
                ('state', '!=', 'cancel'),
                ('id', 'not in', order.invoice_ids.ids)
            ])
            if extra_invoices:
                order.invoice_ids |= extra_invoices
                order.invoice_count = len(order.invoice_ids)

    @api.depends('order_line.qty_to_invoice', 'margin_bill_status', 'margin_line_ids', 'request_type', 'state', 'margin_line_ids.move_id')
    def _get_invoiced(self):
        super()._get_invoiced()
        for order in self:
            if order.request_type == 'foreign' and order.margin_line_ids:
                # If margin billing is used, it replaces standard product billing.
                # We set status based ONLY on margin billing progress.
                if order.state in ('purchase', 'done'):
                    if order.margin_bill_status == 'full':
                        order.invoice_status = 'invoiced'
                    else:
                        order.invoice_status = 'to invoice'

    def action_create_invoice(self, attachment_ids=False):
        """Override to prevent standard billing for foreign POs using margins"""
        for order in self:
            if order.request_type == 'foreign' and order.margin_line_ids:
                raise UserError(_(
                    "Standard product billing is disabled for Foreign Purchase Orders with margins.\n"
                    "Please use the 'Manage Margins' button to create vendor bills for each margin installment."
                ))
        return super().action_create_invoice(attachment_ids=attachment_ids)

    def action_open_margin_modal(self):
        self.ensure_one()
        return {
            'name': _('Manage Margins'),
            'type': 'ir.actions.act_window',
            'res_model': 'purchase.order',
            'res_id': self.id,
            'view_mode': 'form',
            'view_id': self.env.ref('procurement_foreign_operations.view_purchase_order_margin_modal_form').id,
            'target': 'new',
            'context': {**self.env.context, 'dialog_size': 'extra-large'},
        }

    def _prepare_invoice(self):
        invoice_vals = super()._prepare_invoice()
        if self.request_type == 'foreign':
            # Force the bill currency to ETB (ensure it is active in the database)
            etb_currency = self.env['res.currency'].with_context(active_test=False).search([('name', '=', 'ETB')], limit=1)
            if etb_currency:
                if not etb_currency.active:
                    etb_currency.sudo().write({'active': True})
                invoice_vals['currency_id'] = etb_currency.id
            else:
                invoice_vals['currency_id'] = self.company_id.currency_id.id
        return invoice_vals

    def action_draft_landed_cost(self):
        self.ensure_one()

        # Check that customs_product_cost is set for all PO lines with stockable/consumable products
        for po_line in self.order_line:
            if po_line.product_id.type in ('product', 'consu'):
                if not po_line.customs_product_cost or po_line.customs_product_cost <= 0.0:
                    raise ValidationError(_(
                        "Customs Product Cost is required for product '%s' before you can draft a Landed Cost."
                    ) % po_line.product_id.display_name)

        if self.landed_cost_count > 0:
            raise ValidationError(_('A landed cost has already been drafted for this Purchase Order. Only one landed cost is allowed.'))
        
        # 1. Find the completed Receipt
        receipts = self.picking_ids.filtered(lambda p: p.state == 'done' and p.picking_type_code == 'incoming')
        if not receipts:
            raise ValidationError(_('There are no validated receipts (GRN) for this Purchase Order yet. You can only apply landed costs after receiving the goods.'))
            
        # 2. Gather Vendor Bills generated by Foreign Payment Requests
        payment_requests = self.payment_request_ids.filtered(lambda r: r.vendor_bill_id)
        if not payment_requests:
            raise ValidationError(_('No vendor bills have been generated from Foreign Payment Requests for this PO.'))

        vendor_bills = payment_requests.mapped('vendor_bill_id')
            
        # 3. Create the Landed Cost record linked directly to these bills
        journal = self.env['account.journal'].search([
            ('type', '=', 'general'), 
            ('company_id', '=', self.company_id.id)
        ], limit=1)
        if not journal:
            raise ValidationError(_("Please configure at least one General Journal for the company to process Landed Costs."))

        landed_cost_vals = {
            'picking_ids': [(6, 0, receipts.ids)],
            'vendor_bill_id': vendor_bills[0].id if len(vendor_bills) == 1 else False,
            'account_journal_id': journal.id,
        }
        
        landed_cost = self.env['stock.landed.cost'].sudo().create(landed_cost_vals)
        
        # Odoo 17+ Landed Cost behavior often requires lines to be pulled from the bills manually or populated via an action.
        # Let's populate the cost lines directly based on the payment request lines to be robust:
        cost_lines = []
        for pr in payment_requests:
            bill = pr.vendor_bill_id
            for line in pr.line_ids:
                if line.product_id and line.product_id.landed_cost_ok:
                    bill_line = False
                    if bill:
                        bill_line = bill.invoice_line_ids.filtered(lambda l: l.product_id == line.product_id)[:1]
                    
                    if bill_line and bill_line.account_id:
                        account_id = bill_line.account_id.id
                    else:
                        account_id = line.product_id.property_account_expense_id.id or line.product_id.categ_id.property_account_expense_categ_id.id
                    
                    cost_lines.append((0, 0, {
                        'product_id': line.product_id.id,
                        'name': line.description or line.product_id.name,
                        'account_id': account_id,
                        'split_method': 'by_customs_amount',
                        'price_unit': line.amount,
                    }))
                    
        if cost_lines:
             landed_cost.write({'cost_lines': cost_lines})
        else:
            raise ValidationError(_("None of the products in the Payment Requests are configured as Landed Cost products. Please check the 'Is a Landed Cost' setting on the products."))


        return {
            'name': _('Landed Cost'),
            'type': 'ir.actions.act_window',
            'res_model': 'stock.landed.cost',
            'res_id': landed_cost.id,
            'view_mode': 'form',
            'target': 'current',
        }

    # Legacy shipment fields (kept for compatibility)
    vessel_name = fields.Char(string="Vessel / Flight", tracking=True)
    bl_awb_number = fields.Char(string="BL / AWB Number", tracking=True)
    shipping_line = fields.Char(string="Shipping Line / Airline", tracking=True)
    container_number = fields.Char(string="Container No", tracking=True)
    container_type = fields.Selection([
        ('20ft', '20ft'),
        ('40ft', '40ft'),
        ('40hc', '40ft HC'),
        ('reefer', 'Reefer'),
        ('other', 'Other'),
    ], string="Container Type", tracking=True)
    etd = fields.Date(string="ETD (Estimated Departure)", tracking=True)
    eta = fields.Date(string="ETA (Estimated Arrival)", tracking=True)
    actual_departure_date = fields.Date(string="Actual Departure", tracking=True)
    actual_arrival_date = fields.Date(string="Actual Arrival", tracking=True)
    port_of_loading_id = fields.Many2one('purchase.port.loading', string="Port of Loading", domain="[('port_type', '=', 'loading')]", tracking=True)
    port_of_discharge_id = fields.Many2one('purchase.port.loading', string="Port of Discharge", domain="[('port_type', '=', 'discharge')]", tracking=True)
    shipment_attachment = fields.Many2many(
        'ir.attachment', 'po_shipment_attach_rel',
        string="Shipment Documents"
    )


    # ============================================================
    # GOODS CLEARANCE
    # ============================================================
    # Freight Payment - Left Column
    mod_of_shipment = fields.Char(string="Mod Of Shipment", tracking=True)
    arrival_date_fin_dest = fields.Date(string="Arrival Date to Fin Dest", tracking=True)
    freight_paid_date = fields.Date(string="Freight Paid Date", tracking=True)
    freight_settlement = fields.Float(string="Freight Settlement", tracking=True)
    container_deposit = fields.Float(string="Container Deposit", tracking=True)
    container_status = fields.Selection([
        ('returned', 'Returned'),
        ('not_returned', 'Not Returned'),
    ], string="Container Status", default='not_returned', tracking=True)
    ship_doc_settlement = fields.Date(string="Ship Doc & Settlement", tracking=True)
    declaration_number = fields.Char(string="Declaration Number", tracking=True)
    custom_duty_tax = fields.Float(string="Custom Duty Tax", tracking=True)
    withholding_tax = fields.Float(string="Withholding Tax", tracking=True)
    tax_paid_date = fields.Date(string="Tax Paid Date", tracking=True)
    accep_duty_tax = fields.Boolean(string="Accep of the Duty Tax", tracking=True)
    additional_duty_tax = fields.Float(string="Additional Duty Tax", tracking=True)
    actual_duty_tax_paid = fields.Float(string="Actual Duty Tax Paid", tracking=True)

    # Additional Info - Right Column
    release_permit_fda = fields.Date(string="Release Permit FDA", tracking=True)
    release_permit = fields.Date(string="Release Permit", tracking=True)
    storage_cost = fields.Float(string="Storage Cost", tracking=True)
    demurrage_cost = fields.Float(string="Demurrage Cost", tracking=True)
    local_transport_cost = fields.Float(string="Local Transport Cost", tracking=True)
    loading_unloading = fields.Float(string="Loading & Unloading", tracking=True)
    delivery_to_warehouse = fields.Date(string="Delivery to Warehouse", tracking=True)

    # Legacy clearance fields (kept for compatibility)
    customs_office = fields.Char(string="Customs Office", tracking=True)
    customs_duty = fields.Float(string="Customs Duty Amount", tracking=True)
    customs_tax = fields.Float(string="Tax Amount", tracking=True)
    customs_total = fields.Float(string="Total Duty & Tax", compute='_compute_customs_total', store=True, tracking=True)
    clearance_date = fields.Date(string="Clearance Date", tracking=True)
    clearing_agent = fields.Many2one('res.partner', string="Clearing Agent", tracking=True)
    clearance_attachment = fields.Many2many(
        'ir.attachment', 'po_clearance_attach_rel',
        string="Clearance Documents"
    )


    @api.depends('customs_duty', 'customs_tax')
    def _compute_customs_total(self):
        for rec in self:
            rec.customs_total = rec.customs_duty + rec.customs_tax

    # ============================================================
    # POST CLEARANCE
    # ============================================================
    # Inventory - Left Column
    packing_list = fields.Char(string="Packing List", tracking=True)
    warehouse_arrival_date = fields.Date(string="Warehouse Arrival Date", tracking=True)
    grn_rec = fields.Char(string="GRN Rec", tracking=True)
    rec_discrepancy = fields.Boolean(string="Rec Discrepancy", tracking=True)

    # Additional Info - Right Column
    grn_to_finance = fields.Date(string="GRN to Finance", tracking=True)
    declaration_receive = fields.Date(string="Declaration Receive", tracking=True)
    delinquent_sett_date = fields.Date(string="Delinquent Sett Date", tracking=True)
    transitor_payment = fields.Float(string="Transitor Payment", tracking=True)
    pc_container_deposit = fields.Date(string="Container Deposit", tracking=True)
    transitor_payment_done = fields.Date(string="Transitor Payment Done", tracking=True)

    # Legacy post clearance fields (kept for compatibility)
    inspection_date = fields.Date(string="Inspection Date", tracking=True)
    quality_status = fields.Selection([
        ('pending', 'Pending'),
        ('passed', 'Passed'),
        ('failed', 'Failed'),
        ('partial', 'Partially Passed'),
    ], string="Quality Status", tracking=True)
    warehouse_receipt_no = fields.Char(string="Warehouse Receipt No", tracking=True)
    delivery_date = fields.Date(string="Delivery Date", tracking=True)
    post_clearance_remarks = fields.Text(string="Remarks", tracking=True)
    post_clearance_attachment = fields.Many2many(
        'ir.attachment', 'po_post_clearance_attach_rel',
        string="Post Clearance Documents"
    )


    # ============================================================
    # PAYMENT REQUESTS
    # ============================================================
    payment_request_ids = fields.One2many('foreign.payment.request', 'purchase_order_id', string='Payment Requests')
    payment_request_count = fields.Integer(compute='_compute_payment_request_count')

    @api.depends('payment_request_ids')
    def _compute_payment_request_count(self):
        for rec in self:
            rec.payment_request_count = len(rec.payment_request_ids)

    def action_view_payment_requests(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Payment Requests'),
            'res_model': 'foreign.payment.request',
            'view_mode': 'list,form',
            'domain': [('purchase_order_id', '=', self.id)],
            'context': {'default_purchase_order_id': self.id},
        }

    def action_create_payment_request(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Create Payment Request'),
            'res_model': 'foreign.payment.request',
            'view_mode': 'form',
            'context': {
                'default_purchase_order_id': self.id,
            },
        }

class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    exchange_rate_related = fields.Float(related='order_id.exchange_rate', string="Exchange Rate", readonly=True)

    @api.depends('order_id.margin_line_ids.move_id.state', 'order_id.margin_line_ids.margin_percent')
    def _compute_qty_invoiced(self):
        super()._compute_qty_invoiced()
        for line in self:
            order = line.order_id
            if order.request_type == 'foreign' and order.margin_line_ids:
                billed_margins = order.margin_line_ids.filtered(lambda m: m.move_id and m.move_id.state != 'cancel')
                total_billed_percent = sum(billed_margins.mapped('margin_percent'))
                
                line.qty_invoiced = line.product_uom_id.round(line.product_qty * (total_billed_percent / 100.0))
                if line.order_id.state in ('purchase', 'done'):
                    line.qty_to_invoice = line.product_uom_id.round(line.product_qty - line.qty_invoiced)
                else:
                    line.qty_to_invoice = 0

    def _prepare_account_move_line(self, move=False):
        res = super()._prepare_account_move_line(move)
        if self.order_id.request_type == 'foreign':
            # Prioritize price_unit_etb when billing foreign POs
            res['price_unit'] = self.price_unit_etb
        return res

    def _get_stock_move_price_unit(self):
        self.ensure_one()
        order = self.order_id
        if order.request_type == 'foreign' and order.exchange_rate:
            price_unit = self.price_unit_discounted
            price_unit_prec = self.env['decimal.precision'].precision_get('Product Price')
            if self.tax_ids:
                qty = self.product_qty or 1
                price_unit = self.tax_ids.compute_all(
                    price_unit,
                    currency=self.order_id.currency_id,
                    quantity=qty,
                    product=self.product_id,
                    partner=self.order_id.partner_id,
                    rounding_method="round_globally",
                )['total_void']
                price_unit = price_unit / qty
            if self.product_uom_id.id != self.product_id.uom_id.id:
                price_unit /= self.product_uom_id.factor
                price_unit *= self.product_id.uom_id.factor
            # Use custom exchange rate
            price_unit = price_unit * order.exchange_rate
            return tools.float_round(price_unit, precision_digits=price_unit_prec)
        return super()._get_stock_move_price_unit()

class PurchaseImportMargin(models.Model):
    _name = 'purchase.import.margin'
    _description = 'Purchase Import Margin'

    import_id = fields.Many2one(
        'purchase.order',
        string="Import Reference",
        required=True,
        ondelete='cascade'
    )

    margin_order = fields.Selection([
        ('first_margin', 'First Margin'),
        ('partial_margin', 'Partial Margin'),
        ('last_margin', 'Last Margin'),
    ], string="Margin Order")
    margin_percent = fields.Float(string="Margin %")
    calculation = fields.Selection([
        ('post_full', 'Post Full Amount'),
        ('post_difference', 'Post the Difference'),
        ('partial', 'Partial Amount'),
    ], string="Calculation")
    usd_amount = fields.Float(string="USD")
    exchange_rate = fields.Float(string="Exchange Rate", compute="_compute_exchange_rate", store=True, readonly=False)

    @api.depends('import_id.exchange_rate')
    def _compute_exchange_rate(self):
        for rec in self:
            if rec.import_id:
                rec.exchange_rate = rec.import_id.exchange_rate or 1.0
            else:
                rec.exchange_rate = 1.0
    etb_amount = fields.Float(
        string="ETB",
        compute="_compute_etb",
        store=True
    )
    account_id = fields.Many2one('account.account', string="Account")
    lc_reference = fields.Many2one(
        'account.account', 
        string="LC",
        domain="[('account_type', 'in', ('asset_cash', 'asset_receivable'))]"
    )
    move_id = fields.Many2one('account.move', string="Vendor Bill", readonly=True)
    move_reference = fields.Char(string="Move")
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        related='import_id.company_id',
        store=True,
        readonly=True
    )

    @api.depends('usd_amount', 'exchange_rate')
    def _compute_etb(self):
        for rec in self:
            rec.etb_amount = rec.usd_amount * rec.exchange_rate

    @api.constrains('usd_amount', 'margin_percent', 'import_id')
    def _check_total_margin_amount(self):
        for rec in self:
            po = rec.import_id
            if not po:
                continue
            
            # 1. Validate Total Percentage
            total_percent = sum(po.margin_line_ids.mapped('margin_percent'))
            if total_percent > 100.01:
                 raise ValidationError(_("The total margin percentage (%.2f%%) cannot exceed 100%%.") % total_percent)
            
            # 2. Validate Total Amount against PO Total
            if po.amount_total:
                total_usd = sum(po.margin_line_ids.mapped('usd_amount'))
                if total_usd > po.amount_total + 0.01:
                    raise ValidationError(_("The total margin amount (%.2f USD) cannot exceed the PO total amount (%.2f USD).") % (total_usd, po.amount_total))

    @api.onchange('margin_percent', 'calculation')
    def _calculate_margin(self):
        for rec in self:
            po = rec.import_id
            if po and po.amount_total:
                # Get the exchange rate from the PO and set it on the line
                rec.exchange_rate = po.exchange_rate or 1.0
                
                if rec.calculation == 'post_full':
                    rec.margin_percent = 100.0
                    rec.usd_amount = po.amount_total
                elif rec.calculation == 'post_difference':
                    other_margins = po.margin_line_ids - rec
                    posted_usd = sum(other_margins.mapped('usd_amount'))
                    rec.usd_amount = max(0.0, po.amount_total - posted_usd)
                    rec.margin_percent = (rec.usd_amount / po.amount_total) * 100.0 if po.amount_total else 0.0
                elif rec.calculation == 'partial':
                    if rec.margin_percent == 0.0:
                        rec.margin_percent = 50.0
                    rec.usd_amount = (po.amount_total * rec.margin_percent) / 100.0
                else:
                    rec.usd_amount = (po.amount_total * rec.margin_percent) / 100.0
    def action_create_bill(self):
        for rec in self:
            if rec.move_reference:
                continue
            
            # Determine basic bill values
            partner_id = rec.import_id.partner_id.id
            etb_currency = rec.env['res.currency'].with_context(active_test=False).search([('name', '=', 'ETB')], limit=1)
            if etb_currency:
                if not etb_currency.active:
                    etb_currency.sudo().write({'active': True})
                currency_id = etb_currency.id
            else:
                currency_id = rec.import_id.company_id.currency_id.id

            move_vals = {
                'move_type': 'in_invoice',
                'partner_id': partner_id,
                'currency_id': currency_id,
                'po_import_id': rec.import_id.id,
                'invoice_date': fields.Date.today(),
                'invoice_line_ids': [(0, 0, {
                    'name': f"Margin: {rec.import_id.name}",
                    'account_id': rec.account_id.id if rec.account_id else False,
                    'price_unit': rec.etb_amount,
                    'quantity': 1,
                })],
            }
            move = self.env['account.move'].create(move_vals)
            # Link the reference
            rec.move_id = move.id
            rec.move_reference = move.name if move.name != '/' else str(move.id)

            # Trigger recomputes on the PO to ensure smart buttons and status are updated
            rec.import_id.modified(['invoice_ids', 'invoice_count', 'invoice_status', 'margin_bill_status'])
            rec.import_id.order_line.modified(['qty_invoiced', 'qty_to_invoice'])
            rec.import_id._compute_invoice()
            rec.import_id._get_invoiced()
            rec.import_id._compute_margin_bill_status()
            
            return {
                'type': 'ir.actions.act_window',
                'name': _('Vendor Bill'),
                'res_model': 'account.move',
                'view_mode': 'form',
                'res_id': move.id,
                'target': 'current',
            }

    def unlink(self):
        for rec in self:
            if rec.move_reference:
                raise ValidationError(_('You cannot delete a margin line after a bill has been created.'))
        return super().unlink()


class PurchaseShippingReconciliation(models.Model):
    _name = 'purchase.shipping.reconciliation'
    _description = 'Shipping Reconciliation'
    _order = 'step_order'

    purchase_order_id = fields.Many2one('purchase.order', string='Purchase Order', required=True, ondelete='cascade')
    step_order = fields.Integer(string="Step Order", default=1)
    name = fields.Char(string="Name", required=True)
    state = fields.Selection([
        ('right', 'Right'),
        ('wrong', 'Wrong'),
    ], string="State", default='right')
    remark = fields.Text(string="Remark")
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        related='purchase_order_id.company_id',
        store=True,
        readonly=True
    )

class ForeignRFQOperations(models.Model):
    _inherit = 'foreign.rfq'

    # Unified fields for consolidated cost tracking
    cost_line_ids = fields.One2many(
        'foreign.rfq.cost.line',
        'rfq_id',
        string="Cost Lines"
    )

    # Link to all POs created from this RFQ (for robust cost aggregation)
    all_po_ids = fields.One2many(
        'purchase.order',
        'foreign_rfq_id',
        string="All Linked POs"
    )

    inventory_amount_usd = fields.Float(
        string="Inventory Amount USD",
        compute="_compute_standard_costs",
        store=True,
        help="Inventory value from RFQ lines (pre-PO) or PO lines (post-PO)"
    )
    inventory_amount_etb = fields.Float(
        string="Inventory Amount ETB",
        compute="_compute_standard_costs",
        store=True,
        help="Inventory value in ETB from RFQ lines (pre-PO) or PO lines (post-PO)"
    )
    total_landed_cost = fields.Float(
        string="Total Landed Cost",
        compute="_compute_standard_costs",
        store=True,
        help="Sum of manual cost lines OR actual bill lines (if PO exists)"
    )
    total_rfq_cost = fields.Float(
        string="Total Cost",
        compute="_compute_standard_costs",
        store=True,
        help="Inventory ETB + Total Landed Cost"
    )
    coefficient = fields.Float(
        string="Coefficient",
        compute="_compute_standard_costs",
        store=True,
        help="Total Cost / Inventory Amount ETB"
    )

    @api.depends('line_ids.price_subtotal', 'line_ids.price_subtotal_etb', 'cost_line_ids.amount',
                 'all_po_ids.order_line.price_subtotal', 
                 'all_po_ids.payment_request_ids.line_ids.amount')
    def _compute_standard_costs(self):
        for rec in self:
            # 1. Inventory Logic: Post-PO data is more authoritative
            pos = rec.all_po_ids or rec.purchase_order_id
            if pos:
                inv_usd = sum(pos.mapped('order_line.price_subtotal_usd'))
                inv_etb = sum(pos.mapped('order_line.price_subtotal'))
            else:
                inv_usd = sum(rec.line_ids.mapped('price_subtotal'))
                inv_etb = sum(rec.line_ids.mapped('price_subtotal_etb'))

            # 2. Landed Cost Logic
            manual_landed = sum(rec.cost_line_ids.mapped('amount'))
            
            actual_landed = 0.0
            if pos:
                pay_requests = pos.mapped('payment_request_ids')
                for pr in pay_requests:
                    for line in pr.line_ids:
                        if line.product_id.landed_cost_ok:
                            actual_landed += line.amount * pr.exchange_rate
            
            # Prefer actuals if they exist, otherwise use manual estimates
            rec.total_landed_cost = actual_landed if actual_landed > 0 else manual_landed
            
            rec.inventory_amount_usd = inv_usd
            rec.inventory_amount_etb = inv_etb
            rec.total_rfq_cost = inv_etb + rec.total_landed_cost
            rec.coefficient = rec.total_rfq_cost / inv_etb if inv_etb else 0.0

    def action_fetch_actual_costs(self):
        self.ensure_one()
        pos = self.all_po_ids or self.purchase_order_id
        if not pos:
            return
        
        # Gather bill lines that are landed costs
        new_lines = []
        pay_requests = pos.mapped('payment_request_ids')
        for pr in pay_requests:
            for line in pr.line_ids:
                if line.product_id.landed_cost_ok:
                    new_lines.append((0, 0, {
                        'product_id': line.product_id.id,
                        'amount': line.amount * pr.exchange_rate
                    }))
        
        if new_lines:
            # Clear manual lines and populate with actuals
            self.cost_line_ids.unlink()
            self.write({'cost_line_ids': new_lines})

class ForeignRFQCostLine(models.Model):
    _name = 'foreign.rfq.cost.line'
    _description = 'Foreign RFQ Cost Line'

    rfq_id = fields.Many2one('foreign.rfq', string='RFQ', ondelete='cascade')
    product_id = fields.Many2one(
        'product.product', 
        string='Cost Type', 
        required=True,
        domain="[('landed_cost_ok', '=', True)]"
    )
    amount = fields.Float(string='Amount', required=True)
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        related='rfq_id.company_id',
        store=True,
        readonly=True
    )

class AccountMove(models.Model):
    _inherit = 'account.move'

    po_import_id = fields.Many2one('purchase.order', string="PO Import Reference", index=True)


class StockLandedCostLines(models.Model):
    _inherit = 'stock.landed.cost.lines'

    split_method = fields.Selection(
        selection_add=[('by_customs_amount', 'By Customs Amount')],
        ondelete={'by_customs_amount': 'cascade'}
    )


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    split_method_landed_cost = fields.Selection(
        selection_add=[('by_customs_amount', 'By Customs Amount')],
        ondelete={'by_customs_amount': 'set null'}
    )


class StockLandedCostSummary(models.Model):
    _name = 'stock.landed.cost.summary'
    _description = 'Landed Cost Product Summary'

    cost_id = fields.Many2one('stock.landed.cost', string='Landed Cost', ondelete='cascade')
    product_id = fields.Many2one('product.product', string='Product', readonly=True)
    quantity = fields.Float(string='Quantity', readonly=True)
    former_cost = fields.Float(string='Original Value', readonly=True)
    customs_cost_value = fields.Float(string='Customs Cost Value', readonly=True)
    allocated_cost = fields.Float(string='Allocated Landed Cost', readonly=True)
    new_cost = fields.Float(string='New Value', compute='_compute_new_cost', store=True)
    unit_cost = fields.Float(string='Unit Cost', compute='_compute_unit_cost', store=True)
    proportion = fields.Float(string='Proportion', readonly=True)
    currency_id = fields.Many2one('res.currency', related='cost_id.currency_id')

    @api.depends('former_cost', 'allocated_cost')
    def _compute_new_cost(self):
        for rec in self:
            rec.new_cost = rec.former_cost + rec.allocated_cost

    @api.depends('new_cost', 'quantity')
    def _compute_unit_cost(self):
        for rec in self:
            if rec.quantity:
                rec.unit_cost = rec.new_cost / rec.quantity
            else:
                rec.unit_cost = 0.0


class StockLandedCost(models.Model):
    _inherit = 'stock.landed.cost'

    summary_line_ids = fields.One2many(
        'stock.landed.cost.summary',
        'cost_id',
        string="Product Summaries",
        copy=False
    )

    def compute_landed_cost(self):
        # Call super first to let standard Odoo compute for its standard split methods
        super().compute_landed_cost()
        
        # Now, recalculate only the cost lines that use 'by_customs_amount'
        for cost in self:
            customs_lines = cost.cost_lines.filtered(lambda l: l.split_method == 'by_customs_amount')
            if not customs_lines:
                continue
            
            AdjustementLines = self.env['stock.valuation.adjustment.lines']
            valuation_lines = cost.valuation_adjustment_lines
            
            rounding = cost.currency_id.rounding
            
            # Calculate total customs amount for all valuation lines
            total_customs = 0.0
            for valuation in valuation_lines:
                move = valuation.move_id
                if move and move.purchase_line_id:
                    total_customs += move.purchase_line_id.customs_product_cost * valuation.quantity
            
            towrite_dict = {}
            for line in customs_lines:
                value_split = 0.0
                # Filter valuation adjustments for this specific cost line
                line_valuations = valuation_lines.filtered(lambda v: v.cost_line_id == line)
                total_line = len(line_valuations)
                
                for valuation in line_valuations:
                    value = 0.0
                    move = valuation.move_id
                    customs_amt = (move.purchase_line_id.customs_product_cost * valuation.quantity) if (move and move.purchase_line_id) else 0.0
                    
                    if total_customs > 0.0:
                        per_unit = line.price_unit / total_customs
                        value = customs_amt * per_unit
                    else:
                        # Fallback to equal split if total customs is 0
                        if total_line > 0:
                            value = line.price_unit / total_line
                        else:
                            value = 0.0
                            
                    if rounding:
                        value = tools.float_round(value, precision_rounding=rounding, rounding_method='HALF-UP')
                        value_split += value
                        
                    towrite_dict[valuation.id] = value
                    
                # Rounding difference distribution
                if line_valuations and rounding:
                    rounding_diff = cost.currency_id.round(line.price_unit - value_split)
                    if not cost.currency_id.is_zero(rounding_diff):
                        # Add to the valuation line with the max ID
                        max_val_id = max(line_valuations.ids)
                        if max_val_id in towrite_dict:
                            towrite_dict[max_val_id] += rounding_diff
                            
            # Write updated values
            for key, val_amount in towrite_dict.items():
                AdjustementLines.browse(key).write({'additional_landed_cost': val_amount})
                
        # Finally, generate the summary lines
        for cost in self:
            cost.summary_line_ids.unlink()
            
            summary_dict = {}
            move_processed = set()
            
            for val_line in cost.valuation_adjustment_lines:
                prod = val_line.product_id
                if prod not in summary_dict:
                    summary_dict[prod] = {
                        'product_id': prod.id,
                        'quantity': 0.0,
                        'former_cost': 0.0,
                        'customs_cost_value': 0.0,
                        'allocated_cost': 0.0,
                    }
                
                # Only add quantity, former_cost, and customs_cost_value once per stock move
                if val_line.move_id not in move_processed:
                    move_processed.add(val_line.move_id)
                    summary_dict[prod]['quantity'] += val_line.quantity
                    summary_dict[prod]['former_cost'] += val_line.former_cost
                    
                    move = val_line.move_id
                    po_line = move.purchase_line_id if move else False
                    customs_amt = (po_line.customs_product_cost * val_line.quantity) if po_line else 0.0
                    summary_dict[prod]['customs_cost_value'] += customs_amt
                
                summary_dict[prod]['allocated_cost'] += val_line.additional_landed_cost
                
            # Calculate totals for proportion
            total_allocated = sum(d['allocated_cost'] for d in summary_dict.values())
            
            summary_vals = []
            for prod, data in summary_dict.items():
                if total_allocated > 0:
                    data['proportion'] = data['allocated_cost'] / total_allocated
                else:
                    data['proportion'] = 0.0
                summary_vals.append((0, 0, data))
                
            if summary_vals:
                cost.write({'summary_line_ids': summary_vals})

        return True


class StockMove(models.Model):
    _inherit = 'stock.move'

    def _action_done(self, cancel_backorder=False):
        res = super()._action_done(cancel_backorder=cancel_backorder)
        for move in res:
            if move.state == 'done' and move.purchase_line_id:
                po_line = move.purchase_line_id
                order = po_line.order_id
                if order.request_type == 'foreign' and order.exchange_rate:
                    product = move.product_id
                    # price_unit_etb is computed on PO line as price_unit * exchange_rate
                    price_unit_etb = po_line.price_unit_etb or (po_line.price_unit * order.exchange_rate)
                    # Convert price to product UOM if move's UOM is different
                    if move.product_uom != product.uom_id:
                        price_unit_etb = move.product_uom._compute_price(price_unit_etb, product.uom_id)
                    product.sudo().with_company(move.company_id).write({'standard_price': price_unit_etb})
        return res
