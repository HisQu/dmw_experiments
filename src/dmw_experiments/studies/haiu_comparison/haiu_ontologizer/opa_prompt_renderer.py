"""Versioned local rendering of the locked OPA prompt structure.

The standalone condition deliberately has no runtime dependency on OPA.  This
module is a narrow, auditable transcription of the shared OPA prompt sections
from ``src/opa/create_prompt.py`` at the recorded source commit and content
hash.  The two additions for the standalone condition are explicit: raw regest
text and the historian-curated annotation guideline.
"""

from __future__ import annotations

from dmw_experiments.studies.haiu_comparison.model.traces import (
    PromptBundle,
    RegestText,
)


OPA_PROMPT_SOURCE_PATH = "src/opa/create_prompt.py"
OPA_PROMPT_SOURCE_COMMIT = "fbe22fa122f33cd0c9dd77785f570828cd33f505"
OPA_PROMPT_SOURCE_SHA256 = (
    "882647dd37f722d2e1563260ff74deb31041e84f77fe8b79205ab8d96c554b90"
)
OPA_PROMPT_RENDERER_VERSION = "opa-create-prompt-v1"
INTENTIONAL_STANDALONE_ADDITIONS = (
    "raw_regest_text",
    "historian_annotation_guideline",
)


PLANNER_SYSTEM = "\n".join(
    [
        "Du bist eine Expertin fuer Ontologie-Engineering im Kontext der Digital Humanities (Repertorium Germanicum).",
        "Deine Aufgabe ist ein Modellierungsplan: praezise Entscheidungen, nachvollziehbar begruendet, ohne Code.",
        "",
        "Grundsaetze:",
        "- Historikerinnen-Vorgaben haben hoechste Prioritaet.",
        "- Vollstaendigkeit: Die Petentenvita mit Kopf und Regesten/Rechtsvorgaengen (und ggf. Annotationen) muss vollstaendig abgedeckt werden.",
        "- Strikte Konsistenz: Falls Referenzontologie oder Beispiele gegeben sind, halte dich stringent an deren Muster.",
        "- Output: nur Markdown gemaess Formatvorgaben.",
    ]
)

TURTLE_SYSTEM = "\n".join(
    [
        "Du bist eine Expertin fuer RDF und Turtle.",
        "Du implementierst den Modellierungsplan als eine merge-sichere Turtle-Datei (TTL).",
        "",
        "Grundsaetze:",
        "- Strikte Formatdisziplin: nur TTL, keine Prosa.",
        "- Strikte Konsistenz: Falls Referenzontologie oder Beispiele gegeben sind, uebernimm deren Benennungen und Muster.",
        "- Selbsttragendes Snippet: TBox fuer verwendete Terme und komplette ABox fuer die Petentenvita.",
    ]
)


def build_stage1_prompts(
    *,
    regest: RegestText,
    historian_input: str,
    annotation_guidelines: str,
    retrieved_turtle: str,
    allow_text_interpretation: bool,
) -> PromptBundle:
    """Render the standalone planner with OPA-equivalent shared sections.

    :param regest: Raw source text, intentionally added for standalone use.
    :param historian_input: Shared historian-owned ontology instruction.
    :param annotation_guidelines: Curated guidance, intentionally added here.
    :param retrieved_turtle: Exact Turtle retrieved by Haiu before Stage 1.
    :param allow_text_interpretation: Locked interpretation policy.
    :return: OPA-structure-compatible Stage-1 prompt pair.
    """
    return PromptBundle(
        system=PLANNER_SYSTEM,
        user=_assemble(
            [
                _role_and_objective(
                    "Planner-Agent",
                    "Erstelle einen entscheidungsorientierten Modellierungsplan in Markdown. Kein TTL.",
                ),
                _historian_directives(historian_input),
                _raw_regest_text(regest),
                _annotation_guideline(annotation_guidelines),
                _context_resources(retrieved_turtle),
                _planner_task(allow_text_interpretation),
            ]
        ),
    )


