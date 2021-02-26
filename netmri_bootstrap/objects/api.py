import os
import re
import json
import logging
import importlib
from requests import exceptions
from netmri_bootstrap import config, webui_broker
from netmri_bootstrap.dryrun import get_dryrun, check_dryrun
from lxml.builder import E
import lxml.etree as etree
logger = logging.getLogger(__name__)


class ApiObject():
    api_broker = None
    # Lists all attributes that should be received from api
    api_attributes = ()
    # Lists all attributes that are unique on netmri (such as name)
    secondary_keys = ()

    def __init__(self, id=None, blob=None, error=None, **api_metadata):
        self.client = config.get_api_client()
        self._broker = None
        self.id = id
        if blob is not None:
            self._blob = blob
            self.path = blob.path
        else:
            self._blob = None
            self.path = None
        self.error = error
        self.updated_at = api_metadata.get("updated_at", None)
        self.set_metadata(api_metadata)

    def get_metadata(self):
        res = {}
        if self.id is not None:
            res['id'] = self.id
        if self.updated_at is not None:
            res['updated_at'] = self.updated_at
        for attr in self.api_attributes:
            res[attr] = getattr(self, attr)
        return res

    def set_metadata(self, metadata):
        logger.debug(f"setting metadata for instance of "
                     f"{self.__class__.__name__} with {metadata}")
        if 'id' in metadata:
            self.id = metadata['id']
        if 'updated_at' in metadata:
            self.updated_at = metadata['updated_at']
        if 'error' in metadata:
            self.updated_at = metadata['error']
        for attr in self.api_attributes:
            # Don't replace existing attributes if we only got partial metadata
            # (can happen if we parse metadata block)
            # If you want to unset an attribute, set it to None explicitly
            if attr not in metadata and getattr(self, attr, None) is not None:
                continue
            value = metadata.get(attr, None)
            setattr(self, attr, value)

    @property
    def broker(self):
        if self._broker is None:
            self._broker = self.get_broker()
        return self._broker

    @classmethod
    def get_broker(cls):
        """
        cls.api_broker can be either callable or string. If it's a string,
        we use it as broker for infoblox_netmri. If it's callbale, we use
        its return value as API broker
        """
        if callable(cls.api_broker):
            return cls.api_broker()
        client = config.get_api_client()
        return client.get_broker(cls.api_broker)

    @classmethod
    def scripts_dir(cls):
        path = config.get_config().class_paths.get(cls.__name__, None)
        if path is None:
            raise ValueError(f"Cannot determine repo path for {cls.__name__}")
        return path

    @classmethod
    def _get_subclass_by_path(cls, path):
        subclass_name = None
        for cls, cls_path in config.get_config().class_paths.items():
            if path.startswith(cls_path):
                subclass_name = cls
                break

        the_module = importlib.import_module(cls.__module__)
        if subclass_name is None or subclass_name not in dir(the_module):
            raise ValueError(f"Cannot find subclass for path {path}")
        return getattr(the_module, subclass_name)

    @classmethod
    # Create object from XXXRemote
    def from_api(cls, remote):
        logger.debug(f"creating {cls.__name__} from {remote.__class__}")
        item_dict = {}
        item_dict["id"] = remote.id
        item_dict["updated_at"] = remote.updated_at
        for attr in cls.api_attributes:
            item_dict[attr] = getattr(remote, attr, None)
        logger.debug(f"creating {cls.api_broker} object from {item_dict}")
        return cls(**item_dict)

    @classmethod
    def from_blob(cls, blob):
        if cls.__name__ == "ApiObject":
            cls = cls._get_subclass_by_path(blob.path)

        logger.debug(f"creating {cls.__name__} from {blob.path}")
        item_dict = {}
        note = blob.find_note_on_ancestors()
        if note.content is not None:
            item_dict = dict(**(note.content))  # poor man's deepcopy
        item_dict['blob'] = blob
        item_dict['path'] = blob.path
        logger.debug(f"setting attributes from {item_dict}")
        res = cls(**item_dict)
        res.load_content_from_repo()
        # This will update metadata values from note with ones from the content
        # Note that we don't update git note here. It will be done
        # on api push, if necessary
        res.set_metadata_from_content()
        return res

    def load_content_from_api(self):
        raise NotImplementedError(f"Class {self.__class__} must implement "
                                  f"load_content_from_api")

    def load_content_from_repo(self):
        logger.debug(f"loading content for {self.api_broker} from "
                     f"{self._blob.path}")
        self._content = self._blob.get_content()

    def delete_on_server(self):
        logger.info(f"DEL {repr(self)} [{self.path}]")
        if self.id is None:
            logger.info(f"{self.path} wasn't found on server, ignoring")
        else:
            logger.debug(f"calling {self.api_broker}.destroy with id {self.id}")
            check_dryrun(self.broker.destroy)(id=self.id)
        check_dryrun(self._blob.note.clear)()

    def push_to_api(self):
        # TODO: We need to check that the object is in clean state
        # (i. e. content and metatada properties are same as in repo)
        if self._content is None:
            if self.path is None:
                raise ValueError("There is no such file in the repository")
            else:
                raise ValueError(f"Content for {self.path} is not loaded")
        if self.id is None:
            logger.info(f"{self.path} -> {repr(self)} NEW")
        else:
            logger.info(f"{self.path} -> {repr(self)})")
        try:
            api_result = self._do_push_to_api()
            if api_result is None and get_dryrun:
                # No point in updating the object if dry run is enabled
                return None
            item_dict = {}
            item_dict["id"] = api_result.id
            item_dict["updated_at"] = api_result.updated_at
            for attr in self.api_attributes:
                item_dict[attr] = getattr(api_result, attr, None)
            logger.debug(f"Updating object attributes with API result {item_dict}")
            self.set_metadata(item_dict)
            self.error = None
        except Exception as e:
            self.error = self._parse_error(e)
            logger.error(f"An error has occured while syncing {self.path}: "
                         f"{self.error}")
            self.save_note()
            return False

        self.save_note()
        return True

    @check_dryrun
    def _do_push_to_api(self):
        """
        _do_push_to_api must be defined in a subclass and must return instance
        of XXXRemote. In some cases, this can be achieved by calling
        self.broker.show(id=received_id) to obtain necessary metadata
        """
        raise NotImplementedError(f"Class {self.__class__} must implement "
                                  "_do_push_to_api")

    # This must be overridden in a subclass
    def set_metadata_from_content(self):
        raise NotImplementedError(f"Class {self.__class__} must implement "
                                  "set_metadata_from_content")

    def get_full_path(self):
        # TODO: find path by broker and id if no path is provided
        pass

    def export_to_repo(self):
        """ Exports content in a form suitable to be stored in the repo
        Some modules may write metadata block before content itself
        """
        logger.info(f"{repr(self)} -> {self.path}")
        return self._content

    @check_dryrun
    def save_note(self):
        self._blob.note = self.get_note()

    def get_note(self):
        return {
            "id": self.id,
            "path": self.path,
            "updated_at": self.updated_at,
            "blob": self._blob.id,
            "class": self.__class__.__name__,
            "error": self.error
        }

    # Some objects, like scripts, have subcategories.
    # These categories are represented as subdirs
    def get_subpath(self):
        return ''

    def get_extension(self):
        return ''

    def generate_path(self):
        if self.path is None:
            # use id in unlikely case the object has no secondary keys
            base_key = getattr(self, self.secondary_keys[0], None)
            if base_key is None:
                base_key = self.id
                logger.warning(f"{self.__class__.__name__} object doesn't have"
                               " {self.secondary_keys[0]} attribute , using id "
                               "{self.id} instead")
            filename = re.sub(r"[^A-Za-z0-9_\-.]", "_", base_key)
            extension = self.get_extension()
            filename = '.'.join([filename, extension])
            self.path = os.path.join(self.scripts_dir(), self.get_subpath(),
                                     filename)
            logger.debug(f"Generated path for {base_key}: {self.path}")
        return self.path

    def find_by_secondary_keys(self):
        args = {}
        for key in self.secondary_keys:
            args[f"op_{key}"] = "="
            args[f"val_c_{key}"] = getattr(self, key)
        logger.debug(f"Executing {self.api_broker}.find with {args}")
        return self.broker.find(**args)

    @classmethod
    def index(cls):
        return cls.get_broker().index()

    def show(self, id=None):
        if id is None:
            id = self.id
        return self.broker.show(id=id)

    @staticmethod
    def _parse_error(e):
        msg = str(e)
        if isinstance(e, exceptions.RequestException) and getattr(e, "response", None) is not None:
            msg = e.response.content
            try:
                # NetMRI returns errors in JSON
                msg_dict = json.loads(msg)
                message = msg_dict['message']
                field_msgs = []
                if 'fields' in msg_dict:
                    for field, val in msg_dict['fields'].items():
                        field_msg = field + ': ' + " ".join(val)
                        field_msgs.append(field_msg)
                if field_msgs:
                    message = message + ': ' + ', '.join(field_msgs)
                return message
            except json.JSONDecodeError:
                pass
            except KeyError:
                pass
        # If error is not in json, return it as is
        return msg

    def __repr__(self):
        if self.id is None:
            return f'{self.api_broker} "{self.name}"'
        else:
            return f'{self.api_broker} "{self.name}" (id {self.id})'


