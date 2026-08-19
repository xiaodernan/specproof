from toycalc import greeting, multiply


def test_multiply():
    assert multiply(2, 3) == 6
    assert multiply(-2, 3) == -6


def test_greeting():
    assert greeting() == "hi"