def build_stage2_prompts(
    *, regest: RegestText, allow_text_interpretation: bool
) -> PromptBundle:
    """Render same-thread Turtle coding instructions matching locked OPA.

    :param regest: Identifier retained as OPA's context anchor.
    :param allow_text_interpretation: Locked interpretation policy.
    :return: OPA-structure-compatible Stage-2 prompt pair.
    """
    return PromptBundle(
        system=TURTLE_SYSTEM,
        user=_assemble(
            [
                _role_and_objective(
                    "TTL-Coder-Agent",
                    "Uebersetze den Stage-1-Plan in eine einzige Turtle-Datei (TTL). Keine Prosa.",
                ),
                "\n".join(
                    [
                        "# Bindende Grundlage aus diesem Thread",
                        "Nutze den Modellierungsplan aus Stage 1 in diesem Thread als bindend.",
                        "Erfinde keine neuen Inhalte, sondern implementiere den vorhandenen Plan deterministisch.",
                    ]
                ),
                "\n".join(
                    [
                        "# Kontextanker",
                        f"- Petentenvita-ID: `{regest.regest_id}`",
                    ]
                ),
                _turtle_task(allow_text_interpretation),
            ]
        ),
    )


def _assemble(parts: list[str | None]) -> str:
    """Join non-empty OPA prompt sections with its standard separator."""
    return "\n\n".join(part.strip() for part in parts if part and part.strip())


def _role_and_objective(title: str, objective: str) -> str:
    """Render OPA's shared role/objective section."""
    return "\n".join(["# ROLLE UND ZIEL", f"**{title}**", objective])


def _historian_directives(historian_input: str) -> str | None:
    """Render OPA's historian-directive heading without changing content."""
    cleaned = historian_input.strip()
    if not cleaned:
        return None
    return "\n".join(
        ["# Historikerinnen-Vorgaben (hoechste Prioritaet)", cleaned]
    )


def _raw_regest_text(regest: RegestText) -> str:
    """Render raw text as the first explicit standalone-only addition."""
    parts = [
        "# Petentenvita (Textgrundlage)",
        "## Rohregest (nur Standalone-Bedingung)",
        f"**Petentenvita-ID:** `{regest.regest_id}`",
        "",
        "**Kopf:**",
        "```",
        regest.header,
        "```",
    ]
    for index, subentry in enumerate(regest.subentries, start=1):
        parts.extend(
            [
                "",
                f"**Regest/Rechtsvorgang {index}:**",
                "```",
                subentry,
                "```",
            ]
        )
    return "\n".join(parts)


def _annotation_guideline(annotation_guidelines: str) -> str | None:
    """Render the second explicit standalone-only addition."""
    cleaned = annotation_guidelines.strip()
    if not cleaned:
        return None
    return "\n".join(
        [
            "# Historikerinnen-Annotationsrichtlinien (nur Standalone-Bedingung)",
            "Dies ist ein kuratiertes historisches Eingabeartefakt, keine automatisch erzeugte DMW-Annotation.",
            cleaned,
        ]
    )


def _context_resources(retrieved_turtle: str) -> str:
    """Render OPA reference context from an exact Haiu retrieval snapshot."""
    cleaned = retrieved_turtle.strip()
    if not cleaned:
        raise ValueError(
            "The haiu_rag_ontologizer planner requires retrieved Turtle context."
        )
    return _assemble(
        [
            "# Kontextressourcen",
            "\n".join(
                [
                    "## Referenzontologie (Ausschnitt, Turtle)",
                    "Dies ist ein relevanter Ausschnitt der bestehenden Gesamtontologie. Er ist in Turtle notiert.",
                    "```ttl",
                    cleaned,
                    "```",
                ]
            ),
            _reference_alignment_policy(),
        ]
    )


def _planner_task(allow_text_interpretation: bool) -> str:
    """Render the locked OPA SUGGEST planner-task structure."""
    return _assemble(
        [
            "# Aufgabe (Planner)",
            _deep_modelling_guidance(),
            _schema_conventions(
                "## Schema-Konventionen fuer TBox-Terme (verbindlich)"
            ),
            _individual_iri_policy(),
            _content_modulation_conventions(),
            _interpretation_policy(allow_text_interpretation),
            _suggest_mode_rules(),
            _reference_alignment_policy(),
            _planner_output_format(),
        ]
    )


