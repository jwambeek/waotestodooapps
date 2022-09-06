from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import requests
import binascii
import xml.etree.ElementTree as etree
from requests.auth import HTTPBasicAuth
from odoo.addons.swisspost_shipping_integration.models.swisspost_response import Response
import logging

_logger = logging.getLogger("SwissPost")


class DeliveryCarrier(models.Model):
    _inherit = 'delivery.carrier'

    delivery_type = fields.Selection(selection_add=[("swiss_post", "SwissPost")],
                                     ondelete={'swiss_post': 'set default'})

    package_id = fields.Many2one('stock.package.type', string="Default Package", help="please select package type")
    swiss_post_service = fields.Many2one('swiss.post.carrier.service', string="SwissPost Service")

    def swiss_post_rate_shipment(self, orders):
        "This Method Is Used For Get Rate"
        return {'success': True, 'price': 0.0, 'error_message': False, 'warning_message': False}

    def convert_weight(self, weight):
        """This Method use for convert weight in specif format"""

        grams_for_kg = 1000  # 1 Kg to Grams
        grams_for_pound = 453.592  # 1 pounds to Grams
        uom_id = self.env['product.template']._get_weight_uom_id_from_ir_config_parameter()
        if uom_id.name == 'kg':
            return str(int(round(weight * grams_for_kg, 3)))
        elif uom_id.name in ["lb", "lbs"]:
            return str(int(round(weight * grams_for_pound, 3)))
        else:
            return weight

    def swiss_post_send_shipping(self, pickings):
        """this method is used for generate request data for send all details to carrier"""
        response = []

        shipper_address = pickings.picking_type_id.warehouse_id.partner_id
        recipient_address = pickings.partner_id

        # check sender Address
        if not shipper_address.zip or not shipper_address.city or not shipper_address.country_id:
            raise ValidationError("Please Define Proper Sender Address!")

        # check receiver Address
        if not recipient_address.zip or not recipient_address.city or not recipient_address.country_id:
            raise ValidationError("Please Define Proper Receiver Address!")

        shipping_request = etree.Element("soapenv:Envelope")
        shipping_request.attrib['xmlns:soapenv'] = "http://schemas.xmlsoap.org/soap/envelope/"
        shipping_request.attrib['xmlns:typ'] = "https://wsbc.post.ch/wsbc/barcode/v2_4/types"

        header_node = etree.SubElement(shipping_request, "soapenv:Header")
        body_node = etree.SubElement(shipping_request, "soapenv:Body")

        generate_label = etree.SubElement(body_node, "typ:GenerateLabel")
        etree.SubElement(generate_label, 'typ:Language').text = 'en'
        envelope_tag = etree.SubElement(generate_label, "typ:Envelope")

        label_definition = etree.SubElement(envelope_tag, "typ:LabelDefinition")
        etree.SubElement(label_definition, 'typ:LabelLayout').text = 'A6'
        etree.SubElement(label_definition, 'typ:PrintAddresses').text = 'RecipientAndCustomer'
        etree.SubElement(label_definition, 'typ:ImageFileType').text = 'PDF'
        etree.SubElement(label_definition, 'typ:ImageResolution').text = '300'
        etree.SubElement(label_definition, 'typ:PrintPreview').text = 'false' if self.prod_environment else 'true'


        file_infos = etree.SubElement(envelope_tag, "typ:FileInfos")
        etree.SubElement(file_infos, 'typ:FrankingLicense').text = self.company_id.sp_franking_licence
        etree.SubElement(file_infos, 'typ:PpFranking').text = "false"

        customer_tag = etree.SubElement(file_infos, "typ:Customer")
        etree.SubElement(customer_tag, 'typ:Name1').text = shipper_address.name or ''
        etree.SubElement(customer_tag, 'typ:Street').text = shipper_address.street or ''
        etree.SubElement(customer_tag, 'typ:ZIP').text = shipper_address.zip or ''
        etree.SubElement(customer_tag, 'typ:City').text = shipper_address.city or ''
        etree.SubElement(customer_tag,
                         'typ:Country').text = shipper_address.country_id and shipper_address.country_id.code or ''

        data_tag = etree.SubElement(envelope_tag, "typ:Data")
        provider_tag = etree.SubElement(data_tag, "typ:Provider")
        sending_tag = etree.SubElement(provider_tag, "typ:Sending")

        selected_services = self.swiss_post_service.name.split(',')
        for package_id in pickings.package_ids:
            item_tag = etree.SubElement(sending_tag, "typ:Item")
            recipient_tag = etree.SubElement(item_tag, "typ:Recipient")
            etree.SubElement(recipient_tag, 'typ:Name1').text = recipient_address.name or ''
            etree.SubElement(recipient_tag, 'typ:Street').text = recipient_address.street or ''
            etree.SubElement(recipient_tag, 'typ:ZIP').text = recipient_address.zip or ''
            etree.SubElement(recipient_tag, 'typ:City').text = recipient_address.city or ''
            etree.SubElement(recipient_tag,
                             'typ:Country').text = recipient_address.country_id and recipient_address.country_id.code or ''

            attributes_tag = etree.SubElement(item_tag, "typ:Attributes")
            if isinstance(selected_services, list):
                for selected_service in selected_services:
                    etree.SubElement(attributes_tag, 'typ:PRZL').text = str(selected_service)
            else:
                etree.SubElement(attributes_tag, 'typ:PRZL').text = str(selected_services)
            dimension_tag = etree.SubElement(attributes_tag, "typ:Dimensions")
            etree.SubElement(dimension_tag, 'typ:Weight').text = self.convert_weight(package_id.shipping_weight)

        if pickings.weight_bulk:
            item_tag = etree.SubElement(sending_tag, "typ:Item")
            recipient_tag = etree.SubElement(item_tag, "typ:Recipient")
            etree.SubElement(recipient_tag, 'typ:Name1').text = recipient_address.name or ''
            etree.SubElement(recipient_tag, 'typ:Street').text = recipient_address.street or ''
            etree.SubElement(recipient_tag, 'typ:ZIP').text = recipient_address.zip or ''
            etree.SubElement(recipient_tag, 'typ:City').text = recipient_address.city or ''
            etree.SubElement(recipient_tag,
                             'typ:Country').text = recipient_address.country_id and recipient_address.country_id.code or ''

            attributes_tag = etree.SubElement(item_tag, "typ:Attributes")
            if isinstance(selected_services, list):
                for selected_service in selected_services:
                    etree.SubElement(attributes_tag, 'typ:PRZL').text = str(selected_service)
            else:
                etree.SubElement(attributes_tag, 'typ:PRZL').text = str(selected_services)
            dimension_tag = etree.SubElement(attributes_tag, "typ:Dimensions")
            etree.SubElement(dimension_tag, 'typ:Weight').text = self.convert_weight(pickings.weight_bulk)
        try:
            api_url = self.company_id.sp_api_url
            headers = {
                'Content-Type': "text/xml;  charset=utf-8",
                'SOAPAction': 'GenerateLabel'
            }
            username = self.company_id.sp_username
            password = self.company_id.sp_password
            response_body = requests.request(method="POST", url=api_url, headers=headers,
                                             auth=HTTPBasicAuth(username=username, password=password),
                                             data=etree.tostring(shipping_request))
            _logger.info(
                ">>> sending Shipment request to {0} and get response {1}".format(api_url, response_body.content))
            if response_body.status_code in [200, 201]:
                api = Response(response_body.content)
                response_data = api.dict()
                _logger.info("Shipping Json Response::::%s" % response_data)
                label_datas = response_data.get('Envelope').get('Body').get('GenerateLabelResponse').get(
                    'Envelope').get('Data').get('Provider').get('Sending').get('Item')
                if isinstance(label_datas,dict):
                    if label_datas and label_datas.get('Errors'):
                        raise ValidationError(label_datas.get('Errors').get('Error').get('Message'))
                else:
                    for label_data in label_datas:
                        if label_data.get('Errors'):
                            raise ValidationError(label_data.get('Errors').get('Error').get('Message'))
                if isinstance(label_datas,dict):
                    label_datas = [label_datas]
                ident_code = []
                for label in label_datas:
                    base64_label_data = label.get('Label')
                    ident_code.append(label.get('IdentCode'))
                    label_binary_data = binascii.a2b_base64(str(base64_label_data))
                    message = (_(
                        "Label created!"))
                    pickings.message_post(body=message, attachments=[
                        ('%s.%s' % (pickings.name, "pdf"), label_binary_data)])
                shipping_data = {
                    'exact_price': 0.0,
                    'tracking_number': ', '.join(ident_code)}
                response += [shipping_data]
                return response
            else:
                raise ValidationError(response_body.content)
        except Exception as e:
            raise ValidationError(e)

    def swiss_post_cancel_shipment(self, picking):
        raise ValidationError("Cancel API is not available")

    def swiss_post_get_tracking_link(self, pickings):
        return "https://service.post.ch/ekp-web/ui/list"
