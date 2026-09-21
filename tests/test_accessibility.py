from pathlib import Path
from html.parser import HTMLParser
import unittest


ROOT = Path(__file__).parents[1]
TEMPLATE_NAMES = ("username", "password", "otp", "welcome")


class PageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []
        self.forms = []
        self.inputs = []
        self.labels = []
        self.scripts = []
        self.body_attributes = {}

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        self.tags.append((tag, attributes))
        if tag == "form":
            self.forms.append(attributes)
        elif tag == "input":
            self.inputs.append(attributes)
        elif tag == "label":
            self.labels.append(attributes)
        elif tag == "script":
            self.scripts.append(attributes)
        elif tag == "body":
            self.body_attributes = attributes


def load_template(name):
    parser = PageParser()
    parser.feed((ROOT / "templates" / f"{name}.html").read_text())
    return parser


class AccessibilityTemplateTests(unittest.TestCase):
    def test_authentication_templates_have_one_labeled_main_input(self):
        expected_inputs = {"username": "username", "password": "password", "otp": "otp"}

        for name, input_id in expected_inputs.items():
            page = load_template(name)
            self.assertEqual(len(page.inputs), 1)
            self.assertEqual(page.inputs[0].get("id"), input_id)
            self.assertIn("autofocus", page.inputs[0])
            self.assertIn({"for": input_id}, page.labels)

    def test_authentication_forms_use_post_and_expected_actions(self):
        expected_actions = {
            "username": "/login",
            "password": "/login/password",
            "otp": "/login/otp",
        }

        for name, action in expected_actions.items():
            form = load_template(name).forms[0]
            self.assertEqual(form["method"].lower(), "post")
            self.assertEqual(form["action"], action)

        welcome_form = load_template("welcome").forms[0]
        self.assertEqual(welcome_form["method"].lower(), "post")
        self.assertEqual(welcome_form["action"], "/logout")

    def test_all_pages_include_accessibility_script_and_welcome_has_no_input(self):
        for name in TEMPLATE_NAMES:
            page = load_template(name)
            self.assertIn({"src": "/static/accessibility.js"}, page.scripts)

        self.assertEqual(load_template("welcome").inputs, [])

    def test_speech_prompts_do_not_read_password_or_otp_values(self):
        password = load_template("password")
        otp = load_template("otp")

        self.assertEqual(
            password.body_attributes["data-speech-prompt"], "Type your password now."
        )
        self.assertEqual(
            otp.body_attributes["data-speech-prompt"],
            "Type the six digit code sent to your email.",
        )

        script = (ROOT / "static" / "accessibility.js").read_text()
        self.assertNotIn("input.value", script)
        self.assertNotIn("password", script.lower())
        self.assertNotIn("otp", script.lower())

    def test_otp_page_has_keyboard_resend_and_accessible_message_regions(self):
        page = load_template("otp")
        self.assertIn({"action": "/login/otp/resend", "method": "post"}, page.forms)
        markup = (ROOT / "templates" / "otp.html").read_text()
        self.assertIn('role="alert"', markup)
        self.assertIn('role="status"', markup)

    def test_accessibility_script_speaks_status_or_error_before_page_prompt(self):
        script = (ROOT / "static" / "accessibility.js").read_text()
        self.assertIn('[role="alert"], [role="status"]', script)
        self.assertIn("announcement ? announcement.textContent.trim() : prompt", script)


if __name__ == "__main__":
    unittest.main()
