from odoo import models, api

class Base(models.AbstractModel):
    _inherit = 'base'

    @api.model
    def _valid_field_parameter(self, field, name):
        """Allow 'min_display_digits' parameter on fields to silence warnings from AI modules or Odoo Enterprise."""
        return name == 'min_display_digits' or super()._valid_field_parameter(field, name)
