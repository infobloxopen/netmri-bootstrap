import os
import re
import json
import logging
import importlib
from netmri_bootstrap import config
from lxml.builder import E
import lxml.etree as etree
logger = logging.getLogger(__name__)


class ApiObject():
    client = config.get_api_client()
    api_broker = None

    def __init__(self, **kwargs):
        self.broker = self.get_broker()
        self.from_dict(kwargs)

    def to_dict(self):
        res = {}
        for attr in self._get_attrlist():
            if attr.startswith('_'):
                continue
            res[attr] = getattr(self, attr)
        return res

    def from_dict(self, metadata):
        logger.debug(f"setting metadata for instance of {self.__class__.__name__} with {metadata}")
        for attr in self._get_attrlist():
            if attr.startswith('_'):
                continue
            # Don't replace existing attributes if we only got partial metadata
            # (can happen if we parse metadata block)
            # If you want to unset an attribute, set it to None explicitly
            if attr not in metadata and getattr(self, attr, None) is not None:
                continue
            value = metadata.get(attr, None)
            setattr(self, attr, value)

    @classmethod
    def _get_attrlist(klass):
        # Keys that should not be sent to API must begin with underscore.
        # Note that everything else WILL be sent to API, so watch out if you
        # pass this to broker.update() method
        return ('id', 'path', '_content', 'updated_at', 'description', 'name', '_blob')

    @classmethod
    def get_broker(klass):
        return klass.client.get_broker(klass.api_broker)

    @classmethod
    def scripts_dir(klass):
        path = config.get_config().class_paths.get(klass.__name__, None)
        if path is None:
            raise ValueError("Cannot determine repo path for {klass.__name__}")
        return path

    @classmethod
    def _get_subclass_by_path(klass, path):
        subclass_name = None
        for cls, cls_path in config.get_config().class_paths.items():
            if path.startswith(cls_path):
                subclass_name = cls
                break

        the_module = importlib.import_module(klass.__module__)
        if subclass_name is None or subclass_name not in dir(the_module):
            raise ValueError(f"Cannot find subclass for path {path}")
        return getattr(the_module, subclass_name)

    @classmethod
    # Create object from XXXRemote 
    def from_api(klass, remote):
        logger.debug(f"creating {klass.__name__} from {remote.__class__}")
        item_dict = {}
        for attr in klass._get_attrlist():
            if attr.startswith('_'):
                continue
            item_dict[attr] = getattr(remote, attr, None)
        logger.debug(f"setting attributes from {item_dict}")
        return klass(**item_dict)

    @classmethod
    def from_blob(klass, blob):
        if klass.__name__ == "ApiObject":
            klass = klass._get_subclass_by_path(blob.path)

        logger.debug(f"creating {klass.__name__} from {blob.path}")
        item_dict = {}
        note = blob.find_note_on_ancestors()
        if note.content is not None:    
            item_dict = dict(**(note.content)) # poor man's deepcopy
        item_dict['path'] = blob.path
        logger.debug(f"setting attributes from {item_dict}")
        res = klass(**item_dict)
        res._blob = blob
        res.load_content_from_repo()
        # Note that we don't update git note here. It will be done on api push, if necessary
        res.set_metadata_from_content()
        return res

    # This must be overridden in a subclass
    def load_content_from_api(self):
        raise NotImplementedError("This method must be defined in a subclass")

    def load_content_from_repo(self):
        logger.debug(f"loading content for {self.api_broker} from {self._blob.path}")
        self._content = self._blob.get_content()

    def delete_on_server(self):
        broker = self.get_broker()
        logger.debug(f"calling delete method of {broker.controller} with id {self.id}")
        broker.destroy(id=self.id)

    def push_to_api(self):
        # TODO: We need to check that the object is in clean state
        # (i. e. content and metatada properties are same as in repo)
        if self._content is None:
            if self.path is None:
                raise ValueError(f"There is no such file in the repository")
            else:
                raise ValueError(f"Content for {self.path} is not loaded")
        logger.debug(f"Pushing {self.path} to netmri")
        api_result = self._do_push_to_api()
        # FIXME: fix copypaste
        item_dict = {}
        for attr in self._get_attrlist():
            if attr.startswith('_'):
                continue
            item_dict[attr] = getattr(api_result, attr, None)
        self.from_dict(item_dict)
        self._blob.note = self.to_dict()
        self._blob.note.save()

    # _do_push_to_api must be defined in a subclass and must return XXXRemote object.
    # In some cases, this method must call self.get_broker().show(id=received_id) to obtain necessary metadata
    def _do_push_to_api(self):
        raise NotImplementedError("This method must be defined in a subclass")

    # This must be overridden in a subclass
    def set_metadata_from_content(self):
        raise NotImplementedError("This method must be defined in a subclass")

    def get_full_path(self):
        # TODO: find path by broker and id if no path is provided
        pass 

    # TODO: must create git blobs instead of files so it'll work on bare repo
    # See https://git-scm.com/book/en/v2/Git-Internals-Git-Objects
    # also, git notes should be added here
    def save_to_disk(self):
        conf = config.get_config()
        os.makedirs(os.path.join(conf.scripts_root, self.scripts_dir()), exist_ok=True)
        fn = os.path.join(conf.scripts_root, self.generate_path())
        logger.info(f"saving {self.api_broker} \"{self.name}\" (id {self.id}) to {fn}")
        with open(fn, 'w') as f:
            f.write(self._content)
        return fn

    # NOTE: These methods SHOULD be overridden in subclasses
    def generate_path(self):
        return os.path.join(self.scripts_dir(), str(self.id))


