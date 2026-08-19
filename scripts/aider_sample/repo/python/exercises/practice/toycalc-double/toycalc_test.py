from toycalc import double, greeting


def test_double():
    assert double(2) == 4
    assert double(-3) == -6


def test_greeting():
    assert greeting() == "hi"
