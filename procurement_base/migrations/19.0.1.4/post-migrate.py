def migrate(cr, version):
    if not version:
        return
    
    # Ensure request_type is 'foreign' for all POs linked to foreign requests.
    # We check if the column exists first, since this is a base module
    # and the column might not be loaded into the db if the foreign module is installed later.
    cr.execute("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name='purchase_order' AND column_name='foreign_purchase_request_id'
    """)
    if cr.fetchone():
        cr.execute("""
            UPDATE purchase_order 
            SET request_type = 'foreign' 
            WHERE request_type = 'local' 
            AND foreign_purchase_request_id IS NOT NULL
        """)