def _turtle_task(allow_text_interpretation: bool) -> str:
    """Render the locked OPA SUGGEST Turtle-coder task structure."""
    return _assemble(
        [
            "# Aufgabe (TTL-Ausgabe)",
            _prefix_policy(),
            _schema_conventions(
                "## Schema-Konventionen fuer TBox-Terme (verbindlich)"
            ),
            _individual_iri_policy(),
            _content_modulation_conventions(),
            _interpretation_policy(allow_text_interpretation),
            _suggest_mode_rules(),
            _reference_alignment_policy(),
            _turtle_output_format(),
        ]
    )


def _deep_modelling_guidance() -> str:
    """Return OPA's shared deep-modelling instruction without DMW annotations."""
    return "\n".join(
        [
            "## Modellierungsleitlinien (Tiefe Modellierung, verbindlich)",
            "",
            "- Modelliere nicht nur die Annotationen. Das Ziel ist ein vollwertiges, semantisch reiches Modell der Petentenvita.",
            "- Nutze Annotationen (falls vorhanden) als Startpunkte und Evidenz, nicht als alleinige Struktur.",
            "- Rekonstruiere die zentrale Sachstruktur aus Kopf und Regesten/Rechtsvorgaengen:",
            "  - Welche Ereignisse/Akte liegen vor (z.B. Provisio, Dispens, Zahlung, Prozess, Kommissionsvermerk, Ernennung)?",
            "  - Wer sind die beteiligten Akteure, in welchen Rollen, und wie sind sie miteinander verknuepft?",
            "  - Welche Orte, Zeiten, Institutionen, Dokumente, Objekte oder Rechtsformeln sind relevant?",
            "- Beziehe auch implizite Informationen ein, wenn sie in der Petentenvita klar nahegelegt werden (z.B. eine Provision impliziert einen Akt der Vergabe).",
            "- Behalte die Granularitaet stabil: lieber wenige, gut begruendete Event-Knoten als flache Schlagwortlisten.",
        ]
    )


def _schema_conventions(title: str) -> str:
    """Return OPA's term-annotation convention section."""
    return "\n".join(
        [
            title,
            "",
            "1) Labels:",
            "- rdfs:label ist das primaere Label (mehrsprachig erlaubt).",
            "- Alternative Bezeichnungen in derselben Sprache: skos:altLabel.",
            "",
            "2) Definitionen:",
            "- skos:definition enthaelt eine Definition (kurz, praezise).",
            "",
            "3) Beispiele:",
            "- skos:example enthaelt exemplarische Textstellen aus Petentenviten bzw. ihren Regesten/Rechtsvorgaengen (als Referenz).",
            "",
            "4) Direkter String-Match im RG:",
            "- :stringInRG fuer konkrete Oberflaechenformen/Abkuerzungen aus dem Text der Petentenvita.",
            "",
            "5) Kommentare / Hinweise:",
            "- skos:editorialNote fuer redaktionelle Kommentare und Modellierungsnotizen.",
        ]
    )


def _content_modulation_conventions() -> str:
    """Return OPA's ABox-term convention section."""
    return _schema_conventions(
        "## Schema-Konventionen fuer ABOX-Terme (verbindlich)"
    )


def _individual_iri_policy() -> str:
    """Return OPA's deterministic individual-IRI policy."""
    return "\n".join(
        [
            "## IRI-Regeln fuer Individuen (merge-sicher)",
            "",
            "- Verwende deterministische, reproduzierbare IRIs fuer Individuen.",
            "- Empfehlungsschema (Beispiele, anpassbar):",
            "  - :i_{REGEST_ID}_person_{slug}",
            "  - :i_{REGEST_ID}_institution_{slug}",
            "  - :i_{REGEST_ID}_place_{slug}",
            "  - :i_{REGEST_ID}_event_{n}",
            "  - :i_{REGEST_ID}_document_{n}",
            "- Slugs kurz halten, nur [a-z0-9_], keine Leerzeichen.",
        ]
    )


