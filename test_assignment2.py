import unittest
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import app


class ModerateContentTests(unittest.TestCase):
    def setUp(self):
        # Small, known lists keep these tests independent of the encrypted data.
        lists = patch.multiple(
            app,
            TIER1_WORDS=["severe"],
            TIER2_PHRASES=["claim prize"],
            TIER3_WORDS=["mild", "rude", "coarse"],
        )
        lists.start()
        self.addCleanup(lists.stop)

    def test_clean_and_empty_content_are_unchanged(self):
        for content in ("", "Hello, world!", "123 !!!"):
            with self.subTest(content=content):
                self.assertEqual(app.moderate_content(content), (content, 0.0))

    def test_tier1_is_case_insensitive_and_matches_whole_words(self):
        for content in ("severe", "A SeVeRe!", "(SEVERE)"):
            with self.subTest(content=content):
                self.assertEqual(
                    app.moderate_content(content),
                    ("[content removed due to severe violation]", 5.0),
                )

    def test_tier1_does_not_match_inside_a_word(self):
        for content in ("unsevere", "severely", "xseverex"):
            with self.subTest(content=content):
                self.assertEqual(app.moderate_content(content), (content, 0.0))

    def test_tier2_is_case_insensitive_and_matches_a_whole_phrase(self):
        for content in ("claim prize", "Please CLAIM Prize!", "(claim prize)"):
            with self.subTest(content=content):
                self.assertEqual(
                    app.moderate_content(content),
                    ("[content removed due to spam/scam policy]", 5.0),
                )

    def test_tier2_does_not_match_inside_words(self):
        for content in ("reclaim prize", "claim prizes"):
            with self.subTest(content=content):
                self.assertEqual(app.moderate_content(content), (content, 0.0))

    def test_tier1_takes_priority_over_all_other_violations(self):
        content = "claim prize mild https://example.com SEVERE"
        self.assertEqual(
            app.moderate_content(content),
            ("[content removed due to severe violation]", 5.0),
        )

    def test_tier2_takes_priority_over_scored_violations(self):
        content = "claim prize mild https://example.com"
        self.assertEqual(
            app.moderate_content(content),
            ("[content removed due to spam/scam policy]", 5.0),
        )

    def test_tier3_does_not_filter_parts_of_words(self):
        content = "milder unmild xrudex"
        self.assertEqual(app.moderate_content(content), (content, 0.0))

    def test_each_tier3_occurrence_adds_two_to_score(self):
        for content, expected, score in (
            ('mild mild', '**** ****', 4.0),
            ('mild mild mild', '**** **** ****', 6.0),
            ('MILD, mild! (MiLd)', '****, ****! (****)', 6.0),
            ('mild mild https://example.com', '**** **** [link removed]', 6.0),
        ):
            with self.subTest(content=content):
                self.assertEqual(app.moderate_content(content), (expected, score))

    def test_each_url_is_filtered_and_scored(self):
        content = "Visit https://example.com/path and http://example.org/page"
        self.assertEqual(
            app.moderate_content(content),
            ("Visit [link removed] and [link removed]", 4.0),
        )

    def test_tier3_and_url_scores_accumulate(self):
        self.assertEqual(
            app.moderate_content("mild https://example.com rude"),
            ("**** [link removed] ****", 6.0),
        )

    def test_capitalization_requires_more_than_fifteen_letters(self):
        for content, score in (("ABCDEFGHIJKLMNO", 0.0), ("ABCDEFGHIJKLMNOP", 0.5)):
            with self.subTest(content=content):
                self.assertEqual(app.moderate_content(content), (content, score))

    def test_capitalization_requires_more_than_seventy_percent_uppercase(self):
        for content, score in (
            ("ABCDEFGHIJKLMNabcdef", 0.0),  # 14 of 20: exactly 70%
            ("ABCDEFGHIJKLMNOabcde", 0.5),  # 15 of 20: 75%
        ):
            with self.subTest(content=content):
                self.assertEqual(app.moderate_content(content), (content, score))

    def test_capitalization_counts_only_letters_and_adds_once(self):
        content = "ABCDEFGHIJKLMNOP 1234567890!!!"
        self.assertEqual(app.moderate_content(content), (content, 0.5))

    def test_capitalization_score_is_added_to_tier3_score(self):
        content = "ABCDEFGHIJKLMNOP mild"
        self.assertEqual(app.moderate_content(content), ("ABCDEFGHIJKLMNOP ****", 2.5))


