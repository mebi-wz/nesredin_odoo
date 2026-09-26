FROM odoo:19.0

USER root

RUN pip install --no-cache-dir --break-system-packages qifparse

USER odoo

EXPOSE 8069

CMD ["odoo"]