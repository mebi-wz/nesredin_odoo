def migrate(cr, version):
    if not version:
        return

    # Remove the stale 'amount_total_etb_char' field that was previously defined
    # on purchase.order but has since been removed from the model code.
    # Its ghost record in ir.model.fields causes AttributeError during onchange
    # snapshot comparison (fields.py has_changed).
    cr.execute("""
        DELETE FROM ir_model_fields
        WHERE model = 'purchase.order'
          AND name = 'amount_total_etb_char'
    """)

    # Drop the actual column from the DB table if it still exists
    cr.execute("""
        ALTER TABLE purchase_order
        DROP COLUMN IF EXISTS amount_total_etb_char
    """)
