import os
import unittest
from netmri_bootstrap.objects import git

BASE_PATH = "/tmp/netmri_bootstrap"


def setUpModule():
    os.system(f"mkdir -p {BASE_PATH}")


def tearDownModule():
    os.system(f"rm -rf {BASE_PATH}")


class TestInitRepo(unittest.TestCase):
    repo_path = f"{BASE_PATH}/new_repo"

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


class TestRepo(unittest.TestCase):
    repo_path = f"{BASE_PATH}/new_repo"
    repo = None

    def setUp(self):
        os.makedirs(self.repo_path)
        self.repo = git.Repo.init_empty_repo(self.repo_path)

    def tearDown(self):
        os.system(f"rm -rf {self.repo_path}")

    def test_basic_file_operations(self):
        sample_path = f"{self.repo_path}/added_file"
        with open(sample_path, "w") as f:
            f.write("unittest")
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
            path = f"{self.repo_path}/{name}"
            with open(path, "w") as f:
                f.write(f"file {name}")
            file2blob[name] = self.repo.stage_file(path)
        self.repo.commit(message="Create some files")
        (added, _, _) = self.repo.detect_changes()
        for blob in file2blob.values():
            self.assertIn(blob, added)

        self.repo.mark_bootstrap_sync()
        self.repo.repo.index.remove(file2blob["file3"].path, working_tree=True)
        with open(f"{self.repo_path}/file2", "w") as f:
            f.write(f"file file2, updated")
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