class Script(ApiObject):
    api_broker = "Script"

    def __init__(self, **kwargs):
        super(Script, self).__init__(**kwargs)

    @classmethod
    def _get_attrlist(klass):
        return ('risk_level', 'language', 'category') + super(Script, klass)._get_attrlist()

    def generate_path(self):
        # Name must be unique, so it is safe
        name = re.sub("[^A-Za-z0-9_\-.]", "_", self.name)
        extension = self.get_extension(self.language)
        filename = '.'.join([name, extension])
        return os.path.join(self.get_subdir(), filename)

    def get_subdir(self):
        subdir = self.category
        if subdir == 'Uncategorized':
            subdir = ''
        return os.path.join(self.scripts_dir(), subdir)

    def load_content_from_api(self):
        broker = self.get_broker()
        logger.debug(f"downloading content for {self.api_broker} id {self.id}")
        res = broker.export_file(id=self.id)
        self._content = res["content"]

    def _do_push_to_api(self):
        broker = self.get_broker()
        if self.id is None:
            logger.info(f"Pushing {self.api_broker} {self.path} to netmri")
            rv = broker.create(script_file=self._content, language=self.language)
        else:
            logger.info(f"Pushing {self.api_broker} {self.path} to netmri (id {self.id})")
            rv = broker.update(id=self.id, script_name=self.name, script_file=self._content, language=self.language)
        return rv

    def save_to_disk(self):
        conf = config.get_config()
        os.makedirs(os.path.join(conf.scripts_root, self.get_subdir()), exist_ok=True)
        fn = os.path.join(conf.scripts_root, self.generate_path())
        logger.info(f"saving {self.api_broker} \"{self.name}\" (id {self.id}) to {fn}")
        with open(fn, 'w') as f:
            f.write(self.build_metadata_block())
            f.write(self._content)
        return fn

    def build_metadata_block(self):
        res = []
        # It works this way. Don't ask me why.
        if self.language == 'CCS':
            res.append(f"Script: {self.name}")
            res.append(f"Script-Description: {self.description}")
        else:
            res.append('# BEGIN-INTERNAL-SCRIPT-BLOCK')
            res.append(f"# Script: {self.name}")
            res.append(f"# Script-Description: {self.description}")
            res.append('# END-INTERNAL-SCRIPT-BLOCK')
        res.append(f"## Script-Level: {self.risk_level}")
        res.append(f"## Script-Category: {self.category}")
        res.append(f"## Script-Language: {self.language}")
        res.append('')
        return os.linesep.join(res)

    def set_metadata_from_content(self):
        regex = re.compile(r'^#*\s*Script-?(Description|Level|Category|Language)?:\s+(.*)$')
        metadata = {}
        for line in self._content.splitlines():
            m = regex.match(line)
            if m:
                key = m.group(1)
                val = m.group(2)
                # We use first occurence of metadata entry, if there is more than one of it in the file
                if key is None and 'name' not in metadata:
                    metadata["name"] = val
                elif key == 'Description' and 'description' not in metadata:
                    metadata["description"] = val
                elif key == 'Level' and 'risk_level' not in metadata:
                    metadata['risk_level'] = val
                elif key == 'Category' and 'category' not in metadata:
                    metadata['category'] = val
                elif key == 'Language' and 'language' not in metadata:
                    metadata['language'] = val

        # These values are mandatory. Fill them from path, for the lack of better alternative
        if 'language' not in metadata:
            metadata['language'] = self.detect_language(self.path)
        if 'name' not in metadata:
            metadata['name'] = os.path.basename(self.path)

        logger.debug(f"setting object metadata from {metadata}")
        self.from_dict(metadata)

    @staticmethod
    def get_extension(lang):
        if lang == 'CCS':
            return 'ccs'
        elif lang == 'Perl':
            return 'pl'
        elif lang == 'Python':
            return 'py'
        else:
            # TODO: warn about unknown language
            return lang.lower()

    @staticmethod
    def detect_language(filename):
        extension = filename.split('.')[-1].lower()

        if extension == 'ccs':
            return 'CCS'
        elif extension == 'pl':
            return 'Perl'
        elif extension == 'py':
            return 'Python'
        else:
            raise ValueError(f"Cannot determine language for {filename}")