class ScriptLike(ApiObject):
    """
    Script-like objects contain their metadata in commented block in
    the beginning of the file. Presently, this includes scripts, script
    modules, config lists and config templates.
    """
    comment_to_props = {}

    def __init__(self, **kwargs):
        super(ScriptLike, self).__init__(**kwargs)

    def _get_metadata_block_regex(self):
        raise NotImplementedError(f"Class {self.__class__} must implement "
                                  "_get_metadata_block_regex")

    def set_metadata_from_content(self):
        regex = re.compile(self._get_metadata_block_regex())
        metadata = {}
        for line in self._content.splitlines():
            m = regex.match(line)
            if m:
                key = m.group(1)
                val = m.group(2)
                prop = self.comment_to_props[key]
                # We use first occurence of metadata entry, if there is
                # more than one of it in the file
                if prop not in metadata:
                    metadata[prop] = val

        # These values are mandatory. Fill them from path, for the lack
        # of better alternative
        old_name = getattr(self, self.secondary_keys[0], None)
        if old_name is None and self.secondary_keys[0] not in metadata:
            metadata[self.secondary_keys[0]] = os.path.basename(self.path)

        logger.debug(f"setting object metadata from {metadata}")
        self.set_metadata(metadata)

    def build_metadata_block(self):
        res = []
        res.append('#' * 79)
        for comment, prop in self.comment_to_props.items():
            val = getattr(self, prop, '')
            res.append(f"# {comment}: {val}")
        res.append('#' * 79)
        res.append('')
        return os.linesep.join(res)

    def export_to_repo(self):
        logger.info(f"{repr(self)} -> {self.path}")
        content = self.build_metadata_block()
        content += self._content
        return content

    def _strip_metadata_block(self):
        lines_filtered = []
        metadata_boundary_regex = re.compile(r'^#{10,}$')
        metadata_block_started = False
        metadata_block_ended = False
        for line in self._content.splitlines():
            if metadata_block_ended:
                lines_filtered.append(line)
            elif not metadata_block_started:
                if metadata_boundary_regex.match(line):
                    metadata_block_started = True
                else:
                    lines_filtered.append(line)
            elif metadata_block_started:
                if metadata_boundary_regex.match(line):
                    metadata_block_ended = True
        return "\n".join(lines_filtered)


