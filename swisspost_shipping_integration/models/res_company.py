from odoo import models, fields, api
import requests
from odoo.exceptions import Warning, ValidationError, UserError
import xml.etree.ElementTree as etree
from requests.auth import HTTPBasicAuth
from odoo.addons.swisspost_shipping_integration.models.swisspost_response import Response
import json

import logging

_logger = logging.getLogger('SwissPost')


class ResCompany(models.Model):
    _inherit = 'res.company'

    use_swiss_post_shipping_provider = fields.Boolean(string="Is Use SwissPost Shipping Provider?",
                                                      help="True when we need to use SwissPost shipping provider",
                                                      default=False, copy=False)
    sp_username = fields.Char(string='Username')
    sp_password = fields.Char(string='Password')
    sp_franking_licence = fields.Char(string="Franking Licence")
    sp_api_url = fields.Char(string='API URL', help="Enter Api Url",
                             default="https://wsbc.post.ch/wsbc/barcode/v2_4")

    def swiss_post_api_calling(self, api_url=False):
        try:
            headers = {
                'Content-Type': "text/xml;  charset=utf-8",
                'SOAPAction': 'ReadAllowedServicesByFrankingLicense'
            }
            service_request = etree.Element("soapenv:Envelope")
            service_request.attrib['xmlns:soapenv'] = "http://schemas.xmlsoap.org/soap/envelope/"
            service_request.attrib['xmlns:typ'] = "https://wsbc.post.ch/wsbc/barcode/v2_4/types"

            header_node = etree.SubElement(service_request, "soapenv:Header")
            body_node = etree.SubElement(service_request, "soapenv:Body")

            service_node = etree.SubElement(body_node, "typ:ReadAllowedServicesByFrankingLicense")

            etree.SubElement(service_node, 'typ:FrankingLicense').text = self.sp_franking_licence
            etree.SubElement(service_node, 'typ:Language').text = "en"

            request_data = etree.tostring(service_request)
            username = self.sp_username
            password = self.sp_password
            response_body = requests.request(method="POST", url=api_url, headers=headers,
                                             auth=HTTPBasicAuth(username=username, password=password),
                                             data=request_data)
            _logger.info("Service Response %s" % response_body.content)
            if response_body.status_code in [200, 201]:
                api = Response(response_body.content)
                response_data = api.dict()
                _logger.info("Services Json Response::::%s" % response_data)
                return response_data
            else:
                raise ValidationError(response_body.content)
        except Exception as e:
            raise ValidationError(e)

    def get_swisspost_services(self):
        api_url = self.sp_api_url
        try:
            response_data = self.swiss_post_api_calling(api_url)
            swiss_post_carrier_service = self.env['swiss.post.carrier.service']
            service_list_group = response_data.get('Envelope').get('Body').get(
                'ReadAllowedServicesByFrankingLicenseResponse').get('ServiceGroups')
            if isinstance(service_list_group, dict):
                service_list_group = [service_list_group]
            for service_group in service_list_group:
                for basic_service in service_group.get('BasicService'):
                    if isinstance(basic_service, dict):
                        basic_service = [basic_service]
                    for service in basic_service:
                        swisspost_carrier_service_id = swiss_post_carrier_service.sudo().search(
                            [('name', '=', service.get('Description'))])
                        if not swisspost_carrier_service_id:
                            if isinstance(service.get('PRZL'), list):
                                vals = {'name': ', '.join(service.get('PRZL')),
                                        'service_code': service.get('Description')}
                            else:
                                vals = {'name': service.get('PRZL'),
                                        'service_code': service.get('Description')}
                            swisspost_carrier_service_id = swiss_post_carrier_service.create(vals)
        except Exception as e:
            raise ValidationError(e)
        return {
            'effect': {
                'fadeout': 'slow',
                'message': "Yeah! SwissPost Services Imported successfully.",
                'img_url': '/web/static/src/img/smile.svg',
                'type': 'rainbow_man',
            }
        }
