#!/usr/bin/python3
import os
import git
import json
import binascii
import logging
from netmri_bootstrap import config
from netmri_bootstrap.dryrun import check_dryrun
logger = logging.getLogger(__name__)


# Notes in Git cannot exist without parent object (blob or commit). Therefore,
# all notes should be accessed as .note property of their parent objects
# This class exists only because gitpython doesn't have support for notes
class _Note():
    bootstrap_notes_ref = "refs/notes/netmri-bootstrap"

    def __init__(self, repo, parent, content=None):
        self.repo = repo
        self.parent = parent
        self.content = content

    # TODO: this takes relatively long time (approx. 35ms on my machine)
    # because repo.git.notes() runs git executable. Perhaps direct access
    # to git database via gitdb or GitCmdObjectDB would be faster
    def read_note(self):
        logger.debug(f"Loading git note for {self.parent.id}")
        note_raw = None
        try:
            note_raw = self.repo.git.notes('--ref', self.bootstrap_notes_ref,
                                           'show', self.parent.id)
        except git.exc.GitCommandError as e:
            # This exception is thrown if anything goes wrong. Not having
            # a note attached is expected, any other error should be re-raised
            no_note_error = f"error: no note found for object {self.parent.id}"
            if no_note_error not in e.stderr:
                raise
        if note_raw is None:
            self.content = None
        else:
            self.content = json.loads(note_raw)

    @check_dryrun
    def save(self):
        logger.debug(f"Saving git note for {self.parent.id}: {self.content}")
        old_note = self.parent.find_note_on_ancestors(skip_self=True)
        if old_note is not None:
            old_note.clear()
        self.repo.git.notes('--ref', self.bootstrap_notes_ref, 'add',
                            self.parent.id, '-f', '-m',
                            json.dumps(self.content))
        # Reset index to keep stale notes out of it
        self.repo.reset_object_index()

    @check_dryrun
    def clear(self):
        self.content = None
        logger.debug(f"Deleting git note for {self.parent.id}")
        self.repo.git.notes('--ref', self.bootstrap_notes_ref,
                            'remove', self.parent.id)
        # Reset index to keep stale notes out of it
        self.repo.reset_object_index()


# TODO: As blob objects are immutable, we can memoize them
class Blob():
    def __init__(self, repo, blob):
        self.repo = repo
        self._blob = blob

        self.id = self._blob.hexsha
        self.path = self._blob.path

        self._note = None

    def __eq__(self, other):
        if isinstance(other, Blob):
            return self.id == other.id
        else:
            return False

    @classmethod
    def from_note(cls, repo, note):
        if isinstance(note, _Note):
            note = note.content
        blob = git.Blob(repo.repo, binascii.a2b_hex(note['blob']),
                        path=note['path'])
        return cls(repo, blob)

    @classmethod
    def from_path(cls, repo, path, commit=None):
        # Use latest commit of current branch unless otherwise specified
        if commit is None:
            commit = repo.repo.head.commit
        blob = commit.tree[path]
        return cls(repo, blob)

    @property
    def note(self):
        if self._note is None:
            logger.debug(f"Trying to load git note for {self.id}")
            self._note = _Note(self.repo, self)
            self._note.read_note()
        return self._note

    @note.setter
    def note(self, note):
        if self._note is None:
            self._note = _Note(self.repo, self)

        if (isinstance(note, _Note)):
            self._note.content = note.content
        else:
            self._note.content = note

        self._note.save()

    def find_note_on_ancestors(self, skip_self=False):
        logger.debug(f"Trying to find git note on ancestors of {self.id}")
        if skip_self:
            logger.debug("Skipping own note")
            # We don't want to return the note if there isn't any note
            # on older revision
            note = None
        else:
            note = self.note

        if skip_self or note.content is None:
            logger.debug(f"Examining all blobs for path {self.path}")
            for commit in self.repo.repo.head.commit.iter_parents(
                    paths=self.path):
                ancestor = Blob(self.repo, commit.tree[self.path])

                logger.debug(f"Examining note on {ancestor.id}")
                if ancestor.note.content is not None:
                    # multiple tree entries will point to same blob if their
                    # content is identical. We have to account for the fact
                    # that these files can evolve differently afterwards, so we
                    # treat these duplicates as independent files
                    # Steps to reproduce (assuming a.ccs is already in
                    # the repository):
                    #   cp a.ccs b.ccs
                    #   git add b.ccs
                    #   git commit
                    if ancestor.note.content['path'] == self.path:
                        logger.debug(f"Found note on {ancestor.id}")
                        note = ancestor.note
                    else:
                        logger.debug(f"Ancestor has path "
                                     f"{ancestor.note.content['path']}, but we"
                                     f" need note for {self.path}: two copies "
                                     f"of same file have diverged?")
                    break
        return note

    def get_content(self, return_bytes=False):
        logger.debug(f"Loading content for {self.path} from blob {self.id}")
        if return_bytes:
            return self._blob.data_stream.read()
        return self._blob.data_stream.read().decode('utf-8')

    def __repr__(self):
        return f"(Blob {self.id}, {self.path})"


