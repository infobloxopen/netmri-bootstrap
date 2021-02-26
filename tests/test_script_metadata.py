import unittest
from netmri_bootstrap.objects import api


class TestScriptMetadata(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import os
        from importlib import reload
        from netmri_bootstrap import config
        reload(config)
        config.config_path = os.path.join(os.path.dirname(os.path.realpath(__file__)),
                                          "test_config.json")

    def test_parse_metadata(self):
        script_content = """
# BEGIN-INTERNAL-SCRIPT-BLOCK
### Script-Level: 3
### Script-Category: TEST
### Script-Language: Python
# Script: test python
# Script-Description: This is a description
# END-INTERNAL-SCRIPT-BLOCK
print("Hello world!")
        """
        obj = api.Script(id=None, path="scripts/test.py")
        obj._content = script_content
        obj.set_metadata_from_content()
        self.assertEqual(obj.name, "test python")
        self.assertEqual(obj.description, "This is a description")
        self.assertEqual(obj.risk_level, "3")
        self.assertEqual(obj.language, "Python")
        self.assertEqual(obj.category, "TEST")

    def test_parse_metadata_ccs(self):
        script_content = """
## Script-Level: 3
## Script-Category: TEST
## Script-Language: CCS
Script: test ccs
Script-Description: This is a description
Script-Filter:
    true
        """
        obj = api.Script(id=None, path="scripts/test.py")
        obj._content = script_content
        obj.set_metadata_from_content()
        self.assertEqual(obj.name, "test ccs")
        self.assertEqual(obj.description, "This is a description")
        self.assertEqual(obj.risk_level, "3")
        self.assertEqual(obj.language, "CCS")
        self.assertEqual(obj.category, "TEST")

    def test_build_metadata(self):
        obj = api.Script(
            id=None,
            path="scripts/test.py",
            name="test python",
            language="Python",
            description="The description",
            risk_level="3",
            category="TEST")
        expected = """# BEGIN-INTERNAL-SCRIPT-BLOCK
### Script-Level: 3
### Script-Category: TEST
### Script-Language: Python
# Script: test python
# Script-Description: The description
# END-INTERNAL-SCRIPT-BLOCK
"""
        self.assertEqual(obj.build_metadata_block(), expected)

    def test_build_metadata_ccs(self):
        obj = api.Script(
            id=None,
            path="scripts/test.ccs",
            name="test python",
            language="CCS",
            description="The description",
            risk_level="3",
            category="TEST")
        expected = """## Script-Level: 3
## Script-Category: TEST
## Script-Language: CCS
Script: test python
Script-Description: The description
"""
        self.assertEqual(obj.build_metadata_block(), expected)

    def test_build_multiline_metadata(self):
        obj = api.Script(
            id=None,
            path="scripts/test.py",
            name="test python",
            language="Python",
            description="The description\non two lines",
            risk_level="3",
            category="TEST")
        expected = """# BEGIN-INTERNAL-SCRIPT-BLOCK
### Script-Level: 3
### Script-Category: TEST
### Script-Language: Python
# Script: test python
# Script-Description: The description
#   on two lines
# END-INTERNAL-SCRIPT-BLOCK
"""
        self.assertEqual(obj.build_metadata_block(), expected)
