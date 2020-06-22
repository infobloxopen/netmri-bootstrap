#!/usr/bin/python3
import os
import git
import json
import binascii
import logging
logger = logging.getLogger(__name__)

# Notes in Git cannot exist without parent object (blob or commit). Therefore,
# all notes should be accessed as .note property of their parent objects
# This class exists only because gitpython doesn't have support for notes
class _Note():
    def __init__(self, repo, parent, content=None):
        self.repo = repo
        self.parent = parent
        self.content = content

    # TODO: this takes relatively long time (approx. 35ms on my machine) because
    # repo.git.notes() runs git executable. Perhaps direct access to git database
    # via gitdb or GitCmdObjectDB would be faster
    def read_note(self):
        logger.debug(f"Loading git note for {self.parent.id}")
        note_raw = None
        try:
            note_raw = self.repo.git.notes('show', self.parent.id)
        except git.exc.GitCommandError as e:
            # This exception is thrown if anything goes wrong. Not having
            # a note attached is expected, any other error should be re-raised
            no_note_error = f"error: no note found for object {self.parent.id}"
            if not no_note_error in e.stderr:
                raise
        if note_raw is None:
            self.content = None
        else:
            self.content = json.loads(note_raw)


    def save(self):
        logger.debug(f"Saving git note for {self.parent.id}: {self.content}")
        self.repo.git.notes('add', self.parent.id, '-m', json.dumps(self.content), '-f')
        old_note = self.parent.find_note_on_ancestors(skip_self=True)
        if old_note is not None:
            old_note.clear()
        # Reset index to keep stale notes out of it
        self.repo.reset_object_index()

    def clear(self):
        self.content = None
        logger.debug(f"Deleting git note for {self.parent.id}")
        self.repo.git.notes('remove', self.parent.id)
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
    def get_blob_by_path(klass):
        pass

    @classmethod
    def get_blob_by_sha(klass):
        pass

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
            note = None # We don't want to return the note if there isn't any note on older revision
        else:
            note = self.note

        if skip_self or note.content is None:
            logger.debug(f"Examining all blobs for path {self.path}")
            for commit in self.repo.repo.head.commit.iter_parents(paths=self.path):
                ancestor = Blob(self.repo, commit.tree[self.path])

                logger.debug(f"Examining note on {ancestor.id}")
                if ancestor.note.content is not None:
                    # multiple tree entries will point to same blob if their 
                    # content is identical. We have to account for the fact that
                    # these files can evolve differently afterwards, so we treat
                    # these duplicates as independent files
                    # Steps to reproduce (assuming a.ccs is already in
                    # the repository):
                    #   cp a.ccs b.ccs
                    #   git add b.ccs
                    #   git commit
                    if ancestor.note.content['path'] == self.path:
                        logger.debug(f"Found note on {ancestor.id}")
                        note = ancestor.note
                    else:
                        logger.debug(f"Ancestor has path {ancestor.note.content['path']}, but we need note for {self.path}: two copies of same file have diverged?")
                    break
        return note

    def get_content(self, return_bytes=False):
        logger.debug(f"Loading content for {self.path} from blob {self.id}")
        if return_bytes:
            return self._blob.data_stream.read()
        return self._blob.data_stream.read().decode('utf-8')

    def __repr__(self):
        return f"(Blob {self.id}, {self.path})"


# TODO: list object categories (scripts, list, templates, etc.) here and
# initialise subdirs for them
class Repo():
    def __init__(self, repo_path, watched_branch='master'):
        self.repo = git.Repo(repo_path) # TODO: point head to correct branch
        self.path = repo_path
        self.branch = watched_branch

        self.git = self.repo.git
        # helper structure to speed up note lookups
        self._notes_index = None


    @classmethod
    def init_empty_repo(klass, repo_path, watched_branch='master'):
        logger.warn(f"Creating empty repo in {repo_path}")
        git.Repo.init(repo_path)
        # Create branch to sync with netmri (see bootstrap_branch in config)
        if watched_branch != "master":
            logger.debug(f"Creating branch {watched_branch}")
            branch = repo.create_head(watched_branch, 'HEAD')
            repo.head.reference = branch
            # Repo is empty, no need to reset index and working tree

        return klass(repo_path)

    # TODO: make this work on bare repo
    def stage_file(self, path):
        logger.debug(f"Adding file {path} for commit")
        rv = self.repo.index.add(path)
        return Blob(self, rv[0].to_blob(self))

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


    # Creates tag "synced_to_netmri" that points to last commit successfully pushed to server.
    def mark_bootstrap_sync(self, commit=None, force=True):
        if commit is None:
            commit = self.repo.heads[self.branch].commit
        logger.debug(f"Marking commit {commit.hexsha} as synced to netmri")
        tag = git.refs.tag.TagReference.create(self.repo, "synced_to_netmri", ref=commit, force=force)
        return tag


    def get_last_synced_commit(self):
        for tag in git.refs.tag.TagReference.iter_items(self.repo):
            if tag.path == "refs/tags/synced_to_netmri":
                return tag.commit

    # NOTE: Untracked and uncommitted files won't be taken into account
    def detect_changes(self):
        old_state = self.get_last_synced_commit()
        logger.debug(f"Finding changes since commit {old_state}")
        old_blobs = {b.path:b for b in self.get_blobs(old_state)}
        new_blobs = {b.path:b for b in self.get_blobs()}

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

    def build_object_index(self):
        if self._notes_index is None:
            self._notes_index = {}
            for line in self.git.notes('list').splitlines():
                note_target = line.split()[1]
                note_obj = json.loads(self.git.notes('show', note_target))
                note_class = note_obj["class"]
                note_id = note_obj["id"]
                if note_class not in self._notes_index:
                    self._notes_index[note_class] = {}
                if note_id in self._notes_index[note_class]:
                    logger.warn(f"Found duplicates for {note_class} id {note_id}: {self._notes_index[note_class][note_id]['path']}")
                self._notes_index[note_class][note_id] = note_obj
        return self._notes_index

    def reset_object_index(self):
        self._notes_index = None

    def find_note_by_id(self, klass, id):
        if self._notes_index is None:
            self.build_object_index()
        # klass can be either a class or class name
        if (isinstance(klass, type)):
            klass = klass.__name__
        class_subindex = self._notes_index.get(klass, {})
        return class_subindex.get(id, None)