def _interpretation_policy(allow_text_interpretation: bool) -> str:
    """Return OPA's locked text-interpretation policy."""
    if allow_text_interpretation:
        return "\n".join(
            [
                "## Text Interpretations Richtlinien",
                "",
                "Interpreatationen sind erlaubt, aber nur wenn sie stark durch den Quelltext gestuetzt werden.",
                "Alle Interpretationen muessen begruendbar sein.",
                "",
                "Dies beinhaltet unter anderem:",
                " - aufloesen von Abkuerzungen",
                " - auflösen von Koreferenzen",
                " - normalisieren von Plural/Singular-Formen",
                "",
                "Wenn Informationen mehrdeutig sind, bewahre die Mehrdeutigkeit.",
            ]
        )
    return "\n".join(
        [
            "## Text Interpretations Richtlinien",
            "",
            "Interpretationen sind deaktiviert. Nutze nur Informationen, die explizit vorhanden sind in:",
            "- dem Text der Petentenvita (Kopf und Regesten/Rechtsvorgaenge)",
            "- den bereitgestellten Annotationen",
            "- dem bereitgestellten Ontologie-Kontext",
            "",
            "Was nicht getan werden darf:",
            "- Abkuerzungen erweitern",
            "- Koreferenzen aufloesen",
            "- weggelassene Entitaeten erschliessen",
            "- Plural/Singular-Formen normalisieren",
            "- implizite Ereignisse einfuehren",
            "- implizite Relationen einfuehren",
            "- historische Identitaeten erraten",
            "",
            "Wenn Informationen mehrdeutig sind, bewahre die Mehrdeutigkeit.",
        ]
    )


def _suggest_mode_rules() -> str:
    """Return OPA's SUGGEST-mode schema-extension policy."""
    return "\n".join(
        [
            "## Modus: SUGGEST",
            "",
            "- Du darfst neue Klassen oder Properties vorschlagen, aber nur wenn es keinen passenden bestehenden Term gibt.",
            "- Unterscheide zwei Arten von Vorschlaegen:",
            "  1) Petentenvita-spezifische Ergaenzungen: Terme, die du fuer diese Petentenvita unmittelbar brauchst und im TTL verwenden wirst.",
            "  2) Fundamentale (abstrakte) Ergaenzungen: uebergeordnete Klassen/Properties oder generische Modellierungsbausteine,",
            "     die als stabile Grundlage fehlen. Diese muessen in der konkreten Petentenvita nicht zwingend verwendet werden,",
            "     werden aber als strukturelle Luecke dokumentiert.",
            "",
            "- Neue Terme muessen mindestens erhalten:",
            "  - rdfs:label (@de),",
            "  - skos:definition (kurz),",
            "  - optional skos:example, :stringInRG, skos:editorialNote.",
            "",
            "- Fundamentale (abstrakte) Vorschlaege nur dann nennen, wenn du eine echte strukturelle Luecke erkennst",
            "  (z.B. fehlende Oberklasse, fehlende Oberproperty, fehlendes allgemeines Rollen- oder Ereignis-Muster).",
            "- Die neu erstellten Terme muessen auch konkret in der ABox verwendet werden.",
        ]
    )


def _reference_alignment_policy() -> str:
    """Return OPA's reference-alignment policy."""
    return "\n".join(
        [
            "## Konsistenz-Regel (wenn Referenzmaterial vorhanden ist)",
            "",
            "- Wenn Referenzontologie und/oder Beispiele gegeben sind, halte dich strikt an deren Benennungen, Muster und Stil.",
            "- Fuehre keine Format- oder Stilwechsel ein (z.B. andere Prefix-Strategie) ohne zwingenden Grund.",
        ]
    )


