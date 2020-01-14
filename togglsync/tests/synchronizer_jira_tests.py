import unittest
from unittest.mock import Mock, MagicMock

import dateutil.parser

from togglsync.config import Entry
from togglsync.jira_wrapper import JiraTimeEntry, JiraHelper
from togglsync.synchronizer import Synchronizer
from togglsync.toggl import TogglEntry, TogglHelper


class SynchronizerJiraTests(unittest.TestCase):
    redmine_config = Entry("test", task_patterns=["(#)([0-9]{1,})"])

    def test_start_one_day_empty(self):
        redmine = Mock()
        toggl = Mock()
        toggl.get = MagicMock()

        s = Synchronizer(Mock(), redmine, toggl, None)
        s.start(1)

        toggl.get.assert_called_once_with(1)

    def test_start_one_day_single(self):
        redmine = Mock()
        toggl = Mock()

        toggl.get.return_value = [
            TogglEntry(
                None, 3600, "2016-01-01T01:01:01", 777, "test #333", self.redmine_config
            )
        ]

        redmine.get.return_value = [
            JiraTimeEntry(
                777,
                "2016-01-01T01:02:03",
                "john doe",
                1.25,
                "2016-03-02",
                333,
                "test #333 [toggl#777]",
            )
        ]

        s = Synchronizer(Mock(), redmine, toggl, None)
        s.start(1)

        toggl.get.assert_called_once_with(1)

    def test_groupTogglByIssueId(self):
        entries = [
            TogglEntry(None, 3600, None, 1, "#15", self.redmine_config),
            TogglEntry(None, 3600, None, 2, "#16", self.redmine_config),
            TogglEntry(None, 3600, None, 3, "#16", self.redmine_config),
            TogglEntry(None, 3600, None, 4, "#16", self.redmine_config),
            TogglEntry(None, 3600, None, 5, "#17", self.redmine_config),
        ]

        groups = Synchronizer.groupTogglByIssueId(entries)

        self.assertIsNotNone(groups)

        self.assertEqual(3, len(groups))

        self.assertTrue("15" in groups)
        self.assertTrue("16" in groups)
        self.assertTrue("17" in groups)

        self.assertEquals(1, len(groups["15"]))
        self.assertEquals(3, len(groups["16"]))
        self.assertEquals(1, len(groups["17"]))

        self.assertEquals(1, groups["15"][0].id)
        self.assertEquals(2, groups["16"][0].id)
        self.assertEquals(3, groups["16"][1].id)
        self.assertEquals(4, groups["16"][2].id)
        self.assertEquals(5, groups["17"][0].id)

    def test_groupRedmineByIssueId(self):
        entries = [
            JiraTimeEntry(66, None, None, None, None, 1, "[toggl#21]"),
            JiraTimeEntry(67, None, None, None, None, 2, "[toggl#22]"),
            JiraTimeEntry(68, None, None, None, None, 2, "[toggl#23]"),
            JiraTimeEntry(69, None, None, None, None, 2, "[toggl#24]"),
        ]

        groups = Synchronizer.groupRedmineByIssueId(entries)

        self.assertEquals(2, len(groups))

        self.assertTrue(1 in groups)
        self.assertTrue(2 in groups)

        self.assertEquals(1, len(groups[1]))
        self.assertEquals(3, len(groups[2]))

        self.assertEquals(22, groups[2][0].toggl_id)
        self.assertEquals(23, groups[2][1].toggl_id)
        self.assertEquals(24, groups[2][2].toggl_id)

    def test_sync_single_toggl_no_redmine(self):
        config = MagicMock()
        redmine = JiraHelper(None, None, None, False)
        redmine.get = Mock()
        redmine.put = Mock()
        toggl = TogglHelper("url", None)
        toggl.get = Mock()

        toggl.get.return_value = [
            TogglEntry(
                None,
                3600,
                "2016-01-01T01:01:01",
                17,
                "#987 hard work",
                self.redmine_config,
            )
        ]

        redmine.get.return_value = []

        s = Synchronizer(config, redmine, toggl, None)
        s.start(1)

        toggl.get.assert_called_once_with(1)

        redmine.put.assert_called_once_with(
            issueId="987",
            started="2016-01-01T01:01:01",
            seconds=3600,
            comment="#987 hard work [toggl#17]",
        )

    def test_sync_single_toggl_already_inserted_in_redmine(self):
        class RedmineSpec:
            def get(self):
                pass

        class TogllSpec:
            def get(self, days):
                pass

        redmine = MagicMock(spec_set=RedmineSpec)
        toggl = MagicMock(spec_set=TogllSpec)

        toggl.get.return_value = [
            TogglEntry(
                None,
                3600,
                "2016-01-01T01:01:01",
                17,
                "#987 hard work",
                self.redmine_config,
            )
        ]

        redmine.get.return_value = [
            JiraTimeEntry(
                222,
                "2016-05-01T04:02:22",
                "john doe",
                1,
                "2016-01-01",
                987,
                "#987 hard work [toggl#17]",
            )
        ]

        s = Synchronizer(MagicMock(), redmine, toggl, None)
        s.start(1)

    def test_sync_single_toggl_modified_entry(self):
        redmine = JiraHelper(None, None, None, False)
        redmine.get = Mock()
        redmine.update = Mock()
        toggl = TogglHelper("url", None)
        toggl.get = Mock()

        toggl.get.return_value = [
            TogglEntry(
                None,
                2 * 3600,
                "2016-01-01T01:01:01",
                17,
                "#987 hard work",
                self.redmine_config,
            )
        ]

        redmine.get.return_value = [
            JiraTimeEntry(
                222,
                "2016-05-01T04:02:22",
                "john doe",
                1,
                "2016-01-01T01:01:01",
                "987",
                "#987 hard work [toggl#17]",
            )
        ]

        s = Synchronizer(MagicMock(), redmine, toggl, None)
        s.start(1)

        redmine.update.assert_called_once_with(
            id=222,
            issueId="987",
            started="2016-01-01T01:01:01",
            seconds=2 * 3600,
            comment="#987 hard work [toggl#17]",
        )

    def test_ignore_negative_duration(self):
        """
        Synchronizer should ignore entries with negative durations (pending entries).

		From toggl docs:
           duration: time entry duration in seconds. If the time entry is currently running, the duration attribute contains a negative value, denoting the start
           of the time entry in seconds since epoch (Jan 1 1970). The correct duration can be calculated as current_time + duration, where current_time is the current
           time in seconds since epoch. (integer, required)
        """

        redmine = JiraHelper(None, None, None, False)
        redmine.get = Mock()
        redmine.put = Mock()
        toggl = TogglHelper("url", None)
        toggl.get = Mock()

        toggl.get.return_value = [
            TogglEntry(
                None, 3600, "2016-01-01T01:01:01", 777, "test #333", self.redmine_config
            ),
            TogglEntry(
                None,
                -3600,
                "2016-01-01T01:01:01",
                778,
                "test #334",
                self.redmine_config,
            ),
        ]

        redmine.get.return_value = []

        s = Synchronizer(Mock(), redmine, toggl, None)
        s.start(1)

        toggl.get.assert_called_once_with(1)
        redmine.get.assert_called_once_with("333")

        redmine.put.assert_called_once_with(
            issueId="333",
            started="2016-01-01T01:01:01",
            seconds=3600,
            comment="test #333 [toggl#777]",
        )

    def create_test_entries_pair(self):
        toggl = TogglEntry(
            None, 3600, "2020-01-13T08:11:04+00:00", 777, "test #333", self.redmine_config
        )
        jira = JiraTimeEntry(
            "987654321",
            created_on="2020-01-13T08:11:04.000+00:00",
            user="user",
            seconds=3600,
            started="2020-01-13T08:11:04.000+00:00",
            issue="333",
            comments="test #333 [toggl#777]",
            jira_issue_id="12345",
        )
        return toggl, jira

    def test_equal_exact(self):
        toggl, jira = self.create_test_entries_pair()

        helper = JiraHelper(None, None, None, False)
        sync = Synchronizer(None, helper, None, None)
        self.assertTrue(sync._equal(toggl, jira))

    def test_equal_rounding_to_min(self):
        toggl, jira = self.create_test_entries_pair()
        toggl.seconds += 30

        helper = JiraHelper(None, None, None, False)
        sync = Synchronizer(None, helper, None, None)
        self.assertTrue(sync._equal(toggl, jira))

    def test_equal_diff_time(self):
        toggl, jira = self.create_test_entries_pair()
        toggl.seconds = 120

        helper = JiraHelper(None, None, None, False)
        sync = Synchronizer(None, helper, None, None)
        self.assertFalse(sync._equal(toggl, jira))

    def test_equal_diff_started(self):
        toggl, jira = self.create_test_entries_pair()
        toggl.start = "2016-12-25T01:01:01"

        helper = JiraHelper(None, None, None, False)
        sync = Synchronizer(None, helper, None, None)
        self.assertFalse(sync._equal(toggl, jira))

    def test_equal_diff_comment(self):
        toggl, jira = self.create_test_entries_pair()
        toggl.description = "changed #333"

        helper = JiraHelper(None, None, None, False)
        sync = Synchronizer(None, helper, None, None)
        self.assertFalse(sync._equal(toggl, jira))


if __name__ == "__main__":
    unittest.main()
