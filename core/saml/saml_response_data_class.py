import xml.etree.ElementTree as ET


class SamlResponseDataClass:
    def __init__(self, assertion_id=None, issuer=None, attributes=None):
        self.assertion_id = assertion_id
        self.issuer = issuer
        self.attributes = attributes if attributes is not None else {}

    @classmethod
    def parse_saml_response(cls, xml_string):
        root = ET.fromstring(xml_string)

        namespaces = {'saml': 'urn:oasis:names:tc:SAML:2.0:assertion'}

        assertion_id = root.find('.//saml:Assertion', namespaces=namespaces).get('ID')
        issuer = root.find('.//saml:Issuer', namespaces=namespaces).text

        attributes = {}
        attribute_elements = root.findall('.//saml:Attribute', namespaces=namespaces)
        for attribute_element in attribute_elements:
            attribute_name = attribute_element.get('Name')
            attribute_value = attribute_element.find('saml:AttributeValue', namespaces=namespaces).text
            attributes[attribute_name] = attribute_value

        return cls(assertion_id, issuer, attributes)