class Script(ScriptLike):
    depends_on = ()
    api_broker = "Script"
    api_attributes = ('name', 'description', 'risk_level', 'language',
                      'category')
    secondary_keys = ("name",)
    comment_to_props = {
        None: "name",
        "Description": "description",
        "Level": "risk_level",
        "Category": "category",
        "Language": "language"
    }

    def __init__(self, **kwargs):
        super(Script, self).__init__(**kwargs)

    def get_subpath(self):
        subpath = self.category
        if subpath == 'Uncategorized' or subpath is None:
            subpath = ''
        return subpath

    def _get_metadata_block_regex(self):
        return r'^#*\s*Script-?(Description|Level|Category|Language)?:\s+(.*)$'

    def load_content_from_api(self):
        logger.debug(f"downloading content for {self.api_broker} id {self.id}")
        res = self.broker.export_file(id=self.id)
        # Some of the metadata will remain in imported file. Remove it here
        # to add it later in more controlled fashion
        content_filtered = []
        for line in res["content"].splitlines():
            if line == f"## Script-Level: {self.risk_level}" \
                    or line == f"## Script-Category: {self.category}" \
                    or line == f"## Script-Language: {self.language}":
                continue
            content_filtered.append(line)
        self._content = "\n".join(content_filtered)

    @check_dryrun
    def _do_push_to_api(self):
        if self.id is None:
            rv = self.broker.create(script_file=self._content,
                                    language=self.language)
        else:
            rv = self.broker.update(id=self.id,
                                    script_name=self.name,
                                    script_file=self._content,
                                    language=self.language)
        return rv

    def build_metadata_block(self):
        res = []
        # It works this way. Don't ask me why.
        if self.language == 'CCS':
            res.append(f"## Script-Level: {self.risk_level}")
            res.append(f"## Script-Category: {self.category}")
            res.append(f"## Script-Language: {self.language}")
            res.append(f"Script: {self.name}")
            res.append(f"Script-Description: {self.description}")
        else:
            res.append('# BEGIN-INTERNAL-SCRIPT-BLOCK')
            res.append(f"### Script-Level: {self.risk_level}")
            res.append(f"### Script-Category: {self.category}")
            res.append(f"### Script-Language: {self.language}")
            res.append(f"# Script: {self.name}")
            res.append(f"# Script-Description: {self._format_description(self.description)}")
            res.append('# END-INTERNAL-SCRIPT-BLOCK')
        res.append('')
        return os.linesep.join(res)

    def set_metadata_from_content(self):
        super(Script, self).set_metadata_from_content()
        if getattr(self, 'language', '') == '':
            self.language = self.detect_language(self.path)

    def get_extension(self):
        lang = self.language.lower()
        if lang == 'ccs':
            return 'ccs'
        elif lang == 'perl':
            return 'pl'
        elif lang == 'python':
            return 'py'
        else:
            logger.warning(f"{self.path} is written in unknown language {self.lang}")
            return lang

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

    def _format_description(self, value):
        if value is None:
            value = ""
        first_line = True
        result = []
        for line in value.splitlines():
            if first_line:
                result.append(line)
                first_line = False
            else:
                if self.language.lower() == 'ccs':
                    result.append("    " + line)
                else:
                    result.append("#   " + line)
        return "\n".join(result)


