"""Input rules of the bot's registration wizard (pure functions, no API)."""

from bot import texts
from bot.registration import Step, check_name, normalize_code, suggested_name


def test_login_code_is_recognised_with_dash_space_or_nothing() -> None:
    assert normalize_code("LOMI-7241") == "LOMI-7241"
    assert normalize_code("lomi 7241") == "LOMI-7241"
    assert normalize_code(" LOMI7241 ") == "LOMI-7241"
    assert normalize_code("Сандро") is None
    assert normalize_code("LOMI-724") is None


def test_check_name_accepts_and_tidies_text() -> None:
    assert check_name("  Нино   Церетели ", Step.PARENT) == ("Нино Церетели", None)
    assert check_name("Сандро", Step.CHILD) == ("Сандро", None)
    # A login code typed at step one is just a name; the wizard shows it back.
    assert check_name("LOMI-7241", Step.PARENT) == ("LOMI-7241", None)


def test_check_name_asks_again_on_bad_input() -> None:
    assert check_name(None, Step.PARENT) == (None, texts.NEED_TEXT["parent"])
    assert check_name("   ", Step.CHILD) == (None, texts.NEED_TEXT["child"])
    assert check_name("/report", Step.PARENT) == (None, texts.COMMAND_FIRST["parent"])
    assert check_name("/unknown", Step.CHILD) == (None, texts.COMMAND_FIRST["child"])
    name, reply = check_name("x" * 101, Step.PARENT)
    assert name is None and reply == texts.too_long_text(101)
    assert check_name("x" * 100, Step.PARENT)[0] == "x" * 100


def test_suggested_name_from_the_telegram_profile() -> None:
    assert suggested_name("Микаел", "Казарян") == "Микаел Казарян"
    assert suggested_name("Микаел", None) == "Микаел"
    assert suggested_name("  Nino ", " ") == "Nino"
    assert suggested_name("🙂", None) is None
    assert suggested_name("", None) is None
    assert suggested_name("x" * 64, "y" * 64) is None
