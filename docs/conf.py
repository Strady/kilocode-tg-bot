"""Sphinx configuration for the kilocode-tg-bot documentation."""

import os
import sys

sys.path.insert(0, os.path.abspath(".."))

project = "kilocode-tg-bot"
copyright = "2026, Strady"
author = "Strady"
release = "0.1.0"

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.intersphinx",
    "sphinx_autodoc_typehints",
    "sphinx.ext.viewcode",
]

templates_path = ["_templates"]

exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

# aiogram's pydantic models fail `model_rebuild` when imported under Sphinx's
# autodoc dynamic importer; mock the package so we can still document the bot's
# own modules (their signatures/docstrings) without importing it.
autodoc_mock_imports = ["aiogram"]

# pydantic's ``Field`` imports pull in an unresolvable ``JsonValue`` forward
# reference inside ``pydantic.fields``; it is not part of our docs.
suppress_warnings = ["sphinx_autodoc_typehints.forward_reference"]

autodoc_default_options = {
    "members": True,
    "undoc-members": True,
    "show-inheritance": True,
    "member-order": "bysource",
}

autodoc_typehints = "description"

always_document_param_types = True
typehints_defaults = "comma"

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "pydantic": ("https://docs.pydantic.dev/latest/", None),
}

html_theme = "furo"
html_static_path = ["_static"]
html_title = "kilocode-tg-bot"

root_doc = "index"
