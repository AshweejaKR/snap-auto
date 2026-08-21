"""Central selector candidates for Snapchat Web.

Selectors are ordered from semantic/stable to compatibility fallback. The client
chooses the first visible match, which lets it support both ``www.snapchat.com/web``
and the older ``web.snapchat.com`` UI without scattering selectors through logic.
"""

from __future__ import annotations

from collections.abc import Sequence

SelectorSpec = str | Sequence[str]


class LoginLocators:
    username_input = (
        'input[autocomplete="username"]',
        'input[name*="user" i]',
        'input[type="email"]',
        'input[type="text"]',
        "role=textbox",
    )
    username_submit_button = (
        '[data-testid*="username" i][type="submit"]',
        '[data-testid*="login" i][type="submit"]',
        'button[type="submit"]',
    )
    password_input = (
        'input[autocomplete="current-password"]',
        'input[type="password"]',
        "role=textbox[name=/password/i]",
    )
    password_submit_button = (
        '[data-testid="password-submit-button"]',
        '[data-testid*="password" i][type="submit"]',
        'button[type="submit"]',
    )
    post_login_dismiss_button = (
        "role=button[name=/not now/i]",
        'button:has-text("Not now")',
    )
    otp_input = (
        'input[autocomplete="one-time-code"]',
        'input[inputmode="numeric"]',
        'input[name*="code" i]',
        'input[data-testid*="otp" i]',
    )
    otp_submit_button = (
        '[data-testid*="otp" i][type="submit"]',
        '[data-testid*="code" i][type="submit"]',
        'button[type="submit"]',
    )
    login_error_banner = (
        '[role="alert"]',
        '[aria-live="assertive"]',
        '[data-testid*="error" i]',
        "text=/incorrect|invalid|could not|try again|something went wrong/i",
    )
    logged_in_marker = (
        '[role="button"][aria-labelledby*="title-"]',
        '[role="link"][aria-labelledby*="title-"]',
        '[aria-label*="new chat" i]',
        '[placeholder*="search" i]',
        ".Titq2",
    )
    account_menu_button = (
        'button[aria-label*="profile" i]',
        'button[aria-label*="bitmoji" i]',
        '[role="button"][aria-label*="account" i]',
        ".Titq2",
    )
    logout_button = (
        'a[href*="logout" i]',
        "role=button[name=/log out|logout/i]",
        "role=link[name=/log out|logout/i]",
        'a:has-text("Log Out")',
    )


class FriendsLocators:
    """Friends are derived from chats; Snapchat Web has no full friends page."""


class ChatLocators:
    nav_button = (
        'a[href$="/web"]',
        "role=button[name=/chat|chats/i]",
    )
    search_input = (
        'input[role="searchbox"]',
        '[role="searchbox"] input',
        'input[aria-label*="search" i]',
        'input[placeholder*="search" i]',
    )
    chat_list_item = (
        '[role="button"][aria-labelledby*="title-"]',
        '[role="link"][aria-labelledby*="title-"]',
        'button:has-text(",")',
    )
    chat_list_dom_selector = (
        '[role="button"][aria-labelledby*="title-"]'
        ', [role="link"][aria-labelledby*="title-"]'
    )
    chat_item_username = 'span[id^="title-"]'
    chat_item_preview = '[id^="status-"]'
    chat_item_timestamp = "time"
    chat_item_unread_marker = (
        '[aria-label*="unread" i]',
        '[class*="unread" i]',
    )
    new_chat_button = "role=button[name=/new chat/i]"
    view_friend_requests_button = "role=button[name=/view friend requests/i]"

    conversation_root = 'ul[id^="cv-"]'
    message_input = (
        '[contenteditable="true"][aria-label*="chat" i]',
        '[contenteditable="true"][data-placeholder*="chat" i]',
        'textarea[aria-label*="chat" i]',
        'input[aria-label*="chat" i]',
        '[contenteditable="true"]',
    )
    send_button = (
        'button[aria-label*="send" i]',
        '[role="button"][aria-label*="send" i]',
        'button[title*="send" i]',
    )
    message_bubble = 'ul[id^="cv-"] > li'
    message_bubble_sender = "header"
    message_bubble_text = (
        '[dir="auto"]',
        '[data-testid*="message" i]',
    )
    message_bubble_timestamp = "time"
    message_bubble_read_marker = (
        '[aria-label*="seen" i]',
        '[aria-label*="opened" i]',
        '[aria-label*="delivered" i]',
        "text=/seen|opened|read|delivered|sent/i",
    )
    message_media = "img, video, canvas"
