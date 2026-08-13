"""CSS/text selectors for web.snapchat.com, isolated from page logic.

Page Object Model: UI changes should only ever require editing this file,
not client.py. Values below are placeholders pending Phase 1 DOM inspection.
"""


class LoginLocators:
    # Login is a multi-step wizard: a username-only page, then (after
    # submitting) a separate navigation to a password-only page.
    #
    # The username step's UI is NOT stable across sessions: two consecutive
    # logins recorded in the same codegen run showed the username field's
    # accessible name in both English ("Username or email address" /
    # "Username or Email") and Hindi ("यूज़रनेम या ईमेल पता"), and the
    # submit button's label as both "Log in" and "Next" (likely locale
    # detection / A/B variants). Selectors below deliberately avoid matching
    # on that translated text.
    username_input = "role=textbox"  # only one textbox on this page, regardless of label language
    username_submit_button = 'button[type="submit"]'  # best-effort guess independent of "Log in"/"Next" label; re-check via devtools if login stalls here
    password_input = 'role=textbox[name="Password"]'
    password_submit_button = '[data-testid="password-submit-button"]'
    # Post-login nag screen (e.g. "turn on notifications?") seen on at least
    # one account; dismissed best-effort, not required for login to count as
    # successful.
    post_login_dismiss_button = 'role=button[name="Not now"]'
    # Not yet observed against a real account (this test account has no 2FA
    # challenge) — fill in once a login actually triggers one.
    otp_input = "TODO"
    otp_submit_button = "TODO"
    login_error_banner = "TODO"
    # Profile/avatar button in the top bar; present only when logged in, and
    # doubles as the trigger that opens the menu containing "Log Out". Class
    # name looks like a generated/hashed CSS-module identifier (".Titq2") —
    # fragile across deploys; re-capture via codegen if this starts failing.
    logged_in_marker = ".Titq2"
    account_menu_button = ".Titq2"
    logout_button = 'a:has-text("Log Out")'


class FriendsLocators:
    friend_list_container = "TODO"
    friend_list_item = "TODO"
    friend_name = "TODO"


class ChatLocators:
    chat_list_container = "TODO"
    chat_list_item = "TODO"
    message_input = "TODO"
    send_button = "TODO"
    message_bubble = "TODO"
