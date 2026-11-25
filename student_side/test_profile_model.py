from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase

from .models import (
    DUPLICATE_ID_MESSAGE,
    LearnerCredential,
    SetupCode,
    StudentProfile,
    is_valid_student_id,
    normalize_student_id,
)


class StudentIdTests(TestCase):

    def test_normalize_trims_spaces_and_lowercases(self):
        self.assertEqual(normalize_student_id("  S-12345 "), "s-12345")

    def test_valid_formats(self):
        self.assertTrue(is_valid_student_id("s-12345"))
        self.assertTrue(is_valid_student_id("s-123456"))

    def test_invalid_formats(self):
        for bad in ["s-1234", "s-1234567", "s12345", "x-12345", "s-12a45", "s-12345 extra", ""]:
            self.assertFalse(is_valid_student_id(bad), bad)

    def test_clean_rejects_wrong_format(self):
        profile = StudentProfile(student_id="12345")
        with self.assertRaises(ValidationError) as error:
            profile.full_clean()
        self.assertIn("student_id", error.exception.message_dict)

    def test_save_stores_normalized_id(self):
        profile = StudentProfile.objects.create(student_id=" S-12345 ")
        profile.refresh_from_db()
        self.assertEqual(profile.student_id, "s-12345")

    def test_database_rejects_duplicate_id(self):
        StudentProfile.objects.create(student_id="s-12345")
        with self.assertRaises(IntegrityError):
            StudentProfile.objects.create(student_id=" S-12345")

    def test_duplicate_gives_the_agreed_message(self):
        StudentProfile.objects.create(student_id="s-12345")
        second = StudentProfile(student_id="S-12345 ")
        with self.assertRaises(ValidationError) as error:
            second.full_clean()
        self.assertEqual(error.exception.message_dict["student_id"], [DUPLICATE_ID_MESSAGE])

    def test_updating_same_profile_is_not_a_duplicate(self):
        profile = StudentProfile.objects.create(student_id="s-12345")
        profile.commitment = "high"
        profile.full_clean()  # must not raise
        profile.save()
        self.assertEqual(StudentProfile.objects.count(), 1)


class CredentialTests(TestCase):

    def test_no_password_field_on_student_profile(self):
        names = [field.name for field in StudentProfile._meta.get_fields()]
        self.assertFalse(any("password" in name for name in names if name != "credential"))

    def test_password_is_stored_as_hash(self):
        profile = StudentProfile.objects.create(student_id="s-12345")
        credential = LearnerCredential.set_for(profile, "Secret-123")
        self.assertNotIn("Secret-123", credential.password_hash)
        self.assertTrue(profile.has_password)

    def test_check_login(self):
        profile = StudentProfile.objects.create(student_id="s-12345")
        LearnerCredential.set_for(profile, "Secret-123")
        self.assertEqual(LearnerCredential.check_login(" S-12345 ", "Secret-123"), profile)
        self.assertIsNone(LearnerCredential.check_login("s-12345", "wrong"))
        self.assertIsNone(LearnerCredential.check_login("s-99999", "Secret-123"))

    def test_new_password_replaces_old_and_keeps_profile(self):
        profile = StudentProfile.objects.create(student_id="s-12345", commitment="high")
        LearnerCredential.set_for(profile, "Old-pass-1")
        LearnerCredential.set_for(profile, "New-pass-2")
        self.assertEqual(LearnerCredential.objects.count(), 1)
        self.assertIsNone(LearnerCredential.check_login("s-12345", "Old-pass-1"))
        found = LearnerCredential.check_login("s-12345", "New-pass-2")
        self.assertEqual(found.commitment, "high")


class SetupCodeTests(TestCase):

    def test_code_works_once(self):
        raw_code = SetupCode.issue(" S-12345 ")
        self.assertNotEqual(SetupCode.objects.get(student_id="s-12345").code_hash, raw_code)
        self.assertTrue(SetupCode.verify("s-12345", raw_code))
        self.assertFalse(SetupCode.verify("s-12345", "WRONG123"))
        self.assertFalse(SetupCode.verify("s-99999", raw_code))
        SetupCode.objects.get(student_id="s-12345").mark_used()
        self.assertFalse(SetupCode.verify("s-12345", raw_code))

    def test_new_code_replaces_old_one(self):
        old_code = SetupCode.issue("s-12345")
        new_code = SetupCode.issue("s-12345")
        self.assertFalse(SetupCode.verify("s-12345", old_code))
        self.assertTrue(SetupCode.verify("s-12345", new_code))


class StudentProfileFormTests(TestCase):

    def test_form_shows_friendly_errors(self):
        from .forms import StudentProfileForm

        StudentProfile.objects.create(student_id="s-001069")
        duplicate = StudentProfileForm(data={"student_id": " S-001069 "})
        wrong = StudentProfileForm(data={"student_id": "12345"})
        self.assertFalse(duplicate.is_valid())
        self.assertFalse(wrong.is_valid())
        self.assertEqual(duplicate.errors["student_id"], [DUPLICATE_ID_MESSAGE])
        self.assertIn("student_id", wrong.errors)
