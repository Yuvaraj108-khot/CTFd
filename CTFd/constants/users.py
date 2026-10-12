from collections import namedtuple

# TODO: CTFd 4.0. Consider changing to a dataclass
UserAttrsFields = [
    "id",
    "oauth_id",
    "name",
    "email",
    "type",
    "secret",
    "website",
    "affiliation",
    "country",
    "bracket_id",
    "hidden",
    "banned",
    "verified",
    "language",
    "team_id",
    "created",
    "change_password",
    "usn",
    "college_email",
    "year_of_study",
    "department",
    "profile_completed",
]
UserAttrs = namedtuple(  # type: ignore
    "UserAttrs", UserAttrsFields, defaults=(None,) * len(UserAttrsFields)
)


class _UserAttrsWrapper:
    def __getattr__(self, attr):
        from CTFd.utils.user import get_current_user_attrs

        attrs = get_current_user_attrs()
        return getattr(attrs, attr, None)

    @property
    def place(self):
        from CTFd.utils.user import get_user_place

        return get_user_place(user_id=self.id)

    @property
    def score(self):
        from CTFd.utils.user import get_user_score

        return get_user_score(user_id=self.id)

    @property
    def filled_all_required_fields(self):
        if self.type == "admin":
            return True
        return bool(
            self.name and str(self.name).strip() and
            self.usn and str(self.usn).strip() and
            self.college_email and str(self.college_email).strip() and
            self.year_of_study and str(self.year_of_study).strip() and
            self.department and str(self.department).strip() and
            self.profile_completed
        )


User = _UserAttrsWrapper()
