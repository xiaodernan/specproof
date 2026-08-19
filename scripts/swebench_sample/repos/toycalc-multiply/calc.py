"""Toy calculator (multiply bug) for the offline SWE-bench-Lite sample.

This instance has NO deterministic fix rule registered, so the harness must
report it as honestly unresolved ("no fix produced") — never fabricated.
"""


def multiply(a, b):
    return a + b


def greeting(name):
    return "hello " + name
