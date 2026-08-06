"""Ontology serialization constants shared by collection and analysis."""

TURTLE_PREFIXES = """
@prefix : <http://hisqu.de/rg_ontology/ontology/> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix xml: <http://www.w3.org/XML/1998/namespace/> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix rg: <http://hisqu.de/rg_ontology/ontology/> .
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .
@base <http://hisqu.de/rg_ontology/ontology/> .
""".strip()
