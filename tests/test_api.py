import os
import unittest
import json
from httmock import with_httmock, urlmatch
from netmri_bootstrap import config
from netmri_bootstrap.objects import api
from netmri_bootstrap.objects import git
# import logging
# logging.basicConfig(level=logging.DEBUG)

BASE_PATH = "/tmp/netmri_bootstrap"
SCRIPT_PY_CONTETNT = r'{"script": {"category": "TEST", "created_at": "2020-07-17 04:56:25", "created_by": "admin", "description": "a description on multiple lines", "id": 74, "language": "Python", "module": "CCS", "name": "test python", "read_only": false, "risk_level": 3, "target_mapping": "device", "taskflow_create": "device\/standard", "taskflow_edit": "device\/standard", "taskflow_revert": null, "transactional_ind": false, "updated_at": "2020-08-10 04:25:48", "updated_by": "admin", "visible": true, "script_variables": [], "_class": "Script"}}'
SCRIPT_PY_EXPORT = r'{"content": "## Script-Level: 2\n## Script-Category: TEST\n## Script-Language: Python\n\n# BEGIN-SCRIPT-BLOCK\n#\n# Script-Filter:\n#   True\n\n## END-SCRIPT-BLOCK\nprint(\"Hello universe!\")\n\n\n"}'
SCRIPT_CSS_CONTENT = r'{"script": {"category": "TEST", "created_at": "2020-07-17 04:23:30", "created_by": "admin", "description": "This script executes an arbitrary batch of commands on all selected devices. The user will be prompted to enter the batch of commands when the script is executed.", "id": 72, "language": "CCS", "module": "CCS", "name": "test ccs import", "read_only": false, "risk_level": 3, "target_mapping": "device", "taskflow_create": "device\/standard", "taskflow_edit": "device\/standard", "taskflow_revert": null, "transactional_ind": false, "updated_at": "2020-07-17 04:23:30", "updated_by": "admin", "visible": true, "script_variables": [{"variable": "$commands_to_be_executed", "input_type": "text", "form_input": "textarea", "default_value": "Enter commands here, one per line", "eval_type": null}], "_class": "Script"}}'
SCRIPT_CSS_EXPORT = r'{"content": "## Script-Level: 2\n## Script-Category: TEST\n## Script-Language: CCS\n\n\n\n\nScript-Filter:\n\ttrue\n\nScript-Variables:\n\t$Commands_to_be_Executed\ttext\t\t\"Enter commands here, one per line\"\n\n########################################################################\nAction:\n\tExecute Command Batch\n\nAction-Description:\n\tExecute the commands contained in the Commands_to_be_Executed variable.\n\nAction-Commands:\n\t$Commands_to_be_Executed\n\n########################################################################\n\n\n\n"}'
SCRIPTMODULE_CONTENT = r'{"script_module": {"category": "None", "created_at": "2020-07-01 13:18:52", "created_by": "admin", "description": "Simple library that doesnt do anything useful", "id": 10, "language": "Python", "name": "greeter_lib", "script_source": "\ndef say_hello():\n    print(\"Hello universe!\")", "updated_at": "2020-07-01 13:18:52", "updated_by": "admin", "_class": "ScriptModule"}}'
SCRIPTMODULE_EXPORT = r'{"content": "\ndef say_hello():\n    print(\"Hello universe!\")"}'
CONFIGLIST_CONTENT = r'{"config_list": {"auth_user_id": null, "created_at": "2020-05-21 05:53:08", "description": "this is another test list (updated)", "id": 6, "name": "test list 6", "updated_at": "2020-07-17 07:16:43", "json_columns": [{"name": "deviceid", "mapping": "deviceid"}, {"name": "text", "mapping": "text"}], "json_column_model": [{"header": "DeviceID", "dataIndex": "deviceid", "id": 37, "position": 1, "hidden": false, "sortable": true}, {"header": "Text", "dataIndex": "text", "id": 38, "position": 2, "hidden": false, "sortable": true}], "_class": "ConfigList"}}'
CONFIGLIST_EXPORT = r'{"content": "###################################\n# Name:        test list 6\n# Description: this is another test list (updated)\n###################################\n\n\"DeviceID\",\"Text\"\n\"1\",\"a\"\n\"2\",\"b\"\n\"3\",\"c\"\n\"4\",\"d\""}'
POLICYRULE_CONTENT = r'''{"policy_rule": {"action_after_exec": null, "author": "me, myself and I", "created_at": "2020-05-19 16:01:35", "description": "The description", "id": 1, "name": "example rule", "read_only": false, "remediation": "Not necessary", "rule_logic": "<PolicyRuleLogic editor='basic-file' xmlns='http:\/\/www.infoblox.com\/NetworkAutomation\/1.0\/ScriptXml'>\n<If>\n<Expr op='and'>\n<ConfigFileCheck op='contains-some'>conf t\nconfigure terminal<\/ConfigFileCheck>\n<ConfigFileCheck op='does-not-contain-any'\/>\n<\/Expr>\n<Then><PolicyRulePass\/><\/Then>\n<Else><PolicyRuleFail\/><\/Else>\n<\/If>\n<\/PolicyRuleLogic>", "set_filter": null, "severity": "info", "short_name": "example_rule", "updated_at": "2020-08-11 03:13:54", "_class": "PolicyRule"}}'''
POLICY_CONTENT = r'{"policy": {"author": "me", "created_at": "2020-04-29 06:19:01", "description": "Test policy", "id": 1, "name": "test_policy", "read_only": false, "schedule_mode": "change", "set_filter": null, "short_name": "test", "updated_at": "2020-08-10 04:49:28", "_class": "Policy"}}'
POLICY_POLICYRULES = r'''{"policy_rules": [{"action_after_exec": null, "author": "me, myself and I", "created_at": "2020-05-19 16:01:35", "description": "The description", "id": 1, "name": "example rule", "policy_id": 1, "policy_rule_id": 1, "read_only": false, "remediation": "Not necessary", "rule_logic": "<PolicyRuleLogic editor='basic-file' xmlns='http:\/\/www.infoblox.com\/NetworkAutomation\/1.0\/ScriptXml'>\n<If>\n<Expr op='and'>\n<ConfigFileCheck op='contains-some'>conf t\nconfigure terminal<\/ConfigFileCheck>\n<ConfigFileCheck op='does-not-contain-any'\/>\n<\/Expr>\n<Then><PolicyRulePass\/><\/Then>\n<Else><PolicyRuleFail\/><\/Else>\n<\/If>\n<\/PolicyRuleLogic>", "set_filter": null, "severity": "info", "short_name": "example_rule", "updated_at": "2020-08-11 03:13:54", "_class": "PolicyRule"}, {"action_after_exec": null, "author": "Me, myself, and I", "created_at": "2020-06-01 13:46:15", "description": "", "id": 2, "name": "Example rule No. 2", "policy_id": 1, "policy_rule_id": 2, "read_only": false, "remediation": "No problems here", "rule_logic": "<PolicyRuleLogic editor='basic-file' xmlns='http:\/\/www.infoblox.com\/NetworkAutomation\/1.0\/ScriptXml'>\n<If>\n<Expr op='and'>\n<ConfigFileCheck op='contains-all'>conf t<\/ConfigFileCheck>\n<ConfigFileCheck op='does-not-contain-any'\/>\n<\/Expr>\n<Then><PolicyRulePass\/><\/Then>\n<Else><PolicyRuleFail\/><\/Else>\n<\/If>\n<\/PolicyRuleLogic>", "set_filter": null, "severity": "warning", "short_name": "example2", "updated_at": "2020-06-02 04:13:08", "_class": "PolicyRule"}, {"action_after_exec": null, "author": "Me, myself, and I", "created_at": "2020-06-04 16:45:48", "description": "", "id": 3, "name": "Example rule No. 3", "policy_id": 1, "policy_rule_id": 3, "read_only": false, "remediation": "No problems here", "rule_logic": "<PolicyRuleLogic editor='basic-file' xmlns='http:\/\/www.infoblox.com\/NetworkAutomation\/1.0\/ScriptXml'>\n<If>\n<Expr op='and'>\n<ConfigFileCheck op='contains-all'>conf t<\/ConfigFileCheck>\n<ConfigFileCheck op='does-not-contain-any'\/>\n<\/Expr>\n<Then><PolicyRulePass\/><\/Then>\n<Else><PolicyRuleFail\/><\/Else>\n<\/If>\n<\/PolicyRuleLogic>", "set_filter": null, "severity": "warning", "short_name": "example3", "updated_at": "2020-06-04 16:45:48", "_class": "PolicyRule"}]}'''