class UserRiskAnalysisTests(unittest.TestCase):
    def setUp(self):
        # Clone the database for each test so writes never reach the original.
        source_path = Path(__file__).resolve().with_name("database.sqlite")
        source = sqlite3.connect(f"{source_path.as_uri()}?mode=ro", uri=True)
        self.addCleanup(source.close)
        self.db = sqlite3.connect(":memory:", detect_types=sqlite3.PARSE_DECLTYPES)
        self.addCleanup(self.db.close)
        source.backup(self.db)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys = ON")

        db_patch = patch.object(app, "get_db", return_value=self.db)
        db_patch.start()
        self.addCleanup(db_patch.stop)
        context = app.app.app_context()
        context.push()
        self.addCleanup(context.pop)

        self.now = datetime(2026, 1, 31, 12, 0, 0)
        clock = patch.object(app, "datetime")
        clock_mock = clock.start()
        clock_mock.utcnow.return_value = self.now
        self.addCleanup(clock.stop)
        # Treat each piece of test content as its known content score.
        moderation = patch.object(
            app, "moderate_content", side_effect=lambda content: (content, float(content))
        )
        moderation.start()
        self.addCleanup(moderation.stop)

    def create_dummy_user(self, user_id, age_days=30, profile="0"):
        app.query_db(
            "INSERT INTO users (id, username, created_at, profile) VALUES (?, ?, ?, ?)",
            (user_id, f"dummy_user_{user_id}", self.now - timedelta(days=age_days), profile),
        )

    def create_dummy_post(self, user_id, content):
        cursor = self.db.execute(
            "INSERT INTO posts (user_id, content, created_at, community_id) VALUES (?, ?, ?, ?)",
            (user_id, content, self.now, 1),
        )
        return cursor.lastrowid

    def create_dummy_comment(self, user_id, post_id, content):
        self.db.execute(
            "INSERT INTO comments (post_id, user_id, content, created_at) VALUES (?, ?, ?, ?)",
            (post_id, user_id, content, self.now),
        )

    def test_empty_content_scores_zero(self):
        self.create_dummy_user(10000, age_days=0)
        self.assertEqual(app.user_risk_analysis(10000), 0.0)

    def test_profile_only_and_missing_posts_or_comments(self):
        self.create_dummy_user(10000, profile="0.5")
        self.assertAlmostEqual(app.user_risk_analysis(10000), 0.5)
        self.create_dummy_post(10000, "1")
        self.assertAlmostEqual(app.user_risk_analysis(10000), 3.5)

    def test_comments_without_posts_are_included(self):
        self.create_dummy_user(10000)
        self.create_dummy_user(10001)
        post_id = self.create_dummy_post(10001, "0")
        self.create_dummy_comment(10000, post_id, "2")
        self.assertAlmostEqual(app.user_risk_analysis(10000), 2.0)

    def test_weighted_averages_exclude_other_users_content(self):
        self.create_dummy_user(10000, profile="0.5")
        self.create_dummy_user(10001, profile="5")
        post_id = self.create_dummy_post(10000, "0.5")
        self.create_dummy_post(10000, "1.5")
        self.create_dummy_post(10001, "5")
        self.create_dummy_comment(10000, post_id, "0.5")
        self.create_dummy_comment(10000, post_id, "1.5")
        self.create_dummy_comment(10001, post_id, "5")
        self.assertAlmostEqual(app.user_risk_analysis(10000), 4.5)


    def test_score_is_capped_after_age_multiplier(self):
        self.create_dummy_user(10000, age_days=7, profile="4.5")
        self.assertEqual(app.user_risk_analysis(10000), 5.0)
        self.create_dummy_user(10001, age_days=30, profile="5")
        self.assertEqual(app.user_risk_analysis(10001), 5.0)
        self.create_dummy_user(10002, age_days=30, profile="6")
        self.assertEqual(app.user_risk_analysis(10002), 5.0)

if __name__ == "__main__":
    unittest.main()
