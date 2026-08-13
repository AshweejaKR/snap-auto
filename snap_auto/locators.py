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
    """web.snapchat.com has no dedicated friends page (confirmed via a Playwright
    codegen session against a real, logged-in account): every friend appears as a
    row in the chat list instead. get_fnd_list() in client.py derives its dicts
    from ChatLocators.chat_list_item rather than a separate selector set, so this
    class intentionally has no fields. If a broader friend source shows up later
    (e.g. the "New Chat" dialog's contact picker, which the same codegen session
    touched via a still-unlabeled search box and `div.nth(3)` result — too fragile
    to use as-is), add selectors here then.
    """


class ChatLocators:
    # Confirmed via Playwright codegen against a real, logged-in session: every
    # chat/friend row on the default view is a <button> whose accessible name
    # (and text content) is "{username} , {status}", e.g. "Anagha Hegde , New
    # Snap", "kiran , Received", "Simple_02 , New Snap on mobile". client.py
    # splits that combined text on " , " (see _parse_chat_row) rather than
    # scraping username/preview from separate sub-elements, since no distinct
    # sub-selectors are confirmed yet. There's no evidence of a separate nav tab
    # for the chat list (it appears to be the default view after login), so
    # nav_button is left as a no-op TODO.
    nav_button = "TODO"
    # `:has-text(",")` is a heuristic: every observed chat row's accessible name
    # contains " , ", and neither "New Chat" nor "View friend requests" (the
    # other buttons seen in the same session) do. Re-tighten with a real
    # container/class selector (via scripts/inspect_dom.py) if this starts
    # matching unrelated buttons.
    chat_list_container = 'button:has-text(",")'
    chat_list_item = 'button:has-text(",")'
    # Row text is "{username} , {status}", parsed in client.py — no confirmed
    # separate DOM elements for these yet.
    chat_item_username = "TODO"
    chat_item_preview = "TODO"
    chat_item_timestamp = "TODO"
    # Presence-based (e.g. an unread-dot element); count() > 0 means unread.
    # Status text alone ("New Snap" vs "Received") might imply unread state, but
    # that's a product-semantics guess, not a confirmed DOM signal — left TODO.
    chat_item_unread_marker = "TODO"
    # Opportunistic: name of a data-* attribute (e.g. "data-user-id") on
    # chat_list_item that exposes an internal id, if the DOM has one at all.
    chat_item_user_id_attribute = "TODO"
    new_chat_button = 'role=button[name="New Chat"]'
    view_friend_requests_button = 'role=button[name="View friend requests"]'
    # Message thread UI (Phase 3), not the chat list itself.
    message_input = "TODO"
    send_button = "TODO"
    message_bubble = "TODO"