def _planner_output_format() -> str:
    """Return OPA's SUGGEST planner output-format contract."""
    return "\n".join(
        [
            "## Striktes Output-Format (Markdown)",
            "",
            "Gib nur Markdown aus (kein TTL, kein JSON). Nutze exakt diese Gliederung:",
            "",
            "### 1) Modellierungsziel (entscheidungsorientiert)",
            "- 5 bis 10 Sätze: Welche Sicht wird modelliert? Welche Granularitaet? Welche stabilen Muster werden genutzt?",
            "",
            "### 2) Extraktion (Evidenzliste)",
            "- Personen / Institutionen / Orte / Dokumente / Ereignisse / Rollen / Datumsangaben",
            "- Je Item falls vorhanden: kurze Evidenz (Textstelle).",
            "",
            "### 3) Modellplan",
            "- TBox-Termliste: Klassen und Properties, die du im TTL verwenden wirst.",
            "- ABox-Plan: Individuen (IRIs) + wichtigste Beziehungen (konkret, in Klartext).",
            "",
            "### 4) TBox-Ergaenzungen (Petentenvita-spezifisch, nur wenn wirklich noetig)",
            "- Liste nur neue Terme, die du fuer diese Petentenvita unmittelbar brauchst und im TTL verwenden wirst.",
            "- Pro Vorschlag: Term-IRI, rdfs:label (@de), skos:definition, Begruendung, optional :stringInRG.",
            "",
            "### 5) Fundamentale TBox-Defizite (abstrakt, optional)",
            "- Hier duerfen auch uebergeordnete Klassen/Properties (Overclasses/Overproperties) oder generische Modellierungsbausteine vorgeschlagen werden,",
            "  wenn sie als stabile Grundlage fehlen.",
            "- Nur aufnehmen, wenn es eine echte strukturelle Luecke ist (nicht nur 'nice to have').",
            "- Pro Vorschlag:",
            "  - Term-IRI,",
            "  - rdfs:label (@de),",
            "  - skos:definition,",
            "  - Einordnung: rdfs:subClassOf / rdfs:subPropertyOf zu einem vorhandenen allgemeinen Term (wenn moeglich),",
            "  - Begruendung: welches wiederkehrende Modellierungsproblem loest das?",
            "",
            "### 6) Unklarheiten / Risiken (max. 5 Punkte)",
            "- Nur echte Mehrdeutigkeiten oder echte Ontologie-Luecken nennen, jeweils mit gewaehltem Workaround.",
        ]
    )


def _prefix_policy() -> str:
    """Return OPA's required TTL prefix block."""
    return "\n".join(
        [
            "## Prefix-Definitionen (Verbindlich)",
            "",
            "Die Ausgabe MUSS mit den folgenden Prefix-Definitionen beginnen:",
            "```ttl",
            "@prefix : <http://hisqu.de/rg_ontology/ontology/> .",
            "@prefix owl: <http://www.w3.org/2002/07/owl#> .",
            "@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .",
            "@prefix xml: <http://www.w3.org/XML/1998/namespace/> .",
            "@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .",
            "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .",
            "@prefix rg: <http://hisqu.de/rg_ontology/ontology/> .",
            "@prefix skos: <http://www.w3.org/2004/02/skos/core#> .",
            "@base <http://hisqu.de/rg_ontology/ontology/> .",
            "",
            "<http://hisqu.de/rg_ontology/ontology/> a owl:Ontology .",
            "```",
        ]
    )


def _turtle_output_format() -> str:
    """Return OPA's Turtle output-format contract."""
    return "\n".join(
        [
            "## Striktes Output-Format",
            "",
            "Gib ausschliesslich eine einzige Turtle-Datei aus (kein Markdown, keine Prosa).",
            "Struktur:",
            "1. Prefix-Definitionen (@prefix ...).",
            "2. Kommentarzeile: # --- TBOX ---",
            "3. TBox-Definitionen (Klassen/Properties).",
            "4. Kommentarzeile: # --- ABOX ---",
            "5. ABox-Daten (Individuen).",
            "",
            "Zusaetzliche harte Regeln:",
            "- Das Ergebnis muss valides Turtle (Syntax-Check) sein.",
            "- Wiederhole TBox-Deklarationen auch dann, wenn die Terme im Referenzmaterial bereits existieren (Snippet muss selbsttragend sein).",
            "- Keine WebProtege-Kommentarzeilen der Form '### http://...' ausgeben.",
        ]
    )
