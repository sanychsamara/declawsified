"""Facet classifiers — one module per facet, each exporting at least one
class that implements `FacetClassifier` (see `.base`).

The pipeline does not import from this package directly; it receives a list
of classifier instances from `declawsified_core.registry.default_classifiers()`.
"""
