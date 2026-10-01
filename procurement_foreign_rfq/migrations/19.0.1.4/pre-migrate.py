def migrate(cr, version):
    if not version:
        return
    
    # Clean up requested_by to avoid constraint errors
    cr.execute("""
        UPDATE procurement_currency_request
        SET requested_by = NULL
        WHERE requested_by IS NOT NULL 
        AND NOT EXISTS (
            SELECT 1 FROM res_users WHERE res_users.id = procurement_currency_request.requested_by
        )
    """)
