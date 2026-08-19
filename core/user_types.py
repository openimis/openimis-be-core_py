import graphene

UT_INTERACTIVE = "INTERACTIVE"
UT_TECHNICAL = "TECHNICAL"
UT_OFFICER = "OFFICER"
UT_CLAIM_ADMIN = "CLAIM_ADMIN"

UserTypeEnum = graphene.Enum(
    "UserTypes",
    [
        (UT_INTERACTIVE, UT_INTERACTIVE),
        (UT_OFFICER, UT_OFFICER),
        (UT_TECHNICAL, UT_TECHNICAL),
        (UT_CLAIM_ADMIN, UT_CLAIM_ADMIN),
    ],
)


def get_user_types(user):
    """Return the user types linked to a core User instance."""
    types = []
    if user.i_user_id is not None:
        types.append(UT_INTERACTIVE)
    if user.officer_id is not None:
        types.append(UT_OFFICER)
    if user.claim_admin_id is not None:
        types.append(UT_CLAIM_ADMIN)
    if user.t_user_id is not None:
        types.append(UT_TECHNICAL)
    return types
