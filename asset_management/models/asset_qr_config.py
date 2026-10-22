from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class AssetQRConfiguration(models.Model):
    _name = 'am.asset.qr.config'
    _description = 'Asset Tag Number Configuration'
    _rec_name = 'company_id'

    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company,
        ondelete='cascade', index=True,
    )
    include_company = fields.Boolean(string='Company Code', default=True)
    include_branch = fields.Boolean(string='Branch Code', default=True)
    include_major_category = fields.Boolean(string='Major Category Code', default=True)
    include_minor_category = fields.Boolean(string='Minor Category Code', default=True)
    separator = fields.Selection([
        ('hyphen', 'Hyphen (-)'),
        ('slash', 'Slash (/)'),
        ('dot', 'Dot (.)'),
        ('underscore', 'Underscore (_)'),
        ('none', 'No Separator'),
    ], required=True, default='hyphen')
    sequence_padding = fields.Integer(
        string='Sequence Digits', required=True, default=4,
        help='Number of digits in the final sequential number, for example 0001.',
    )
    format_preview = fields.Char(compute='_compute_format_preview')

    _sql_constraints = [
        (
            'company_unique',
            'unique(company_id)',
            'Only one Asset QR configuration is allowed per company.',
        ),
    ]

    @api.constrains('sequence_padding')
    def _check_sequence_padding(self):
        for config in self:
            if not 1 <= config.sequence_padding <= 10:
                raise ValidationError(_('Sequence digits must be between 1 and 10.'))

    @api.depends(
        'include_company', 'include_branch', 'include_major_category',
        'include_minor_category', 'separator', 'sequence_padding',
    )
    def _compute_format_preview(self):
        separator_values = {
            'hyphen': '-', 'slash': '/', 'dot': '.',
            'underscore': '_', 'none': '',
        }
        for config in self:
            parts = []
            if config.include_company:
                parts.append('COM')
            if config.include_branch:
                parts.append('BR')
            if config.include_major_category:
                parts.append('MAJ001')
            if config.include_minor_category:
                parts.append('MIN0001')
            parts.append(str(1).zfill(config.sequence_padding or 4))
            config.format_preview = separator_values.get(config.separator, '-').join(parts)

    def action_regenerate_qr_codes(self):
        self.ensure_one()
        return self.env['am.asset'].action_regenerate_all_qr_codes()
