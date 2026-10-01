import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return

    # Our custom 'amount_total_cc' Char field on purchase.order was shadowing
    # the native Odoo Monetary field of the same name, causing a TypeError in
    # _compute_tax_totals when formatLang() received a string instead of a float.
    #
    # Fix: renamed our custom field to 'amount_total_display'.
    #
    # Migration steps:
    # 1. Remove our stale Char ir_model_fields entry for amount_total_cc
    #    (Odoo will restore the native Monetary entry on upgrade).
    # 2. Drop the VARCHAR column so Odoo recreates it as NUMERIC (Monetary type).

    _logger.info("procurement_foreign_rfq 19.0.1.6: removing stale Char amount_total_cc "
                 "field to restore native Monetary field on purchase.order")

    # Remove only our custom Char version (ttype='char'), not the native Monetary one
    cr.execute("""
        DELETE FROM ir_model_fields
        WHERE model = 'purchase.order'
          AND name = 'amount_total_cc'
          AND ttype = 'char'
    """)

    # Drop the VARCHAR column — Odoo will recreate it as NUMERIC from the native field
    cr.execute("""
        ALTER TABLE purchase_order
        DROP COLUMN IF EXISTS amount_total_cc
    """)

    _logger.info("procurement_foreign_rfq 19.0.1.6: amount_total_cc column dropped; "
                 "Odoo will recreate it as Monetary on next upgrade.")
