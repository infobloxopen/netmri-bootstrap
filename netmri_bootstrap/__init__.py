import os
import logging
import time
from netmri_bootstrap import config
from netmri_bootstrap.objects import git
from netmri_bootstrap.objects import api
logger = logging.getLogger(__name__)
# TODO: get classes from config and order them according to their dependencies
object_classes = [api.Script, api.ScriptModule, api.ConfigList, api.PolicyRule, api.Policy, api.ConfigTemplate]

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
        for klass in object_classes:
            broker = klass.get_broker()
            logger.debug(f"getting index of {broker.controller}")
            for item in broker.index():
                # NetMRI comes with a lot of pre-installed policies and rules. 
                # These rules cannot be edited by user, so there is little point in keeping them in the repo
                if self.config.skip_readonly_objects and getattr(item, "read_only", False):
                    logger.debug(f"skipping {klass.__name__} \"{item.name}\" because it's read-only")
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
            obj.save_note()


    def update_netmri(self, retry_errors=False):
        added, deleted, changed = self.repo.detect_changes()
        if not retry_errors and len(added) == 0 and len(deleted) == 0 and len(changed) == 0:
            logger.info("No changes to push to server")
            return

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

        if retry_errors:
            for class_subindex in self.repo.failed_objects.values():
                for obj in class_subindex.values():
                    blob = git.Blob.from_note(self.repo, obj)
                    # Don't retry freshly failed objects
                    if blob in added + deleted + changed:
                        continue
                    logger.debug(f"retrying sync of {blob.path}")
                    script = api.ApiObject.from_blob(blob)
                    script.push_to_api()
        self.repo.mark_bootstrap_sync()

    def force_push(self, paths):
        for path in paths:
            repo_path = self.repo.get_path_in_repo(path)
            blob = git.Blob.from_path(self.repo, repo_path)
            obj = api.ApiObject.from_blob(blob)
            obj.push_to_api()


    # Make sure that scripts weren't changed outside of netmri-bootstrap
    def check_netmri(self):
        for klass in object_classes:
            broker = klass.get_broker()
            logger.debug(f"getting index of {broker.controller}")
            api_objects = {}
            git_objects = {}
            for api_item in broker.index():
                if self.config.skip_readonly_objects and getattr(api_item, "read_only", False):
                    logger.debug(f"skipping {klass.__name__} {api_item.name} because it's read-only")
                    continue
                api_objects[api_item.id] = api_item

            for git_item in self.repo.object_index[klass.__name__].values():
                if git_item["id"] is None:
                    logger.debug(f"Skipping {klass.__name__} \"{git_item['path']}\" because it doesn't have id assigned (not synced to netmri yet?)")
                    continue
                git_objects[git_item["id"]] = git_item

            api_objects_set = set(api_objects.keys())
            git_objects_set = set(git_objects.keys())

            err_count = 0
            for obj_id in api_objects_set - git_objects_set:
                obj = api_objects[obj_id]
                logger.warn(f"{klass.__name__} \"{obj.name}\" (id: {obj.id}) was added outside of netmri-bootstrap")
                err_count += 1

            for git_id in git_objects_set - api_objects_set:
                obj = git_objects[git_id]
                logger.warn(f"{klass.__name__} \"{obj['path']}\" was deleted outside of netmri-bootstrap")
                err_count += 1

            for id in git_objects_set & api_objects_set:
                api_date = time.strptime(api_objects[id].updated_at, "%Y-%m-%d %H:%M:%S")
                git_date = time.strptime(git_objects[id]["updated_at"], "%Y-%m-%d %H:%M:%S")
                if git_date < api_date:
                    logger.warn(f"{klass.__name__} \"{api_objects[id].name}\" (id: {id}) ({git_objects[id]['path']}) was changed outside of netmri-bootstrap")
                    logger.debug(f"modification date on netmri: {api_objects[id].updated_at}, in git: {git_objects[id]['updated_at']}")
                    err_count += 1

                # git_date may be newer than api_date after netmri was restored from an archive.
                if git_date > api_date:
                    logger.warn(f"{klass.__name__} \"{api_objects[id].name}\" is outdated on netmri")
                    err_count += 1

        for class_subindex in self.repo.failed_objects.values():
            for obj in class_subindex.values():
                # TODO: notify the user if failed object has been updated after that sync
                msg = f"{obj['path']} has had sync errors: {obj['error']}"
                logger.info(msg)
                err_count += 1

        # True if no errors were found, False otherwise
        all_clear = (err_count == 0)
        if all_clear:
            logger.info("Repository and the server are in sync")
        return all_clear

    def cat_file(self, path, from_api=False):
        repo_path = self.repo.get_path_in_repo(path)
        blob = git.Blob.from_path(self.repo, repo_path)
        obj = api.ApiObject.from_blob(blob)
        if from_api:
            if obj.id is None:
                logger.error(f"Cannot fetch content for {obj.path} from server. Object hasn't been synced yet?")
                return
            obj.load_content_from_api()
        print(obj._content)

    def show_metadata(self, path):
        repo_path = self.repo.get_path_in_repo(path)
        blob = git.Blob.from_path(self.repo, repo_path)
        obj = api.ApiObject.from_blob(blob)
        for key, value in obj.get_note().items():
            print(f"{key}: {value}")

    def relink(self, path):
        repo_path = self.repo.get_path_in_repo(path)
        blob = git.Blob.from_path(self.repo, repo_path)
        obj = api.ApiObject.from_blob(blob)
        res = obj.find_by_secondary_keys()
        if len(res) == 0:
            if obj.id is None:
                logger.info(f"{path} wasn't found on server")
            else:
                logger.info(f"{path} wasn't found on server. Changing id of {obj.path} from {obj.id} to None")
                obj.id = None
                obj.save_note()
        elif len(res) == 1:
            remote = res[0]
            if remote.id == obj.id:
                logger.info(f"{path} already has correct id on server: {remote.id}")
                return
            else:
                logger.info(f"Changing id of {obj.path} from {obj.id} to {remote.id}")
                obj.id = remote.id
                obj.save_note()
        else:
            duplicates = [remote.id for remote in res]
            raise ValueError(f"Found duplicates of {obj.path}: {','.join(duplicates)}. This should not happen.")
        

    def fetch(self, path, id=None, overwrite=False):
        repo_path = self.repo.get_path_in_repo(path)
        if self.repo.path_exists(repo_path):
            blob = git.Blob.from_path(self.repo, repo_path)
            obj = api.ApiObject.from_blob(blob)

            if id is None:
                id = obj.id

            if id != obj.id:
                if overwrite:
                    remote = obj.get_broker().show(id=id)
                    obj = obj.from_api(remote)
                    obj.path = path
                else:
                    raise ValueError(f"Cannot replace {path} without --overwrite")
        else:
            if id is None:
                raise ValueError(f"Must supply id for {path} because it doesn't exist")
            klass = api.ApiObject._get_subclass_by_path(repo_path)
            remote = klass.get_broker().show(id=id)
            obj = klass.from_api(remote)
            obj.path = path

        obj.load_content_from_api()
        obj.save_to_disk()

        obj._blob = self.repo.stage_file(obj.path)

        logger.debug("Committing downloaded objects to repo")
        self.repo.commit(message=f"Fetch of {path} by netmri-bootstrap")


    # Delete all scripts on netmri, then upload scripts from repo
    # While it looks simple on the surface, any failure in this process will
    # lead to loss of data on netmri side that would be hard to remediate
    def full_resync(repo):
        pass
