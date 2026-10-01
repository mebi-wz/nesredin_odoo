def migrate(cr, version):
    if not version:
        return

    # 1. Ensure set_po_date_as_receipt_date column exists on res_company
    # to prevent SQL column errors when loading views
    cr.execute("""
        ALTER TABLE res_company 
        ADD COLUMN IF NOT EXISTS set_po_date_as_receipt_date BOOLEAN DEFAULT TRUE;
    """)

    # 2. Reset stuck module states before migration steps
    cr.execute("""
        UPDATE ir_module_module 
        SET state = 'installed' 
        WHERE state IN ('to upgrade', 'to install', 'to remove', 'upgrading');
    """)
