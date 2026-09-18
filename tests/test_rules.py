from namescope.rules import validate_username


def test_github_rules() -> None:
    assert validate_username("github", "abc").valid
    assert validate_username("github", "09f").valid
    assert validate_username("github", "a-b").valid
    assert not validate_username("github", "-abc").valid
    assert not validate_username("github", "abc-").valid
    assert not validate_username("github", "a--b").valid


def test_instagram_rules() -> None:
    assert validate_username("instagram", "1a2").valid
    assert validate_username("instagram", "a_b.c").valid
    assert not validate_username("instagram", "122").valid
    assert not validate_username("instagram", ".abc").valid
    assert not validate_username("instagram", "abc.").valid
    assert not validate_username("instagram", "a..b").valid


def test_telegram_rules() -> None:
    assert validate_username("telegram", "abcde").valid
    assert validate_username("telegram", "a_123").valid
    assert not validate_username("telegram", "1abcd").valid
    assert not validate_username("telegram", "_abcd").valid
    assert not validate_username("telegram", "abcd_").valid
    assert not validate_username("telegram", "abcd").valid