@urlmatch(path=r"^/api/authenticate$")
def authenticate_response(url, request):
    return {'status_code': 200, 'content': r"{}",
            'headers': {'content-type': 'application/json'}}


@urlmatch(path=r"^/api/3.1/scripts/(show|create|update)")
def scripts_show(url, request):
    params = json.loads(request.body)
    if params.get("id") == 74:
        return {'status_code': 200, 'content': SCRIPT_PY_CONTETNT,
                'headers': {'content-type': 'application/json'}}
    elif params.get("id") == 72:
        return {'status_code': 200, 'content': SCRIPT_CSS_CONTENT,
                'headers': {'content-type': 'application/json'}}


@urlmatch(path=r"^/api/3.1/scripts/export_file")
def scripts_export_file(url, request):
    params = json.loads(request.body)
    if params.get("id") == 74:
        return {'status_code': 200, 'content': SCRIPT_PY_EXPORT,
                'headers': {'content-type': 'application/json'}}
    elif params.get("id") == 72:
        return {'status_code': 200, 'content': SCRIPT_CSS_EXPORT,
                'headers': {'content-type': 'application/json'}}


@urlmatch(path=r"^/api/3.1/script_modules/show")
def script_modules_show(url, request):
    return {'status_code': 200, 'content': SCRIPTMODULE_CONTENT,
            'headers': {'content-type': 'application/json'}}