class ConfigList(ApiObject):
    api_broker = "ConfigList"

    def __init__(self, **kwargs):
        super(ConfigList, self).__init__(**kwargs)

    def generate_path(self):
        # Name must be unique, so it is safe
        name = f"{self.name}.csv"
        name = re.sub("[^A-Za-z0-9_\-.]", "_", name)
        return os.path.join(self.scripts_dir(), name)

    def load_content_from_api(self):
        logger.debug(f"downloading content for {self.api_broker} id {self.id}")
        try:
            res = self.get_broker().export(id=self.id)
        except json.JSONDecodeError:
            logger.error("You have hit a bug in netmri Python client. Please update it to at least [VERSION_UNAVAILABLE]")
            raise 
        self._content = res["content"]

    def _do_push_to_api(self):
        msg = f"Pushing {self.api_broker} {self.path} to netmri"
        if self.id is not None:
            msg += f" (id {self.id})"
        logger.info(msg)
        # Import of config lists is very, very broken
        broker = self.get_broker()
        self.client._authenticate()
        url = self.client._method_url(broker._get_method_fullname("import"))
        resp = self.client.session.request("post", url, files={"overwrite_ind": 1, "file": self._content})
        resp.raise_for_status()
        result = resp.json()

        if not result.get("success", False):
            raise ValueError(f"Sync of ConfigList {self.path} failed: {result['message']}")
        return self.get_broker().show(id=result["id"])

    def save_to_disk(self):
        conf = config.get_config()
        os.makedirs(os.path.join(conf.scripts_root, self.scripts_dir()), exist_ok=True)
        fn = os.path.join(conf.scripts_root, self.generate_path())
        logger.info(f"saving {self.api_broker} \"{self.name}\" (id {self.id}) to {fn}")
        with open(fn, 'w') as f:
            # No need to write metadata block, it's already exported
            f.write(self._content)
        return fn

    def build_metadata_block(self):
        res = []
        res.append('#' * 36)
        res.append(f"# Name: {self.name}")
        res.append(f"# Description: {self.description}")
        res.append('#' * 36)
        res.append('')
        return os.linesep.join(res)


    def set_metadata_from_content(self):
        regex = re.compile(r'^#*\s*(Name|Description)?:\s+(.*)$')
        metadata = {}
        for line in self._content.splitlines():
            m = regex.match(line)
            if m:
                key = m.group(1)
                val = m.group(2)
                # We use first occurence of metadata entry, if there is more than one of it in the file
                if key == "Name" and 'name' not in metadata:
                    metadata["name"] = val
                elif key == 'Description' and 'description' not in metadata:
                    metadata["description"] = val

        # These values are mandatory. Fill them from path, for the lack of better alternative
        if 'name' not in metadata:
            metadata['name'] = os.path.basename(self.path)

        logger.debug(f"setting object metadata from {metadata}")
        self.from_dict(metadata)