class ScriptModule(ScriptLike):
    depends_on = ()
    api_broker = "ScriptModule"
    api_attributes = ('name', 'category', 'description', 'language')
    secondary_keys = ("name",)
    comment_to_props = {
        "Export of Script Module": "name",
        "Language": "language",
        "Category": "category",
        "Description": "description"
    }

    def __init__(self, **kwargs):
        super(ScriptModule, self).__init__(**kwargs)

    def _get_metadata_block_regex(self):
        return r'^#*\s*(Export of Script Module|Description|Category|Language)?:\s+(.*)$'

    def load_content_from_api(self):
        logger.debug(f"downloading content for {self.api_broker} id {self.id}")
        res = self.broker.export_file(id=self.id)
        self._content = res["content"]

    @check_dryrun
    def _do_push_to_api(self):
        content = self._strip_metadata_block()
        if self.id is None:
            rv = self.broker.create(name=self.name,
                                    script_source=content,
                                    language=self.language,
                                    category=self.category,
                                    description=self.description)
        else:
            rv = self.broker.update(id=self.id,
                                    name=self.name,
                                    script_source=content,
                                    language=self.language,
                                    category=self.category,
                                    description=self.description,
                                    overwrite_ind=1)
        return rv['script_module']

    def get_extension(self):
        lang = self.language.lower()
        if lang == 'perl':
            return 'pm'
        elif lang == 'python':
            return 'py'
        else:
            logger.warning(f"{self.path} is written in unknown language {self.lang}")
            return lang

    @staticmethod
    def detect_language(filename):
        extension = filename.split('.')[-1].lower()

        if extension == 'pm':
            return 'Perl'
        elif extension == 'py':
            return 'Python'
        else:
            raise ValueError(f"Cannot determine language for {filename}")


