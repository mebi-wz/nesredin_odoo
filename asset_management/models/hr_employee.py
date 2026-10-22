from odoo import models, fields, api


class HREmployee(models.Model):
    _inherit = 'hr.employee'

    employee_asset_ids = fields.One2many(
        'am.employee.asset',  # Related model
        'employee_id',        # Field on am.employee.asset that links to employee
        string='Assets'
    )


class HRPublicEmployee(models.Model):
    _inherit = 'hr.employee.public'

    employee_asset_ids = fields.One2many(
        'am.employee.asset',  # Related model
        'employee_id',        # Field on am.employee.asset that links to employee
        string='Assets'
    )
