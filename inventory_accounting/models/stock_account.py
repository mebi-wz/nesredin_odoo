from odoo import fields, models, Command, api


class ProductCategory(models.Model):
    _inherit = 'product.category'

    property_bill_journal_id = fields.Many2one(
        'account.journal',
        string='Billing Journal',
        company_dependent=True,
        domain="[('type', '=', 'purchase')]",
        help="Accounting journal used for vendor bills on products in this category.",
    )


class StockMove(models.Model):
    _inherit = 'stock.move'

    def _has_incoming_journal_config(self):
        """Return True if the product category has all accounts configured for receipt.

        Receipt requires:
          - Stock Journal
          - Stock Valuation Account  (inventory asset)
          - Stock Variation Account  (purchase/variation clearing)
        """
        self.ensure_one()
        categ = self.product_id.categ_id
        return bool(
            categ.property_stock_journal
            and categ.property_stock_valuation_account_id
            and categ.account_stock_variation_id
        )

    def _has_outgoing_journal_config(self):
        """Return True if the product category has all accounts configured for delivery.

        Delivery requires:
          - Stock Journal
          - Stock Valuation Account  (inventory asset — credited to reduce stock)
          - Expense Account          (COGS/expense — debited to record cost of sale)
        """
        self.ensure_one()
        categ = self.product_id.categ_id
        return bool(
            categ.property_stock_journal
            and categ.property_stock_valuation_account_id
            and categ.property_account_expense_categ_id
        )

    def _should_create_account_move(self):
        """Override: also create journal entries when the product category has
        a stock journal + valuation accounts configured, even if the product
        category uses Periodic (non real_time) inventory valuation.

        - Receipts:   requires variation account
        - Deliveries: requires expense/COGS account
        """
        # Standard check first (real_time / automated valuation)
        if super()._should_create_account_move():
            return True

        if not (self.product_id.is_storable and self.is_valued):
            return False

        # Exclude adjustments and scraps from custom logic
        if self.location_id.usage == 'inventory' or self.location_dest_id.usage == 'inventory':
            return False

        # Incoming (receipt / dropship)
        if self.is_in or self.is_dropship:
            return self._has_incoming_journal_config()

        # Outgoing (delivery)
        if self.is_out:
            return self._has_outgoing_journal_config()

        return False

    def _create_account_move(self):
        """Override to use product category's stock journal."""
        aml_vals_list = []
        move_to_link = set()
        journal = self.env['account.journal']

        for move in self:
            if move._should_create_account_move():
                vals = move._get_account_move_line_vals()
                if vals:
                    aml_vals_list += vals
                    move_to_link.add(move.id)
                    if not journal:
                        categ = move.product_id.categ_id
                        journal = (
                            categ.property_stock_journal
                            or move.company_id.account_stock_journal_id
                        )

        if not aml_vals_list:
            return self.env['account.move']

        if not journal:
            journal = self.company_id.account_stock_journal_id

        account_move = self.env['account.move'].create({
            'journal_id': journal.id,
            'line_ids': [Command.create(v) for v in aml_vals_list],
            'date': self.env.context.get('force_period_date') or fields.Date.context_today(self),
        })
        self.env['stock.move'].browse(move_to_link).account_move_id = account_move.id
        account_move._post()
        return account_move

    def _get_account_move_line_vals(self):
        """Override to use category accounts for journal entry lines.

        On Receive (incoming / dropship):
            DR  Stock Valuation Account   (property_stock_valuation_account_id)
            CR  Stock Variation Account   (account_stock_variation_id)

        On Deliver (outgoing):
            DR  Expense / COGS Account    (property_account_expense_categ_id)
            CR  Stock Valuation Account   (property_stock_valuation_account_id)
        """
        self.ensure_one()
        categ = self.product_id.categ_id
        valuation_account = categ.property_stock_valuation_account_id
        variation_account = categ.account_stock_variation_id
        expense_account = categ.property_account_expense_categ_id

        # Fallback to standard Odoo logic for Inventory Adjustments and Scraps
        if self.location_id.usage == 'inventory' or self.location_dest_id.usage == 'inventory':
            return super()._get_account_move_line_vals()

        # Outgoing (delivery or vendor return)
        if self.is_out:
            # Vendor Return: Reverse receipt (DR Variation, CR Valuation)
            if self.location_dest_id.usage == 'supplier':
                if not (valuation_account and variation_account):
                    return super()._get_account_move_line_vals()
                debit_acc, credit_acc = variation_account, valuation_account
            # Delivery: DR Expense, CR Valuation
            else:
                if not (valuation_account and expense_account):
                    return super()._get_account_move_line_vals()
                debit_acc, credit_acc = expense_account, valuation_account

        # Incoming (receipt, customer return, or dropship)
        elif self.is_in or self.is_dropship:
            # Customer Return: Reverse delivery (DR Valuation, CR Expense)
            if self.location_id.usage == 'customer':
                if not (valuation_account and expense_account):
                    return super()._get_account_move_line_vals()
                debit_acc, credit_acc = valuation_account, expense_account
            # Receipt / Dropship: DR Valuation, CR Variation
            else:
                if not (valuation_account and variation_account):
                    return super()._get_account_move_line_vals()
                debit_acc, credit_acc = valuation_account, variation_account

        else:
            return super()._get_account_move_line_vals()

        # Use price_unit * qty for periodic products (self.value may be 0)
        value = abs(self.value or 0.0)
        if not value:
            value = abs(self.product_id.standard_price * self.product_qty)
        if value == 0.0:
            return []

        label = self.reference or self.picking_id.name or self.name
        return [
            {
                'account_id': debit_acc.id,
                'name': label,
                'debit': value,
                'credit': 0.0,
                'product_id': self.product_id.id,
            },
            {
                'account_id': credit_acc.id,
                'name': label,
                'debit': 0.0,
                'credit': value,
                'product_id': self.product_id.id,
            },
        ]


class AccountMove(models.Model):
    _inherit = 'account.move'

    @api.depends('invoice_line_ids.product_id')
    def _compute_journal_id(self):
        super()._compute_journal_id()
        for move in self:
            if move.is_purchase_document(include_receipts=True) and move.state == 'draft':
                for line in move.invoice_line_ids:
                    if line.product_id:
                        categ = line.product_id.categ_id
                        if categ.property_bill_journal_id:
                            move.journal_id = categ.property_bill_journal_id
                            break

    def _stock_account_prepare_realtime_out_lines_vals(self):
        """Override to prevent duplicate COGS lines on customer invoices since
        cost of sales is already posted on delivery.
        """
        return []


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    @api.depends('product_id')
    def _compute_account_id(self):
        super()._compute_account_id()
        for line in self:
            if not line.move_id.is_purchase_document():
                continue
            if not line.product_id:
                continue
            categ = line.product_id.categ_id
            if categ.account_stock_variation_id and categ.property_bill_journal_id:
                line.account_id = categ.account_stock_variation_id