class ConfigList(ScriptLike):
    depends_on = ()
    api_broker = "ConfigList"
    api_attributes = ("name", "description")
    secondary_keys = ("name",)
    comment_to_props = {
        "Name": "name",
        "Description": "description"
    }

    def __init__(self, **kwargs):
        super(ConfigList, self).__init__(**kwargs)

    def _get_metadata_block_regex(self):
        return r'^#*\s*(Name|Description)?:\s+(.*)$'

    def get_extension(self):
        return 'csv'

    def load_content_from_api(self):
        logger.debug(f"downloading content for {self.api_broker} id {self.id}")
        try:
            res = self.broker.export(id=self.id)
        except json.JSONDecodeError:
            logger.error("You have hit a bug in infoblox_netmri. "
                         "Please update it to at least 3.6.0.0")
            raise
        if isinstance(res, dict):
            self._content = res["content"]
        else:
            # Older versions of API can return string instead of JSON on export
            self._content = res

    @check_dryrun
    def _do_push_to_api(self):
        # Import of config lists is very, very broken
        self.broker.update(id=self.id, name=self.name,
                           description=self.description)
        url = self.client._method_url(self.broker._get_method_fullname("import"))
        resp = self.client.session.request("post", url, files={"overwrite_ind": 1, "file": self._content})
        resp.raise_for_status()
        result = resp.json()

        if not result.get("success", False):
            raise ValueError(f"Sync of ConfigList {self.path} failed: "
                             f"{result['message']}")
        return self.show(id=result["id"])

    # Do we need this? One way to find out
    # def export_to_repo(self):
    #    logger.info(f"{repr(self)} -> {self.path}")
    #    # Metadata block is generated by netmri during export.
    #    # No need to add it here
    #    return self._content

    # Metadata block is already present in exported file
    def build_metadata_block(self):
        return ''


