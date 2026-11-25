import re  # NEW: regular expressions
import secrets  # NEW

from django.contrib.auth.hashers import check_password, make_password  # NEW
from django.core.exceptions import ValidationError  # NEW
from django.db import models
from django.utils import timezone  # NEW

# NEW: Student ID format: small "s", a dash, then 5 or 6 digits. Examples: s-12345, s-001069
STUDENT_ID_PATTERN = r"s-[0-9]{5,6}"


# NEW: same wording as Gerda's form, so the learner sees one consistent message
DUPLICATE_ID_MESSAGE = "This student ID already has a profile. Use “Update my profile” instead."


# NEW: the one team rule for cleaning student IDs. Everyone imports this.
def normalize_student_id(value):
    """Team rule: remove spaces at the start and end, then use small letters."""
    if value is None:
        return ""
    return str(value).strip().lower()


# NEW: the format check, using the regular expression above
def is_valid_student_id(value):
    """True if the (already normalized) ID matches the whole pattern."""
    return re.fullmatch(STUDENT_ID_PATTERN, value) is not None


class Task(models.Model):
    name = models.CharField(max_length=200)
    active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class StudentProfile(models.Model):
    student_id = models.CharField(max_length=200)

    availability_monday = models.CharField(max_length=200, blank=True)
    availability_tuesday = models.CharField(max_length=200, blank=True)
    availability_wednesday = models.CharField(max_length=200, blank=True)
    availability_thursday = models.CharField(max_length=200, blank=True)
    availability_friday = models.CharField(max_length=200, blank=True)
    availability_saturday = models.CharField(max_length=200, blank=True)
    availability_sunday = models.CharField(max_length=200, blank=True)

    commitment = models.CharField(max_length=20, blank=True)
    educational_background = models.CharField(max_length=200, blank=True)
    professional_background = models.CharField(max_length=200, blank=True)
    age = models.PositiveIntegerField(null=True, blank=True)
    gender = models.CharField(max_length=20, blank=True)
    experience_level = models.CharField(max_length=20, blank=True)
    lead_preference = models.CharField(max_length=20, blank=True)
    preferred_tasks = models.ManyToManyField(Task, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["student_id"],
                name="unique_student_id",
                violation_error_message=DUPLICATE_ID_MESSAGE,
            ),
        ]

    # NEW: friendly checks, used by forms and full_clean()
    def clean(self):
        super().clean()
        self.student_id = normalize_student_id(self.student_id)
        if not self.student_id:
            raise ValidationError({"student_id": "Enter your student ID."})
        if not is_valid_student_id(self.student_id):
            raise ValidationError(
                {"student_id": "Enter your student ID like s-123456 (small s, dash, 5 or 6 digits)."}
            )
        already_used = StudentProfile.objects.filter(
            student_id=self.student_id
        ).exclude(pk=self.pk)
        if already_used.exists():
            raise ValidationError({"student_id": DUPLICATE_ID_MESSAGE})

    # NEW: always save the cleaned-up ID, whoever saves the profile
    def save(self, *args, **kwargs):
        self.student_id = normalize_student_id(self.student_id)
        super().save(*args, **kwargs)

    # NEW: True once the learner has chosen a password (used by the admin)
    @property
    def has_password(self):
        return LearnerCredential.objects.filter(profile=self).exists()

    def __str__(self):
        return self.student_id


# NEW
class SetupCode(models.Model):
    """A one-time code a teacher gives a student for their first registration."""

    student_id = models.CharField(max_length=200, unique=True)
    code_hash = models.CharField(max_length=128, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    used_at = models.DateTimeField(null=True, blank=True)

    def save(self, *args, **kwargs):
        self.student_id = normalize_student_id(self.student_id)
        super().save(*args, **kwargs)

    @classmethod
    def issue(cls, student_id):
        """Create (or replace) the code for one student and return it ONCE."""
        raw_code = secrets.token_hex(4).upper()  # e.g. 'A3F09C1B'
        setup, _ = cls.objects.get_or_create(student_id=normalize_student_id(student_id))
        setup.code_hash = make_password(raw_code)
        setup.used_at = None
        setup.save()
        return raw_code

    @classmethod
    def verify(cls, student_id, raw_code):
        """True if this student has an unused setup code and it matches."""
        setup = cls.objects.filter(student_id=normalize_student_id(student_id)).first()
        return setup is not None and setup.check_code(raw_code)

    def check_code(self, raw_code):
        if self.used_at is not None or not self.code_hash:
            return False
        return check_password(raw_code, self.code_hash)

    def mark_used(self):
        self.used_at = timezone.now()
        self.save(update_fields=["used_at"])

    def __str__(self):
        return f"Setup code for {self.student_id}"


# NEW: the learner's password lives here, NOT on StudentProfile (Gerda's design)
class LearnerCredential(models.Model):
    """The password hash for one learner, linked one-to-one to their profile."""

    profile = models.OneToOneField(
        StudentProfile, on_delete=models.CASCADE, related_name="credential"
    )
    password_hash = models.CharField(max_length=128, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    @classmethod
    def set_for(cls, profile, raw_password):
        """Create the password, or replace it (e.g. after a new setup code)."""
        credential, _ = cls.objects.get_or_create(profile=profile)
        credential.password_hash = make_password(raw_password)
        credential.save()
        return credential

    @classmethod
    def check_login(cls, student_id, raw_password):
        """Return the StudentProfile if ID and password match, otherwise None."""
        credential = (
            cls.objects.select_related("profile")
            .filter(profile__student_id=normalize_student_id(student_id))
            .first()
        )
        if credential is None:
            make_password(raw_password)  # takes the same time, so nobody learns which IDs exist
            return None
        if check_password(raw_password, credential.password_hash):
            return credential.profile
        return None

    def __str__(self):
        return f"Password for {self.profile.student_id}"
