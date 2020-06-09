import os
import logging
from netmri_bootstrap import config
from netmri_bootstrap.objects import git
from netmri_bootstrap.objects import api
logger = logging.getLogger(__name__)

class Bootstrapper:
    def __init__(self, repo=None):
        self.config = config.get_config()

        if repo is None:
            repo = git.Repo(self.config.scripts_root, self.config.bootstrap_branch)
        self.repo = repo

    @classmethod
    def init_empty_repo(klass):
        conf = config.get_config()
        logger.debug(f"Creating empty git repository in {conf.scripts_root}")
        os.makedirs(conf.scripts_root)
        repo = git.Repo.init_empty_repo(conf.scripts_root, conf.bootstrap_branch)
        return klass(repo=repo)


    def export_from_netmri(self):
        logger.debug(f"Downloading API items from NetMRI")
        saved_objs = []
        # TODO: some classes depend on each other. We should account for that and sync them in correct order
        for klass in [api.Script, api.ConfigList, api.PolicyRule, api.Policy]:
            broker = klass.get_broker()
            logger.debug(f"getting index of {broker.controller}")
            for item in broker.index():
                # NetMRI comes with a lot of pre-installed policies and rules. 
                # These rules cannot be edited by user, so there is little point in keeping them in the repo
                if self.config.skip_readonly_objects and getattr(item, "read_only", False):
                    logger.debug(f"skipping item {item.id} because it's read-only")
                    continue
                logger.debug(f"processing {broker.controller} id {item.id}")
                obj = klass.from_api(item)
                obj.path = obj.generate_path()
                obj.load_content_from_api()
                obj.save_to_disk()
                saved_objs.append(obj)

                obj._blob = self.repo.stage_file(obj.path)
                saved_objs.append(obj)

        logger.debug("Committing downloaded objects to repo")
        commit = self.repo.commit(message="Repository initialised by netmri-bootstrap")
        self.repo.mark_bootstrap_sync(commit)
        for obj in saved_objs:
            obj._blob.note = obj.to_dict() # FIXME: must be done in ApiObject class


    def update_netmri(self):
        added, deleted, changed = self.repo.detect_changes()
        for blob in deleted:
            logger.debug(f"deleting {blob.path} on netmri")
            script = api.ApiObject.from_blob(blob)
            script.delete_on_server()

        for blob in added:
            logger.debug(f"adding {blob.path} on netmri")
            script = api.ApiObject.from_blob(blob)
            script.push_to_api()

        for blob in changed:
            logger.debug(f"updating {blob.path} on netmri")
            script = api.ApiObject.from_blob(blob)
            script.push_to_api()
        self.repo.mark_bootstrap_sync()


    # Delete all scripts on netmri, then upload scripts from repo
    # While it looks simple on the surface, any failure in this process will
    # lead to loss of data on netmri side that would be hard to remediate
    def full_resync(repo):
        pass


    # Make sure that scripts weren't changed outside of netmri-bootstrap
    def check_repository():
        pass

