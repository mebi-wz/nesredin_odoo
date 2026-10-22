# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class ProductSecondaryPartNumber(models.Model):
    _name = 'product.secondary.part.number'
    _description = 'Product Secondary / Cross-Reference Part Number'
    _order = 'name'

    name = fields.Char(
        string='Secondary Part Number',
        required=True,
        index=True,
        trim=True,
        help="Alternative, interchangeable, or OEM part number used for purchasing and cross-referencing."
    )
    product_tmpl_id = fields.Many2one(
        'product.template',
        string='Product Template',
        ondelete='cascade',
        required=True,
        index=True,
    )
    source_product_id = fields.Many2one(
        'product.product',
        string='Reference Product',
        domain="[('part_number', '!=', False)]",
        help="Optional: Select another product to link its Primary Part Number as an interchangeable part."
    )
    note = fields.Char(
        string='Source / Note',
        help="e.g. OEM Number, Superseded Code, Supplier Ref, or Model Cross-Reference."
    )

    part_type = fields.Selection(
        [('primary', 'Primary'), ('secondary', 'Secondary')],
        string='Part Type',
        default='secondary',
        required=True,
    )
    is_primary = fields.Boolean(
        string='Is Primary',
        default=False,
    )

    _product_secondary_uniq = models.Constraint(
        'UNIQUE (product_tmpl_id, name)',
        'This part number is already registered for this product!'
    )

    @api.depends('name', 'part_type', 'note')
    def _compute_display_name(self):
        for record in self:
            if record.part_type == 'primary':
                record.display_name = f"{record.name} (Primary)"
            elif record.note:
                record.display_name = f"{record.name} (Secondary: {record.note})"
            else:
                record.display_name = f"{record.name} (Secondary)"

    @api.onchange('source_product_id')
    def _onchange_source_product_id(self):
        if self.source_product_id and self.source_product_id.part_number:
            self.name = self.source_product_id.part_number
            if not self.note:
                self.note = _("Interchangeable with %s") % self.source_product_id.display_name

    @api.constrains('name', 'product_tmpl_id', 'part_type')
    def _check_secondary_part_number(self):
        for record in self:
            name = (record.name or '').strip()
            if not name:
                raise ValidationError(_("Part Number cannot be empty!"))
            if record.part_type == 'secondary' and record.product_tmpl_id and record.product_tmpl_id.part_number:
                if name.lower() == record.product_tmpl_id.part_number.strip().lower():
                    raise ValidationError(
                        _("'%s' is already the Primary Part Number of this product! Secondary numbers must be alternative or cross-reference codes.")
                        % record.name
                    )

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records.product_tmpl_id._compute_secondary_parts_info()
        return records

    def write(self, vals):
        res = super().write(vals)
        self.product_tmpl_id._compute_secondary_parts_info()
        return res

    def unlink(self):
        tmpls = self.product_tmpl_id
        res = super().unlink()
        tmpls._compute_secondary_parts_info()
        return res