@urlmatch(path=r"^/api/3.1/script_modules/export_file")
def script_modules_export_file(url, request):
    return {'status_code': 200, 'content': SCRIPTMODULE_EXPORT,
            'headers': {'content-type': 'application/json'}}


@urlmatch(path=r"^/api/3.1/config_lists/show")
def config_lists_show(url, request):
    return {'status_code': 200, 'content': CONFIGLIST_CONTENT,
            'headers': {'content-type': 'application/json'}}


@urlmatch(path=r"^/api/3.1/config_lists/export")
def config_lists_export_file(url, request):
    return {'status_code': 200, 'content': CONFIGLIST_EXPORT,
            'headers': {'content-type': 'application/json'}}


@urlmatch(path=r"^/api/3.1/policy_rules/show")
def policy_rules_show(url, request):
    return {'status_code': 200, 'content': POLICYRULE_CONTENT,
            'headers': {'content-type': 'application/json'}}


@urlmatch(path=r"^/api/3.1/policies/show")
def policies_show(url, request):
    return {'status_code': 200, 'content': POLICY_CONTENT,
            'headers': {'content-type': 'application/json'}}


@urlmatch(path=r"^/api/3.1/policies/policy_rules")
def policies_policy_rules(url, request):
    return {'status_code': 200, 'content': POLICY_POLICYRULES,
            'headers': {'content-type': 'application/json'}}


def setUpModule():
    config.config_path = os.path.join(os.path.dirname(os.path.realpath(__file__)),
                                      "test_config_full.json")
    os.system(f"mkdir -p {BASE_PATH}")


def tearDownModule():
    os.system(f"rm -rf {BASE_PATH}")


class TestCaseBase (unittest.TestCase):
    repo_path = f"{BASE_PATH}/new_repo"
    repo = None

    def setUp(self):
        os.makedirs(self.repo_path)
        self.repo = git.Repo.init_empty_repo(self.repo_path)

    def tearDown(self):
        os.system(f"rm -rf {self.repo_path}")

    @classmethod
    def _get_abspath(cls, path):
        return f"{cls.repo_path}/{path}"

    def _write_file(self, path, content):
        if not path.startswith(self.repo_path):
            raise ValueError("{path} is outside the repo (use _get_abspath())")
        with open(path, "w") as f:
            f.write(content)

    def _test_object_import(self, api_class, id):
        broker = api_class.get_broker()
        remote = broker.show(id=id)
        obj = api_class.from_api(remote)

        self.assertEqual(obj.id, id)
        self.assertEqual(obj.updated_at, remote.updated_at)
        for attr in obj.api_attributes:
            self.assertEqual(getattr(obj, attr, None), getattr(remote, attr))

        obj.load_content_from_api()
        obj.set_metadata_from_content()

        obj.path = obj.generate_path()
        self.repo.write_file(obj.path, obj.export_to_repo())
        obj._blob = self.repo.stage_file(obj.path)
        self.repo.commit()
        obj.save_note()
        for attr in ["id", "path", "updated_at", "error"]:
            self.assertEqual(obj._blob.note.content[attr], getattr(obj, attr))
        self.assertEqual(obj._blob.note.content["blob"], obj._blob.id)
        # Return the object to do further tests
        return obj

    def _test_push_to_api(self, obj):
        res = obj.push_to_api()
        assert(res)
        return obj


class SmokeTest(TestCaseBase):
    @classmethod
    def setUpClass(cls):
        import os
        from importlib import reload
        from netmri_bootstrap import config
        reload(config)
        config.config_path = os.path.join(os.path.dirname(os.path.realpath(__file__)),
                                          "test_config_full.json")

    @with_httmock(authenticate_response, scripts_show, scripts_export_file)
    def test_script_import(self):
        obj = self._test_object_import(api.Script, 74)
        # Content must be same as one we got from api
        self.assertTrue(obj._content.startswith("## Script-Level: 2"))
        # Risk level has been changed from the content
        self.assertEqual(obj.risk_level, '2')
        obj2 = api.Script.from_blob(git.Blob.from_note(self.repo, obj._blob.note))
        obj2 = self._test_push_to_api(obj2)

    @with_httmock(authenticate_response, scripts_show, scripts_export_file)
    def test_ccs_import(self):
        obj = self._test_object_import(api.Script, 72)
        obj2 = api.Script.from_blob(git.Blob.from_note(self.repo, obj._blob.note))
        obj2 = self._test_push_to_api(obj2)

    @with_httmock(authenticate_response, script_modules_show, script_modules_export_file)
    def test_script_module_import(self):
        self._test_object_import(api.ScriptModule, 10)

    @with_httmock(authenticate_response, config_lists_show, config_lists_export_file)
    def test_config_list_import(self):
        self._test_object_import(api.ConfigList, 6)

    @with_httmock(authenticate_response, policy_rules_show)
    def test_policy_rule_import(self):
        self._test_object_import(api.PolicyRule, 1)

    @with_httmock(authenticate_response, policies_show, policies_policy_rules)
    def test_policy_import(self):
        self._test_object_import(api.Policy, 1)
