from odoo import models, fields, api


class SwissPostCarrierService(models.Model):
    _name = "swiss.post.carrier.service"
    _description = 'SwissPost Delivery Carrier Service'

    name = fields.Char(string='Service Name')
    service_code = fields.Char(string='Service Description')