class ConfigTemplate(ScriptLike):
    depends_on = ()
    api_broker = "ConfigTemplate"
    api_attributes = ('name', 'description', 'device_type', 'model',
                      'risk_level', 'template_type', 'vendor', 'version',
                      'template_variables_text')
    secondary_keys = ("name",)

    def __init__(self, **kwargs):
        super(ConfigTemplate, self).__init__(**kwargs)

    def get_extension(self):
        return 'txt'

    def load_content_from_api(self):
        logger.debug(f"downloading content for {self.api_broker} id {self.id}")
        res = self.broker.export(id=self.id)
        if isinstance(res, dict):
            self._content = res["content"]
        else:
            # Older versions of API can return string instead of JSON on export
            self._content = res

    @check_dryrun
    def _do_push_to_api(self):
        api_args = self.get_metadata()
        api_args["template_text"] = self._strip_metadata_block()
        for k, v in api_args.items():
            if v is None:
                api_args[k] = ""
        if self.id is None:
            logger.debug(f"calling {self.api_broker}.create with {api_args}")
            res = self.broker.create(**api_args)
        else:
            logger.debug(f"calling {self.api_broker}.update with {api_args}")
            res = self.broker.update(**api_args)

        return res["config_template"]

    def set_metadata_from_content(self):
        # There can be several variables. Each of them is defined on its own
        # line pefixed with "## Template-Variable: " tag
        template_vars = []
        # Description can be multi-line. Every line is prefixed
        # with "## Template-Description: " tag
        template_description = []
        metadata = {}
        tag2attr = {
            "Level": "risk_level",
            "Vendor": "vendor",
            "Device Type": "device_type",
            "Model": "model",
            "Version": "version"
        }
        name_regex = re.compile(r'#*\s+Export of Template:\s+(.*)$')
        attr_regex = re.compile(r'^#*\s*Template-([^:]*):\s+(.*)$')
        for line in self._content.splitlines():
            name_match = name_regex.match(line)
            if name_match:
                metadata["name"] = name_match.group(1)
                continue
            attr_match = attr_regex.match(line)
            if attr_match:
                tag = attr_match.group(1)
                val = attr_match.group(2)
                # We use first occurence of metadata entry, if there is
                # more than one of it in the file
                if tag == "Variable":
                    template_vars.append(val)
                elif tag == 'Description':
                    template_description.append(val)
                elif tag in tag2attr:
                    # We use first match here
                    if tag not in metadata:
                        metadata[tag2attr[tag]] = val
                else:
                    logger.warning(f"Unknown {self.api_broker} metadata tag {tag}. Ignoring")

        metadata["template_variables_text"] = template_vars
        metadata["description"] = "\n".join(template_description)
        # These values are mandatory. Fill them from path
        if 'name' not in metadata:
            metadata['name'] = os.path.basename(self.path)

        # This field is required. Set it to "Device" if not specified
        if self.template_type is None:
            metadata["template_type"] = "Device"
        logger.debug(f"setting object metadata from {metadata}")
        self.set_metadata(metadata)


class XmlObject(ApiObject):
    def __init__(self, **kwargs):
        super(XmlObject, self).__init__(**kwargs)

    def get_extension(self):
        return 'xml'

    def export_to_repo(self):
        logger.info(f"{repr(self)} -> {self.path}")
        content = etree.tostring(self._content, pretty_print=True,
                                 xml_declaration=True, encoding="UTF-8")
        return content.decode('utf8')

    def load_content_from_api(self):
        logger.debug(f"downloading content for {self.api_broker} id {self.id}")
        res = self.show()
        rule_tree = E(self.root_element)
        if isinstance(self.api_attrs, dict):
            api_attrs = self.api_attrs.keys()
        else:
            api_attrs = self.api_attrs
        for attr in api_attrs:
            if isinstance(self.api_attrs, list):
                attr_in_api = attr.replace('-', '_')
            elif isinstance(self.api_attrs, dict):
                attr_in_api = self.api_attrs[attr]

            if isinstance(res, dict):
                val = str(res.get(attr_in_api, None))
            else:
                val = getattr(res, attr_in_api, None)
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
            elif attr in self.custom_parsing:
                # self.custom_parsing is a mapping between attibute
                # and parser method. Parser method must accept attribute value
                # as the only parameter and return lxml.builder.E object
                parser = self.custom_parsing[attr]
                rule_tree.append(parser(val))
            else:
                if val is None:
                    val = ""
                if attr in self.boolean_attrs:
                    # We try to cover a number of different ways to represent
                    # boolean values
                    if str(val).lower() in ('y', 'yes', 'true', 'on', '1'):
                        val = "true"
                    elif str(val).lower() in ('n', 'no', 'false', 'off', '0'):
                        val = "false"
                    else:
                        raise ValueError(f"Boolean attribute {attr} has "
                                         f"unrecognized value '{str(val)}'")

                else:
                    val = str(val)
                rule_tree.append(E(attr, val, **kwargs))

        self._content = rule_tree

    def load_content_from_repo(self):
        logger.debug(f"loading content for {self.api_broker} from "
                     f"{self._blob.path}")
        content = self._blob.get_content(return_bytes=True)
        self._content = etree.fromstring(content)