class XmlObject(ApiObject):
    def __init__(self, **kwargs):
        super(XmlObject, self).__init__(**kwargs)

    @classmethod
    def _get_attrlist(klass):
        return super(XmlObject, klass)._get_attrlist()

    def generate_path(self):
        # Name must be unique, so it is safe
        name = f"{self.short_name}.xml"
        name = re.sub("[^A-Za-z0-9_\-.]", "_", name)
        return os.path.join(self.scripts_dir(), name)

    def save_to_disk(self):
        conf = config.get_config()
        os.makedirs(os.path.join(conf.scripts_root, self.scripts_dir()), exist_ok=True)
        fn = os.path.join(conf.scripts_root, self.generate_path())
        logger.info(f"saving {self.api_broker} \"{self.name}\" (id {self.id}) to {fn}")
        content = etree.tostring(self._content, pretty_print=True, xml_declaration=True, encoding="UTF-8")
        with open(fn, 'wb') as f:
            f.write(content)
        return fn

    def load_content_from_api(self):
        logger.debug(f"downloading content for {self.api_broker} id {self.id}")
        broker = self.get_broker()
        res = self.get_broker().show(id=self.id)
        rule_tree = E(self.root_element)
        for attr in self.api_attrs:
            val = getattr(res, attr.replace('-', '_'), None)
            kwargs = {}
            if attr in self.datetime_attrs:
                kwargs["type"] = "datetime"
            if attr in self.boolean_attrs:
                kwargs["type"] = "boolean"
            if attr in self.nil_attrs:
                if val is None:
                    kwargs["nil"] = "true"

            if attr in self.xml_attrs:
                if val is not None:
                    rule_tree.append(etree.XML(val))
            else:
                if val is None:
                    val = ""
                if attr in self.boolean_attrs:
                    # False -> "false"
                    val = str(val).lower()
                rule_tree.append(E(attr, val, **kwargs))


        # FIXME: there is NetmriVersion tag in exported rules. Need to investigate it
        self._content = rule_tree

    def load_content_from_repo(self):
        logger.debug(f"loading content for {self.api_broker} from {self._blob.path}")
        content = self._blob.get_content(return_bytes=True)
        self._content = etree.fromstring(content)


class PolicyRule(XmlObject):
    api_broker = "PolicyRule"
    root_element = "policy-rule"
    api_attrs = ["action-after-exec", "author", "created-at", "description", "name", "read-only", "remediation", "severity", "short-name", "updated-at", "rule-logic", "script-filter"]
    datetime_attrs = ["created-at", "updated_at"]
    boolean_attrs = ["read-only"]
    nil_attrs = ["action-after-exec"]
    xml_attrs = ["rule-logic", "script-filter"]

    def __init__(self, **kwargs):
        super(PolicyRule, self).__init__(**kwargs)

    @classmethod
    def _get_attrlist(klass):
        return ('author', 'set_filter', 'rule_logic', 'severity', 'action_after_exec', 'remediation', 'short_name', 'read_only') + super(PolicyRule, klass)._get_attrlist()

    def _do_push_to_api(self):
        broker = self.get_broker()
        update_dict = self.to_dict()
        if self.id is None:
            logger.info(f"Pushing {self.api_broker} {self.path} to netmri")
            res = broker.create(**update_dict)
            self.id = res['id']
        else:
            logger.info(f"Pushing {self.api_broker} {self.path} to netmri (id {self.id})")
            res = broker.update(**update_dict)

        return res["policy_rule"]


    def set_metadata_from_content(self):
        self.author = self._content.findtext("author")
        self.description = self._content.findtext("description")
        self.name = self._content.findtext("name")
        self.read_only = self._content.findtext("read-only")
        self.remediation = self._content.findtext("remediation")
        self.severity = self._content.findtext("severity")
        self.short_name = self._content.findtext("short-name")
        self.updated_at = self._content.findtext("updated-at")

        rule_logic = self._content.find("{http://www.infoblox.com/NetworkAutomation/1.0/ScriptXml}PolicyRuleLogic")
        if rule_logic is not None:
            self.rule_logic = etree.tostring(rule_logic).decode("utf8")

        set_filter = self._content.find("{http://www.infoblox.com/NetworkAutomation/1.0/ScriptXml}SetFilter")
        if set_filter is not None:
            self.set_filter = etree.tostring(set_filter).decode("utf8")


