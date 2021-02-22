import os
import logging
import time
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
    def init_empty_repo(cls):
        conf = config.get_config()
        logger.debug(f"Creating empty git repository in {conf.scripts_root}")
        os.makedirs(conf.scripts_root)
        repo = git.Repo.init_empty_repo(conf.scripts_root, conf.bootstrap_branch)
        return cls(repo=repo)

    def export_from_netmri(self):
        """Download all objects of given class (init subcommand)"""
        logger.debug("Downloading API items from NetMRI")
        saved_objs = []
        for klass in self.get_object_classes():
            broker = klass.get_broker()
            logger.debug(f"getting index of {broker.controller}")
            for item in klass.index():
                # NetMRI comes with a lot of pre-installed policies and rules.
                # These rules cannot be edited by user, so there is little point in keeping them in the repo
                if self.config.skip_readonly_objects and getattr(item, "read_only", False):
                    logger.debug(f"skipping {klass.__name__} \"{item.name}\" because it's read-only")
                    continue
                logger.debug(f"processing {broker.controller} id {item.id}")
                obj = klass.from_api(item)
                obj.path = obj.generate_path()
                try:
                    obj.load_content_from_api()
                except Exception as e:
                    msg = obj._parse_error(e)
                    logger.error(f"Cannot sync {broker.controller} id {item.id}: {msg}")
                    continue
                self.repo.write_file(obj.path, obj.export_to_repo())
                saved_objs.append(obj)

                obj._blob = self.repo.stage_file(obj.path)
                saved_objs.append(obj)

        logger.debug("Committing downloaded objects to repo")
        commit = self.repo.commit(message="Repository initialised by netmri-bootstrap")
        self.repo.mark_bootstrap_sync(commit)
        for obj in saved_objs:
            obj.save_note()

    def update_netmri(self, retry_errors=False):
        """Update all objects changed since last synced commit
        retry_errors: also sync objects that had error on previous sync
        """
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
        """Update specified objects on server regardless of their sync status"""
        for path in paths:
            repo_path = self.repo.get_path_in_repo(path)
            blob = git.Blob.from_path(self.repo, repo_path)
            obj = api.ApiObject.from_blob(blob)
            obj.push_to_api()

    def check_netmri(self, local_only=False):
        """List objects that were changed outside of netmri-bootstrap,
        or have sync errors
        """
        err_count = 0
        err_count += self._local_check()
        # Skip long remote checks
        if local_only:
            return err_count

        for klass in self.get_object_classes():
            broker = klass.get_broker()
            logger.debug(f"getting index of {broker.controller}")
            api_objects = {}
            git_objects = {}
            for api_item in klass.index():
                if self.config.skip_readonly_objects and getattr(api_item, "read_only", False):
                    logger.debug(f"skipping {klass.__name__} {api_item.name} because it's read-only")
                    continue
                api_objects[api_item.id] = api_item

            for git_item in self.repo.object_index.get(klass.__name__, {}).values():
                if git_item["id"] is None:
                    logger.debug(
                        f"Skipping {klass.__name__} \"{git_item['path']}\" because it doesn't have id assigned (not synced to netmri yet?)")
                    continue
                git_objects[git_item["id"]] = git_item

            api_objects_set = set(api_objects.keys())
            git_objects_set = set(git_objects.keys())

            for obj_id in api_objects_set - git_objects_set:
                obj = api_objects[obj_id]
                logger.warning(f"{klass.__name__} \"{obj.name}\" (id: {obj.id}) was added outside of netmri-bootstrap")
                err_count += 1

            for git_id in git_objects_set - api_objects_set:
                obj = git_objects[git_id]
                logger.warning(f"{klass.__name__} \"{obj['path']}\" was deleted outside of netmri-bootstrap")
                err_count += 1

            for id in git_objects_set & api_objects_set:
                api_date = time.strptime(api_objects[id].updated_at, "%Y-%m-%d %H:%M:%S")
                git_date = time.strptime(git_objects[id]["updated_at"], "%Y-%m-%d %H:%M:%S")
                if git_date < api_date:
                    logger.warning(
                        f"{klass.__name__} \"{api_objects[id].name}\" (id: {id}) ({git_objects[id]['path']}) was changed outside of netmri-bootstrap")
                    logger.debug(
                        f"modification date on netmri: {api_objects[id].updated_at}, in git: {git_objects[id]['updated_at']}")
                    err_count += 1

                # git_date may be newer than api_date after netmri was restored from an archive.
                if git_date > api_date:
                    logger.warning(f"{klass.__name__} \"{api_objects[id].name}\" is outdated on netmri")
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

    def _local_check(self):
        """Checks that there are no untracked and uncommitted files"""
        err_count = 0
        for path in self.repo.repo.untracked_files:
            logger.warning(f"File {path} is untracked. This file will be ignored")
            err_count += 1
        for item in self.repo.repo.index.diff(None):
            logger.warning(f"File {item.a_path} has been modified, but not committed. Changes will be ignored")
            err_count += 1
        for item in self.repo.repo.index.diff(self.repo.repo.head.commit):
            logger.warning(f"File {item.a_path} has been staged for commit. Changes will be ignored")
            err_count += 1
        return err_count

    def cat_file(self, path, from_api=False):
        """Print file contents from the repo or from API"""
        repo_path = self.repo.get_path_in_repo(path)
        blob = git.Blob.from_path(self.repo, repo_path)
        obj = api.ApiObject.from_blob(blob)
        if from_api:
            if obj.id is None:
                logger.error(f"Cannot fetch content for {obj.path} from server. Object hasn't been synced yet?")
                return
            try:
                obj.load_content_from_api()
            except Exception as e:
                msg = obj._parse_error(e)
                logger.error(f"Cannot fetch {obj.broker.controller} id {obj.id}: {msg}")
                return
        print(obj._content)

    def show_metadata(self, path):
        """Displays git note for the object"""
        repo_path = self.repo.get_path_in_repo(path)
        blob = git.Blob.from_path(self.repo, repo_path)
        obj = api.ApiObject.from_blob(blob)
        for key, value in obj.get_note().items():
            print(f"{key}: {value}")

    def relink(self, path):
        """Find object on server by its secondary key and store id in git note
        """
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
        """Download object from API and commit it to the repo"""
        repo_path = self.repo.get_path_in_repo(path)
        if self.repo.path_exists(repo_path):
            blob = git.Blob.from_path(self.repo, repo_path)
            obj = api.ApiObject.from_blob(blob)

            if id is None:
                id = obj.id

            if id != obj.id and not overwrite:
                raise ValueError(f"Cannot replace {path} without --overwrite")

            remote = obj.get_broker().show(id=id)
            obj = obj.from_api(remote)
            obj.path = path
        else:
            if id is None:
                raise ValueError(f"Must supply id for {path} because it doesn't exist")
            klass = api.ApiObject._get_subclass_by_path(repo_path)
            remote = klass.get_broker().show(id=id)
            obj = klass.from_api(remote)
            obj.path = path

        try:
            obj.load_content_from_api()
        except Exception as e:
            msg = obj._parse_error(e)
            logger.error(f"Cannot fetch {obj.broker.controller} id {obj.id}: {msg}")
            return
        self.repo.write_file(obj.path, obj.export_to_repo())

        obj._blob = self.repo.stage_file(obj.path)

        logger.debug("Committing downloaded objects to repo")
        self.repo.commit(message=f"Fetch of {path} by netmri-bootstrap")
        obj.save_note()

    @staticmethod
    def get_object_classes(class_names=None):
        """
        Resolve class names from config into actual classes.
        Also, always return dependencies before dependent classes
        """
        if class_names is None:
            conf = config.get_config()
            classes = conf.class_paths.keys()
        else:
            classes = class_names

        class_list = []
        for class_name in classes:
            klass = getattr(api, class_name)
            class_list.extend(Bootstrapper.get_object_classes(class_names=klass.depends_on))
            class_list.append(klass)

        if class_names is None:
            res = []
            for klass in class_list:
                if klass not in res:
                    res.append(klass)
            return res
        else:
            return class_list