class Repo():
    def __init__(self, repo_path, watched_branch='master'):
        self.repo = git.Repo(repo_path)
        self.path = repo_path
        self.branch = watched_branch

        self.git = self.repo.git
        # helper structure to speed up note lookups
        self.reset_object_index()

    @classmethod
    def init_empty_repo(cls, repo_path, watched_branch='master'):
        logger.warning(f"Creating empty repo in {repo_path}")
        repo = git.Repo.init(repo_path)
        repo.git.commit("--allow-empty", "-m", "Init repo")
        # Create branch to sync with netmri (see bootstrap_branch in config)
        if watched_branch != "master":
            logger.debug(f"Creating branch {watched_branch}")
            branch = repo.create_head(watched_branch)
            repo.head.reference = branch
            # Repo is empty, no need to reset index and working tree

        # We have non-bare repo. Set this to make pushes work
        repo.config_writer().set_value("receive", "denyCurrentBranch",
                                       "updateInstead").release()
        return cls(repo_path)

    @check_dryrun
    def write_file(self, path, content):
        fn = os.path.join(self.path, path)
        os.makedirs(os.path.dirname(fn), exist_ok=True)
        with open(fn, 'w') as f:
            f.write(content)
        return fn

    @check_dryrun
    def stage_file(self, path):
        logger.debug(f"Adding file {path} for commit")
        rv = self.repo.index.add(path)
        return Blob(self, rv[0].to_blob(self))

    @check_dryrun
    def commit(self, message="Committed by netmri-bootstrap"):
        logger.debug("Committing staged changes to the repo")
        return self.repo.index.commit(message)

    def get_blobs(self, commit=None):
        if commit is None:
            commit = self.repo.heads[self.branch].commit
        for blob in commit.tree.traverse():
            if isinstance(blob, git.objects.tree.Tree):
                continue
            yield Blob(self, blob)

    # Creates tag "synced_to_netmri" that points to last commit successfully
    # pushed to the server.
    @check_dryrun
    def mark_bootstrap_sync(self, commit=None, force=True):
        if commit is None:
            commit = self.repo.heads[self.branch].commit
        logger.debug(f"Marking commit {commit.hexsha} as synced to netmri")
        tag = git.refs.tag.TagReference.create(self.repo,
                                               "synced_to_netmri", ref=commit,
                                               force=force)
        return tag

    def get_last_synced_commit(self):
        for tag in git.refs.tag.TagReference.iter_items(self.repo):
            if tag.path == "refs/tags/synced_to_netmri":
                return tag.commit

    # NOTE: Untracked and uncommitted files won't be taken into account
    def detect_changes(self):
        old_state = self.get_last_synced_commit()
        logger.debug(f"Finding changes since commit {old_state}")
        old_blobs = {b.path: b for b in self.get_blobs(old_state)}
        new_blobs = {b.path: b for b in self.get_blobs()}

        old_paths = set(old_blobs.keys())
        new_paths = set(new_blobs.keys())
        added = [new_blobs[p] for p in (new_paths - old_paths)]
        deleted = [old_blobs[p] for p in (old_paths - new_paths)]

        # If file is renamed, its paths will be in both added and deleted, but
        # blob they point to will stay the same. Rename changes nothing on
        # netmri side, so we'll ignore it
        # (renaming scripts/something.py -> lists/something.csv will cause
        # problems for netmri-bootstrap, but they should be rejected by
        # pre-commit hook)
        for blob in added:
            if blob in deleted:
                logger.debug(f"Detected rename for {blob.path}; ignoring")
                added.remove(blob)
                deleted.remove(blob)

        changed = []
        for path in (new_paths & old_paths):
            if new_blobs[path].id != old_blobs[path].id:
                changed.append(new_blobs[path])

        logger.debug(f"Added: {added}")
        logger.debug(f"Deleted: {deleted}")
        logger.debug(f"Changed: {changed}")
        return (added, deleted, changed)

    @property
    def object_index(self):
        if self._object_index is None:
            logger.debug("building index from git notes")
            self._object_index = {}
            notes_list = self.git.notes("--ref", _Note.bootstrap_notes_ref, 'list')
            for line in notes_list.splitlines():
                # accessing note blob directly is much faster than running
                # 'git notes show'
                note_id, note_target = line.split()
                note_blob = git.Blob(self.repo, binascii.a2b_hex(note_id))
                note_content = note_blob.data_stream.read()
                note_obj = json.loads(note_content)
                note_class = note_obj["class"]
                note_id = note_obj["id"]
                if note_class not in self._object_index:
                    self._object_index[note_class] = {}
                if note_id not in self._object_index[note_class]:
                    self._object_index[note_class][note_id] = note_obj
                else:
                    logger.warning(
                        f"Found duplicates for {note_class} id {note_id}: "
                        f"{self._object_index[note_class][note_id]['path']}")
        return self._object_index

    @property
    def failed_objects(self):
        if self._errors_index is None:
            self._errors_index = {}
            for klass in self.object_index.keys():
                self._errors_index[klass] = {}
                for note in self.object_index[klass].values():
                    if note["error"]:
                        self._errors_index[klass][note["id"]] = note
        return self._errors_index

    def reset_object_index(self):
        self._object_index = None
        self._errors_index = None

    def find_note_by_id(self, klass, id):
        # klass can be either a class or class name
        if (isinstance(klass, type)):
            klass = klass.__name__
        class_subindex = self.object_index.get(klass, {})
        return class_subindex.get(id, None)

    def path_exists(self, path, commit=None):
        if commit is None:
            commit = self.repo.heads[self.branch].commit
        for item in commit.tree.traverse():
            if item.path == path:
                return True
        return False

    def get_path_in_repo(self, path):
        """
        Path can be in one of these forms:
        Absolute path (/opt/netmri_bootstrap/scripts/foo.py)
        Path relative to current directory (./netmri_bootstrap/scripts/foo.py)
        Path relative to repo root (scripts/foo.py)
        This method converts them all into path relative to repo root.
        """
        absolute_path = os.path.abspath(path)
        absolute_repo_root = os.path.abspath(self.path)
        if os.path.commonpath([absolute_path, absolute_repo_root]) \
                != absolute_repo_root:
            if os.path.isabs(path):
                raise ValueError(f"{path} is outside of repository {self.path}")
            else:
                # Simplify constructions like a//b/../c (becomes a/c)
                normalized_path = os.path.normpath(path)
                for object_subpath in config.get_config().class_paths.values():
                    if normalized_path.startswith(object_subpath):
                        logger.debug(f"Assuming {path} is inside the repo")
                        return normalized_path
                raise ValueError(f"Relative path {path} is invalid")
        else:
            relative_path = os.path.relpath(absolute_path,
                                            start=absolute_repo_root)
            logger.debug(f"Translated {path} to {relative_path}")
            return relative_path
