"""CLI package for SpecProof.

The Click group lives in cli.specproof.main. This package deliberately does
NOT import it (a package-level import of a runpy entry module triggers a
RuntimeWarning and an import-order tangle).
"""