class PolicyRule(XmlObject):
    depends_on = ()
    api_broker = "PolicyRule"
    api_attributes = ('name', 'description', 'author', 'set_filter',
                      'rule_logic', 'severity', 'action_after_exec',
                      'remediation', 'short_name', 'read_only')
    secondary_keys = ("short_name", "name")

    root_element = "policy-rule"
    api_attrs = ["action-after-exec", "author", "description", "name",
                 "read-only", "remediation", "severity", "short-name",
                 "rule-logic", "script-filter"]
    datetime_attrs = ["created-at", "updated_at"]
    boolean_attrs = ["read-only"]
    nil_attrs = ["action-after-exec"]
    xml_attrs = ["rule-logic", "script-filter"]
    custom_parsing = {}

    def __init__(self, **kwargs):
        super(PolicyRule, self).__init__(**kwargs)

    @check_dryrun
    def _do_push_to_api(self):
        update_dict = self.get_metadata()
        if self.id is None:
            logger.debug(f"calling {self.api_broker}.create with {update_dict}")
            res = self.broker.create(**update_dict)
            self.id = res['id']
        else:
            logger.debug(f"calling {self.api_broker}.update with {update_dict}")
            res = self.broker.update(**update_dict)

        return res["policy_rule"]

    def set_metadata_from_content(self):
        self.author = self._content.findtext("author")
        self.description = self._content.findtext("description")
        self.name = self._content.findtext("name")
        self.read_only = self._content.findtext("read-only")
        self.remediation = self._content.findtext("remediation")
        self.severity = self._content.findtext("severity")
        self.short_name = self._content.findtext("short-name")

        rule_logic = self._content.find("{http://www.infoblox.com/NetworkAutomation/1.0/ScriptXml}PolicyRuleLogic")
        if rule_logic is not None:
            self.rule_logic = etree.tostring(rule_logic).decode("utf8")

        set_filter = self._content.find("{http://www.infoblox.com/NetworkAutomation/1.0/ScriptXml}SetFilter")
        if set_filter is not None:
            self.set_filter = etree.tostring(set_filter).decode("utf8")


class Policy(XmlObject):
    # We should sync policy rules before we sync policies that use them
    depends_on = ("PolicyRule",)
    api_broker = "Policy"
    api_attributes = ('name', 'description', 'author', 'set_filter',
                      'schedule_mode', 'short_name', 'read_only')
    secondary_keys = ("short_name", "name")

    root_element = "policy"
    api_attrs = ["author", "description", "name", "read-only", "schedule-mode",
                 "short-name", "set-filter"]
    datetime_attrs = ["created-at", "updated_at"]
    boolean_attrs = ["read-only"]
    nil_attrs = []
    xml_attrs = ["set-filter"]
    custom_parsing = {}

    def __init__(self, *args, **kwargs):
        super(Policy, self).__init__(*args, **kwargs)

    def load_content_from_api(self):
        super(Policy, self).load_content_from_api()
        res = self.broker.policy_rules(id=self.id)
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
        self.rules = []
        for rule in self._content.iter(tag="policy-rule-reference"):
            self.rules.append(rule.text)

    @check_dryrun
    def _do_push_to_api(self):
        update_dict = self.get_metadata()
        if self.id is None:
            logger.debug(f"calling {self.api_broker}.create with {update_dict}")
            res = self.broker.create(**update_dict)
            self.id = res['id']
        else:
            logger.debug(f"calling {self.api_broker}.update with {update_dict}")
            res = self.broker.update(**update_dict)

        old_rules = [r["short_name"] for r in self.broker.policy_rules(id=self.id)]
        all_rules = {r.short_name: r.id for r in PolicyRule.index()}

        all_rules_set = set(all_rules.keys())
        old_rules_set = set(old_rules)
        new_rules_set = set(self.rules)

        invalid_rules = new_rules_set - all_rules_set
        if invalid_rules:
            msg = f"Policy {self.short_name} references nonexistent rule(s): "\
                + ",".join(invalid_rules)
            raise ValueError(msg)

        rules_to_delete = [all_rules[short_name] for short_name in old_rules_set - new_rules_set]
        rules_to_add = [all_rules[short_name] for short_name in new_rules_set - old_rules_set]
        for rule_id in rules_to_delete:
            logger.debug(f"Removing reference to rule {rule_id} from policy {self.id}")
            self.broker.remove_policy_rules(id=self.id, policy_rule_id=rule_id)

        for rule_id in rules_to_add:
            logger.debug(f"Adding reference to rule {rule_id} to policy {self.id}")
            self.broker.add_policy_rules(id=self.id, policy_rule_id=rule_id)
        return res["policy"]


