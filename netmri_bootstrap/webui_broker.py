from dataclasses import dataclass
import requests
import logging
logger = logging.getLogger(__name__)


class WebuiBroker():
    """
    This class has interface similar to API broker from infoblox_netmri, but
    calls /webui endpoints instead. Note that webui is not documented and its
    behavior can and will change without warning. If there is any possibility
    to use API, use API instead.
    """

    def __init__(self, host=None, login=None, password=None, proto="https", ssl_verify=True):
        self.proto = proto
        self.host = host
        self.login = login
        self.password = password

        self.is_authenticated = False
        self.session = requests.Session()
        # Disable SSL verify because NetMRI often operates on self-signed certificates
        self.session.verify = ssl_verify

    def show(self, id):
        raise NotImplementedError("WebuiBroker.show must be implemented in a subclass")

    def create(self, *args, **kwargs):
        raise NotImplementedError("WebuiBroker.create must be implemented in a subclass")

    def update(self, *args, **kwargs):
        raise NotImplementedError("WebuiBroker.update must be implemented in a subclass")

    def destroy(self, id):
        raise NotImplementedError("WebuiBroker.destroy must be implemented in a subclass")

    def find(self, *args, **kwargs):
        raise NotImplementedError("WebuiBroker.find must be implemented in a subclass")

    def do_request(self, url, method="get", params=None, bypass_auth=False):
        full_url = f"{self._base_url()}{url}"
        self.session.auth = requests.auth.HTTPBasicAuth(self.login, self.password)
        res = self.session.request(method, full_url, data=params)
        res.raise_for_status()
        if 'application/json' in res.headers.get('content-type'):
            return res.json()
        else:
            return {"content": res.text}

    def _base_url(self):
        return f"{self.proto}://{self.host}"


class IssueAdhocBroker(WebuiBroker):
    controller = "IssueAdhoc"

    def show(self, id):
        logger.debug("WARNING: CustomIssue uses undocumented API. It may stop working at some point in the future")
        url = f"/webui/issues_adhoc/{id}.json"
        res = self.do_request(url)
        item = res['ad_hoc_issue']
        item['Details'] = res['details']
        return IssueAdHocRemote(**item)

    def index(self):
        logger.debug("WARNING: CustomIssue uses undocumented API. It may stop working at some point in the future")
        url = "/webui/grid_data/custom_issues_config_manage_job_manage_grid.json?IssueSource=C"
        res = self.do_request(url)
        out = []
        for item in res['rows']:
            out.append(IssueAdHocRemote(**item))
        return out

    def create(self, data):
        url = "/webui/issues_adhoc/create"
        res = self.do_request(url, params=data, method="post")
        return res

    def update(self, data):
        url = "/webui/issues_adhoc/update"
        res = self.do_request(url, params=data, method="post")
        return res

    def destroy(self, id, issue_id):
        url = "/webui/issues_adhoc/delete"
        data = {"IssueAdHocID": id, "IssueTypeID": issue_id}
        self.do_request(url, params=data, method="post")

    def find(self, field, value):
        url = f'/webui/grid_data/custom_issues_config_manage_job_manage_grid.json?IssueSource=C&start=0&limit=31&fields=["{field}"]&query={value}'
        res = self.do_request(url)
        out = []
        for item in res['rows']:
            out.append(IssueAdHocRemote(**item))
        return out


@dataclass
class IssueAdHocRemote:
    id: int = 0
    name: str = ""
    issue_id: str = ""
    IssueAdHocID: int = 0
    Component: str = ""
    Correctness: str = ""
    Description: str = ""
    IssueSource: str = ""
    IssueTypeID: str = ""
    Module: str = ""
    Stability: str = ""
    Title: str = ""
    Visible: str = ""
    Details: str = ""
    updated_at: str = "1970-01-01 00:00:00"

    def __post_init__(self):
        self.name = self.Title
        self.issue_id = self.IssueTypeID
        self.id = self.IssueAdHocID
