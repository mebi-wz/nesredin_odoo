from odoo import models, fields, api
from odoo.exceptions import ValidationError

class AssetTransactionWizard(models.TransientModel):
    _name = 'am.asset.transaction.wizard'
    _description = 'Asset Transaction Wizard'

    TRANSACTION_TYPES = [
        ('assign_employee', 'Assign Asset → Employee'),
        ('assign_warehouse', 'Assign Asset → Warehouse'),
        ('transfer_warehouse', 'Transfer: Warehouse → Warehouse'),
        ('transfer_employee', 'Transfer: Employee → Employee'),
        ('assign_temp', 'Assign (Temporary): Warehouse → Employee'),
        ('assign_perm', 'Assign (Permanent): Warehouse → Employee'),
        ('return', 'Return: Employee → Warehouse'),
        ('dispose', 'Dispose Asset')
    ]

    transaction_type = fields.Selection(TRANSACTION_TYPES, string='Transaction Type', required=True)
    asset_ids = fields.Many2many('am.asset', string='Assets', default=lambda self: self._get_active_assets())
    from_warehouse_id = fields.Many2one('am.asset.warehouse', string='From Warehouse')
    to_warehouse_id = fields.Many2one('am.asset.warehouse', string='To Warehouse')
    employee_id = fields.Many2one('hr.employee', string='Employee')
    reference = fields.Char(string='Reference')

    @api.model
    def _get_active_assets(self):
        return self.env['am.asset'].browse(self.env.context.get('active_ids', []))

    def _log_transaction(self, asset):
        """Register the transaction in am.asset.transaction"""
        vals = {
            'asset_id': asset.id,
            'transaction_type': self.transaction_type,
            'from_warehouse_id': self.from_warehouse_id.id,
            'to_warehouse_id': self.to_warehouse_id.id,
            'employee_id': self.employee_id.id,
            'reference': self.reference,
            'company_id': asset.company_id.id,
        }
        self.env['am.asset.transaction'].create(vals)

    def action_confirm(self):
        Stock = self.env['am.asset.warehouse.stock']
        EmployeeAsset = self.env['am.employee.asset']

        if not self.asset_ids:
            raise ValidationError("No assets selected.")

        for asset in self.asset_ids:
            # === Assign to Employee ===
            if self.transaction_type == 'assign_employee':
                if not self.employee_id:
                    raise ValidationError("Employee is required for assignment.")
                EmployeeAsset.replace_employee_assignment(
                    asset.id,
                    self.employee_id.id,
                    asset.company_id.id,
                    fields.Date.today(),
                )
                self._log_transaction(asset)

            # === Assign to Warehouse ===
            elif self.transaction_type == 'assign_warehouse':
                if not self.to_warehouse_id:
                    raise ValidationError("Warehouse is required for assignment.")
                existing_stock = Stock.search([
                    ('asset_id', '=', asset.id),
                    ('warehouse_id', '=', self.to_warehouse_id.id)
                ], limit=1)
                if not existing_stock:
                    Stock.with_context(allowed_bypass_request_check=True).create({
                        'asset_id': asset.id,
                        'warehouse_id': self.to_warehouse_id.id,
                        'branch_id': self.to_warehouse_id.branch_id.id if self.to_warehouse_id.branch_id else False,
                        'company_id': asset.company_id.id
                    })
                self._log_transaction(asset)

            # === Transfer Warehouse → Warehouse ===
            elif self.transaction_type == 'transfer_warehouse':
                if not self.from_warehouse_id or not self.to_warehouse_id:
                    raise ValidationError("Source and destination warehouses are required.")
                stock = Stock.search([('asset_id', '=', asset.id)], limit=1)
                if not stock or stock.warehouse_id != self.from_warehouse_id:
                    raise ValidationError(f"Asset {asset.name} not found in source warehouse.")
                stock.with_context(allowed_bypass_request_check=True).write({'warehouse_id': self.to_warehouse_id.id})
                self._log_transaction(asset)

            # === Transfer Employee → Employee ===
            elif self.transaction_type == 'transfer_employee':
                if not self.employee_id:
                    raise ValidationError("Target employee must be set for transfer.")
                EmployeeAsset.replace_employee_assignment(
                    asset.id,
                    self.employee_id.id,
                    asset.company_id.id,
                    fields.Date.today(),
                )
                self._log_transaction(asset)

            # === Assign from Warehouse → Employee (Temp/Perm) ===
            elif self.transaction_type in ['assign_temp', 'assign_perm']:
                if not self.employee_id:
                    raise ValidationError("Employee is required for assignment.")
                stock = Stock.search([('asset_id', '=', asset.id)], limit=1)
                if not stock or stock.warehouse_id != self.to_warehouse_id:
                    raise ValidationError(f"Asset {asset.name} not found in warehouse.")
                stock.with_context(allowed_bypass_request_check=True).unlink()
                EmployeeAsset.replace_employee_assignment(
                    asset.id,
                    self.employee_id.id,
                    asset.company_id.id,
                    fields.Date.today(),
                )
                self._log_transaction(asset)

            # === Return Employee → Warehouse ===
            elif self.transaction_type == 'return':
                if not self.to_warehouse_id:
                    raise ValidationError("Destination warehouse is required for return.")
                emp_asset = EmployeeAsset.search([
                    ('asset_id', '=', asset.id),
                    ('status', '=', 'active')
                ], limit=1)
                if emp_asset:
                    emp_asset.with_context(allowed_bypass_request_check=True).unlink()
                stock = Stock.search([('asset_id', '=', asset.id)], limit=1)
                if stock:
                    stock.with_context(allowed_bypass_request_check=True).unlink()
                Stock.with_context(allowed_bypass_request_check=True).create({
                    'asset_id': asset.id,
                    'warehouse_id': self.to_warehouse_id.id,
                    'branch_id': self.to_warehouse_id.branch_id.id if self.to_warehouse_id.branch_id else False,
                    'company_id': asset.company_id.id
                })
                self._log_transaction(asset)

            # === Dispose ===
            elif self.transaction_type == 'dispose':
                emp_asset = EmployeeAsset.search([('asset_id', '=', asset.id)], limit=1)
                if emp_asset:
                    emp_asset.with_context(allowed_bypass_request_check=True).unlink()
                stock = Stock.search([('asset_id', '=', asset.id)], limit=1)
                if stock:
                    stock.with_context(allowed_bypass_request_check=True).unlink()
                asset.active = False
                self._log_transaction(asset)

        return {'type': 'ir.actions.act_window_close'}
