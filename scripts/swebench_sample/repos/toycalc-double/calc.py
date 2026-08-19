"""Toy calculator (double bug) for the offline SWE-bench-Lite sample.

The bundled sample ships one deliberately broken function per repo so the
deterministic craft loop has an observable failing test to converge on.
"""


def double(x):
    return x / 2


def greeting(name):
    return "hello " + name