class CustomIssue(XmlObject):
    """
    Note that CustomIssue will not detect edits made via web UI due to API deficiencies
    """
    depends_on = ()
    api_attributes = ("issue_id", "name", "description", "component",
                      "correctness", "stability", "details")
    secondary_keys = ("issue_id", "name")

    root_element = "issue-adhoc"
    api_attrs = {
        "issue_id": "IssueTypeID",
        "name": "Title",
        "description": "Description",
        "component": "Component",
        "correctness": "Correctness",
        "stability": "Stability",
        "details": "Details"
    }
    datetime_attrs = []
    boolean_attrs = ["correctness", "stability"]
    nil_attrs = []
    xml_attrs = []
    custom_parsing = None

    def __init__(self, **kwargs):
        super(CustomIssue, self).__init__(**kwargs)
        self.custom_parsing = {"details": self._parse_details}

    @classmethod
    def api_broker(cls):
        client = config.get_api_client()
        return webui_broker.IssueAdhocBroker(
            host=client.host,
            login=client.username,
            password=client.password,
            proto=client.protocol,
            ssl_verify=client.ssl_verify
        )

    @check_dryrun
    def _do_push_to_api(self):
        update_dict = {}
        if self.id is not None:
            update_dict["IssueAdHocID"] = self.id
        for our_attr, api_attr in self.api_attrs.items():
            if our_attr in self.boolean_attrs:
                val = getattr(self, our_attr, False)
                if val:
                    update_dict[api_attr] = "on"
                else:
                    update_dict[api_attr] = "off"
            else:
                update_dict[api_attr] = getattr(self, our_attr, "WAAGH")

        logger.debug(f"calling {self.api_broker}.update with {update_dict}")
        res = self.broker.update(update_dict)
        if self.id is None:
            self.id = res["id"]

        return self.broker.show(id=self.id)

    def set_metadata_from_content(self):
        for attr in self.api_attributes:
            if attr in self.boolean_attrs:
                val = self._content.findtext(attr)
                if val == "true":
                    val = True
                elif val == "false":
                    val = False
                else:
                    raise ValueError(f"Boolean attribute {attr} must be either"
                                     f" 'true' or 'false', not '{val}'")
            elif attr == "details":
                details = self._content.find(attr)
                val_arr = []
                for field in details:
                    val_arr.append(f"{field.text},{field.get('type')}")
                val = "\n".join(val_arr)
            else:
                val = self._content.findtext(attr)
            setattr(self, attr, val)

    def find_by_secondary_keys(self):
        field = self.api_attrs[self.secondary_keys[0]]
        value = getattr(self, self.secondary_keys[0])
        logger.debug(f"Executing {self.api_broker}.find with {field} {value}")
        return self.broker.find(field, value)

    def delete_on_server(self):
        logger.info(f"DEL {self.api_broker} {self.name} (id {self.id}) [{self.path}]")
        if self.id is None:
            logger.info(f"{self.path} wasn't found on server, ignoring")
        else:
            logger.debug(f"calling {self.api_broker}.destroy with id {self.id}")
            check_dryrun(self.broker.destroy)(self.id, self.issue_id)
        check_dryrun(self._blob.note.clear)()

    @staticmethod
    def _parse_details(details):
        tree = E("details")
        for detail in details.splitlines():
            field, type = detail.split(',')
            tree.append(E("field", field, type=type))
        return tree

    def __repr__(self):
        if self.id is None:
            return f'CustomIssue "{self.name}"'
        else:
            return f'CustomIssue "{self.name}" (id {self.id})'
