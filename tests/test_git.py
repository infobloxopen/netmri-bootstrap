import os
import unittest
from netmri_bootstrap.objects import git

BASE_PATH = "/tmp/netmri_bootstrap"


def setUpModule():
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


class TestInitRepo(TestCaseBase):
    def setUp(self):
        os.makedirs(self.repo_path)

    def tearDown(self):
        os.system(f"rm -rf {self.repo_path}")

    def test_init_repo(self):
        repo = git.Repo.init_empty_repo(self.repo_path)
        expected_output = "* master"
        self.assertEqual(repo.repo.git.branch(), expected_output)
        deny_current_branch = repo.repo.config_reader().\
            get_value("receive", "denyCurrentBranch")
        self.assertEqual(deny_current_branch, "updateInstead")

    def test_custom_branch(self):
        repo = git.Repo.init_empty_repo(self.repo_path,
                                        watched_branch="unittest")
        expected_output = "  master\n* unittest"
        self.assertEqual(repo.repo.git.branch(), expected_output)


class TestRepo(TestCaseBase):
    def test_basic_file_operations(self):
        sample_path = self._get_abspath("added_file")
        self._write_file(sample_path, "unittest")
        blob = self.repo.stage_file(sample_path)
        self.assertEqual(blob.id, '1570cd548baa9998c08cd500e88daa254dbbe66c')
        index = list(self.repo.repo.index.diff('HEAD'))
        self.assertEqual(len(index), 1)
        self.assertEqual(blob._blob, index[0].a_blob)

        commit = self.repo.commit(message="Commit by unittest")
        self.assertEqual(commit.message, "Commit by unittest")
        filelist = list(commit.tree)
        self.assertEqual(len(filelist), 1)
        self.assertEqual(filelist[0], blob._blob)

        self.assertIsNone(self.repo.get_last_synced_commit())
        tag = self.repo.mark_bootstrap_sync()
        self.assertEqual(tag.path, "refs/tags/synced_to_netmri")
        self.assertEqual(tag.commit, commit)
        self.assertEqual(self.repo.get_last_synced_commit(), tag.commit)

    def test_detect_changes(self):
        self.repo.mark_bootstrap_sync()
        file2blob = {}
        for name in ["file1", "file2", "file3"]:
            path = self._get_abspath(name)
            self._write_file(path, f"file {name}")
            file2blob[name] = self.repo.stage_file(path)
        self.repo.commit(message="Create some files")
        (added, _, _) = self.repo.detect_changes()
        for blob in file2blob.values():
            self.assertIn(blob, added)

        self.repo.mark_bootstrap_sync()
        self.repo.repo.index.remove(file2blob["file3"].path, working_tree=True)
        self._write_file(self._get_abspath("file2"), "file file2, updated")
        file2blob["file2"] = self.repo.stage_file(file2blob["file2"].path)
        self.repo.commit(message="Edit file2 and delete file3")
        (added, deleted, changed) = self.repo.detect_changes()
        self.assertEqual(len(added), 0)
        self.assertEqual(len(deleted), 1)
        self.assertEqual(len(changed), 1)
        self.assertIn(file2blob["file3"], deleted)
        self.assertIn(file2blob["file2"], changed)

        # Check that renames are ignored
        self.repo.mark_bootstrap_sync()
        self.repo.repo.git.mv("file1", "file4")
        file2blob["file4"] = self.repo.stage_file("file4")
        del file2blob["file1"]
        self.repo.commit(message="mv file1 -> file4")
        self.assertFalse(self.repo.path_exists("file1"))
        self.assertTrue(self.repo.path_exists("file4"))

        (added2, deleted2, changed2) = self.repo.detect_changes()
        self.assertEqual(len(added2), 0)
        self.assertEqual(len(deleted2), 0)
        self.assertEqual(len(changed2), 0)


class TestBlob(TestCaseBase):
    def test_blob(self):
        filename = "file.txt"
        self._write_file(self._get_abspath(filename), "sample file")
        self.repo.stage_file(filename)
        self.repo.commit()

        blob = git.Blob.from_path(self.repo, filename)
        self.assertIs(type(blob), git.Blob)
        self.assertEqual(blob.path, filename)
        self.assertEqual(blob.get_content(), "sample file")

    def test_note(self):
        filename = "file.txt"
        self._write_file(self._get_abspath(filename), "sample file")
        blob = self.repo.stage_file(filename)
        self.repo.commit()
        self.assertIs(type(blob.note), git._Note)
        self.assertIs(blob.note.content, None)
        the_note = {"blob": blob.id, "path": blob.path}
        blob.note = the_note
        notes_ref = git._Note.bootstrap_notes_ref
        # No notes in default ref
        self.assertEqual(self.repo.git.notes("list"), "")
        # Our notes are in custom ref
        expected_output = "6eba0460b31bca76aa301468376baf5c239e6cfd 13162a5be8d1a9dc0a00ba18190cc1907b0a73e5"
        self.assertEqual(self.repo.git.notes("--ref", notes_ref, "list"),
                         expected_output)
        del blob
        blob2 = git.Blob.from_path(self.repo, filename)
        self.assertEqual(blob2.note.content, the_note)

        blob2.note.clear()
        self.assertEqual(self.repo.git.notes("--ref", notes_ref, "list"), "")

    def test_note_operations(self):
        filename = "file.txt"
        self._write_file(self._get_abspath(filename), "sample file")
        blob = self.repo.stage_file(filename)
        self.repo.commit(f"Created {filename}")

        the_note = {"blob": blob.id, "path": blob.path}
        blob.note = the_note

        self._write_file(self._get_abspath(filename), "sample file, updated")
        new_blob = self.repo.stage_file(filename)
        self.repo.commit(f"New version of {filename}")
        self.assertIsNone(new_blob.note.content)

        old_note = new_blob.find_note_on_ancestors()
        self.assertEqual(old_note.content, the_note)
        new_blob.note = {"id": new_blob.id, "path": new_blob.path}

        self.assertEqual(old_note.content, the_note)
        notes_list = self.repo.git.notes("--ref",
                                         git._Note.bootstrap_notes_ref, "list")
        # Make sure previous note has been deleted
        self.assertEqual(len(notes_list.splitlines()), 1)
