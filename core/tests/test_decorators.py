from django.test import SimpleTestCase

from core.decorators import _parse_business_requirement


class ParseBusinessRequirementTest(SimpleTestCase):
    def test_list_with_optional_link_type(self):
        model, ids, link_type = _parse_business_requirement(['location.location', ['id-1', 'id-2'], 'eo'])
        self.assertEqual(model, 'location.location')
        self.assertEqual(ids, ['id-1', 'id-2'])
        self.assertEqual(link_type, 'eo')

    def test_list_without_link_type(self):
        model, ids, link_type = _parse_business_requirement(['location.location', ['id-1']])
        self.assertEqual(model, 'location.location')
        self.assertEqual(ids, ['id-1'])
        self.assertIsNone(link_type)

    def test_dict_requirement(self):
        model, ids, link_type = _parse_business_requirement(
            {'model': 'location.healthfacility', 'ids': ['hf-1'], 'link_type': 'ca'}
        )
        self.assertEqual(model, 'location.healthfacility')
        self.assertEqual(ids, ['hf-1'])
        self.assertEqual(link_type, 'ca')

    def test_legacy_pair_format(self):
        model, ids, link_type = _parse_business_requirement(['location.location', 'legacy-id'])
        self.assertEqual(model, 'location.location')
        self.assertEqual(ids, ['legacy-id'])
        self.assertIsNone(link_type)