class Policy(XmlObject):
    # We should sync policy rules before we sync policies that use them
    depends_on=["PolicyRule"]
    api_broker = "Policy"
    root_element = "policy"
    api_attrs = ["author", "created-at", "description", "name", "read-only", "schedule-mode", "short-name", "updated-at", "set-filter"]
    datetime_attrs = ["created-at", "updated_at"]
    boolean_attrs = ["read-only"]
    nil_attrs = []
    xml_attrs = ["set-filter"]

    def __init__(self, *args, **kwargs):
        super(Policy, self).__init__(*args, **kwargs)

    @classmethod
    def _get_attrlist(klass):
        return ('author', 'set_filter', 'severity', 'schedule_mode', 'short_name', 'read_only') + super(Policy, klass)._get_attrlist()

    def load_content_from_api(self):
        super(Policy, self).load_content_from_api()
        res = self.get_broker().policy_rules(id=self.id)
        policy_rules = E("policy-rules", type="array")
        self.rules = []
        for rule in res:
            self.rules.append(rule["short_name"])
            policy_rules.append(E("policy-rule-reference", rule["short_name"]))
        self._content.append(policy_rules)

    def set_metadata_from_content(self):
        self.author = self._content.findtext("author")
        self.name = self._content.findtext("name")
        self.description = self._content.findtext("description")
        self.schedule_mode = self._content.findtext("schedule-mode")
        self.read_only = self._content.findtext("read-only")
        self.short_name = self._content.findtext("short-name")
        self.updated_at = self._content.findtext("updated-at")
        self.rules = []
        for rule in self._content.iter(tag="policy-rule-reference"):
            self.rules.append(rule.text)

    def _do_push_to_api(self):
        broker = self.get_broker()
        update_dict = self.to_dict()
        if self.id is None:
            logger.info(f"Pushing {self.api_broker} {self.path} to netmri")
            res = broker.create(**update_dict)
            self.id = res['id']
        else:
            logger.info(f"Pushing {self.api_broker} {self.path} to netmri (id {self.id})")
            res = broker.update(**update_dict)

        old_rules = [r["short_name"] for r in broker.policy_rules(id=self.id)]
        # TODO: load it from git instead. It will be faster (but there might be sync errors)
        all_rules = {r.short_name:r.id for r in PolicyRule.get_broker().index()}

        all_rules_set = set(all_rules.keys())
        old_rules_set = set(old_rules)
        new_rules_set = set(self.rules)

        invalid_rules = new_rules_set - all_rules_set
        if invalid_rules:
            raise ValueError(f"Policy {self.short_name} references nonexistent rule(s): " + ",".join(invalid_rules))

        rules_to_delete = [all_rules[short_name] for short_name in old_rules_set - new_rules_set]
        rules_to_add = [all_rules[short_name] for short_name in new_rules_set - old_rules_set ]
        for rule_id in rules_to_delete:
            logger.debug(f"Removing reference to rule {rule_id} from policy {self.id}")
            broker.remove_policy_rules(id=self.id, policy_rule_id=rule_id)

        for rule_id in rules_to_add:
            logger.debug(f"Adding reference to rule {rule_id} to policy {self.id}")
            broker.add_policy_rules(id=self.id, policy_rule_id=rule_id)
        return res["policy"]

